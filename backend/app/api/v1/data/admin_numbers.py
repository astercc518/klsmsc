"""管理员 - 号码管理 API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, or_, and_
from typing import Optional
from datetime import datetime, timedelta, date
import json
import uuid
import csv
import io
import re
import phonenumbers

from app.database import get_db
from app.modules.data.models import DataNumber, DataImportBatch, DataOrderNumber, DataProduct, DataPricingTemplate, DATA_SOURCES, DATA_PURPOSES, SOURCE_LABELS, PURPOSE_LABELS
from app.core.auth import get_current_admin
from app.utils.logger import get_logger
from app.schemas.data import NumberBatchTagRequest, NumberBatchStatusRequest
from app.api.v1.data.helpers import serialize_number, compute_freshness

logger = get_logger(__name__)
router = APIRouter()

HEADER_KEYWORDS = re.compile(
    r'(?i)^(phone|mobile|number|tel|手机|号码|电话|编号|序号|#|id|index)',
)
NON_DIGIT_RE = re.compile(r'[^\d+]')


def clean_phone_string(raw: str) -> Optional[str]:
    """清洗手机号字符串，去除无用字符，返回 None 表示应跳过"""
    s = raw.strip().strip('\ufeff').strip('\u200b').strip('"').strip("'")
    if not s:
        return None
    if HEADER_KEYWORDS.match(s):
        return None
    s = NON_DIGIT_RE.sub('', s)
    if not s:
        return None
    digits = s.lstrip('+')
    if len(digits) < 7 or len(digits) > 20:
        return None
    if not s.startswith('+'):
        s = '+' + s
    return s


@router.get("/numbers")
async def list_data_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    tag: Optional[str] = None,
    batch_id: Optional[str] = None,
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取号码资源池列表"""
    query = select(DataNumber)

    if country:
        query = query.where(DataNumber.country_code == country)
    if status:
        query = query.where(DataNumber.status == status)
    if source:
        query = query.where(DataNumber.source == source)
    if purpose:
        query = query.where(DataNumber.purpose == purpose)
    if tag:
        query = query.where(DataNumber.tags.contains([tag]))
    if batch_id:
        query = query.where(DataNumber.batch_id == batch_id)
    if account_id:
        query = query.where(DataNumber.account_id == account_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(DataNumber.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    numbers = result.scalars().all()

    return {
        "success": True,
        "items": [serialize_number(n) for n in numbers],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/numbers/stats")
async def get_number_stats(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取号码资源统计（含来源/用途维度）"""
    country_stats = await db.execute(
        select(DataNumber.country_code, func.count(DataNumber.id)).group_by(DataNumber.country_code)
    )
    country_data = {row[0]: row[1] for row in country_stats.fetchall()}

    status_stats = await db.execute(
        select(DataNumber.status, func.count(DataNumber.id)).group_by(DataNumber.status)
    )
    status_data = {row[0]: row[1] for row in status_stats.fetchall()}

    source_stats = await db.execute(
        select(DataNumber.source, func.count(DataNumber.id)).where(DataNumber.source.isnot(None)).group_by(DataNumber.source)
    )
    source_data = {row[0]: row[1] for row in source_stats.fetchall()}

    purpose_stats = await db.execute(
        select(DataNumber.purpose, func.count(DataNumber.id)).where(DataNumber.purpose.isnot(None)).group_by(DataNumber.purpose)
    )
    purpose_data = {row[0]: row[1] for row in purpose_stats.fetchall()}

    total = await db.execute(select(func.count(DataNumber.id)))

    return {
        "success": True,
        "total": total.scalar() or 0,
        "by_country": country_data,
        "by_status": status_data,
        "by_source": {k: {"count": v, "label": SOURCE_LABELS.get(k, k)} for k, v in source_data.items()},
        "by_purpose": {k: {"count": v, "label": PURPOSE_LABELS.get(k, k)} for k, v in purpose_data.items()},
    }


@router.post("/numbers/import")
async def import_numbers(
    file: UploadFile = File(...),
    source: str = Query(..., description="来源"),
    purpose: str = Query(..., description="用途"),
    country_code: Optional[str] = Query(None, description="国家ISO代码(如VN,BR)，用于解析本地号码格式"),
    data_date: Optional[str] = Query(None, description="数据采集日期(YYYY-MM-DD)"),
    pricing_template_id: Optional[int] = Query(None, description="关联定价模板ID"),
    default_tags: Optional[str] = Query(None, description="默认标签，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """提交导入任务（异步），立即返回 batch_id，后台 Worker 处理"""
    if source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail=f"无效来源: {source}")
    if purpose not in DATA_PURPOSES:
        raise HTTPException(status_code=400, detail=f"无效用途: {purpose}")

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "txt"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 和 TXT 格式文件")

    if data_date:
        try:
            date.fromisoformat(data_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD")

    import os, tempfile
    MAX_SIZE = 500 * 1024 * 1024
    upload_dir = "/tmp/smsc_imports"
    os.makedirs(upload_dir, exist_ok=True)

    batch_id = f"IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    file_path = os.path.join(upload_dir, f"{batch_id}.{ext}")

    file_size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(4 * 1024 * 1024)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > MAX_SIZE:
                os.remove(file_path)
                raise HTTPException(status_code=413, detail="文件大小超过限制(最大500MB)")
            f.write(chunk)

    tags_list = [t.strip() for t in default_tags.split(",")] if default_tags else None

    import_batch = DataImportBatch(
        batch_id=batch_id, file_name=filename, source=source,
        status="pending", created_by=admin.id,
        purpose=purpose,
        data_date_str=data_date or date.today().isoformat(),
        pricing_template_id=pricing_template_id,
        default_tags_json=json.dumps(tags_list, ensure_ascii=False) if tags_list else None,
        country_code=country_code,
    )
    db.add(import_batch)
    await db.flush()
    await db.commit()

    from app.workers.celery_app import celery_app as _celery
    _celery.send_task('data_import_numbers', args=[
        batch_id, file_path, ext, source, purpose,
        data_date or date.today().isoformat(),
        pricing_template_id, tags_list,
        country_code,
    ], queue='data_tasks')

    logger.info(f"[{batch_id}] 导入任务已提交: {filename} ({file_size/1024/1024:.1f}MB)")

    return {
        "success": True,
        "batch_id": batch_id,
        "file_name": filename,
        "file_size_mb": round(file_size / 1024 / 1024, 2),
        "status": "pending",
        "message": "导入任务已提交，可在任务列表查看进度",
    }


@router.get("/numbers/import-progress/{batch_id}")
async def get_import_progress(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """查询导入任务实时进度"""
    import json as _json
    from app.utils.cache import get_redis_client

    redis_client = await get_redis_client()
    key = f"import_progress:{batch_id}"
    data = await redis_client.get(key)
    if data:
        progress = _json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        return {"success": True, "batch_id": batch_id, **progress}

    result = await db.execute(
        select(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "success": True,
        "batch_id": batch_id,
        "status": batch.status,
        "phase": "已完成" if batch.status == "completed" else ("失败" if batch.status == "failed" else "等待中"),
        "total_count": batch.total_count or 0,
        "valid_count": batch.valid_count or 0,
        "duplicate_count": batch.duplicate_count or 0,
        "invalid_count": batch.invalid_count or 0,
        "progress_pct": 100 if batch.status == "completed" else 0,
    }


@router.post("/numbers/import-retry/{batch_id}")
async def retry_import(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """重新提交卡住的导入任务（pending/failed 可重试），无需重新上传文件"""
    import os
    upload_dir = "/tmp/smsc_imports"

    result = await db.execute(
        select(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="任务不存在")

    if batch.status not in ("pending", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"仅支持对「等待中」或「失败」任务重试，当前状态: {batch.status}",
        )

    filename = batch.file_name or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext not in ("csv", "txt"):
        ext = "txt"

    file_path = os.path.join(upload_dir, f"{batch_id}.{ext}")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="导入文件已不存在，请重新上传")

    purpose = batch.purpose or DATA_PURPOSES[0]
    data_date_str = batch.data_date_str or date.today().isoformat()
    tags_list = json.loads(batch.default_tags_json) if batch.default_tags_json else None

    if batch.status == "failed":
        batch.error_message = None
        batch.status = "pending"

    await db.commit()

    from app.workers.celery_app import celery_app as _celery
    _celery.send_task(
        "data_import_numbers",
        args=[
            batch_id,
            file_path,
            ext,
            batch.source,
            purpose,
            data_date_str,
            batch.pricing_template_id,
            tags_list,
            batch.country_code,
        ],
        queue="data_tasks",
    )

    logger.info(f"[{batch_id}] 导入任务已重新提交（重试）")

    return {
        "success": True,
        "batch_id": batch_id,
        "message": "已重新提交到处理队列，请刷新查看进度",
    }


@router.post("/numbers/import-supplement-product/{batch_id}")
async def supplement_product_for_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """为已完成但未创建商品的导入批次补充创建商品（0 写入 + 有重复时）"""
    from app.api.v1.data.helpers import calculate_stock
    from app.modules.data.models import DataPricingTemplate, DataProduct
    from app.workers.data_worker import _auto_create_product, _to_iso

    result = await db.execute(
        select(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="任务不存在")
    if batch.status != "completed":
        raise HTTPException(status_code=400, detail="仅支持已完成的任务")
    if batch.valid_count > 0:
        raise HTTPException(status_code=400, detail="该任务已有写入，应已有商品")

    if not batch.duplicate_count or batch.duplicate_count <= 0:
        raise HTTPException(status_code=400, detail="无重复数据，无法补充商品")

    source, purpose = batch.source, batch.purpose or "stock"
    data_date_str = batch.data_date_str or date.today().isoformat()
    parsed_date = date.fromisoformat(data_date_str) if data_date_str else date.today()
    freshness = compute_freshness(parsed_date)
    effective_country = (batch.country_code or "").upper() if batch.country_code else None
    matched_tpl_id = batch.pricing_template_id

    if not matched_tpl_id:
        tpl_result = await db.execute(
            select(DataPricingTemplate.id).where(
                DataPricingTemplate.source == source,
                DataPricingTemplate.purpose == purpose,
                DataPricingTemplate.freshness == freshness,
                DataPricingTemplate.status == "active",
            ).limit(1)
        )
        matched_tpl_id = tpl_result.scalar_one_or_none()
    if not matched_tpl_id:
        tpl_result = await db.execute(
            select(DataPricingTemplate.id).where(
                DataPricingTemplate.source == source,
                DataPricingTemplate.purpose == purpose,
                DataPricingTemplate.status == "active",
            ).limit(1)
        )
        matched_tpl_id = tpl_result.scalar_one_or_none()

    if not matched_tpl_id:
        raise HTTPException(status_code=400, detail="未找到匹配的定价模板")

    tpl_row = await db.execute(
        select(DataPricingTemplate).where(DataPricingTemplate.id == matched_tpl_id)
    )
    tpl = tpl_row.scalar_one_or_none()
    if tpl and not effective_country:
        if tpl.country_code and tpl.country_code != "*":
            effective_country = _to_iso(tpl.country_code)
        elif batch.country_code:
            effective_country = (batch.country_code or "").upper()

    if not effective_country:
        raise HTTPException(status_code=400, detail="无法确定国家，请检查批次或模板")

    fc = {"source": source, "purpose": purpose, "freshness": freshness, "country": effective_country}
    stock = await calculate_stock(db, fc, public_only=True)

    # 若已有同条件商品则不再创建
    exist_q = select(DataProduct).where(
        DataProduct.is_deleted == False,
        DataProduct.filter_criteria.isnot(None),
        func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.country")) == effective_country,
        func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.source")) == source,
        func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.purpose")) == purpose,
        func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.freshness")) == freshness,
    )
    existing = (await db.execute(exist_q)).scalars().first()
    if existing:
        # 刷新库存
        existing.stock_count = stock
        if stock > 0 and existing.status == "sold_out":
            existing.status = "active"
        elif stock == 0 and existing.status == "active":
            existing.status = "sold_out"
        existing.max_purchase = max(stock, 100000)
        await db.commit()
        return {"success": True, "product_code": existing.product_code, "stock_count": stock, "message": "已刷新现有商品库存"}

    product_code = await _auto_create_product(
        db, source, purpose, freshness,
        country_code=effective_country, matched_tpl_id=matched_tpl_id,
        batch_id=batch_id, valid_count=stock,
        file_name=batch.file_name,
    )

    return {"success": True, "product_code": product_code, "stock_count": stock, "message": "商品已补充"}


@router.get("/import-batches")
async def list_import_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取导入批次列表"""
    query = select(DataImportBatch).order_by(DataImportBatch.created_at.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    batches = result.scalars().all()

    return {
        "success": True,
        "items": [
            {
                "id": b.id,
                "batch_id": b.batch_id,
                "file_name": b.file_name,
                "source": b.source,
                "total_count": b.total_count,
                "valid_count": b.valid_count,
                "duplicate_count": b.duplicate_count,
                "invalid_count": b.invalid_count,
                "cleaned_count": getattr(b, 'cleaned_count', 0) or 0,
                "file_dedup_count": getattr(b, 'file_dedup_count', 0) or 0,
                "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            }
            for b in batches
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/import-batches/{batch_id}")
async def delete_import_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """删除导入任务记录（同时删除该批次的号码数据，已售出号码保留）"""
    # 先删未被订单引用的号码
    used_subq = select(DataOrderNumber.number_id).distinct()
    stmt = delete(DataNumber).where(
        DataNumber.batch_id == batch_id,
        DataNumber.id.not_in(used_subq),
    )
    result = await db.execute(stmt)
    deleted_numbers = result.rowcount
    # 再删任务记录
    del_stmt = delete(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
    r = await db.execute(del_stmt)
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    logger.info(f"删除导入任务: {batch_id}, 同时删除{deleted_numbers}条号码")
    return {"success": True, "deleted_numbers": deleted_numbers, "message": f"任务已删除，同时删除 {deleted_numbers} 条号码"}


@router.post("/clear-all")
async def clear_all_data(
    confirm: str = Query(..., description="必须传入 confirm=RESET_ALL 才会执行"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """清空所有导入任务、号码数据、数据商品（危险操作，慎用）"""
    if confirm != "RESET_ALL":
        raise HTTPException(status_code=400, detail="必须传入 confirm=RESET_ALL 确认执行")

    # 1. 删除订单-号码关联（解除外键）
    r1 = await db.execute(delete(DataOrderNumber))
    deleted_order_numbers = r1.rowcount
    # 2. 删除所有号码
    r2 = await db.execute(delete(DataNumber))
    deleted_numbers = r2.rowcount
    # 3. 删除所有导入任务
    r3 = await db.execute(delete(DataImportBatch))
    deleted_batches = r3.rowcount
    # 4. 软删除所有数据商品
    r4 = await db.execute(update(DataProduct).where(or_(DataProduct.is_deleted == False, DataProduct.is_deleted.is_(None))).values(is_deleted=True))
    deleted_products = r4.rowcount
    await db.commit()

    logger.warning(f"清空全部: 订单关联{deleted_order_numbers}条, 号码{deleted_numbers}条, 任务{deleted_batches}个, 商品{deleted_products}个")
    return {
        "success": True,
        "deleted_order_numbers": deleted_order_numbers,
        "deleted_numbers": deleted_numbers,
        "deleted_batches": deleted_batches,
        "deleted_products": deleted_products,
        "message": f"已清空: {deleted_numbers} 条号码, {deleted_batches} 个任务, {deleted_products} 个商品",
    }


# ============ 批量操作 ============

@router.post("/numbers/batch-tag")
async def batch_tag_numbers(
    data: NumberBatchTagRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """批量打标签"""
    result = await db.execute(
        select(DataNumber).where(DataNumber.id.in_(data.number_ids))
    )
    numbers = result.scalars().all()

    if not numbers:
        raise HTTPException(status_code=404, detail="未找到指定号码")

    updated = 0
    for num in numbers:
        if data.mode == "replace":
            num.tags = data.tags
        else:
            existing = num.tags or []
            num.tags = list(set(existing + data.tags))
        updated += 1

    await db.commit()
    return {"success": True, "updated": updated}


@router.delete("/numbers/by-batch/{batch_id}")
async def delete_numbers_by_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """按导入任务（批次）删除号码数据。已售出号码保留。"""
    used_subq = select(DataOrderNumber.number_id).distinct()
    stmt = delete(DataNumber).where(
        DataNumber.batch_id == batch_id,
        DataNumber.id.not_in(used_subq),
    )
    result = await db.execute(stmt)
    await db.commit()
    deleted = result.rowcount
    logger.info(f"按批次删除: {batch_id}, 删除{deleted}条")
    return {"success": True, "deleted": deleted, "message": f"已删除批次 {batch_id} 的 {deleted} 条号码"}


@router.delete("/numbers/by-country/{country_code}")
async def delete_numbers_by_country(
    country_code: str,
    source: Optional[str] = Query(None, description="仅删除指定来源，不传则删除该国全部"),
    purpose: Optional[str] = Query(None, description="仅删除指定用途，不传则全部"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """按国家删除号码数据（可指定来源/用途）。已售出号码保留不删，避免订单关联断裂。"""
    cc = country_code.upper()
    conditions = [DataNumber.country_code == cc]
    if source:
        conditions.append(DataNumber.source == source)
    if purpose:
        conditions.append(DataNumber.purpose == purpose)

    # 仅删除未被订单引用的号码（避免 DataOrderNumber.number_id 外键约束报错）
    used_subq = select(DataOrderNumber.number_id).distinct()
    conditions.append(DataNumber.id.not_in(used_subq))

    # 先查可删除数量
    count_q = select(func.count()).select_from(DataNumber).where(and_(*conditions))
    cnt = (await db.execute(count_q)).scalar() or 0
    if cnt == 0:
        # 检查是否有匹配但已售出的
        total_conditions = [DataNumber.country_code == cc]
        if source:
            total_conditions.append(DataNumber.source == source)
        if purpose:
            total_conditions.append(DataNumber.purpose == purpose)
        total_q = select(func.count()).select_from(DataNumber).where(and_(*total_conditions))
        total = (await db.execute(total_q)).scalar() or 0
        if total > 0:
            return {"success": True, "deleted": 0, "message": f"该国 {total} 条号码均已售出，无法删除"}
        return {"success": True, "deleted": 0, "message": "无匹配数据"}

    stmt = delete(DataNumber).where(and_(*conditions))
    result = await db.execute(stmt)
    await db.commit()
    deleted = result.rowcount

    logger.info(f"按国家删除: {cc}" + (f" source={source}" if source else "") + (f" purpose={purpose}" if purpose else "") + f", 删除{deleted}条")
    return {"success": True, "deleted": deleted, "message": f"已删除 {deleted} 条{cc}号码"}


@router.post("/numbers/batch-update-source")
async def batch_update_source(
    country_code: str = Query(..., description="国家代码如 US"),
    old_source: str = Query(..., description="当前来源"),
    new_source: str = Query(..., description="新来源"),
    purpose: Optional[str] = Query(None, description="用途，不传则全部"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """批量将指定条件的号码来源更新为新来源（用于将社工库等划入电销等商品）"""
    if new_source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail=f"无效来源: {new_source}")

    conditions = [
        DataNumber.country_code == country_code.upper(),
        DataNumber.source == old_source,
    ]
    if purpose:
        conditions.append(DataNumber.purpose == purpose)
    stmt = update(DataNumber).where(and_(*conditions)).values(source=new_source)
    result = await db.execute(stmt)
    await db.commit()
    updated = result.rowcount

    logger.info(f"批量更新来源: {country_code} {old_source}->{new_source}, 更新{updated}条")
    return {"success": True, "updated": updated, "message": f"已更新 {updated} 条号码来源"}


@router.post("/numbers/batch-status")
async def batch_update_status(
    data: NumberBatchStatusRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """批量修改状态"""
    if data.status not in ("active", "inactive", "blacklisted"):
        raise HTTPException(status_code=400, detail="无效状态")

    result = await db.execute(
        select(DataNumber).where(DataNumber.id.in_(data.number_ids))
    )
    numbers = result.scalars().all()

    updated = 0
    for num in numbers:
        num.status = data.status
        updated += 1

    await db.commit()
    return {"success": True, "updated": updated}


@router.get("/numbers/export")
async def export_numbers(
    country: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    batch_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """导出号码为 CSV"""
    query = select(DataNumber)
    if country:
        query = query.where(DataNumber.country_code == country)
    if status:
        query = query.where(DataNumber.status == status)
    if tag:
        query = query.where(DataNumber.tags.contains([tag]))
    if batch_id:
        query = query.where(DataNumber.batch_id == batch_id)

    query = query.order_by(DataNumber.id)
    result = await db.execute(query)
    numbers = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["phone_number", "country_code", "carrier", "tags", "status", "source", "use_count"])
    for n in numbers:
        writer.writerow([
            n.phone_number,
            n.country_code,
            n.carrier or "",
            "|".join(n.tags) if n.tags else "",
            n.status,
            n.source or "",
            n.use_count or 0,
        ])

    output.seek(0)
    filename = f"numbers_export_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ 清洗操作 ============

@router.post("/numbers/clean/dedup")
async def dedup_numbers(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """去重：标记重复号码为 inactive"""
    from sqlalchemy import text

    subq = select(
        DataNumber.phone_number,
        func.min(DataNumber.id).label("keep_id"),
    ).group_by(DataNumber.phone_number).having(func.count(DataNumber.id) > 1).subquery()

    dup_numbers = await db.execute(select(subq.c.phone_number, subq.c.keep_id))
    rows = dup_numbers.fetchall()

    dedup_count = 0
    for phone, keep_id in rows:
        res = await db.execute(
            select(DataNumber).where(
                DataNumber.phone_number == phone, DataNumber.id != keep_id
            )
        )
        dups = res.scalars().all()
        for d in dups:
            d.status = "inactive"
            dedup_count += 1

    await db.commit()
    return {"success": True, "dedup_count": dedup_count, "groups": len(rows)}


@router.post("/numbers/clean/blacklist")
async def upload_blacklist(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """上传黑名单文件，批量标记为 blacklisted"""
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.reader(io.StringIO(text))

    blacklisted = 0
    not_found = 0
    for row in reader:
        if not row or not row[0].strip():
            continue
        phone = row[0].strip()
        if not phone.startswith("+"):
            phone = "+" + phone

        result = await db.execute(
            select(DataNumber).where(DataNumber.phone_number == phone)
        )
        num = result.scalar_one_or_none()
        if num:
            num.status = "blacklisted"
            blacklisted += 1
        else:
            not_found += 1

    await db.commit()
    return {"success": True, "blacklisted": blacklisted, "not_found": not_found}


@router.post("/numbers/clean/recycle")
async def recycle_expired_numbers(
    days: int = Query(90, description="超过N天未使用的私库号码释放回公海"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """回收过期私库号码"""
    cutoff = datetime.now() - timedelta(days=days)
    result = await db.execute(
        select(DataNumber).where(
            DataNumber.account_id.isnot(None),
            or_(DataNumber.last_used_at.is_(None), DataNumber.last_used_at < cutoff),
        )
    )
    numbers = result.scalars().all()

    recycled = 0
    for num in numbers:
        num.account_id = None
        recycled += 1

    await db.commit()
    return {"success": True, "recycled": recycled}


@router.post("/numbers/backfill-carriers")
async def trigger_backfill_carriers(
    admin=Depends(get_current_admin),
):
    """触发回填存量号码的运营商信息（异步任务）"""
    from app.workers.celery_app import celery_app as _celery
    _celery.send_task('data_backfill_carriers', args=[5000, 0], queue='data_tasks')
    return {"success": True, "message": "运营商回填任务已提交，后台处理中"}
