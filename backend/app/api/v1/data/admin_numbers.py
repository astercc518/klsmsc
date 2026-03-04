"""管理员 - 号码管理 API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, or_
from typing import Optional
from datetime import datetime, timedelta, date
import uuid
import csv
import io
import re
import phonenumbers

from app.database import get_db
from app.modules.data.models import DataNumber, DataImportBatch, DataPricingTemplate, DATA_SOURCES, DATA_PURPOSES, SOURCE_LABELS, PURPOSE_LABELS
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

    import_batch = DataImportBatch(
        batch_id=batch_id, file_name=filename, source=source,
        status="pending", created_by=admin.id,
    )
    db.add(import_batch)
    await db.flush()
    await db.commit()

    tags_list = [t.strip() for t in default_tags.split(",")] if default_tags else None

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
