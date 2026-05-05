"""客户 - 数据业务 API"""
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (
    select,
    func,
    case,
    or_,
    and_,
    text as sa_text,
    update as sa_update,
    insert,
    tuple_,
    union_all,
    literal,
    cast,
    collate,
    delete as sa_delete,
    Integer,
    desc,
    String,
)
from sqlalchemy.types import Date as SA_Date
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import joinedload
from typing import Optional, List, Dict, Sequence, Any
from datetime import datetime, date, timedelta
import os
import uuid
import csv
import io
import re
import asyncio
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
from pydantic import BaseModel, Field
from passlib.context import CryptContext

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

from app.database import get_db
from app.modules.data.models import (
    DataNumber,
    DataProduct,
    DataOrder,
    DataOrderNumber,
    PrivateLibraryNumber,
    PrivateLibrarySummary,
    PrivateLibraryUploadTask,
    SOURCE_LABELS,
    PURPOSE_LABELS,
    FRESHNESS_LABELS,
)
from app.modules.data.private_library_summary_sync import (
    ORIGIN_MANUAL,
    ORIGIN_PURCHASED,
    build_summary_payload_from_rows,
    carrier_label,
    norm_dim,
    pls_apply_bucket_delta,
    pls_prune_non_positive,
    pls_soft_prune_non_positive,
    pls_apply_deltas_bulk,
)
from app.modules.data.private_upload_core import run_private_library_upload
from app.modules.data.private_upload_parse import (
    batch_lookup_carriers as _batch_lookup_carriers,
    decode_my_numbers_upload_bytes as _decode_my_numbers_upload_bytes,
    extract_phone_numbers_from_upload_text as _extract_phone_numbers_from_upload_text,
    phone_db_lookup_keys as _phone_db_lookup_keys,
)
from app.utils.data_customer_cache import invalidate_my_numbers_summary_cache as _invalidate_my_numbers_summary_cache
from app.utils.phone_utils import export_phone_plain_digits
from app.utils.country_code import normalize_country_code
from app.modules.data.data_account import DataAccount
from app.modules.data.stock_summary_sync import update_stock_summary_delta, update_stock_summary_from_batch
from app.modules.common.account import Account
from app.modules.common.package import AccountPackage
from app.core.auth import get_current_account
from app.utils.logger import get_logger
from app.schemas.data import (
    DataOrderCreate, DataBuyAndSend, ComboBuyRequest,
    FilterCriteria, OrderCancelRequest,
)
from app.api.v1.data.helpers import (
    build_filter_query,
    calculate_stock,
    calculate_stock_with_carriers,
    serialize_product,
    serialize_order,
    compute_freshness,
)
from app.utils.sms_template import render_sms_variables, sms_template_has_variables
from app.utils.account_country_restrict import account_country_iso
from app.utils.cache import get_cache_manager

logger = get_logger(__name__)
router = APIRouter()

# 私库汇总接口缓存（大账户 GROUP BY 可能需要 30s+，用长 TTL + stale-while-revalidate 应对）
_MY_NUMBERS_SUMMARY_CACHE_TTL = 3600
# 默认仅统计「最近 N 个批次」维度，避免单账号数百万行时全表聚合过慢；短信发送页传 max_batches=0 拉全量
_DEFAULT_MY_NUMBERS_SUMMARY_MAX_BATCHES = 400
# 私库号码总数缓存
_MY_NUMBERS_COUNT_CACHE_TTL = 3600


def _my_numbers_summary_cache_key(account_id: int, max_batches: int) -> str:
    return f"data:my_numbers:summary:{account_id}:mb{max_batches}"


async def _summary_from_private_library_summaries_table(
    db: AsyncSession, account_id: int, max_batches: int
) -> dict:
    """
    从 private_library_summaries 读卡片汇总（毫秒级）。
    若迁移未回填或表与明细严重不一致（有明细无汇总行），回退 _compute_summary。
    """
    cnt_pln = (
        await db.execute(
            select(func.count())
            .select_from(PrivateLibraryNumber)
            .where(
                PrivateLibraryNumber.account_id == account_id,
                _pln_client_visible_clause(),
            )
        )
    ).scalar() or 0
    cnt_dn = (
        await db.execute(
            select(func.count())
            .select_from(DataNumber)
            .where(DataNumber.account_id == account_id)
        )
    ).scalar() or 0
    total_detail = cnt_pln + cnt_dn

    rows = (
        await db.execute(
            select(PrivateLibrarySummary).where(
                PrivateLibrarySummary.account_id == account_id,
                PrivateLibrarySummary.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().all()

    if total_detail > 0 and len(rows) == 0:
        logger.warning("私库汇总表无行但明细有数据，回退 GROUP BY 重算 account=%s", account_id)
        return await _compute_summary(db, account_id, max_batches)

    payload = build_summary_payload_from_rows(
        list(rows), max_batches=max_batches, total_all_accounts_hint=total_detail
    )
    _apply_summary_item_canonical_labels(payload.get("items"))

    try:
        cm_count = await get_cache_manager()
        await cm_count.set(
            _my_numbers_count_cache_key(account_id), total_detail, ttl=_MY_NUMBERS_COUNT_CACHE_TTL
        )
    except Exception:
        pass

    return payload


# 后台刷新锁（防止同一账户的多个并发刷新任务）
_refresh_locks: Dict[int, bool] = {}


async def _background_refresh_summary(account_id: int, max_batches: int) -> None:
    """后台独立会话重新计算汇总并更新缓存。仅在版本号未变时清除 stale 标记。"""
    if _refresh_locks.get(account_id):
        return
    _refresh_locks[account_id] = True
    try:
        stale_key = f"data:my_numbers:stale:{account_id}"
        cm = await get_cache_manager()
        redis_client = await cm.redis
        version_before = await redis_client.get(stale_key)

        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            payload = await _summary_from_private_library_summaries_table(db, account_id, max_batches)
            cache_key = _my_numbers_summary_cache_key(account_id, max_batches)
            await cm.set(cache_key, payload, ttl=_MY_NUMBERS_SUMMARY_CACHE_TTL)

            version_after = await redis_client.get(stale_key)
            if version_after == version_before:
                await redis_client.delete(stale_key)
                logger.info(f"后台刷新私库汇总完成: account={account_id}")
            else:
                logger.info(f"后台刷新私库汇总完成但有新变更，保留 stale: account={account_id}")
    except Exception as e:
        logger.warning(f"后台刷新私库汇总失败: account={account_id}, {e}")
    finally:
        _refresh_locks.pop(account_id, None)


def _canon_source_key_for_client(v: Optional[str]) -> str:
    """来源统一为 SOURCE_LABELS 的英文 key（解决汇总表里存中文「撞库」与明细 credential 不一致）"""
    x = norm_dim(v)
    if x in SOURCE_LABELS:
        return x
    for k, lab in SOURCE_LABELS.items():
        if norm_dim(lab) == x:
            return k
    return x


def _canon_purpose_key_for_client(v: Optional[str]) -> str:
    """用途统一为 PURPOSE_LABELS 的英文 key"""
    x = norm_dim(v)
    if x in PURPOSE_LABELS:
        return x
    for k, lab in PURPOSE_LABELS.items():
        if norm_dim(lab) == x:
            return k
    return x


def _apply_summary_item_canonical_labels(items: Optional[List]) -> None:
    """卡片 JSON 中 source/purpose 用字典 key，标签单独字段，便于删除与明细一致"""
    if not items:
        return
    for it in items:
        it["source"] = _canon_source_key_for_client(it.get("source"))
        it["purpose"] = _canon_purpose_key_for_client(it.get("purpose"))
        it["source_label"] = SOURCE_LABELS.get(it.get("source") or "", it.get("source") or "")
        it["purpose_label"] = PURPOSE_LABELS.get(it.get("purpose") or "", it.get("purpose") or "")


def _sql_dim_source_match(col, param: Optional[str]) -> Any:
    """来源：参数可为英文 key 或中文标签，与库内任意一种写法匹配"""
    raw_l = norm_dim(param if param is not None else "").lower()
    vals = {
        raw_l,
        norm_dim(_canon_source_key_for_client(param if param is not None else "")).lower(),
    }
    for k, lab in SOURCE_LABELS.items():
        if norm_dim(lab).lower() == raw_l:
            vals.add(norm_dim(k).lower())
    lhs = func.lower(func.trim(func.coalesce(col, "")))
    parts = [lhs == v for v in vals]
    return or_(*parts) if len(parts) > 1 else parts[0]


def _sql_dim_purpose_match(col, param: Optional[str]) -> Any:
    """用途：参数可为英文 key 或中文标签"""
    raw_l = norm_dim(param if param is not None else "").lower()
    vals = {
        raw_l,
        norm_dim(_canon_purpose_key_for_client(param if param is not None else "")).lower(),
    }
    for k, lab in PURPOSE_LABELS.items():
        if norm_dim(lab).lower() == raw_l:
            vals.add(norm_dim(k).lower())
    lhs = func.lower(func.trim(func.coalesce(col, "")))
    parts = [lhs == v for v in vals]
    return or_(*parts) if len(parts) > 1 else parts[0]


def _sql_dim_ci_trim_eq(col, param: Optional[str]) -> Any:
    """TRIM + 小写比较，避免 BD/bd、bc/BC、首尾空格等与汇总卡片不一致导致删不到行"""
    s = norm_dim(param if param is not None else "").lower()
    return func.lower(func.trim(func.coalesce(col, ""))) == s


def _pln_client_visible_clause():
    """私库分表：客户可见（未软删）。与 is_deleted 默认 False / 迁移回填一致。"""
    return PrivateLibraryNumber.is_deleted == False  # noqa: E712


def _my_numbers_union_subquery(
    account_id: int,
    *,
    country: Optional[str] = None,
    tag: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    batch_id: Optional[str] = None,
):
    """私库分表与公海购入绑定行列对齐后的 UNION 子查询"""
    # library_origin：manual=私库分表手工上传；purchased=公海购入后绑定在 data_numbers
    q_pln = select(
        PrivateLibraryNumber.id,
        PrivateLibraryNumber.phone_number,
        PrivateLibraryNumber.country_code,
        PrivateLibraryNumber.tags,
        PrivateLibraryNumber.carrier,
        PrivateLibraryNumber.status.label("status"),
        PrivateLibraryNumber.source,
        PrivateLibraryNumber.purpose,
        cast(literal(None), SA_Date).label("data_date"),
        PrivateLibraryNumber.batch_id,
        cast(literal(None), Integer).label("pricing_template_id"),
        PrivateLibraryNumber.use_count,
        PrivateLibraryNumber.account_id,
        PrivateLibraryNumber.last_used_at,
        PrivateLibraryNumber.created_at,
        collate(literal("manual"), "utf8mb4_unicode_ci").label("library_origin"),
    ).where(PrivateLibraryNumber.account_id == account_id, _pln_client_visible_clause())
    q_dn = select(
        DataNumber.id,
        DataNumber.phone_number,
        DataNumber.country_code,
        DataNumber.tags,
        DataNumber.carrier,
        collate(cast(DataNumber.status, String), "utf8mb4_unicode_ci").label("status"),
        DataNumber.source,
        DataNumber.purpose,
        DataNumber.data_date,
        DataNumber.batch_id,
        DataNumber.pricing_template_id,
        DataNumber.use_count,
        DataNumber.account_id,
        DataNumber.last_used_at,
        DataNumber.created_at,
        collate(literal("purchased"), "utf8mb4_unicode_ci").label("library_origin"),
    ).where(DataNumber.account_id == account_id)
    if country is not None:
        q_pln = q_pln.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.country_code, country))
        q_dn = q_dn.where(_sql_dim_ci_trim_eq(DataNumber.country_code, country))
    if tag:
        q_pln = q_pln.where(PrivateLibraryNumber.tags.contains([tag]))
        q_dn = q_dn.where(DataNumber.tags.contains([tag]))
    if source is not None:
        q_pln = q_pln.where(_sql_dim_source_match(PrivateLibraryNumber.source, source))
        q_dn = q_dn.where(_sql_dim_source_match(DataNumber.source, source))
    if purpose is not None:
        q_pln = q_pln.where(_sql_dim_purpose_match(PrivateLibraryNumber.purpose, purpose))
        q_dn = q_dn.where(_sql_dim_purpose_match(DataNumber.purpose, purpose))
    if batch_id is not None:
        q_pln = q_pln.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.batch_id, batch_id))
        q_dn = q_dn.where(_sql_dim_ci_trim_eq(DataNumber.batch_id, batch_id))
    return union_all(q_pln, q_dn).subquery()


def _serialize_my_numbers_union_row(r) -> dict:
    """将 UNION 行序列化为与 serialize_number 一致的私库列表项结构"""
    dd = r.data_date
    if dd is not None and not isinstance(dd, date):
        if isinstance(dd, str):
            try:
                dd = date.fromisoformat(dd[:10])
            except ValueError:
                dd = None
        else:
            dd = None
    st = r.status
    if hasattr(st, "value"):
        st = st.value
    fr = compute_freshness(dd if isinstance(dd, date) else None)
    tags = r.tags or []
    return {
        "id": r.id,
        "phone_number": r.phone_number,
        "country_code": r.country_code,
        "tags": tags,
        "carrier": r.carrier,
        "status": st,
        "source": r.source,
        "source_label": SOURCE_LABELS.get(r.source, r.source or ""),
        "purpose": r.purpose,
        "purpose_label": PURPOSE_LABELS.get(r.purpose, r.purpose or ""),
        "data_date": dd.isoformat() if isinstance(dd, date) else None,
        "freshness": fr,
        "freshness_label": FRESHNESS_LABELS.get(fr, ""),
        "batch_id": r.batch_id,
        "pricing_template_id": r.pricing_template_id,
        "use_count": r.use_count or 0,
        "account_id": r.account_id,
        "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        # 与 UNION 列 literal 一致：manual | purchased
        "library_origin": getattr(r, "library_origin", None),
    }


def _my_numbers_count_cache_key(account_id: int) -> str:
    return f"data:my_numbers:count:{account_id}"


def _gen_order_no():
    return f"DO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


# ============ 商品浏览 ============

@router.get("/carriers")
async def get_available_carriers(
    country_code: Optional[str] = Query(None, description="按国家筛选运营商"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """
    获取可用的运营商列表（去重后的 carrier 值）。

    data_numbers 现已 1500w+ 行，按 country_code 做 GROUP BY 在 9M 量级国家上需 130s+。
    冷启动场景（L1 空、Redis 过期）下会触发前端 axios 120s 超时。
    解决：缓存由 Celery beat（data_refresh_carriers_cache_task）每 10 分钟全量预热，TTL=24h；
    本接口只读缓存，未命中时立刻返回 [] 并异步触发预热，绝不在请求线程内跑全表 GROUP BY。
    """
    cache_manager = await get_cache_manager()
    cache_key = f"data:public_carriers:{country_code or 'all'}"
    if not country_code:
        da_result = await db.execute(
            select(DataAccount).where(DataAccount.account_id == account.id)
        )
        da = da_result.scalar_one_or_none()
        if da and da.country_code:
            cache_key = f"data:public_carriers:{da.country_code}"
            country_code = da.country_code

    cached = await cache_manager.get(cache_key)
    if cached is not None:
        return {"success": True, "carriers": cached}

    # 冷启动：beat 还未跑过一次。立刻异步触发预热（不阻塞本请求）后返回空。
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task("data_refresh_carriers_cache", queue="data_tasks")
    except Exception as e:
        logger.warning(f"触发 carriers 缓存预热失败: {e}")

    return {"success": True, "carriers": []}


@router.get("/products")
async def customer_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_type: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    freshness: Optional[str] = None,
    carrier: Optional[str] = Query(None, description="按运营商筛选"),
    country: Optional[str] = Query(None, description="按国家/地区代码筛选"),
    tag: Optional[str] = Query(None, description="按标签筛选"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户获取可购买的数据商品列表"""
    query = select(DataProduct).where(
        DataProduct.is_deleted == False, DataProduct.status == "active"
    )

    # 1. 国家过滤：DataAccount、短信账户 country_code 任一存在则默认只展示该国商品；禁止跨国家查询
    da_result = await db.execute(
        select(DataAccount).where(DataAccount.account_id == account.id)
    )
    da = da_result.scalar_one_or_none()

    acc_locked_iso = account_country_iso(account)
    if country:
        req_iso = normalize_country_code(country)
        if acc_locked_iso and req_iso != acc_locked_iso:
            raise HTTPException(
                400,
                f"当前短信账户仅允许查看 {acc_locked_iso} 地区数据商品，无法切换到其他国家。",
            )
        target_country = country
    else:
        target_country = (da.country_code if da and da.country_code else None) or (
            account.country_code if getattr(account, "country_code", None) else None
        )

    if target_country:
        norm_c = normalize_country_code(target_country)
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.country")) == norm_c
        )

    # 2. 其他筛选项
    if tag:
        import json as _json
        from sqlalchemy import bindparam
        query = query.where(
            func.json_contains(DataProduct.filter_criteria, bindparam("tag_val", _json.dumps(tag)), "$.tags")
        )

    if product_type:
        query = query.where(DataProduct.product_type == product_type)
    if source:
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.source")) == source
        )
    if purpose:
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.purpose")) == purpose
        )
    if freshness:
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.freshness")) == freshness
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(DataProduct.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()

    async def _fetch_available_countries(db: AsyncSession):
        countries_query = select(
            func.distinct(func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.country")))
        ).where(DataProduct.is_deleted == False, DataProduct.status == "active")
        countries_result = await db.execute(countries_query)
        return [c[0] for c in countries_result.all() if c[0]]

    cache_manager = await get_cache_manager()

    # 精确库存：per-product 查询，应用完整 filter_criteria（含 freshness/data_date）
    # 使用 Redis 缓存（60s TTL）避免重复查询
    country_total_carriers: dict = {}

    # 批量获取评分统计
    product_ids = [p.id for p in products]
    from app.modules.data.models import DataProductRating
    rating_stats = {}
    if product_ids:
        recent_30d = datetime.now() - timedelta(days=30)
        all_stats = (await db.execute(
            select(
                DataProductRating.product_id,
                func.count().label("total"),
                func.avg(DataProductRating.rating).label("avg"),
                func.max(DataProductRating.rating).label("max"),
            ).where(DataProductRating.product_id.in_(product_ids))
            .group_by(DataProductRating.product_id)
        )).fetchall()
        for s in all_stats:
            rating_stats[s.product_id] = {
                "total": s.total, "avg": round(float(s.avg or 0), 1), "max": s.max or 0,
            }

        recent_agg = (await db.execute(
            select(
                DataProductRating.product_id,
                func.avg(DataProductRating.rating).label("avg"),
                func.max(DataProductRating.rating).label("max"),
                func.count().label("cnt"),
            ).where(
                DataProductRating.product_id.in_(product_ids),
                DataProductRating.created_at >= recent_30d,
            ).group_by(DataProductRating.product_id)
        )).fetchall()
        for r in recent_agg:
            if r.product_id in rating_stats:
                rating_stats[r.product_id]["recent_avg"] = round(float(r.avg or 0), 1)
                rating_stats[r.product_id]["recent_max"] = r.max or 0
                rating_stats[r.product_id]["recent_count"] = r.cnt

    # 构造返回项：per-product 精确库存（含 freshness 过滤）
    items = []
    for p in products:
        item = serialize_product(p)
        fc = p.filter_criteria or {}

        # 带运营商筛选时合并进 filter_criteria
        stock_fc = dict(fc)
        if carrier:
            stock_fc["carrier"] = carrier

        # Redis 缓存 per-product 精确库存（60s）
        stock_cache_key = f"data:product_stock:{p.id}:{carrier or 'all'}"
        cached_stock = await cache_manager.get(stock_cache_key)
        if cached_stock is not None:
            stock_total = cached_stock["total"]
            carrier_list = cached_stock["carriers"]
        else:
            stock_total, carrier_list = await calculate_stock_with_carriers(db, stock_fc, public_only=True)
            await cache_manager.set(stock_cache_key, {"total": stock_total, "carriers": carrier_list}, ttl=60)

        if carrier:
            item["carrier_filter"] = carrier
            if stock_total <= 0:
                continue

        item["stock_count"] = stock_total
        item["carriers"] = carrier_list

        # 汇总该国家/地区下所有运营商（用于页面顶部运营商筛选器）
        for c_item in carrier_list:
            country_total_carriers[c_item["name"]] = country_total_carriers.get(c_item["name"], 0) + c_item["count"]
        
        rs = rating_stats.get(p.id, {})
        item["rating"] = {
            "avg": rs.get("avg", 0),
            "max": rs.get("max", 0),
            "total": rs.get("total", 0),
            "recent_avg": rs.get("recent_avg", 0),
            "recent_max": rs.get("recent_max", 0),
            "recent_count": rs.get("recent_count", 0),
        }
        items.append(item)

    # 计算所有可用国家列表 (带缓存)
    available_countries = await cache_manager.get_or_set(
        "data:store:available_countries",
        lambda: _fetch_available_countries(db),
        ttl=300
    )

    return {
        "success": True,
        "items": items,
        "total": len(items) if carrier else total,
        "page": page,
        "page_size": page_size,
        "country_code": da.country_code if da else None,
        "available_carriers": [{"name": c, "count": cnt} for c, cnt in country_total_carriers.items()],
        "available_countries": available_countries
    }


@router.post("/preview")
async def preview_data_selection(
    data: FilterCriteria,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """预览筛选结果(不消费数据)"""
    filter_dict = data.dict(exclude_unset=True)
    _assert_account_country_matches_data_filter(account, filter_dict)
    count = await calculate_stock(db, filter_dict, public_only=True)

    query = build_filter_query(filter_dict, public_only=True).limit(10)
    result = await db.execute(query)
    samples = result.scalars().all()

    return {
        "success": True,
        "total_count": count,
        "samples": [
            {"country_code": s.country_code, "carrier": s.carrier, "tags": s.tags or [], "status": s.status}
            for s in samples
        ],
    }


# ============ 购买模式一：单独购买数据 ============

@router.post("/buy-to-stock")
async def buy_to_stock(
    data: DataOrderCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """购买数据到私有库(不立即发送) — 使用 SQL 批量操作"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db, account)

    if data.carrier:
        filter_criteria = dict(filter_criteria or {})
        filter_criteria["carrier"] = data.carrier

    total_price = Decimal(str(unit_price)) * data.quantity

    # ---------- 1. 先锁定号码（防超卖） ----------
    id_query = build_filter_query(filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]

    if len(number_ids) < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {len(number_ids)}")

    lock_result = await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids), DataNumber.account_id.is_(None))
        .values(account_id=account.id)
    )
    locked = lock_result.rowcount
    if locked < data.quantity:
        raise HTTPException(400, "号码已被抢购，请重试")

    # ---------- 2. 原子扣费 ----------
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_price)
        .values(balance=Account.balance - total_price)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, "余额不足")

    # ---------- 3. 记录订单与明细 ----------
    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=data.product_id,
        filter_criteria=filter_criteria,
        quantity=locked,
        unit_price=str(unit_price),
        total_price=str(total_price),
        order_type="data_only",
        status="completed",
        executed_count=locked,
        executed_at=datetime.now(),
    )
    db.add(order)
    await db.flush()

    if number_ids:
        from app.modules.data.models import DataOrderNumber as DON
        db.add_all([DON(order_id=order.id, number_id=nid) for nid in number_ids])

    if product:
        product.total_sold = (product.total_sold or 0) + locked

    from app.modules.common.balance_log import BalanceLog
    new_bal = await db.execute(select(Account.balance).where(Account.id == account.id))
    db.add(BalanceLog(
        account_id=account.id, change_type='charge', amount=-total_price,
        balance_after=float(new_bal.scalar()), description=f"BuyStock: {locked} 条数据"
    ))

    # 更新汇总
    lid_res = await db.execute(
        select(DataNumber.id).where(
            DataNumber.id.in_(number_ids),
            DataNumber.account_id == account.id,
        )
    )
    locked_ids = [r[0] for r in lid_res.all()]

    # 扣减全局库存汇总
    if locked_ids:
        # 获取要扣减的维度分布
        dim_q = select(
            DataNumber.country_code, DataNumber.carrier, DataNumber.source,
            DataNumber.purpose, DataNumber.data_date, func.count().label("cnt")
        ).where(DataNumber.id.in_(locked_ids)).group_by(
            DataNumber.country_code, DataNumber.carrier, DataNumber.source,
            DataNumber.purpose, DataNumber.data_date
        )
        dim_res = await db.execute(dim_q)
        from app.api.v1.data.helpers import compute_freshness
        for drow in dim_res.fetchall():
            await update_stock_summary_delta(
                db, country_code=drow[0], carrier=drow[1], source=drow[2],
                purpose=drow[3], freshness=compute_freshness(drow[4]),
                delta=-int(drow[5])
            )

    await _pls_bump_purchased_for_number_ids(db, account.id, locked_ids)
    await pls_prune_non_positive(db, account.id)

    await db.commit()
    await _invalidate_my_numbers_summary_cache(account.id)
    return {"success": True, "message": f"已购买 {locked} 条数据到私库", "order_no": order.order_no}


# ============ 购买模式二：组合套餐 ============

@router.post("/buy-combo")
async def buy_combo(
    data: ComboBuyRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """购买数据+短信组合套餐"""
    result = await db.execute(
        select(DataProduct).where(
            DataProduct.id == data.product_id,
            DataProduct.product_type == "combo",
            DataProduct.status == "active",
            DataProduct.is_deleted == False,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "组合套餐不存在或不可用")

    if data.quantity < product.min_purchase:
        raise HTTPException(400, f"最小购买量: {product.min_purchase}")
    if data.quantity > product.max_purchase:
        raise HTTPException(400, f"最大购买量: {product.max_purchase}")

    _assert_account_country_matches_data_filter(account, product.filter_criteria)

    available = await calculate_stock(db, product.filter_criteria, public_only=True)
    if available < data.quantity:
        raise HTTPException(400, f"数据库存不足，当前可用: {available}")

    # 计价：使用打包价，若无打包价则按单价
    if product.bundle_price:
        total_price = Decimal(str(product.bundle_price)) * data.quantity
    else:
        total_price = Decimal(str(product.price_per_number)) * data.quantity

    # ---------- 1. 先锁定号码（防超卖） ----------
    id_query = build_filter_query(product.filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]

    if len(number_ids) < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {len(number_ids)}")

    lock_result = await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids), DataNumber.account_id.is_(None))
        .values(account_id=account.id)
    )
    locked = lock_result.rowcount
    if locked < data.quantity:
        raise HTTPException(400, "号码已被抢购，请重试")

    # ---------- 2. 原子扣费 ----------
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_price)
        .values(balance=Account.balance - total_price)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, "余额不足")

    # ---------- 3. 记录订单与明细 ----------
    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=product.id,
        filter_criteria=product.filter_criteria,
        quantity=data.quantity,
        unit_price=product.bundle_price or product.price_per_number,
        total_price=str(total_price),
        order_type="combo",
        status="completed",
        executed_count=data.quantity,
        executed_at=datetime.now(),
    )
    db.add(order)
    await db.flush()

    if number_ids:
        from app.modules.data.models import DataOrderNumber as DON
        db.add_all([DON(order_id=order.id, number_id=nid) for nid in number_ids])

    product.total_sold = (product.total_sold or 0) + locked

    # 记录财务流水
    from app.modules.common.balance_log import BalanceLog
    new_bal = await db.execute(select(Account.balance).where(Account.id == account.id))
    db.add(BalanceLog(
        account_id=account.id, change_type='charge', amount=-total_price,
        balance_after=float(new_bal.scalar()), description=f"BuyCombo: {locked} 条数据套餐"
    ))

    # 写入短信额度到 AccountPackage
    if product.sms_quota:
        sms_total = product.sms_quota * data.quantity
        pkg = AccountPackage(
            account_id=account.id,
            package_id=0,
            sms_remaining=sms_total,
            data_used=0,
            data_remaining=data.quantity,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=365),
            is_active=True,
            purchase_price=total_price,
            order_id=order.order_no,
        )
        db.add(pkg)

    lid_res = await db.execute(
        select(DataNumber.id).where(
            DataNumber.id.in_(number_ids),
            DataNumber.account_id == account.id,
        )
    )
    locked_ids = [r[0] for r in lid_res.all()]
    await _pls_bump_purchased_for_number_ids(db, account.id, locked_ids)
    await pls_prune_non_positive(db, account.id)

    await db.commit()
    await _invalidate_my_numbers_summary_cache(account.id)

    return {
        "success": True,
        "message": f"已购买组合套餐: {locked} 条数据" + (f" + {product.sms_quota * data.quantity} 条短信额度" if product.sms_quota else ""),
        "order_no": order.order_no,
    }


# ============ 购买模式三：买即发 ============

@router.post("/buy-and-send")
async def buy_and_send(
    data: DataBuyAndSend,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """购买数据并立即发送短信（支持变量模板 + 运营商过滤）"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db, account)

    if data.carrier:
        filter_criteria = dict(filter_criteria or {})
        filter_criteria["carrier"] = data.carrier

    available = await calculate_stock(db, filter_criteria, public_only=True)
    if available < data.quantity:
        hint = ""
        if available == 0 and filter_criteria.get("freshness"):
            fc_no_fresh = {k: v for k, v in filter_criteria.items() if k != "freshness"}
            total_no_fresh = await calculate_stock(db, fc_no_fresh, public_only=True)
            if total_no_fresh > 0:
                hint = f"（数据已超过 {filter_criteria['freshness']} 时效，{total_no_fresh} 条数据过期）"
        raise HTTPException(400, f"库存不足，当前可用: {available}{hint}")

    # ---------- 1. 锁定号码 ----------
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.common.balance_log import BalanceLog

    id_query = build_filter_query(filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]
    if len(number_ids) < data.quantity:
        raise HTTPException(400, f"库存不足，仅剩 {len(number_ids)} 条")

    # Core 分批锁定（每批 5000），减少往返、缩短 HTTP 占用时间（不设 status=sold，与现网枚举一致）
    LOCK_CHUNK = 5000
    total_locked = 0
    now_ts = datetime.now()
    locked_ids_all: list = []
    for i in range(0, len(number_ids), LOCK_CHUNK):
        chunk = number_ids[i : i + LOCK_CHUNK]
        lock_result = await db.execute(
            sa_update(DataNumber)
            .where(
                DataNumber.id.in_(chunk),
                DataNumber.account_id.is_(None),
            )
            .values(account_id=account.id, last_used_at=now_ts)
        )
        total_locked += lock_result.rowcount
        locked_ids_all.extend(chunk)
    if total_locked < data.quantity:
        raise HTTPException(400, "号码已被抢购，请重试")

    # 扣减公海库存汇总（summary 的总数定义为 account_id IS NULL 的号码数，卖出须同步扣减）
    if locked_ids_all:
        dim_q = select(
            DataNumber.country_code, DataNumber.carrier, DataNumber.source,
            DataNumber.purpose, DataNumber.data_date, DataNumber.batch_id, func.count().label("cnt")
        ).where(DataNumber.id.in_(locked_ids_all)).group_by(
            DataNumber.country_code, DataNumber.carrier, DataNumber.source,
            DataNumber.purpose, DataNumber.data_date, DataNumber.batch_id
        )
        dim_res = await db.execute(dim_q)
        for drow in dim_res.fetchall():
            await update_stock_summary_delta(
                db, country_code=drow[0], carrier=drow[1], source=drow[2],
                purpose=drow[3], freshness=compute_freshness(drow[4]),
                batch_id=drow[5], delta=-int(drow[6])
            )

    # ---------- 2. 估算费用（用首条号码的通道价格 × 总数估算短信费用） ----------
    from app.core.router import RoutingEngine
    from app.core.pricing import PricingEngine
    from app.utils.phone_utils import country_to_dial_code

    sample_result = await db.execute(
        select(DataNumber.country_code).where(DataNumber.id == number_ids[0])
    )
    sample_country = sample_result.scalar() or "PH"
    routing_engine = RoutingEngine(db)
    pricing_engine = PricingEngine(db)
    dial_code = country_to_dial_code(sample_country)
    sample_channel = None
    for cc in [dial_code, sample_country]:
        try:
            ch = await routing_engine.select_channel(
                country_code=cc, strategy='priority', account_id=account.id
            )
            if ch and ch.protocol in ('VIRTUAL', 'HTTP', 'SMPP'):
                sample_channel = ch
                break
        except Exception:
            continue

    sms_unit_price = Decimal('0')
    currency = 'USD'
    if sample_channel:
        price_info = await pricing_engine.get_price(sample_channel.id, dial_code, account_id=account.id)
        if not price_info:
            price_info = await pricing_engine.get_price(sample_channel.id, sample_country, account_id=account.id)
        if price_info:
            sms_unit_price = Decimal(str(price_info['price']))
            currency = price_info.get('currency', 'USD')

    data_cost = Decimal(str(unit_price)) * data.quantity
    sms_cost_est = sms_unit_price * data.quantity
    total_cost = data_cost + sms_cost_est

    # ---------- 3. 原子扣费 ----------
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_cost)
        .values(balance=Account.balance - total_cost)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, f"余额不足，需要 {total_cost:.4f} {currency}（数据 {data_cost:.4f} + 短信 {sms_cost_est:.4f}）")

    new_bal = await db.execute(select(Account.balance).where(Account.id == account.id))
    db.add(BalanceLog(
        account_id=account.id, change_type='charge', amount=-total_cost,
        balance_after=float(new_bal.scalar()),
        description=f"DataSend: {data.quantity} 条（异步处理中）"
    ))

    # ---------- 4. 创建订单 + 批次（状态 processing） ----------
    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=getattr(data, "product_id", None),
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=str(unit_price),
        total_price=str(total_cost),
        order_type="data_and_send",
        status="processing",
        executed_count=0,
    )
    db.add(order)
    await db.flush()

    batch_tag = f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    sms_batch = SmsBatch(
        account_id=account.id,
        batch_name=f"DataSend-{product.product_name if product else 'Custom'}-{batch_tag}",
        total_count=data.quantity,
        status=BatchStatus.PROCESSING,
    )
    db.add(sms_batch)
    await db.flush()
    # 回填批次：commit 前 flush，保证 Worker 按 order_id 反查时订单与批次已绑定
    order.sms_batch_id = sms_batch.id

    # 订单-号码关联表（与锁定在同一事务）：Worker 仅依赖 order_id 拉号，禁止把 number_ids 塞进 MQ
    _ord_num_chunk = 5000
    for _start in range(0, len(number_ids), _ord_num_chunk):
        _chunk = number_ids[_start : _start + _ord_num_chunk]
        await db.execute(
            insert(DataOrderNumber),
            [{"order_id": order.id, "number_id": int(nid)} for nid in _chunk],
        )

    if product:
        product.total_sold = (product.total_sold or 0) + data.quantity

    await db.flush()
    await db.commit()
    await _invalidate_my_numbers_summary_cache(account.id)

    # ---------- 5. 派发 Celery（瘦 kwargs；线程内发避免阻塞事件循环） ----------
    from app.workers.celery_app import celery_app as _celery

    # 瘦消息：仅传 order_id / batch_id 等；绝不携带 number_ids（数万级 JSON 会拖垮 Broker）
    _kw = {
        "order_id": order.id,
        "batch_id": sms_batch.id,
        "account_id": account.id,
        "message": data.message,
        "messages": data.messages,
        "sender_id": getattr(data, "sender_id", None),
        "channel_id": data.channel_id,
    }
    _kw.pop("number_ids", None)

    def _publish_buy_send() -> None:
        _celery.send_task("data_buy_send_async", kwargs=_kw)

    await asyncio.to_thread(_publish_buy_send)

    return {
        "success": True,
        "message": f"已购买 {data.quantity} 条数据，发送任务处理中",
        "order_no": order.order_no,
        "batch_id": batch_tag,
        "queued": 0,
        "async": True,
        "channel": sample_channel.channel_code if sample_channel else "-",
        "cost": {"data": data_cost, "sms": sms_cost_est, "total": total_cost, "currency": currency},
    }


# ============ 订单管理 ============

@router.post("/orders")
async def create_data_order(
    data: DataOrderCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """创建数据订单(预下单)"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db, account)

    available = await calculate_stock(db, filter_criteria)
    if available < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {available}")

    total_price = str(float(unit_price) * data.quantity)
    if float(account.balance or 0) < float(total_price):
        raise HTTPException(400, "余额不足")

    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=getattr(data, "product_id", None),
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=unit_price,
        total_price=total_price,
        order_type="data_only",
        status="pending",
        expires_at=datetime.now() + timedelta(hours=24),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "success": True,
        "order_no": order.order_no,
        "quantity": data.quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "status": "pending",
        "expires_at": order.expires_at.isoformat(),
    }


@router.get("/orders")
async def customer_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户获取自己的数据订单"""
    query = select(DataOrder).options(joinedload(DataOrder.product)).where(
        DataOrder.account_id == account.id
    )
    if status:
        query = query.where(DataOrder.status == status)

    count_query = select(func.count()).select_from(
        select(DataOrder).where(DataOrder.account_id == account.id).subquery()
    )
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(DataOrder.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.unique().scalars().all()

    # 批量查询当前用户对这些订单的评分
    from app.modules.data.models import DataProductRating
    order_ids = [o.id for o in orders]
    my_ratings = {}
    if order_ids:
        rating_rows = (await db.execute(
            select(DataProductRating.order_id, DataProductRating.rating)
            .where(
                DataProductRating.account_id == account.id,
                DataProductRating.order_id.in_(order_ids),
            )
        )).fetchall()
        for r in rating_rows:
            my_ratings[r.order_id] = r.rating

    items = []
    for o in orders:
        item = serialize_order(o)
        item["_my_rating"] = my_ratings.get(o.id, 0)
        items.append(item)

    return {
        "success": True,
        "items": items,
        "total": total,
        "page_size": page_size,
    }


@router.get("/orders/{order_id}")
async def customer_order_detail(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """获取订单详情"""
    result = await db.execute(
        select(DataOrder)
        .options(joinedload(DataOrder.product))
        .where(DataOrder.id == order_id, DataOrder.account_id == account.id)
    )
    order = result.unique().scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")

    return {"success": True, "data": serialize_order(order)}


@router.post("/orders/{order_id}/cancel")
async def customer_cancel_order(
    order_id: int,
    data: OrderCancelRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户取消 pending 订单"""
    result = await db.execute(
        select(DataOrder).where(
            DataOrder.id == order_id, DataOrder.account_id == account.id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "pending":
        raise HTTPException(400, "只能取消待处理的订单")

    order.status = "cancelled"
    order.cancel_reason = data.reason or "客户主动取消"
    await db.commit()
    return {"success": True, "message": "订单已取消"}


# ============ 私库管理 ============

@router.get("/my-numbers/summary")
async def get_my_numbers_summary(
    max_batches: int = Query(
        _DEFAULT_MY_NUMBERS_SUMMARY_MAX_BATCHES,
        ge=0,
        le=10000,
        description="最近批次数上限；0=不限制（较慢，供短信发送等全量私库分组）",
    ),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """私库号码按来源+用途+国家聚合统计（卡片展示用）"""
    cache_key = _my_numbers_summary_cache_key(account.id, max_batches)
    stale_key = f"data:my_numbers:stale:{account.id}"
    try:
        cm = await get_cache_manager()
        cached = await cm.get(cache_key)
        is_stale = await cm.get(stale_key) if cached is not None else None
        if cached is not None:
            if not is_stale:
                return cached
            asyncio.ensure_future(
                _background_refresh_summary(account.id, max_batches)
            )
            return cached
    except Exception:
        pass

    payload = await _summary_from_private_library_summaries_table(db, account.id, max_batches)
    try:
        cm = await get_cache_manager()
        await cm.set(cache_key, payload, ttl=_MY_NUMBERS_SUMMARY_CACHE_TTL)
        await cm.delete(f"data:my_numbers:stale:{account.id}")
    except Exception:
        pass
    return payload


async def _pls_bump_purchased_for_number_ids(
    db: AsyncSession, account_id: int, number_ids: Sequence[int]
) -> None:
    """购入绑定 data_numbers 后，汇总表 purchased 桶 +N（used 按当前 use_count 是否已使用）"""
    if not number_ids:
        return
    res = await db.execute(select(DataNumber).where(DataNumber.id.in_(number_ids)))
    deltas = []
    for num in res.scalars():
        uc = num.use_count or 0
        deltas.append(
            (
                ORIGIN_PURCHASED,
                norm_dim(num.country_code),
                norm_dim(num.source),
                norm_dim(num.purpose),
                norm_dim(num.batch_id),
                norm_dim(num.carrier),
                1,
                1 if uc > 0 else 0,
                num.remarks,
                num.created_at,
                num.created_at,
            )
        )
    await pls_apply_deltas_bulk(db, account_id, deltas)


async def _compute_summary(db: AsyncSession, account_id: int, max_batches: int) -> dict:
    """实际执行汇总计算（可能耗时数十秒），由接口同步调用或后台刷新复用"""
    # 总数（始终实时查询，~2s，count 缓存在上传/删除时已被清除）
    cnt_pln = (
        await db.execute(
            select(func.count())
            .select_from(PrivateLibraryNumber)
            .where(
                PrivateLibraryNumber.account_id == account_id,
                _pln_client_visible_clause(),
            )
        )
    ).scalar() or 0
    cnt_dn = (
        await db.execute(
            select(func.count())
            .select_from(DataNumber)
            .where(DataNumber.account_id == account_id)
        )
    ).scalar() or 0
    total_count_all = cnt_pln + cnt_dn
    try:
        cm_count = await get_cache_manager()
        await cm_count.set(
            _my_numbers_count_cache_key(account_id), total_count_all, ttl=_MY_NUMBERS_COUNT_CACHE_TTL
        )
    except Exception:
        pass

    batch_keys = None
    truncated_hint = False
    if max_batches > 0:

        def _batch_ids_stmt(model, lim: int, extra_where=None):
            stmt = (
                select(model.batch_id.label("bid"), func.max(model.created_at).label("mx"))
                .where(model.account_id == account_id)
                .group_by(model.batch_id)
                .order_by(func.max(model.created_at).desc())
                .limit(lim)
            )
            if extra_where is not None:
                stmt = stmt.where(extra_where)
            return stmt

        lim = max(max_batches * 2, max_batches)
        rp = (
            await db.execute(_batch_ids_stmt(PrivateLibraryNumber, lim, _pln_client_visible_clause()))
        ).fetchall()
        rd = (await db.execute(_batch_ids_stmt(DataNumber, lim))).fetchall()
        all_bids: list = []
        seen_bid: set = set()
        for row in sorted(
            list(rp) + list(rd),
            key=lambda x: x.mx if x.mx is not None else datetime.min,
            reverse=True,
        ):
            bid_val = row.bid
            if bid_val in seen_bid:
                continue
            seen_bid.add(bid_val)
            all_bids.append(bid_val)
            if len(all_bids) >= max_batches:
                break
        batch_keys = all_bids
        truncated_hint = len(batch_keys) >= max_batches
        if not batch_keys:
            return {
                "success": True,
                "items": [],
                "total": total_count_all,
                "meta": {"max_batches": max_batches, "truncated": False, "batch_card_limit": max_batches},
            }

    def _summary_carrier_stmt(model, bid_list, extra_where=None):
        sq = (
            select(
                func.coalesce(model.country_code, "").label("country_code"),
                func.coalesce(model.source, "").label("source"),
                func.coalesce(model.purpose, "").label("purpose"),
                func.coalesce(model.batch_id, "").label("batch_id"),
                func.max(model.remarks).label("remarks"),
                model.carrier,
                func.count().label("group_count"),
                func.sum(case((model.use_count > 0, 1), else_=0)).label("used_count"),
                func.min(model.created_at).label("first_at"),
                func.max(model.created_at).label("last_at"),
            )
            .where(model.account_id == account_id)
        )
        if extra_where is not None:
            sq = sq.where(extra_where)
        if bid_list is not None:
            sq = sq.where(model.batch_id.in_(bid_list))
        return sq.group_by(model.country_code, model.source, model.purpose, model.batch_id, model.carrier)

    summary_map: Dict[tuple, dict] = {}
    rows_pln = (
        await db.execute(_summary_carrier_stmt(PrivateLibraryNumber, batch_keys, _pln_client_visible_clause()))
    ).fetchall()
    rows_dn = (await db.execute(_summary_carrier_stmt(DataNumber, batch_keys))).fetchall()

    def _merge(rows, origin: str):
        for r in rows:
            key = (r.country_code, r.source, r.purpose, r.batch_id)
            if key not in summary_map:
                summary_map[key] = {
                    "country_code": r.country_code,
                    "source": r.source,
                    "source_label": SOURCE_LABELS.get(r.source, r.source or ""),
                    "purpose": r.purpose,
                    "purpose_label": PURPOSE_LABELS.get(r.purpose, r.purpose or ""),
                    "batch_id": r.batch_id,
                    "remarks": None,
                    "count": 0,
                    "used_count": 0,
                    "unused_count": 0,
                    "_carrier_map": defaultdict(int),
                    "_carrier_unused_map": defaultdict(int),
                    "first_at": r.first_at,
                    "last_at": r.last_at,
                    "_origin_sources": set(),
                }
            group = summary_map[key]
            group["_origin_sources"].add(origin)
            gc = int(r.group_count or 0)
            gu = int(r.used_count or 0)
            group["count"] += gc
            group["used_count"] += gu
            group["unused_count"] = group["count"] - group["used_count"]
            if r.remarks:
                cur = group["remarks"]
                if cur is None or len(str(r.remarks)) > len(str(cur)):
                    group["remarks"] = r.remarks
            if r.first_at and (not group["first_at"] or r.first_at < group["first_at"]):
                group["first_at"] = r.first_at
            if r.last_at and (not group["last_at"] or r.last_at > group["last_at"]):
                group["last_at"] = r.last_at
            cnm = carrier_label(r.carrier)
            group["_carrier_map"][cnm] += gc
            group["_carrier_unused_map"][cnm] += max(0, gc - gu)

    _merge(rows_pln, "manual")
    _merge(rows_dn, "purchased")

    items = list(summary_map.values())
    for item in items:
        cm = item.pop("_carrier_map", None)
        um = item.pop("_carrier_unused_map", None)
        if cm is not None and um is not None:
            item["carriers"] = [
                {
                    "name": n,
                    "count": c,
                    "unused_count": min(c, max(0, int(um[n]))),
                }
                for n, c in sorted(cm.items(), key=lambda x: -x[1])
            ]
        else:
            item["carriers"] = []
        origins = item.pop("_origin_sources", set())
        if "manual" in origins and "purchased" in origins:
            item["library_origin"] = "mixed"
        elif "manual" in origins:
            item["library_origin"] = "manual"
        else:
            item["library_origin"] = "purchased"
        if item["first_at"]:
            item["first_at"] = item["first_at"].isoformat()
        if item["last_at"]:
            item["last_at"] = item["last_at"].isoformat()

    items.sort(key=lambda x: x["last_at"] or "", reverse=True)

    _apply_summary_item_canonical_labels(items)

    return {
        "success": True,
        "items": items,
        "total": total_count_all,
        "meta": {
            "max_batches": max_batches,
            "truncated": bool(truncated_hint) if max_batches > 0 else False,
            "batch_card_limit": max_batches if max_batches > 0 else None,
        },
    }


@router.get("/my-numbers")
async def get_my_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country: Optional[str] = None,
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """获取我的私有库号码（私库分表 + 公海购入绑定行合并分页）"""
    u = _my_numbers_union_subquery(
        account.id, country=country, tag=tag
    )
    count_stmt = select(func.count()).select_from(u)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(u)
        .order_by(desc(u.c.created_at), desc(u.c.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "success": True,
        "items": [_serialize_my_numbers_union_row(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class MyNumbersDeleteBatchBody(BaseModel):
    """POST 删除私库卡片维度（JSON），避免 DELETE 查询串过长或编码异常"""

    country_code: str = ""
    source: str = ""
    purpose: str = ""
    batch_id: str = ""
    remarks: Optional[str] = None
    carrier: Optional[str] = None


async def _execute_my_numbers_batch_delete(
    db: AsyncSession,
    account_id: int,
    *,
    country: Optional[str],
    source: Optional[str],
    purpose: Optional[str],
    batch_id: Optional[str],
    remarks: Optional[str],
    carrier: Optional[str],
    for_admin: bool = False,
    hard_delete: bool = False,
) -> dict:
    """
    私库删除：客户侧默认软删（is_deleted，行保留）；管理端可 hard_delete 物理删除 private_library_numbers。
    公海购入绑定行均为解除 account_id（不删 data_numbers 池内行）。同步维护 private_library_summaries。
    """

    def _pln_scope_where():
        # 管理端硬删：该维度下含已软删行一并清除；客户侧仅处理未软删可见行
        if hard_delete:
            return PrivateLibraryNumber.account_id == account_id
        return and_(PrivateLibraryNumber.account_id == account_id, _pln_client_visible_clause())

    def _filters_pln(q):
        if country is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.country_code, country))
        if source is not None:
            q = q.where(_sql_dim_source_match(PrivateLibraryNumber.source, source))
        if purpose is not None:
            q = q.where(_sql_dim_purpose_match(PrivateLibraryNumber.purpose, purpose))
        if batch_id is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.batch_id, batch_id))
        if remarks is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.remarks, remarks))
        if carrier is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.carrier, carrier))
        return q

    def _filters_dn(q):
        if country is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.country_code, country))
        if source is not None:
            q = q.where(_sql_dim_source_match(DataNumber.source, source))
        if purpose is not None:
            q = q.where(_sql_dim_purpose_match(DataNumber.purpose, purpose))
        if batch_id is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.batch_id, batch_id))
        if remarks is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.remarks, remarks))
        if carrier is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.carrier, carrier))
        return q

    def _filters_pls(q):
        """汇总表维度（无 carrier 条件，与卡片一致）"""
        if country is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibrarySummary.country_code, country))
        if source is not None:
            q = q.where(_sql_dim_source_match(PrivateLibrarySummary.source, source))
        if purpose is not None:
            q = q.where(_sql_dim_purpose_match(PrivateLibrarySummary.purpose, purpose))
        if batch_id is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibrarySummary.batch_id, batch_id))
        return q

    agg_pln = (
        select(
            PrivateLibraryNumber.country_code,
            PrivateLibraryNumber.source,
            PrivateLibraryNumber.purpose,
            PrivateLibraryNumber.batch_id,
            func.coalesce(PrivateLibraryNumber.carrier, "").label("car"),
            func.count().label("cnt"),
            func.sum(case((PrivateLibraryNumber.use_count > 0, 1), else_=0)).label("used"),
        )
        .where(_pln_scope_where())
        .group_by(
            PrivateLibraryNumber.country_code,
            PrivateLibraryNumber.source,
            PrivateLibraryNumber.purpose,
            PrivateLibraryNumber.batch_id,
            func.coalesce(PrivateLibraryNumber.carrier, ""),
        )
    )
    agg_pln = _filters_pln(agg_pln)

    agg_dn = (
        select(
            DataNumber.country_code,
            DataNumber.source,
            DataNumber.purpose,
            DataNumber.batch_id,
            func.coalesce(DataNumber.carrier, "").label("car"),
            func.count().label("cnt"),
            func.sum(case((DataNumber.use_count > 0, 1), else_=0)).label("used"),
        )
        .where(DataNumber.account_id == account_id)
        .group_by(
            DataNumber.country_code,
            DataNumber.source,
            DataNumber.purpose,
            DataNumber.batch_id,
            func.coalesce(DataNumber.carrier, ""),
        )
    )
    agg_dn = _filters_dn(agg_dn)

    cnt_pln_stmt = _filters_pln(
        select(func.count()).select_from(PrivateLibraryNumber).where(_pln_scope_where())
    )
    cnt_dn_stmt = _filters_dn(
        select(func.count()).select_from(DataNumber).where(DataNumber.account_id == account_id)
    )
    n_pln = (await db.execute(cnt_pln_stmt)).scalar() or 0
    n_dn = (await db.execute(cnt_dn_stmt)).scalar() or 0
    if n_pln + n_dn == 0:
        # 明细已无行但汇总表可能残留幽灵桶（与明细不一致时仍占卡片）
        cnt_pls_stmt = _filters_pls(
            select(func.count())
            .select_from(PrivateLibrarySummary)
            .where(PrivateLibrarySummary.account_id == account_id)
        )
        n_pls = (await db.execute(cnt_pls_stmt)).scalar() or 0
        if n_pls > 0:
            if hard_delete:
                ghost_stmt = _filters_pls(
                    sa_delete(PrivateLibrarySummary).where(PrivateLibrarySummary.account_id == account_id)
                )
            else:
                ghost_stmt = _filters_pls(
                    sa_update(PrivateLibrarySummary)
                    .where(PrivateLibrarySummary.account_id == account_id)
                    .values(is_deleted=True, updated_at=datetime.now())
                )
            await db.execute(ghost_stmt)
            cnt_left = (await db.execute(cnt_pls_stmt)).scalar() or 0
            if cnt_left > 0 and norm_dim(batch_id) != "" and norm_dim(country or "") != "":
                if hard_delete:
                    loose = sa_delete(PrivateLibrarySummary).where(
                        PrivateLibrarySummary.account_id == account_id,
                        _sql_dim_ci_trim_eq(PrivateLibrarySummary.country_code, country),
                        _sql_dim_ci_trim_eq(PrivateLibrarySummary.batch_id, batch_id),
                    )
                else:
                    loose = sa_update(PrivateLibrarySummary).where(
                        PrivateLibrarySummary.account_id == account_id,
                        _sql_dim_ci_trim_eq(PrivateLibrarySummary.country_code, country),
                        _sql_dim_ci_trim_eq(PrivateLibrarySummary.batch_id, batch_id),
                    ).values(is_deleted=True, updated_at=datetime.now())
                await db.execute(loose)
            await db.commit()
            await _invalidate_my_numbers_summary_cache(account_id)
            return {
                "success": True,
                "message": f"明细中已无对应号码，已清除无效汇总分组 {n_pls} 个桶",
                "deleted": 0,
                "pruned_summary_buckets": n_pls,
            }
        return {
            "success": False,
            "message": "未找到符合条件的号码（维度可能与明细不一致），请刷新私有库页面后重试",
            "deleted": 0,
        }

    # 未传 carrier 表示删除整张卡片：汇总层按国家/来源/用途/批次合并展示；
    # 若仅对 manual 做 bucket 扣减，可能遗留 library_origin=purchased 且无绑定明细的脏桶。
    carrier_specified = carrier is not None and norm_dim(carrier) != ""

    if carrier_specified:
        for row in (await db.execute(agg_pln)).all():
            await pls_apply_bucket_delta(
                db,
                account_id=account_id,
                library_origin=ORIGIN_MANUAL,
                country_code=norm_dim(row.country_code),
                source=norm_dim(row.source),
                purpose=norm_dim(row.purpose),
                batch_id=norm_dim(row.batch_id),
                carrier=norm_dim(row.car),
                delta_total=-int(row.cnt or 0),
                delta_used=-int(row.used or 0),
            )
        for row in (await db.execute(agg_dn)).all():
            await pls_apply_bucket_delta(
                db,
                account_id=account_id,
                library_origin=ORIGIN_PURCHASED,
                country_code=norm_dim(row.country_code),
                source=norm_dim(row.source),
                purpose=norm_dim(row.purpose),
                batch_id=norm_dim(row.batch_id),
                carrier=norm_dim(row.car),
                delta_total=-int(row.cnt or 0),
                delta_used=-int(row.used or 0),
            )

    if hard_delete:
        stmt_pln = _filters_pln(sa_delete(PrivateLibraryNumber).where(_pln_scope_where()))
        await db.execute(stmt_pln)
    else:
        stmt_pln = _filters_pln(
            sa_update(PrivateLibraryNumber)
            .where(_pln_scope_where())
            .values(is_deleted=True, updated_at=datetime.now())
        )
        await db.execute(stmt_pln)

    stmt_dn = _filters_dn(sa_update(DataNumber).where(DataNumber.account_id == account_id)).values(
        account_id=None, status="inactive"
    )
    await db.execute(stmt_dn)

    if carrier_specified:
        if hard_delete:
            await pls_prune_non_positive(db, account_id)
        else:
            await pls_soft_prune_non_positive(db, account_id)
    else:
        if hard_delete:
            # 管理端硬删：物理删除汇总行
            del_pls_card = _filters_pls(
                sa_delete(PrivateLibrarySummary).where(PrivateLibrarySummary.account_id == account_id)
            )
            await db.execute(del_pls_card)
        else:
            # 客户侧软删：标记汇总行 is_deleted=True（管理端仍可查阅）
            mark_pls_card = _filters_pls(
                sa_update(PrivateLibrarySummary)
                .where(PrivateLibrarySummary.account_id == account_id)
                .values(is_deleted=True, updated_at=datetime.now())
            )
            await db.execute(mark_pls_card)
        # 若汇总表 source/purpose 与请求维度不一致（历史脏数据），严格 WHERE 可能匹配不到行
        cnt_pls_left_stmt = _filters_pls(
            select(func.count())
            .select_from(PrivateLibrarySummary)
            .where(
                PrivateLibrarySummary.account_id == account_id,
                PrivateLibrarySummary.is_deleted == False,  # noqa: E712
            )
        )
        cnt_pls_left = (await db.execute(cnt_pls_left_stmt)).scalar() or 0
        if cnt_pls_left > 0 and norm_dim(batch_id) != "" and norm_dim(country or "") != "":
            if hard_delete:
                loose_stmt = sa_delete(PrivateLibrarySummary).where(
                    PrivateLibrarySummary.account_id == account_id,
                    _sql_dim_ci_trim_eq(PrivateLibrarySummary.country_code, country),
                    _sql_dim_ci_trim_eq(PrivateLibrarySummary.batch_id, batch_id),
                )
            else:
                loose_stmt = sa_update(PrivateLibrarySummary).where(
                    PrivateLibrarySummary.account_id == account_id,
                    _sql_dim_ci_trim_eq(PrivateLibrarySummary.country_code, country),
                    _sql_dim_ci_trim_eq(PrivateLibrarySummary.batch_id, batch_id),
                ).values(is_deleted=True, updated_at=datetime.now())
            await db.execute(loose_stmt)

    await db.commit()
    await _invalidate_my_numbers_summary_cache(account_id)
    deleted_total = n_pln + n_dn
    if for_admin and hard_delete:
        msg = (
            f"已永久删除客户（ID {account_id}）手工私库 {n_pln} 条"
            f"，并解除公海购入绑定 {n_dn} 条（号码仍在公海池，仅解除与该客户的关联）"
        )
    elif for_admin:
        msg = (
            f"已从客户账户（ID {account_id}）私有库处理 {deleted_total} 条"
            "（手工私库为软删；公海购入号码已释放绑定）"
        )
    else:
        msg = (
            f"已从您的私有库移除 {deleted_total} 条"
            "（手工私库为软删，管理端可查阅；公海购入号码已释放绑定）"
        )
    return {
        "success": True,
        "message": msg,
        "deleted": deleted_total,
    }


class MyNumbersResetUsedBody(BaseModel):
    """按卡片维度重置「已使用」回到「未使用」（不动 sms_logs 历史）"""

    country_code: str = ""
    source: str = ""
    purpose: str = ""
    batch_id: str = ""
    remarks: Optional[str] = None
    carrier: Optional[str] = None


async def _execute_my_numbers_reset_used(
    db: AsyncSession,
    account_id: int,
    *,
    country: Optional[str],
    source: Optional[str],
    purpose: Optional[str],
    batch_id: Optional[str],
    remarks: Optional[str],
    carrier: Optional[str],
) -> dict:
    """
    将匹配维度下 use_count>0 的私库行（PrivateLibraryNumber）与公海购入绑定行（DataNumber）
    重置为 use_count=0、last_used_at=NULL，并直接把汇总表对应桶的 used_count 置 0。
    不删除 sms_logs 等历史。全程 3 条 UPDATE，无每桶循环。
    """

    def _filters_pln(q):
        if country is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.country_code, country))
        if source is not None:
            q = q.where(_sql_dim_source_match(PrivateLibraryNumber.source, source))
        if purpose is not None:
            q = q.where(_sql_dim_purpose_match(PrivateLibraryNumber.purpose, purpose))
        if batch_id is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.batch_id, batch_id))
        if remarks is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.remarks, remarks))
        if carrier is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibraryNumber.carrier, carrier))
        return q

    def _filters_dn(q):
        if country is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.country_code, country))
        if source is not None:
            q = q.where(_sql_dim_source_match(DataNumber.source, source))
        if purpose is not None:
            q = q.where(_sql_dim_purpose_match(DataNumber.purpose, purpose))
        if batch_id is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.batch_id, batch_id))
        if remarks is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.remarks, remarks))
        if carrier is not None:
            q = q.where(_sql_dim_ci_trim_eq(DataNumber.carrier, carrier))
        return q

    def _filters_pls(q):
        if country is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibrarySummary.country_code, country))
        if source is not None:
            q = q.where(_sql_dim_source_match(PrivateLibrarySummary.source, source))
        if purpose is not None:
            q = q.where(_sql_dim_purpose_match(PrivateLibrarySummary.purpose, purpose))
        if batch_id is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibrarySummary.batch_id, batch_id))
        if carrier is not None:
            q = q.where(_sql_dim_ci_trim_eq(PrivateLibrarySummary.carrier, carrier))
        return q

    pln_scope = and_(
        PrivateLibraryNumber.account_id == account_id,
        _pln_client_visible_clause(),
        PrivateLibraryNumber.use_count > 0,
    )
    dn_scope = and_(
        DataNumber.account_id == account_id,
        DataNumber.use_count > 0,
    )

    cnt_pln = (await db.execute(
        _filters_pln(select(func.count()).select_from(PrivateLibraryNumber).where(pln_scope))
    )).scalar() or 0
    cnt_dn = (await db.execute(
        _filters_dn(select(func.count()).select_from(DataNumber).where(dn_scope))
    )).scalar() or 0

    if cnt_pln + cnt_dn == 0:
        return {
            "success": True,
            "message": "没有可重置的已使用号码",
            "reset": 0,
        }

    now_ts = datetime.now()
    if cnt_pln > 0:
        await db.execute(_filters_pln(
            sa_update(PrivateLibraryNumber)
            .where(pln_scope)
            .values(use_count=0, last_used_at=None, updated_at=now_ts)
        ))
    if cnt_dn > 0:
        await db.execute(_filters_dn(
            sa_update(DataNumber)
            .where(dn_scope)
            .values(use_count=0, last_used_at=None)
        ))

    # 汇总表直接置零——reset 后该维度下所有行 use_count 均为 0，used_count 必然为 0
    await db.execute(_filters_pls(
        sa_update(PrivateLibrarySummary)
        .where(
            PrivateLibrarySummary.account_id == account_id,
            PrivateLibrarySummary.used_count > 0,
        )
        .values(used_count=0, updated_at=now_ts)
    ))

    await db.commit()
    await _invalidate_my_numbers_summary_cache(account_id)
    total = cnt_pln + cnt_dn
    return {
        "success": True,
        "message": f"已将 {total} 条号码重置为未使用（手工私库 {cnt_pln} 条，公海购入 {cnt_dn} 条）",
        "reset": total,
        "reset_private": cnt_pln,
        "reset_purchased": cnt_dn,
    }


@router.post("/my-numbers/reset-used")
async def post_reset_my_numbers_used(
    body: MyNumbersResetUsedBody,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """按卡片维度把已使用号码重置为未使用（不动 sms_logs 历史）"""
    return await _execute_my_numbers_reset_used(
        db,
        account.id,
        country=body.country_code,
        source=body.source,
        purpose=body.purpose,
        batch_id=body.batch_id,
        remarks=body.remarks,
        carrier=body.carrier,
    )


@router.post("/my-numbers/delete-batch")
async def post_delete_my_numbers_batch(
    body: MyNumbersDeleteBatchBody,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """推荐：JSON 体删除私库卡片对应明细（与页面卡片维度一致）"""
    return await _execute_my_numbers_batch_delete(
        db,
        account.id,
        country=body.country_code,
        source=body.source,
        purpose=body.purpose,
        batch_id=body.batch_id,
        remarks=body.remarks,
        carrier=body.carrier,
        for_admin=False,
        hard_delete=False,
    )


@router.delete("/my-numbers")
async def delete_my_numbers_batch(
    country: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    purpose: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    remarks: Optional[str] = Query(None),
    carrier: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """兼容：DELETE + Query 删除私库分组"""
    return await _execute_my_numbers_batch_delete(
        db,
        account.id,
        country=country,
        source=source,
        purpose=purpose,
        batch_id=batch_id,
        remarks=remarks,
        carrier=carrier,
        for_admin=False,
        hard_delete=False,
    )


@router.get("/my-numbers/export")
async def export_my_numbers(
    fmt: str = Query("csv", regex="^(csv|txt)$"),
    country: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    batch_id: Optional[str] = Query(None),
    export_password: Optional[str] = Query(None, description="下载密码（若该批次设置了加密则必填）"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """导出我的私有库号码（私库分表 + 公海购入绑定行）。若批次已加密，需提供正确下载密码。"""
    # 密码保护验证：仅当指定 batch_id 时生效（全量导出不受单批次密码限制）
    if batch_id:
        pwd_row = await db.execute(
            select(PrivateLibrarySummary.export_password_hash)
            .where(
                PrivateLibrarySummary.account_id == account.id,
                PrivateLibrarySummary.batch_id == batch_id,
                PrivateLibrarySummary.export_password_hash.isnot(None),
            )
            .limit(1)
        )
        stored_hash = pwd_row.scalar_one_or_none()
        if stored_hash:
            if not export_password or not _pwd_ctx.verify(export_password, stored_hash):
                raise HTTPException(403, "该数据包已加密，请提供正确的下载密码")

    u = _my_numbers_union_subquery(
        account.id,
        country=country,
        source=source,
        purpose=purpose,
        batch_id=batch_id,
    )
    stmt = select(u).order_by(u.c.created_at.asc(), u.c.id.asc())
    result = await db.stream(stmt)

    async def generate():
        if fmt == "csv":
            # 写入 BOM 以防 Excel 打开中文乱码
            yield "\ufeff"
            yield "phone_number,country_code,carrier,source,purpose,library_origin,created_at\n"
            async for row in result:
                r = row._mapping
                row_data = [
                    export_phone_plain_digits(r["phone_number"]),
                    r["country_code"] or "",
                    r["carrier"] or "",
                    r["source"] or "",
                    r["purpose"] or "",
                    r["library_origin"] or "",
                    r["created_at"].isoformat() if r["created_at"] else "",
                ]
                yield ",".join(map(str, row_data)) + "\n"
        else:
            async for row in result:
                r = row._mapping
                line = export_phone_plain_digits(r["phone_number"])
                if line:
                    yield f"{line}\n"

    filename = f"my_numbers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
    media_type = "text/csv" if fmt == "csv" else "text/plain"
    return StreamingResponse(
        generate(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.post("/my-numbers/upload")
async def my_numbers_upload(
    file: UploadFile = File(...),
    country_code: str = Form(...),
    source: Optional[str] = Form("Manual Upload"),
    purpose: Optional[str] = Form("Social"),
    remarks: Optional[str] = Form(None),
    detect_carrier: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """
    上传数据到私有库表 private_library_numbers（与公海 data_numbers 分表，按 account_id+phone 唯一）。
    不与公海或其它客户号码冲突；同一账户重复上传则更新批次/备注等。
    """
    fname = file.filename or ""
    if not fname.lower().endswith((".csv", ".txt")):
        raise HTTPException(400, "仅支持 CSV 或 TXT 文件")

    content = await file.read()
    _assert_private_upload_country_matches_account(account, country_code)
    try:
        result = await run_private_library_upload(
            db,
            account.id,
            content,
            fname,
            country_code,
            source,
            purpose,
            remarks,
            detect_carrier,
            progress=None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    result["message"] = (
        f"成功上传 {result['inserted']} 条新数据，更新 {result['updated']} 条已有私库记录（与公海分表存储，互不占用）"
    )
    return result


_PRIVATE_UPLOAD_DIR = Path(os.environ.get("PRIVATE_UPLOAD_DIR", "/tmp/smsc_pl_uploads"))


def _assert_account_country_matches_data_filter(account: Account, filter_criteria: Optional[dict]) -> None:
    """账户配置了国家时，仅允许购买该国数据（商品筛选须含一致的国家）。"""
    acc_iso = account_country_iso(account)
    if not acc_iso:
        return
    fc = filter_criteria or {}
    fc_country = fc.get("country")
    if not fc_country:
        raise HTTPException(
            400,
            f"当前短信账户已限定国家/地区为 {acc_iso}，无法购买未限定国家的数据商品，请选择该国家的数据商品。",
        )
    fc_iso = normalize_country_code(str(fc_country))
    if fc_iso != acc_iso:
        raise HTTPException(
            400,
            f"当前短信账户仅允许购买 {acc_iso} 地区数据，所选商品国家为 {fc_iso}，请选择匹配的商品。",
        )


def _assert_private_upload_country_matches_account(account: Account, country_code: str) -> None:
    """私库上传所选国家必须与账户 country_code 一致（归一化后比较）。"""
    acc_cc = norm_dim(getattr(account, "country_code", None) or "").upper()
    req_cc = norm_dim(country_code or "").upper()
    if not acc_cc:
        raise HTTPException(
            400,
            "账户未设置国家/地区，无法上传私库数据，请在账户资料中完善国家后再试",
        )
    if not req_cc:
        raise HTTPException(400, "请选择国家/地区")
    if req_cc != acc_cc:
        raise HTTPException(
            400,
            f"私库上传仅允许与短信账户一致的国家/地区（账户国家：{acc_cc}）",
        )


def _serialize_private_upload_task(t: PrivateLibraryUploadTask) -> dict:
    """序列化私库上传任务（供列表/详情 API）"""
    return {
        "task_id": t.task_id,
        "status": t.status,
        "stage": t.stage or "",
        "progress_percent": t.progress_percent or 0,
        "total_unique": t.total_unique or 0,
        "inserted": t.inserted or 0,
        "updated": t.updated or 0,
        "original_filename": t.original_filename,
        "country_code": t.country_code,
        "detect_carrier": bool(t.detect_carrier),
        "result_batch_id": t.result_batch_id,
        "error_message": t.error_message,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


class AbandonPrivateUploadTaskIn(BaseModel):
    """放弃排队任务请求体（避免部分反向代理对「/tasks/{id}/abandon」路径返回 404）"""

    task_id: str = Field(..., min_length=1, max_length=80, description="业务任务号 PLU-…")


async def _abandon_private_library_upload_task_core(
    db: AsyncSession,
    account_id: int,
    task_id: str,
) -> dict:
    tid = (task_id or "").strip()
    if not tid:
        raise HTTPException(400, "task_id 无效")
    row = (
        await db.execute(
            select(PrivateLibraryUploadTask).where(
                PrivateLibraryUploadTask.task_id == tid,
                PrivateLibraryUploadTask.account_id == account_id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "任务不存在")
    if row.status != "pending":
        raise HTTPException(400, "仅「排队中」的任务可放弃；处理中请稍候，已完成或失败请勿重复操作")
    row.status = "failed"
    row.error_message = "已手动放弃。若因 Worker 未消费导致长期排队，请重启 worker 后重新上传。"
    row.completed_at = datetime.now()
    row.stage = "abandoned"
    await db.commit()
    fp = Path(row.file_path)
    try:
        if fp.is_file():
            fp.unlink()
    except OSError:
        pass
    return {"success": True, "message": "已放弃该任务，可重新提交上传"}


@router.post("/my-numbers/upload-tasks")
async def create_my_numbers_upload_task(
    file: UploadFile = File(...),
    country_code: str = Form(...),
    source: Optional[str] = Form("Manual Upload"),
    purpose: Optional[str] = Form("Social"),
    remarks: Optional[str] = Form(None),
    detect_carrier: bool = Form(True),
    export_password: Optional[str] = Form(None, description="下载密码（可选）；设置后导出该批次需验证密码"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """
    创建私库异步上传任务：文件落盘后加入 Celery 队列，通过 GET /my-numbers/upload-tasks/{task_id} 轮询进度。
    需运行消费 data_tasks 队列的 Celery Worker。
    export_password 设置后，该批次号码导出时需提供正确密码（SMS 发送不受影响）。
    """
    fname = file.filename or ""
    if not fname.lower().endswith((".csv", ".txt")):
        raise HTTPException(400, "仅支持 CSV 或 TXT 文件")

    content = await file.read()
    _assert_private_upload_country_matches_account(account, country_code)

    # 密码校验：不允许过短
    if export_password is not None:
        export_password = export_password.strip()
        if export_password and len(export_password) < 4:
            raise HTTPException(400, "下载密码至少需要 4 位")

    export_password_hash = _pwd_ctx.hash(export_password) if export_password else None

    task_id = f"PLU-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    _PRIVATE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    fpath = _PRIVATE_UPLOAD_DIR / f"{task_id}.bin"
    fpath.write_bytes(content)

    task = PrivateLibraryUploadTask(
        task_id=task_id,
        account_id=account.id,
        file_path=str(fpath.resolve()),
        original_filename=fname[:250],
        country_code=(country_code or "").strip().upper() or country_code,
        source=source,
        purpose=purpose,
        remarks=remarks,
        detect_carrier=bool(detect_carrier),
        export_password_hash=export_password_hash,
        status="pending",
        stage="queued",
        progress_percent=0,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    try:
        from app.workers.celery_app import celery_app

        celery_app.send_task("private_library_upload", args=[task_id], queue="data_tasks")
    except Exception as e:
        logger.exception("私库上传任务入队失败: %s", task_id)
        task.status = "failed"
        task.error_message = f"任务入队失败: {e}；请检查 RabbitMQ 与 Celery Worker，或使用同步上传接口 POST /my-numbers/upload"
        task.completed_at = datetime.now()
        await db.commit()
        try:
            fpath.unlink(missing_ok=True)
        except TypeError:
            if fpath.exists():
                fpath.unlink()
        raise HTTPException(503, task.error_message or "任务队列不可用")

    return {
        "success": True,
        "task_id": task_id,
        "message": "已创建上传任务，请轮询 GET /data/my-numbers/upload-tasks/{task_id} 查看进度",
    }


@router.get("/my-numbers/upload-tasks")
async def list_my_numbers_upload_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """当前账户的私库上传任务列表（按创建时间倒序）"""
    base = select(PrivateLibraryUploadTask).where(PrivateLibraryUploadTask.account_id == account.id)
    cnt_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(cnt_q)).scalar() or 0

    q = (
        base.order_by(PrivateLibraryUploadTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()
    return {
        "success": True,
        "items": [_serialize_private_upload_task(t) for t in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/my-numbers/upload-tasks/abandon")
async def abandon_my_numbers_upload_task_body(
    body: AbandonPrivateUploadTaskIn,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """放弃仍处于排队中的上传任务（JSON Body 传 task_id，与路径版二选一）"""
    return await _abandon_private_library_upload_task_core(db, account.id, body.task_id)


@router.get("/my-numbers/upload-tasks/{task_id}")
async def get_my_numbers_upload_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """查询单个私库上传任务进度"""
    row = (
        await db.execute(
            select(PrivateLibraryUploadTask).where(
                PrivateLibraryUploadTask.task_id == task_id,
                PrivateLibraryUploadTask.account_id == account.id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "任务不存在")
    return {"success": True, "task": _serialize_private_upload_task(row)}


@router.post("/my-numbers/upload-tasks/{task_id}/abandon")
async def abandon_my_numbers_upload_task_path(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """放弃仍处于排队中的上传任务（路径传 task_id，兼容旧前端）"""
    return await _abandon_private_library_upload_task_core(db, account.id, task_id)


# ============ 辅助 ============

async def _validate_purchase(data, db: AsyncSession, account: Optional[Account] = None):
    """验证购买请求，返回 (product, filter_criteria, unit_price)"""
    if getattr(data, "product_id", None):
        result = await db.execute(
            select(DataProduct).where(
                DataProduct.id == data.product_id,
                DataProduct.status == "active",
                DataProduct.is_deleted == False,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(404, "商品不存在或已下架")
        if data.quantity < product.min_purchase:
            raise HTTPException(400, f"最小购买量: {product.min_purchase}")
        if data.quantity > product.max_purchase:
            raise HTTPException(400, f"最大购买量: {product.max_purchase}")
        fc = product.filter_criteria
        if account is not None:
            _assert_account_country_matches_data_filter(account, fc)
        return product, fc, product.price_per_number

    if getattr(data, "filter_criteria", None):
        fc = data.filter_criteria
        if account is not None:
            _assert_account_country_matches_data_filter(account, fc)
        return None, fc, "0.001"

    raise HTTPException(400, "请选择商品或指定筛选条件")


# ============ 商品评分 ============

@router.post("/products/{product_id}/rate")
async def rate_product(
    product_id: int,
    rating: int = Query(..., ge=1, le=5, description="评分(1-5)"),
    order_id: Optional[int] = Query(None, description="关联订单ID"),
    comment: Optional[str] = Query(None, max_length=500, description="评价内容"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户对数据商品评分（需要有该商品的已完成订单）"""
    from app.modules.data.models import DataProductRating

    product = (await db.execute(
        select(DataProduct).where(DataProduct.id == product_id, DataProduct.is_deleted == False)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "商品不存在")

    order_filter = [DataOrder.account_id == account.id, DataOrder.product_id == product_id]
    if order_id:
        order_filter.append(DataOrder.id == order_id)
    order = (await db.execute(
        select(DataOrder).where(*order_filter).order_by(DataOrder.created_at.desc())
    )).scalars().first()
    if not order:
        raise HTTPException(400, "您没有该商品的订单，无法评分")

    actual_order_id = order_id or order.id

    existing = (await db.execute(
        select(DataProductRating).where(
            DataProductRating.account_id == account.id,
            DataProductRating.order_id == actual_order_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.rating = rating
        existing.comment = comment
        await db.commit()
        return {"success": True, "message": "评分已更新", "rating_id": existing.id}

    new_rating = DataProductRating(
        product_id=product_id,
        account_id=account.id,
        order_id=actual_order_id,
        rating=rating,
        comment=comment,
    )
    db.add(new_rating)
    await db.commit()
    await db.refresh(new_rating)
    return {"success": True, "message": "评分成功", "rating_id": new_rating.id}


@router.get("/products/{product_id}/ratings")
async def get_product_ratings(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """获取某个商品的评分统计和近期评分"""
    from app.modules.data.models import DataProductRating

    stats = (await db.execute(
        select(
            func.count().label("total_ratings"),
            func.avg(DataProductRating.rating).label("avg_rating"),
            func.max(DataProductRating.rating).label("max_rating"),
        ).where(DataProductRating.product_id == product_id)
    )).first()

    recent_30d = datetime.now() - timedelta(days=30)
    recent_stats = (await db.execute(
        select(
            func.count().label("recent_count"),
            func.avg(DataProductRating.rating).label("recent_avg"),
            func.max(DataProductRating.rating).label("recent_max"),
        ).where(
            DataProductRating.product_id == product_id,
            DataProductRating.created_at >= recent_30d,
        )
    )).first()

    recent_list = (await db.execute(
        select(DataProductRating)
        .where(DataProductRating.product_id == product_id)
        .order_by(DataProductRating.created_at.desc())
        .limit(10)
    )).scalars().all()

    my_rating = (await db.execute(
        select(DataProductRating).where(
            DataProductRating.product_id == product_id,
            DataProductRating.account_id == account.id,
        ).order_by(DataProductRating.created_at.desc())
    )).scalars().first()

    return {
        "success": True,
        "product_id": product_id,
        "total_ratings": stats.total_ratings or 0,
        "avg_rating": round(float(stats.avg_rating or 0), 1),
        "max_rating": stats.max_rating or 0,
        "recent_avg": round(float(recent_stats.recent_avg or 0), 1),
        "recent_count": recent_stats.recent_count or 0,
        "recent_max": recent_stats.recent_max or 0,
        "my_rating": {
            "rating": my_rating.rating,
            "comment": my_rating.comment,
            "order_id": my_rating.order_id,
            "created_at": my_rating.created_at.isoformat() if my_rating.created_at else None,
        } if my_rating else None,
        "recent_ratings": [
            {
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_list
        ],
    }
