"""客户 - 数据业务 API"""
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (
    select,
    func,
    case,
    text as sa_text,
    update as sa_update,
    insert,
    tuple_,
    union_all,
    literal,
    cast,
    delete as sa_delete,
    Integer,
    desc,
    String,
)
from sqlalchemy.types import Date as SA_Date
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import joinedload
from typing import Optional, List, Dict
from datetime import datetime, date, timedelta
import uuid
import csv
import io
import re
import asyncio
from decimal import Decimal

from app.database import get_db
from app.modules.data.models import (
    DataNumber,
    DataProduct,
    DataOrder,
    DataOrderNumber,
    PrivateLibraryNumber,
    SOURCE_LABELS,
    PURPOSE_LABELS,
    FRESHNESS_LABELS,
)
from app.modules.data.data_account import DataAccount
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
    serialize_product,
    serialize_order,
    compute_freshness,
)
from app.utils.sms_template import render_sms_variables, sms_template_has_variables
from app.utils.cache import get_cache_manager

logger = get_logger(__name__)
router = APIRouter()

# 私库汇总接口缓存（减轻大表 GROUP BY 压力）
_MY_NUMBERS_SUMMARY_CACHE_TTL = 180
# 默认仅统计「最近 N 个批次」维度，避免单账号数百万行时全表聚合过慢；短信发送页传 max_batches=0 拉全量
_DEFAULT_MY_NUMBERS_SUMMARY_MAX_BATCHES = 400
# 私库号码总数缓存（COUNT(*) 在大表上仍可能较慢）
_MY_NUMBERS_COUNT_CACHE_TTL = 600


def _my_numbers_summary_cache_key(account_id: int, max_batches: int) -> str:
    return f"data:my_numbers:summary:{account_id}:mb{max_batches}"


async def _invalidate_my_numbers_summary_cache(account_id: int) -> None:
    """私库汇总数据变更后失效缓存（含不同 max_batches 的键）"""
    try:
        cm = await get_cache_manager()
        await cm.delete_pattern(f"data:my_numbers:summary:{account_id}*")
        await cm.delete(f"data:my_numbers:count:{account_id}")
    except Exception:
        pass


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
        literal("manual").label("library_origin"),
    ).where(PrivateLibraryNumber.account_id == account_id)
    q_dn = select(
        DataNumber.id,
        DataNumber.phone_number,
        DataNumber.country_code,
        DataNumber.tags,
        DataNumber.carrier,
        cast(DataNumber.status, String).label("status"),
        DataNumber.source,
        DataNumber.purpose,
        DataNumber.data_date,
        DataNumber.batch_id,
        DataNumber.pricing_template_id,
        DataNumber.use_count,
        DataNumber.account_id,
        DataNumber.last_used_at,
        DataNumber.created_at,
        literal("purchased").label("library_origin"),
    ).where(DataNumber.account_id == account_id)
    if country:
        q_pln = q_pln.where(PrivateLibraryNumber.country_code == country)
        q_dn = q_dn.where(DataNumber.country_code == country)
    if tag:
        q_pln = q_pln.where(PrivateLibraryNumber.tags.contains([tag]))
        q_dn = q_dn.where(DataNumber.tags.contains([tag]))
    if source:
        q_pln = q_pln.where(PrivateLibraryNumber.source == source)
        q_dn = q_dn.where(DataNumber.source == source)
    if purpose:
        q_pln = q_pln.where(PrivateLibraryNumber.purpose == purpose)
        q_dn = q_dn.where(DataNumber.purpose == purpose)
    if batch_id:
        q_pln = q_pln.where(PrivateLibraryNumber.batch_id == batch_id)
        q_dn = q_dn.where(DataNumber.batch_id == batch_id)
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


_NON_DIGIT_PHONE = re.compile(r"[^\d+]")


def _decode_my_numbers_upload_bytes(content: bytes) -> str:
    """尝试多种编码解码私库上传文件（避免 GBK 误用 UTF-8 导致整文件无效）"""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_line_to_e164(line: str, default_region: Optional[str]) -> Optional[str]:
    """
    将一行文本解析为 E.164（含 +），与后台批量导入逻辑一致。
    default_region：用户在上传表单选择的国家 ISO（如 TH），用于解析本地号。
    """
    import phonenumbers

    s = line.strip().strip("\ufeff").strip("\u200b").strip('"').strip("'")
    if not s:
        return None
    s = _NON_DIGIT_PHONE.sub("", s)
    if not s:
        return None
    digits = s.lstrip("+")
    if len(digits) < 7 or len(digits) > 20:
        return None

    attempts: List[str] = []
    if s.startswith("+"):
        attempts.append(s)
    elif s.startswith("00"):
        attempts.append("+" + s[2:])
    else:
        if default_region:
            attempts.append(s)
        attempts.append("+" + s)

    region = (default_region or "").strip().upper() or None
    for attempt in attempts:
        try:
            pn = phonenumbers.parse(attempt, region)
            if phonenumbers.is_valid_number(pn):
                return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            continue
    return None


def _extract_phone_numbers_from_upload_text(
    filename: str, text_content: str, default_region: Optional[str] = None
) -> List[str]:
    """从上传文本中解析号码为 E.164（同步，可在线程池中执行）"""
    numbers_to_add: List[str] = []
    lower_name = (filename or "").lower()
    if lower_name.endswith(".csv"):
        f = io.StringIO(text_content)
        reader = csv.reader(f)
        for row in reader:
            if not row or not str(row[0]).strip():
                continue
            line = str(row[0]).strip()
            e164 = _parse_line_to_e164(line, default_region)
            if e164:
                numbers_to_add.append(e164)
    else:
        for line in text_content.splitlines():
            e164 = _parse_line_to_e164(line, default_region)
            if e164:
                numbers_to_add.append(e164)
    return numbers_to_add


def _phone_db_lookup_keys(e164: str) -> List[str]:
    """库中可能存 +66… 或 66…，查询时一并匹配"""
    s = (e164 or "").strip()
    d = s.lstrip("+")
    keys = [s, d]
    if d:
        keys.append("+" + d)
    # 去重保序
    seen = set()
    out: List[str] = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _batch_lookup_carriers(nums: List[str]) -> Dict[str, Optional[str]]:
    """批量运营商识别（在线程中执行，避免阻塞事件循环）"""
    import phonenumbers
    from phonenumbers import carrier as pn_carrier

    out: Dict[str, Optional[str]] = {}
    for num in nums:
        try:
            phone_with_plus = num if num.startswith("+") else "+" + num
            parse_obj = phonenumbers.parse(phone_with_plus, None)
            out[num] = pn_carrier.name_for_number(parse_obj, "en")
        except Exception:
            out[num] = None
    return out


# ============ 商品浏览 ============

@router.get("/carriers")
async def get_available_carriers(
    country_code: Optional[str] = Query(None, description="按国家筛选运营商"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """获取可用的运营商列表（去重后的 carrier 值）"""
    query = select(DataNumber.carrier, func.count(DataNumber.id).label("cnt")).where(
        DataNumber.status == 'active',
        DataNumber.account_id.is_(None),
        DataNumber.carrier.isnot(None),
        DataNumber.carrier != '',
        DataNumber.carrier != 'Unknown',
    )

    # 如果有国家过滤或客户绑定了国家
    if country_code:
        query = query.where(DataNumber.country_code == country_code)
    else:
        da_result = await db.execute(
            select(DataAccount).where(DataAccount.account_id == account.id)
        )
        da = da_result.scalar_one_or_none()
        if da and da.country_code:
            query = query.where(DataNumber.country_code == da.country_code)

    query = query.group_by(DataNumber.carrier).order_by(func.count(DataNumber.id).desc())
    result = await db.execute(query)
    rows = result.fetchall()

    return {
        "success": True,
        "carriers": [{"name": row[0], "count": row[1]} for row in rows],
    }


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

    # 1. 基础国家过滤逻辑 - 默认显示本账户对应国家，按国家查询后才显示其他
    da_result = await db.execute(
        select(DataAccount).where(DataAccount.account_id == account.id)
    )
    da = da_result.scalar_one_or_none()
    
    target_country = country or (da.country_code if da else None)
    if target_country:
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.country")) == target_country
        )

    # 2. 其他筛选项
    if tag:
        # 适应 JSON 数组格式: ["tag1", "tag2"]
        query = query.where(
            func.json_contains(DataProduct.filter_criteria, sa_text(f'"{tag}"'), "$.tags")
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

    # 13. 使用 Redis 缓存聚合结果
    cache_manager = await get_cache_manager()
    # 统计范围跟随目标国家
    cache_key = f"data:store:agg_stats:{target_country or 'global'}"
    cached_agg = await cache_manager.get(cache_key)
    
    if cached_agg:
        agg_map = cached_agg["agg_map"]
        country_total_carriers = cached_agg["country_total_carriers"]
    else:
        agg_map = {}
        country_total_carriers = {}
        # 构造聚合查询
        agg_select = select(
            DataNumber.country_code,
            DataNumber.source,
            DataNumber.purpose,
            DataNumber.carrier,
            func.count().label("cnt")
        ).where(
            DataNumber.account_id.is_(None),
            DataNumber.status == 'active'
        )
        
        if target_country:
            agg_select = agg_select.where(DataNumber.country_code == target_country)
            
        agg_res = await db.execute(
            agg_select.group_by(
                DataNumber.country_code,
                DataNumber.source,
                DataNumber.purpose,
                DataNumber.carrier
            )
        )
        
        for r in agg_res.fetchall():
            co, s, p, car, cnt = r.country_code, r.source, r.purpose, r.carrier or "Unknown", int(r.cnt)
            key_str = f"{co}:{s}:{p}" # JSON key 必须是字符串
            if key_str not in agg_map:
                agg_map[key_str] = {}
            agg_map[key_str][car] = agg_map[key_str].get(car, 0) + cnt
            
            # 记录可用运营商 (如果指定了国家则按国家统计，否则全局统计)
            if not target_country or co == target_country:
                country_total_carriers[car] = country_total_carriers.get(car, 0) + cnt
        
        # 存入缓存 (60秒)
        await cache_manager.set(cache_key, {
            "agg_map": agg_map,
            "country_total_carriers": country_total_carriers
        }, ttl=60)

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

    # 构造返回项
    items = []
    for p in products:
        item = serialize_product(p)
        fc = p.filter_criteria or {}
        p_country = fc.get("country")
        p_source = fc.get("source")
        p_purpose = fc.get("purpose")
        
        # 匹配该商品的运营商分布 (增加国家维度)
        product_dist = {}
        if p_country and p_source and p_purpose:
            product_dist = agg_map.get(f"{p_country}:{p_source}:{p_purpose}", {})
        elif p_country and p_source:
            # 兼容：按国家+来源匹配
            for key_str, d in agg_map.items():
                co, s, _ = key_str.split(":")
                if co == p_country and s == p_source:
                    for car, cnt in d.items():
                        product_dist[car] = product_dist.get(car, 0) + cnt
        
        # 构造 carriers 列表并计算总库存
        carrier_list = [{"name": c, "count": cnt} for c, cnt in product_dist.items()]
        
        # 过滤
        if carrier:
            carrier_list = [c for c in carrier_list if c["name"] == carrier]
            item["stock_count"] = sum(c["count"] for c in carrier_list)
            item["carrier_filter"] = carrier
            if item["stock_count"] <= 0:
                continue
        else:
            item["stock_count"] = sum(c["count"] for c in carrier_list)
        
        item["carriers"] = carrier_list
        
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
    product, filter_criteria, unit_price = await _validate_purchase(data, db)

    if data.carrier:
        filter_criteria = dict(filter_criteria or {})
        filter_criteria["carrier"] = data.carrier

    total_price = Decimal(str(unit_price)) * data.quantity

    # P0-FIX: 原子扣费，防止并发双扣
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_price)
        .values(balance=Account.balance - total_price)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, "余额不足")

    # P0-FIX: 锁定号码时加 account_id IS NULL 条件，防止超卖
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
    if locked < len(number_ids):
        logger.warning(f"库存竞争: 请求{len(number_ids)}条, 实际锁定{locked}条")

    actual_price = Decimal(str(unit_price)) * locked

    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=data.product_id,
        filter_criteria=filter_criteria,
        quantity=locked,
        unit_price=str(unit_price),
        total_price=str(actual_price),
        order_type="data_only",
        status="completed",
        executed_count=locked,
        executed_at=datetime.now(),
    )
    db.add(order)
    await db.flush()

    # P0-FIX: 参数化插入，防止 SQL 注入
    if number_ids:
        from app.modules.data.models import DataOrderNumber as DON
        db.add_all([DON(order_id=order.id, number_id=nid) for nid in number_ids])

    # 多扣的差额退回
    if total_price > actual_price:
        refund = total_price - actual_price
        await db.execute(
            sa_update(Account).where(Account.id == account.id)
            .values(balance=Account.balance + refund)
        )

    if product:
        product.total_sold = (product.total_sold or 0) + locked

    from app.modules.common.balance_log import BalanceLog
    new_bal = await db.execute(select(Account.balance).where(Account.id == account.id))
    db.add(BalanceLog(
        account_id=account.id, change_type='charge', amount=-actual_price,
        balance_after=float(new_bal.scalar()), description=f"BuyStock: {locked} 条数据"
    ))

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

    available = await calculate_stock(db, product.filter_criteria, public_only=True)
    if available < data.quantity:
        raise HTTPException(400, f"数据库存不足，当前可用: {available}")

    # 计价：使用打包价，若无打包价则按单价
    if product.bundle_price:
        total_price = Decimal(str(product.bundle_price)) * data.quantity
    else:
        total_price = Decimal(str(product.price_per_number)) * data.quantity

    # P0-FIX: 原子扣费
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_price)
        .values(balance=Account.balance - total_price)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, "余额不足")

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

    # P0-FIX: 批量锁定号码，防止超卖
    id_query = build_filter_query(product.filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]

    lock_result = await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids), DataNumber.account_id.is_(None))
        .values(account_id=account.id)
    )
    locked = lock_result.rowcount

    product.total_sold = (product.total_sold or 0) + locked

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
    product, filter_criteria, unit_price = await _validate_purchase(data, db)

    if data.carrier:
        filter_criteria = dict(filter_criteria or {})
        filter_criteria["carrier"] = data.carrier

    available = await calculate_stock(db, filter_criteria, public_only=True)
    if available < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {available}")

    # ---------- 1. 先锁定号码（防超卖） ----------
    from app.core.router import RoutingEngine
    from app.core.pricing import PricingEngine
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.sms_log import SMSLog
    from app.utils.queue import QueueManager
    from app.utils.phone_utils import country_to_dial_code

    id_query = build_filter_query(filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]
    if len(number_ids) < data.quantity:
        raise HTTPException(400, f"库存不足，仅剩 {len(number_ids)} 条")

    # 原子锁定
    lock_result = await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids), DataNumber.account_id.is_(None))
        .values(account_id=account.id, last_used_at=datetime.now())
    )
    if lock_result.rowcount < data.quantity:
        raise HTTPException(400, "号码已被抢购，请重试")

    num_result = await db.execute(select(DataNumber).where(DataNumber.id.in_(number_ids)))
    numbers = num_result.scalars().all()

    # ---------- 2. 按每个号码的国家单独选通道（与手动发送一致，避免用样本导致通道错误） ----------
    routing_engine = RoutingEngine(db)
    pricing_engine = PricingEngine(db)
    msg_list = data.messages if data.messages and len(data.messages) > 1 else [data.message]
    msg_count = len(msg_list)
    msg_has_vars = [sms_template_has_variables(m) for m in msg_list]

    # 预计算每条短信的通道、价格、成本
    num_plans = []  # [(num, channel, price_info, msg, parts, sell, cost), ...]
    for idx, num in enumerate(numbers, start=1):
        template = msg_list[(idx - 1) % msg_count]
        msg = (
            render_sms_variables(
                template,
                index=idx,
                phone_e164=num.phone_number or "",
                country_code=num.country_code or "",
            )
            if msg_has_vars[(idx - 1) % msg_count]
            else template
        )
        parts = pricing_engine._count_sms_parts(msg)

        phone_country = num.country_code or "PH"
        dial_code = country_to_dial_code(phone_country)

        channel = None
        for cc in [dial_code, phone_country]:
            try:
                ch = await routing_engine.select_channel(
                    country_code=cc,
                    strategy='priority',
                    account_id=account.id
                )
                if ch:
                    # 支持 HTTP 与 SMPP，与手动发送一致
                    if ch.protocol == 'HTTP':
                        if ch.api_url:
                            channel = ch
                            break
                    elif ch.protocol == 'SMPP':
                        if ch.host and ch.port:
                            channel = ch
                            break
            except Exception:
                continue

        if not channel:
            from sqlalchemy import select as sa_select, or_, and_
            from app.modules.sms.channel import Channel
            from app.modules.common.account import AccountChannel
            # 兜底：HTTP 或 SMPP 均可（与手动发送一致）
            base_q = sa_select(Channel).where(
                Channel.status == 'active',
                Channel.is_deleted == False,
                or_(
                    and_(Channel.protocol == 'HTTP', Channel.api_url.isnot(None)),
                    and_(Channel.protocol == 'SMPP', Channel.host.isnot(None), Channel.port.isnot(None)),
                ),
            )
            ac_result = await db.execute(
                select(AccountChannel.channel_id).where(AccountChannel.account_id == account.id)
            )
            bound_ids = [r[0] for r in ac_result.all()]
            if bound_ids:
                base_q = base_q.where(Channel.id.in_(bound_ids))
            ch_result = await db.execute(base_q.order_by(Channel.priority.desc()).limit(1))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            raise HTTPException(
                400,
                f"号码 {num.phone_number}（国家 {phone_country}）无可用发送通道，请检查账户通道绑定与路由规则"
            )

        price_info = await pricing_engine.get_price(channel.id, dial_code, account_id=account.id)
        if not price_info:
            price_info = await pricing_engine.get_price(channel.id, phone_country, account_id=account.id)
        base_cost = await pricing_engine.resolve_base_cost_per_sms(channel.id, phone_country, channel)
        sell = float(price_info['price']) * parts if price_info else 0.0
        cost = float(base_cost) * parts
        currency = price_info['currency'] if price_info else 'USD'
        num_plans.append((num, channel, price_info, msg, parts, sell, cost, currency))

    # 汇总费用
    data_cost = Decimal(str(unit_price)) * data.quantity
    sms_cost = sum(Decimal(str(p[5])) for p in num_plans)
    total_cost = data_cost + sms_cost
    currency = num_plans[0][7] if num_plans else 'USD'

    # P0-FIX: 原子扣费
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_cost)
        .values(balance=Account.balance - total_cost)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, f"余额不足，需要 {total_cost:.4f} {currency}（数据 {data_cost:.4f} + 短信 {sms_cost:.4f}）")

    # ---------- 3. 创建订单 ----------
    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=getattr(data, "product_id", None),
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=str(unit_price),
        total_price=str(total_cost),
        order_type="data_and_send",
        status="completed",
        executed_count=data.quantity,
        executed_at=datetime.now(),
    )
    db.add(order)
    await db.flush()

    # ---------- 4. 创建短信记录（每条使用该号码国家对应的通道） ----------
    batch_tag = f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    sms_batch = SmsBatch(
        account_id=account.id,
        batch_name=f"DataSend-{product.product_name if product else 'Custom'}-{batch_tag}",
        total_count=len(numbers),
        status=BatchStatus.PROCESSING,
    )
    db.add(sms_batch)
    await db.flush()

    message_ids = []
    channels_used = set()
    for idx, (num, channel, price_info, msg, parts, sell, cost, _) in enumerate(num_plans, start=1):
        num.use_count = (num.use_count or 0) + 1
        channels_used.add(channel.channel_code)

        mid = f"msg_{uuid.uuid4().hex}"
        sms = SMSLog(
            message_id=mid,
            account_id=account.id,
            channel_id=channel.id,
            batch_id=sms_batch.id,
            phone_number=num.phone_number,
            country_code=num.country_code,
            message=msg,
            message_count=parts,
            status="pending",
            cost_price=cost,
            selling_price=sell,
            currency=currency,
            submit_time=datetime.now(),
        )
        db.add(sms)
        message_ids.append(mid)
        db.add(DataOrderNumber(order_id=order.id, number_id=num.id))

    if product:
        product.total_sold = (product.total_sold or 0) + len(numbers)

    from app.modules.common.balance_log import BalanceLog
    new_bal = await db.execute(select(Account.balance).where(Account.id == account.id))
    db.add(BalanceLog(
        account_id=account.id, change_type='charge', amount=-total_cost,
        balance_after=float(new_bal.scalar()),
        description=f"DataSend: {len(numbers)} 条 via {','.join(sorted(channels_used))}"
    ))

    await db.commit()
    await _invalidate_my_numbers_summary_cache(account.id)

    queued = 0
    for mid in message_ids:
        if QueueManager.queue_sms(mid):
            queued += 1

    return {
        "success": True,
        "message": f"已购买 {len(numbers)} 条数据并创建发送任务",
        "order_no": order.order_no,
        "batch_id": batch_tag,
        "queued": queued,
        "channel": ",".join(sorted(channels_used)) if channels_used else "-",
        "cost": {"data": data_cost, "sms": sms_cost, "total": total_cost, "currency": currency},
    }


# ============ 订单管理 ============

@router.post("/orders")
async def create_data_order(
    data: DataOrderCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """创建数据订单(预下单)"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db)

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
    try:
        cm = await get_cache_manager()
        cached = await cm.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        pass

    # 总数 = 私库分表 private_library_numbers + 公海购入后绑定在 data_numbers 的号码
    cnt_pln = (
        await db.execute(
            select(func.count())
            .select_from(PrivateLibraryNumber)
            .where(PrivateLibraryNumber.account_id == account.id)
        )
    ).scalar() or 0
    cnt_dn = (
        await db.execute(
            select(func.count())
            .select_from(DataNumber)
            .where(DataNumber.account_id == account.id)
        )
    ).scalar() or 0
    total_count_all = cnt_pln + cnt_dn
    try:
        cm_count = await get_cache_manager()
        ckey = _my_numbers_count_cache_key(account.id)
        await cm_count.set(ckey, total_count_all, ttl=_MY_NUMBERS_COUNT_CACHE_TTL)
    except Exception:
        pass

    batch_keys = None
    truncated_hint = False
    if max_batches > 0:

        def _batch_groups_stmt(model, lim: int):
            cc = func.coalesce(model.country_code, "")
            sc = func.coalesce(model.source, "")
            pc = func.coalesce(model.purpose, "")
            bid_group = func.coalesce(model.batch_id, "")
            return (
                select(
                    func.max(cc).label("c0"),
                    func.max(sc).label("c1"),
                    func.max(pc).label("c2"),
                    bid_group.label("c3"),
                    func.max(model.created_at).label("mx"),
                )
                .where(model.account_id == account.id)
                .group_by(bid_group)
                .order_by(func.max(model.created_at).desc())
                .limit(lim)
            )

        lim = max(max_batches * 2, max_batches)
        rp = (await db.execute(_batch_groups_stmt(PrivateLibraryNumber, lim))).fetchall()
        rd = (await db.execute(_batch_groups_stmt(DataNumber, lim))).fetchall()
        merged_keys: List[tuple] = []
        seen_k = set()
        for row in sorted(
            list(rp) + list(rd),
            key=lambda x: x.mx if x.mx is not None else datetime.min,
            reverse=True,
        ):
            tkey = (row.c0, row.c1, row.c2, row.c3)
            if tkey in seen_k:
                continue
            seen_k.add(tkey)
            merged_keys.append(tkey)
            if len(merged_keys) >= max_batches:
                break
        batch_keys = merged_keys
        truncated_hint = len(batch_keys) >= max_batches
        if not batch_keys:
            payload = {
                "success": True,
                "items": [],
                "total": total_count_all,
                "meta": {
                    "max_batches": max_batches,
                    "truncated": False,
                    "batch_card_limit": max_batches,
                },
            }
            try:
                cm = await get_cache_manager()
                await cm.set(cache_key, payload, ttl=_MY_NUMBERS_SUMMARY_CACHE_TTL)
            except Exception:
                pass
            return payload

    def _summary_carrier_stmt(model, keys):
        cc = func.coalesce(model.country_code, "")
        sc = func.coalesce(model.source, "")
        pc = func.coalesce(model.purpose, "")
        bc = func.coalesce(model.batch_id, "")
        sq = (
            select(
                cc.label("country_code"),
                sc.label("source"),
                pc.label("purpose"),
                bc.label("batch_id"),
                func.max(model.remarks).label("remarks"),
                model.carrier,
                func.count().label("group_count"),
                func.sum(case((model.use_count > 0, 1), else_=0)).label("used_count"),
                func.min(model.created_at).label("first_at"),
                func.max(model.created_at).label("last_at"),
            )
            .where(model.account_id == account.id)
        )
        if keys is not None:
            sq = sq.where(tuple_(cc, sc, pc, bc).in_(keys))
        return sq.group_by(cc, sc, pc, bc, model.carrier)

    summary_map: Dict[tuple, dict] = {}
    rows_pln = (await db.execute(_summary_carrier_stmt(PrivateLibraryNumber, batch_keys))).fetchall()
    rows_dn = (await db.execute(_summary_carrier_stmt(DataNumber, batch_keys))).fetchall()

    def _merge_summary_carrier_rows(rows, origin: str):
        """将按运营商拆分的汇总行并入 summary_map，并记录该分组是否含私库表/公海购入数据"""
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
                    "carriers": [],
                    "first_at": r.first_at,
                    "last_at": r.last_at,
                    "_origin_sources": set(),
                }

            group = summary_map[key]
            group["_origin_sources"].add(origin)
            group["count"] += r.group_count
            group["used_count"] += int(r.used_count or 0)
            group["unused_count"] = group["count"] - group["used_count"]

            if r.remarks:
                cur = group["remarks"]
                if cur is None or len(str(r.remarks)) > len(str(cur)):
                    group["remarks"] = r.remarks

            if r.first_at and (not group["first_at"] or r.first_at < group["first_at"]):
                group["first_at"] = r.first_at
            if r.last_at and (not group["last_at"] or r.last_at > group["last_at"]):
                group["last_at"] = r.last_at

            group["carriers"].append(
                {"name": r.carrier or "Unknown", "count": r.group_count}
            )

    _merge_summary_carrier_rows(rows_pln, "manual")
    _merge_summary_carrier_rows(rows_dn, "purchased")

    items = list(summary_map.values())
    for item in items:
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

    payload = {
        "success": True,
        "items": items,
        "total": total_count_all,
        "meta": {
            "max_batches": max_batches,
            "truncated": bool(truncated_hint) if max_batches > 0 else False,
            "batch_card_limit": max_batches if max_batches > 0 else None,
        },
    }
    try:
        cm = await get_cache_manager()
        await cm.set(cache_key, payload, ttl=_MY_NUMBERS_SUMMARY_CACHE_TTL)
    except Exception:
        pass
    return payload



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
    """批量删除：私库分表物理删除；公海购入绑定行解除 account_id 并置 inactive"""
    from sqlalchemy import or_

    def _filters_pln(q):
        if country:
            q = q.where(PrivateLibraryNumber.country_code == country)
        if source:
            q = q.where(PrivateLibraryNumber.source == source)
        if purpose:
            q = q.where(PrivateLibraryNumber.purpose == purpose)
        if batch_id:
            q = q.where(PrivateLibraryNumber.batch_id == batch_id)
        if remarks is not None:
            q = q.where(PrivateLibraryNumber.remarks == remarks)
        if carrier:
            q = q.where(PrivateLibraryNumber.carrier == carrier)
        elif carrier == "":
            q = q.where(
                or_(PrivateLibraryNumber.carrier.is_(None), PrivateLibraryNumber.carrier == "")
            )
        return q

    def _filters_dn(q):
        if country:
            q = q.where(DataNumber.country_code == country)
        if source:
            q = q.where(DataNumber.source == source)
        if purpose:
            q = q.where(DataNumber.purpose == purpose)
        if batch_id:
            q = q.where(DataNumber.batch_id == batch_id)
        if remarks is not None:
            q = q.where(DataNumber.remarks == remarks)
        if carrier:
            q = q.where(DataNumber.carrier == carrier)
        elif carrier == "":
            q = q.where(or_(DataNumber.carrier.is_(None), DataNumber.carrier == ""))
        return q

    stmt_pln = _filters_pln(sa_delete(PrivateLibraryNumber).where(PrivateLibraryNumber.account_id == account.id))
    r1 = await db.execute(stmt_pln)

    stmt_dn = _filters_dn(sa_update(DataNumber).where(DataNumber.account_id == account.id)).values(
        account_id=None, status="inactive"
    )
    r2 = await db.execute(stmt_dn)

    await db.commit()
    await _invalidate_my_numbers_summary_cache(account.id)
    n = (r1.rowcount or 0) + (r2.rowcount or 0)
    return {"success": True, "message": f"成功删除 {n} 条数据（含私库分表与公海绑定释放）"}


@router.get("/my-numbers/export")
async def export_my_numbers(
    fmt: str = Query("csv", regex="^(csv|txt)$"),
    country: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    batch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """导出我的私有库号码（私库分表 + 公海购入绑定行）"""
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
                    r["phone_number"],
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
                yield f"{r['phone_number']}\n"

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
    detect_carrier: bool = Form(False),
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
    text_content = _decode_my_numbers_upload_bytes(content)
    region_iso = (country_code or "").strip().upper() or None

    # 大文件解析放到线程池，避免长时间占用 asyncio 事件循环
    parse_threshold = 200_000
    if len(content) > parse_threshold:
        numbers_to_add = await asyncio.to_thread(
            _extract_phone_numbers_from_upload_text, fname, text_content, region_iso
        )
    else:
        numbers_to_add = _extract_phone_numbers_from_upload_text(fname, text_content, region_iso)

    if not numbers_to_add:
        raise HTTPException(
            400,
            "未检测到有效手机号码。请确认：已选择正确的国家/地区；TXT/CSV 中号码可被识别（支持带区号或本地号）；"
            "若为 GBK 编码请保存为 UTF-8 或使用 Excel 导出 CSV。",
        )

    # 去重（E.164）；仅写入私库表 private_library_numbers，与公海 data_numbers 无关
    unique_numbers = sorted(list(set(numbers_to_add)))

    existing_pln: Dict[str, int] = {}
    chunk_n = 800
    for i in range(0, len(unique_numbers), chunk_n):
        chunk = unique_numbers[i : i + chunk_n]
        variants: List[str] = []
        for n in chunk:
            variants.extend(_phone_db_lookup_keys(n))
        q = select(PrivateLibraryNumber.id, PrivateLibraryNumber.phone_number).where(
            PrivateLibraryNumber.account_id == account.id,
            PrivateLibraryNumber.phone_number.in_(variants),
        )
        res = await db.execute(q)
        for row in res.all():
            canon = (row.phone_number or "").lstrip("+")
            if canon not in existing_pln:
                existing_pln[canon] = row.id

    insert_dicts: List[dict] = []
    update_ids: List[int] = []

    batch_id = f"UP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now()

    if detect_carrier and len(unique_numbers) > 5_000:
        raise HTTPException(
            400,
            "号码超过 5000 条时请勿开启运营商识别；请取消勾选后重试，或分批上传。",
        )

    new_for_carrier: List[str] = [
        n for n in unique_numbers if n.lstrip("+") not in existing_pln
    ]
    carrier_map: Dict[str, Optional[str]] = {}
    if detect_carrier and new_for_carrier:
        carrier_map = await asyncio.to_thread(_batch_lookup_carriers, new_for_carrier)

    for num in unique_numbers:
        canon = num.lstrip("+")
        pln_id = existing_pln.get(canon)
        if pln_id is None:
            detected_carrier = carrier_map.get(num) if detect_carrier else None
            insert_dicts.append(
                {
                    "phone_number": num,
                    "country_code": country_code,
                    "source": source,
                    "purpose": purpose,
                    "remarks": remarks,
                    "account_id": account.id,
                    "status": "active",
                    "batch_id": batch_id,
                    "carrier": detected_carrier,
                    "tags": ["private_upload"],
                    "created_at": now,
                    "updated_at": now,
                }
            )
        else:
            update_ids.append(pln_id)

    if insert_dicts:
        from sqlalchemy import insert

        chunk_size = 5000
        for i in range(0, len(insert_dicts), chunk_size):
            await db.execute(insert(PrivateLibraryNumber), insert_dicts[i : i + chunk_size])

    if update_ids:
        from sqlalchemy import update

        chunk_size = 5000
        for i in range(0, len(update_ids), chunk_size):
            chunk_ids = update_ids[i : i + chunk_size]
            stmt = (
                update(PrivateLibraryNumber)
                .where(PrivateLibraryNumber.id.in_(chunk_ids))
                .values(
                    status="active",
                    batch_id=batch_id,
                    updated_at=now,
                )
            )
            if remarks is not None:
                stmt = stmt.values(remarks=remarks)
            await db.execute(stmt)

    await db.commit()
    await _invalidate_my_numbers_summary_cache(account.id)

    n_ins = len(insert_dicts)
    n_upd = len(update_ids)
    n_unique = len(unique_numbers)
    written = n_ins + n_upd

    return {
        "success": True,
        "message": f"成功上传 {n_ins} 条新数据，更新 {n_upd} 条已有私库记录（与公海分表存储，互不占用）",
        "total": n_unique,
        "added": written,
        "inserted": n_ins,
        "updated": n_upd,
        "skipped_other_account": 0,
        "duplicates": 0,
    }


# ============ 辅助 ============

async def _validate_purchase(data, db: AsyncSession):
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
        return product, product.filter_criteria, product.price_per_number

    if getattr(data, "filter_criteria", None):
        return None, data.filter_criteria, "0.001"

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
