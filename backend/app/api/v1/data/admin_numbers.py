"""管理员 - 号码管理 API"""
import fcntl
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, or_, and_
from sqlalchemy.exc import DBAPIError
from typing import Optional
from datetime import datetime, timedelta, date
import json
import uuid
import csv
import io
import re
import phonenumbers

from app.database import get_db
from app.modules.data.models import (
    DataNumber,
    DataImportBatch,
    DataOrderNumber,
    DataProduct,
    DataPricingTemplate,
    PrivateLibraryNumber,
    PrivateLibrarySummary,
    DATA_SOURCES,
    DATA_PURPOSES,
    SOURCE_LABELS,
    PURPOSE_LABELS,
)
from app.modules.common.account import Account
from app.core.auth import get_current_admin
from app.utils.logger import get_logger
from app.utils.phone_utils import export_phone_plain_digits
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


@router.post("/numbers/import-raw")
async def import_numbers_raw(
    request: Request,
    source: str = Query(..., description="来源"),
    purpose: str = Query(..., description="用途"),
    filename: str = Query(..., description="文件名，如 data.txt"),
    country_code: Optional[str] = Query(None),
    force_country: bool = Query(False),
    data_date: Optional[str] = Query(None),
    pricing_template_id: Optional[int] = Query(None),
    default_tags: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """原始二进制上传，绕过 multipart 解析限制，适用于大文件(>50MB)。请求体直接为文件字节流。"""
    if source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail=f"无效来源: {source}")
    if purpose not in DATA_PURPOSES:
        raise HTTPException(status_code=400, detail=f"无效用途: {purpose}")

    fn = (filename or "").strip() or "data.txt"
    ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else "txt"
    if ext not in ("csv", "txt"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 和 TXT 格式")
    if data_date:
        try:
            date.fromisoformat(data_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误")

    MAX_SIZE = 500 * 1024 * 1024
    upload_dir = "/tmp/smsc_imports"
    os.makedirs(upload_dir, exist_ok=True)
    batch_id = f"IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    file_path = os.path.join(upload_dir, f"{batch_id}.{ext}")

    file_size = 0
    try:
        with open(file_path, "wb") as f:
            async for chunk in request.stream():
                file_size += len(chunk)
                if file_size > MAX_SIZE:
                    os.remove(file_path)
                    raise HTTPException(status_code=413, detail="文件大小超过限制(最大500MB)")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        logger.exception(f"原始上传写入失败: {e}")
        raise HTTPException(status_code=500, detail="文件写入失败")

    tags_list = [t.strip() for t in (default_tags or "").split(",")] if default_tags else None
    import_batch = DataImportBatch(
        batch_id=batch_id, file_name=fn, source=source, status="pending", created_by=admin.id,
        purpose=purpose, data_date_str=data_date or date.today().isoformat(),
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
        pricing_template_id, tags_list, country_code, force_country,
    ], queue='data_tasks')
    logger.info(f"[{batch_id}] 原始上传已提交: {fn} ({file_size/1024/1024:.1f}MB)")
    return {
        "success": True, "batch_id": batch_id, "file_name": fn,
        "file_size_mb": round(file_size / 1024 / 1024, 2), "status": "pending",
        "message": "导入任务已提交，可在任务列表查看进度",
    }


# 分块上传：每块短连接，避免浏览器经 CDN 的 HTTP/2 长传时出现 net::ERR_HTTP2_PING_FAILED
IMPORT_CHUNK_MAX = 4 * 1024 * 1024  # 单块最大 4MB
IMPORT_TOTAL_MAX = 500 * 1024 * 1024


class ImportRawSessionBody(BaseModel):
    """创建分块上传会话的请求体"""
    source: str
    purpose: str
    filename: str
    country_code: Optional[str] = None
    force_country: bool = False
    data_date: Optional[str] = None
    pricing_template_id: Optional[int] = None
    default_tags: Optional[str] = None


def _import_raw_session_paths(session_id: str) -> tuple[str, str]:
    upload_dir = "/tmp/smsc_imports"
    os.makedirs(upload_dir, exist_ok=True)
    base = os.path.join(upload_dir, f"SES-{session_id}")
    return base + ".meta.json", base + ".data"


def _validate_import_raw_meta(source: str, purpose: str, fn: str, data_date: Optional[str]) -> tuple[str, str]:
    if source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail=f"无效来源: {source}")
    if purpose not in DATA_PURPOSES:
        raise HTTPException(status_code=400, detail=f"无效用途: {purpose}")
    name = (fn or "").strip() or "data.txt"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "txt"
    if ext not in ("csv", "txt"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 和 TXT 格式")
    if data_date:
        try:
            date.fromisoformat(data_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误")
    return name, ext


@router.post("/numbers/import-raw/session")
async def import_raw_session_create(
    body: ImportRawSessionBody,
    admin=Depends(get_current_admin),
):
    """创建分块上传会话，前端按 chunk_size 分片 PUT 上传，最后 POST complete。"""
    fn, ext = _validate_import_raw_meta(body.source, body.purpose, body.filename, body.data_date)
    session_id = uuid.uuid4().hex
    meta_path, data_path = _import_raw_session_paths(session_id)
    meta = {
        "source": body.source,
        "purpose": body.purpose,
        "filename": fn,
        "country_code": body.country_code,
        "force_country": body.force_country,
        "data_date": body.data_date,
        "pricing_template_id": body.pricing_template_id,
        "default_tags": body.default_tags,
        "ext": ext,
        "admin_id": admin.id,
        "next_index": 0,
        "total_bytes": 0,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    open(data_path, "wb").close()
    return {
        "success": True,
        "session_id": session_id,
        "chunk_size": IMPORT_CHUNK_MAX,
        "message": "请按序号上传分块后调用 complete",
    }


@router.put("/numbers/import-raw/session/{session_id}/chunk")
async def import_raw_session_chunk(
    session_id: str,
    request: Request,
    index: int = Query(..., ge=0, description="分块序号，从 0 递增"),
    admin=Depends(get_current_admin),
):
    """上传一个分块（请求体为原始字节，单块不超过 chunk_size）。"""
    if not session_id or len(session_id) != 32 or not all(c in "0123456789abcdef" for c in session_id):
        raise HTTPException(status_code=400, detail="无效的 session_id")
    meta_path, data_path = _import_raw_session_paths(session_id)
    if not os.path.isfile(meta_path):
        raise HTTPException(status_code=404, detail="会话不存在或已结束")

    body = await request.body()
    if len(body) > IMPORT_CHUNK_MAX:
        raise HTTPException(status_code=413, detail=f"单块超过限制（最大 {IMPORT_CHUNK_MAX // (1024 * 1024)}MB）")
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="空分块无效")

    with open(meta_path, "r+", encoding="utf-8") as mf:
        fcntl.flock(mf, fcntl.LOCK_EX)
        try:
            mf.seek(0)
            raw = mf.read()
            meta = json.loads(raw) if raw else {}
            if meta.get("admin_id") != admin.id:
                raise HTTPException(status_code=403, detail="无权操作此会话")
            if index != meta.get("next_index", 0):
                raise HTTPException(
                    status_code=400,
                    detail=f"分块序号错误：期望 {meta.get('next_index', 0)}，收到 {index}",
                )
            new_total = meta.get("total_bytes", 0) + len(body)
            if new_total > IMPORT_TOTAL_MAX:
                raise HTTPException(status_code=413, detail="文件大小超过限制(最大500MB)")
            with open(data_path, "ab") as df:
                df.write(body)
            meta["next_index"] = meta.get("next_index", 0) + 1
            meta["total_bytes"] = new_total
            mf.seek(0)
            mf.truncate()
            json.dump(meta, mf, ensure_ascii=False)
            mf.flush()
        finally:
            fcntl.flock(mf, fcntl.LOCK_UN)

    return {"success": True, "index": index, "total_bytes": meta["total_bytes"]}


@router.post("/numbers/import-raw/session/{session_id}/complete")
async def import_raw_session_complete(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """完成分块上传，创建导入任务（与单次 import-raw 相同）。"""
    if not session_id or len(session_id) != 32 or not all(c in "0123456789abcdef" for c in session_id):
        raise HTTPException(status_code=400, detail="无效的 session_id")
    meta_path, data_path = _import_raw_session_paths(session_id)
    if not os.path.isfile(meta_path) or not os.path.isfile(data_path):
        raise HTTPException(status_code=404, detail="会话不存在或已结束")

    batch_id = f"IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    upload_dir = "/tmp/smsc_imports"
    total_bytes = 0

    with open(meta_path, "r+", encoding="utf-8") as mf:
        fcntl.flock(mf, fcntl.LOCK_EX)
        try:
            mf.seek(0)
            meta = json.load(mf)
            if meta.get("admin_id") != admin.id:
                raise HTTPException(status_code=403, detail="无权操作此会话")
            total_bytes = meta.get("total_bytes", 0)
            if total_bytes <= 0:
                raise HTTPException(status_code=400, detail="未上传任何数据")

            fn = meta["filename"]
            ext = meta["ext"]
            source = meta["source"]
            purpose = meta["purpose"]
            country_code = meta.get("country_code")
            force_country = bool(meta.get("force_country"))
            data_date = meta.get("data_date")
            pricing_template_id = meta.get("pricing_template_id")
            default_tags = meta.get("default_tags")

            final_path = os.path.join(upload_dir, f"{batch_id}.{ext}")
            try:
                os.replace(data_path, final_path)
            except OSError as e:
                logger.exception(f"分块上传收尾移动文件失败: {e}")
                raise HTTPException(status_code=500, detail="文件处理失败")
            try:
                os.remove(meta_path)
            except OSError:
                pass
        finally:
            fcntl.flock(mf, fcntl.LOCK_UN)

    tags_list = [t.strip() for t in (default_tags or "").split(",")] if default_tags else None
    import_batch = DataImportBatch(
        batch_id=batch_id, file_name=fn, source=source, status="pending", created_by=admin.id,
        purpose=purpose, data_date_str=data_date or date.today().isoformat(),
        pricing_template_id=pricing_template_id,
        default_tags_json=json.dumps(tags_list, ensure_ascii=False) if tags_list else None,
        country_code=country_code,
    )
    db.add(import_batch)
    await db.flush()
    await db.commit()

    from app.workers.celery_app import celery_app as _celery
    _celery.send_task('data_import_numbers', args=[
        batch_id, final_path, ext, source, purpose,
        data_date or date.today().isoformat(),
        pricing_template_id, tags_list, country_code, force_country,
    ], queue='data_tasks')
    logger.info(f"[{batch_id}] 分块上传已提交: {fn} ({total_bytes/1024/1024:.1f}MB)")
    return {
        "success": True, "batch_id": batch_id, "file_name": fn,
        "file_size_mb": round(total_bytes / 1024 / 1024, 2), "status": "pending",
        "message": "导入任务已提交，可在任务列表查看进度",
    }


@router.post("/numbers/import")
async def import_numbers(
    request: Request,
    source: str = Query(..., description="来源"),
    purpose: str = Query(..., description="用途"),
    country_code: Optional[str] = Query(None, description="国家ISO代码(如US,VN)，用于解析本地号码格式及商品创建"),
    force_country: bool = Query(False, description="强制使用选定国家：所有号码统一标为该国，不再按区号细分(如+1下的美/加/波多黎各)"),
    data_date: Optional[str] = Query(None, description="数据采集日期(YYYY-MM-DD)"),
    pricing_template_id: Optional[int] = Query(None, description="关联定价模板ID"),
    default_tags: Optional[str] = Query(None, description="默认标签，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """提交导入任务（异步），multipart 上传。大文件(>50MB)建议用 /numbers/import-raw。"""
    if source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail=f"无效来源: {source}")
    if purpose not in DATA_PURPOSES:
        raise HTTPException(status_code=400, detail=f"无效用途: {purpose}")

    try:
        form = await request.form(max_part_size=500 * 1024 * 1024)
    except TypeError:
        form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        raise HTTPException(status_code=400, detail="请上传文件，表单字段名为 file")

    filename = getattr(file, "filename", "") or ""
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
        country_code, force_country,
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
            False,  # force_country（重试不强制）
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
    """删除导入任务记录（同时删除该批次的号码数据，已售出号码保留）。支持任意状态（含等待中、处理中）"""
    import os
    upload_dir = "/tmp/smsc_imports"
    try:
        # 先查批次状态，用于后续清理导入文件
        batch_result = await db.execute(
            select(DataImportBatch).where(DataImportBatch.batch_id == batch_id)
        )
        batch = batch_result.scalar_one_or_none()
        if not batch:
            raise HTTPException(status_code=404, detail="导入任务不存在")

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

        # 等待中/处理中任务：删除上传文件，避免 Worker 后续处理时使用
        if batch.status in ("pending", "processing"):
            for ext in ("csv", "txt"):
                fp = os.path.join(upload_dir, f"{batch_id}.{ext}")
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                    except OSError:
                        pass

        logger.info(f"删除导入任务: {batch_id}, 同时删除{deleted_numbers}条号码")
        return {"success": True, "deleted_numbers": deleted_numbers, "message": f"任务已删除，同时删除 {deleted_numbers} 条号码"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"删除导入任务失败: {batch_id}")
        raise HTTPException(status_code=500, detail=str(e))


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
            export_phone_plain_digits(n.phone_number),
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


def _private_library_db_error_text(exc: BaseException) -> str:
    """提取底层驱动错误文案，便于判断是否为缺列（未迁移）"""
    if isinstance(exc, DBAPIError):
        if exc.orig is not None:
            return str(exc.orig)
        return str(exc)
    return str(exc)


def _raise_if_private_library_schema_mismatch(exc: BaseException) -> None:
    """私库表缺 is_deleted 等字段时给出明确提示（否则 ORM 查询会 500）"""
    raw = _private_library_db_error_text(exc)
    if (
        "is_deleted" in raw
        or "Unknown column" in raw
        or "1054" in raw  # MySQL ER_BAD_FIELD_ERROR
    ):
        logger.error("私库管理接口数据库错误（多为未执行 Alembic 迁移）: %s", raw)
        raise HTTPException(
            status_code=503,
            detail=(
                "数据库表结构与代码不一致：请执行迁移 revision j2k3l4m5n6o7（private_library_numbers.is_deleted）。"
                "在 backend 目录执行: alembic upgrade head；"
                "Docker 部署请重新构建 api 镜像，启动时会自动执行 alembic upgrade head。"
            ),
        ) from exc
    raise exc


@router.get("/private-library-summary")
async def admin_get_private_library_summary(
    max_batches: int = Query(
        0,
        ge=0,
        le=10000,
        description="每客户账户内保留的最近批次数；0=不限制（与客户端 max_batches=0 一致）",
    ),
    account_id: Optional[int] = None,
    country_code: Optional[str] = None,
    country_codes: Optional[str] = Query(
        None,
        description="逗号分隔的 ISO 国码，多选；与 country_code 二选一优先本参数",
    ),
    batch_id: Optional[str] = None,
    min_card_count: Optional[int] = Query(
        None,
        ge=0,
        description="卡片最小条数（按聚合后 count 过滤）",
    ),
    max_card_count: Optional[int] = Query(
        None,
        ge=0,
        description="卡片最大条数（按聚合后 count 过滤）",
    ),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    管理端：按 private_library_summaries 聚合卡片（与客户「我的私有库」结构一致），
    每条带 account_id / account_name 便于区分客户。
    """
    from collections import defaultdict

    from app.modules.data.private_library_summary_sync import build_summary_payload_from_rows
    from app.api.v1.data.customer import _apply_summary_item_canonical_labels

    try:
        q = select(PrivateLibrarySummary)
        if account_id is not None:
            q = q.where(PrivateLibrarySummary.account_id == account_id)
        codes: list[str] = []
        if country_codes and country_codes.strip():
            codes.extend(
                x.strip().upper()
                for x in country_codes.split(",")
                if x.strip()
            )
        elif country_code and country_code.strip():
            codes.append(country_code.strip().upper())
        if codes:
            cc_col = func.upper(func.trim(PrivateLibrarySummary.country_code))
            q = q.where(or_(*[cc_col == c for c in codes]))
        if batch_id is not None and batch_id != "":
            q = q.where(PrivateLibrarySummary.batch_id == batch_id)

        rows = list((await db.execute(q)).scalars().all())
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_private_library_schema_mismatch(e)
        logger.exception("管理端私库汇总查询失败")
        raise HTTPException(status_code=500, detail="查询私库汇总失败") from e

    if not rows:
        return {
            "success": True,
            "items": [],
            "total": 0,
            "meta": {
                "max_batches": max_batches,
                "truncated": False,
                "batch_card_limit": max_batches if max_batches > 0 else None,
            },
        }

    by_acc: dict[int, list] = defaultdict(list)
    for r in rows:
        by_acc[r.account_id].append(r)

    acc_ids = list(by_acc.keys())
    name_rows = (
        await db.execute(select(Account.id, Account.account_name).where(Account.id.in_(acc_ids)))
    ).all()
    name_map = {int(r[0]): (r[1] or "") for r in name_rows}

    all_items: list = []
    truncated_any = False
    for aid in sorted(by_acc.keys()):
        acc_rows = by_acc[aid]
        payload = build_summary_payload_from_rows(
            acc_rows,
            max_batches=max_batches,
            total_all_accounts_hint=None,
        )
        meta = payload.get("meta") or {}
        if meta.get("truncated"):
            truncated_any = True
        for it in payload.get("items") or []:
            it["account_id"] = aid
            it["account_name"] = name_map.get(aid, "")
            all_items.append(it)

    _apply_summary_item_canonical_labels(all_items)
    all_items.sort(key=lambda x: x.get("last_at") or "", reverse=True)

    if min_card_count is not None:
        all_items = [x for x in all_items if int(x.get("count") or 0) >= min_card_count]
    if max_card_count is not None:
        all_items = [x for x in all_items if int(x.get("count") or 0) <= max_card_count]
    grand_total = sum(int(x.get("count") or 0) for x in all_items)

    return {
        "success": True,
        "items": all_items,
        "total": grand_total,
        "meta": {
            "max_batches": max_batches,
            "truncated": truncated_any,
            "batch_card_limit": max_batches if max_batches > 0 else None,
        },
    }


class AdminPrivateLibraryDeleteCardBody(BaseModel):
    """管理端：按与客户私库卡片相同维度删除数据"""

    account_id: int = Field(..., ge=1, description="客户账户 ID")
    country_code: str = ""
    source: str = ""
    purpose: str = ""
    batch_id: str = ""
    remarks: Optional[str] = None
    carrier: Optional[str] = None


@router.post("/private-library-delete-card")
async def admin_delete_private_library_card(
    body: AdminPrivateLibraryDeleteCardBody,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    管理端删除客户私库整张卡片维度数据：手工私库分表软删、汇总表维护、公海购入绑定释放。
    与客户端 POST /data/my-numbers/delete-batch 逻辑一致。
    """
    from app.api.v1.data.customer import _execute_my_numbers_batch_delete

    acc_row = (await db.execute(select(Account.id).where(Account.id == body.account_id))).scalar_one_or_none()
    if acc_row is None:
        raise HTTPException(status_code=404, detail="账户不存在")

    return await _execute_my_numbers_batch_delete(
        db,
        body.account_id,
        country=body.country_code,
        source=body.source,
        purpose=body.purpose,
        batch_id=body.batch_id,
        remarks=body.remarks,
        carrier=body.carrier,
        for_admin=True,
        hard_delete=True,
    )


class AdminPrivateLibraryResyncBody(BaseModel):
    account_id: int


@router.post("/private-library-resync-summary")
async def admin_resync_private_library_summary(
    body: AdminPrivateLibraryResyncBody,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    管理端：从明细表重建指定账户的汇总表（修复汇总与明细不一致时使用）。
    删除该账户旧汇总行，再按 GROUP BY 重新插入。
    """
    from sqlalchemy import case as sa_case
    from app.modules.data.private_library_summary_sync import norm_dim

    acc = (await db.execute(select(Account.id).where(Account.id == body.account_id))).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status_code=404, detail="账户不存在")
    aid = body.account_id

    await db.execute(delete(PrivateLibrarySummary).where(PrivateLibrarySummary.account_id == aid))

    def _agg_stmt(model, account_id, extra_where):
        return (
            select(
                func.coalesce(model.country_code, "").label("cc"),
                func.coalesce(model.source, "").label("src"),
                func.coalesce(model.purpose, "").label("pur"),
                func.coalesce(model.batch_id, "").label("bid"),
                func.coalesce(model.carrier, "").label("car"),
                func.count().label("cnt"),
                func.sum(sa_case((model.use_count > 0, 1), else_=0)).label("used"),
                func.max(model.remarks).label("rmk"),
                func.min(model.created_at).label("fa"),
                func.max(model.created_at).label("la"),
            )
            .where(model.account_id == account_id, *extra_where)
            .group_by("cc", "src", "pur", "bid", "car")
        )

    # 活跃行 → is_deleted=False
    for model, origin in [
        (PrivateLibraryNumber, "manual"),
        (DataNumber, "purchased"),
    ]:
        extra = []
        if model is PrivateLibraryNumber:
            extra.append(PrivateLibraryNumber.is_deleted == False)  # noqa: E712
        rows = (await db.execute(_agg_stmt(model, aid, extra))).all()
        for r in rows:
            cnt = int(r.cnt or 0)
            if cnt <= 0:
                continue
            db.add(PrivateLibrarySummary(
                account_id=aid,
                country_code=norm_dim(r.cc),
                source=norm_dim(r.src),
                purpose=norm_dim(r.pur),
                batch_id=norm_dim(r.bid),
                carrier=norm_dim(r.car),
                library_origin=origin,
                total_count=cnt,
                used_count=int(r.used or 0),
                is_deleted=False,
                remarks=r.rmk,
                first_at=r.fa,
                last_at=r.la,
            ))

    # 已软删行 → is_deleted=True（仅 PrivateLibraryNumber 有软删状态）
    # 由于 unique constraint 不含 is_deleted，同维度只能有一行——若活跃阶段已插入则跳过
    await db.flush()
    existing_keys: set = set()
    ex_rows = (await db.execute(
        select(
            PrivateLibrarySummary.country_code,
            PrivateLibrarySummary.source,
            PrivateLibrarySummary.purpose,
            PrivateLibrarySummary.batch_id,
            PrivateLibrarySummary.carrier,
            PrivateLibrarySummary.library_origin,
        ).where(PrivateLibrarySummary.account_id == aid)
    )).all()
    for ek in ex_rows:
        existing_keys.add((norm_dim(ek[0]), norm_dim(ek[1]), norm_dim(ek[2]),
                           norm_dim(ek[3]), norm_dim(ek[4]), ek[5]))

    soft_del_rows = (await db.execute(
        _agg_stmt(PrivateLibraryNumber, aid, [PrivateLibraryNumber.is_deleted == True])  # noqa: E712
    )).all()
    for r in soft_del_rows:
        cnt = int(r.cnt or 0)
        if cnt <= 0:
            continue
        key = (norm_dim(r.cc), norm_dim(r.src), norm_dim(r.pur),
               norm_dim(r.bid), norm_dim(r.car), "manual")
        if key in existing_keys:
            continue
        db.add(PrivateLibrarySummary(
            account_id=aid,
            country_code=norm_dim(r.cc),
            source=norm_dim(r.src),
            purpose=norm_dim(r.pur),
            batch_id=norm_dim(r.bid),
            carrier=norm_dim(r.car),
            library_origin="manual",
            total_count=cnt,
            used_count=int(r.used or 0),
            is_deleted=True,
            remarks=r.rmk,
            first_at=r.fa,
            last_at=r.la,
        ))
    await db.commit()

    try:
        from app.utils.data_customer_cache import invalidate_my_numbers_summary_cache
        await invalidate_my_numbers_summary_cache(aid)
    except Exception:
        pass

    cnt_new = (await db.execute(
        select(func.count()).select_from(PrivateLibrarySummary).where(PrivateLibrarySummary.account_id == aid)
    )).scalar() or 0

    logger.info("管理员 %s 重建账户 %s 汇总表: %s 行", getattr(admin, "id", "?"), aid, cnt_new)
    return {"success": True, "message": f"已重建账户 {aid} 的汇总表（{cnt_new} 行）"}


def _serialize_admin_private_library_row(pln: PrivateLibraryNumber, account_name: str, email: Optional[str]) -> dict:
    """管理端私库分表行序列化（含客户软删状态，供后台查阅）"""
    return {
        "id": pln.id,
        "account_id": pln.account_id,
        "account_name": account_name or "",
        "email": email or "",
        "phone_number": pln.phone_number,
        "country_code": pln.country_code,
        "carrier": pln.carrier,
        "source": pln.source,
        "purpose": pln.purpose,
        "batch_id": pln.batch_id,
        "status": pln.status,
        "use_count": pln.use_count or 0,
        "last_used_at": pln.last_used_at.isoformat() if pln.last_used_at else None,
        "remarks": pln.remarks,
        "tags": pln.tags or [],
        "is_deleted": bool(pln.is_deleted),
        "created_at": pln.created_at.isoformat() if pln.created_at else None,
        "updated_at": pln.updated_at.isoformat() if pln.updated_at else None,
    }


@router.get("/private-library-numbers")
async def admin_list_private_library_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    account_id: Optional[int] = None,
    is_deleted: Optional[bool] = None,
    country_code: Optional[str] = None,
    batch_id: Optional[str] = None,
    phone: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """管理端：分页查看客户私库分表明细（含客户已软删行）"""
    try:
        q = (
            select(PrivateLibraryNumber, Account.account_name, Account.email)
            .join(Account, Account.id == PrivateLibraryNumber.account_id)
        )
        if account_id is not None:
            q = q.where(PrivateLibraryNumber.account_id == account_id)
        if is_deleted is not None:
            q = q.where(PrivateLibraryNumber.is_deleted == is_deleted)
        if country_code:
            q = q.where(PrivateLibraryNumber.country_code == country_code.strip())
        if batch_id is not None and batch_id != "":
            q = q.where(PrivateLibraryNumber.batch_id == batch_id)
        if phone and phone.strip():
            pat = f"%{phone.strip()}%"
            q = q.where(PrivateLibraryNumber.phone_number.like(pat))

        count_q = select(func.count(PrivateLibraryNumber.id)).select_from(PrivateLibraryNumber).join(
            Account, Account.id == PrivateLibraryNumber.account_id
        )
        if account_id is not None:
            count_q = count_q.where(PrivateLibraryNumber.account_id == account_id)
        if is_deleted is not None:
            count_q = count_q.where(PrivateLibraryNumber.is_deleted == is_deleted)
        if country_code:
            count_q = count_q.where(PrivateLibraryNumber.country_code == country_code.strip())
        if batch_id is not None and batch_id != "":
            count_q = count_q.where(PrivateLibraryNumber.batch_id == batch_id)
        if phone and phone.strip():
            pat = f"%{phone.strip()}%"
            count_q = count_q.where(PrivateLibraryNumber.phone_number.like(pat))
        total = (await db.execute(count_q)).scalar() or 0

        q = q.order_by(PrivateLibraryNumber.created_at.desc(), PrivateLibraryNumber.id.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(q)).all()

        items = [_serialize_admin_private_library_row(r[0], r[1], r[2]) for r in rows]
        return {"success": True, "items": items, "total": total, "page": page, "page_size": page_size}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_private_library_schema_mismatch(e)
        logger.exception("管理端私库列表查询失败")
        raise HTTPException(status_code=500, detail="查询私库列表失败") from e


@router.get("/private-library-numbers/export")
async def admin_export_private_library_numbers(
    account_id: Optional[int] = None,
    is_deleted: Optional[bool] = None,
    country_code: Optional[str] = None,
    batch_id: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    phone: Optional[str] = None,
    fmt: str = Query("csv", description="导出格式：csv（含所有字段）或 txt（纯号码，每行一个）"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """管理端：导出客户私库分表为 CSV 或 TXT"""
    fmt = fmt.strip().lower()
    if fmt not in ("csv", "txt"):
        fmt = "csv"

    if fmt == "txt":
        q = select(PrivateLibraryNumber.phone_number)
    else:
        q = select(
            PrivateLibraryNumber.phone_number,
            PrivateLibraryNumber.country_code,
            PrivateLibraryNumber.carrier,
            PrivateLibraryNumber.source,
            PrivateLibraryNumber.purpose,
            PrivateLibraryNumber.batch_id,
            PrivateLibraryNumber.account_id,
            Account.account_name,
            PrivateLibraryNumber.is_deleted,
            PrivateLibraryNumber.created_at,
        ).join(Account, Account.id == PrivateLibraryNumber.account_id)

    q = q.where(True)  # noqa: base clause
    if account_id is not None:
        q = q.where(PrivateLibraryNumber.account_id == account_id)
    if is_deleted is not None:
        q = q.where(PrivateLibraryNumber.is_deleted == is_deleted)
    if country_code:
        q = q.where(PrivateLibraryNumber.country_code == country_code.strip())
    if batch_id is not None and batch_id != "":
        q = q.where(PrivateLibraryNumber.batch_id == batch_id)
    if source is not None and str(source).strip() != "":
        q = q.where(PrivateLibraryNumber.source == str(source).strip())
    if purpose is not None and str(purpose).strip() != "":
        q = q.where(PrivateLibraryNumber.purpose == str(purpose).strip())
    if phone and phone.strip():
        pat = f"%{phone.strip()}%"
        q = q.where(PrivateLibraryNumber.phone_number.like(pat))

    q = q.order_by(PrivateLibraryNumber.account_id.asc(), PrivateLibraryNumber.id.asc())
    try:
        result = await db.stream(q)
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_private_library_schema_mismatch(e)
        logger.exception("管理端私库导出 stream 失败")
        raise HTTPException(status_code=500, detail="导出私库失败") from e

    if fmt == "txt":
        async def generate_txt():
            async for row in result:
                line = export_phone_plain_digits(row[0])
                if line:
                    yield line + "\n"

        filename = f"private_library_numbers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        return StreamingResponse(
            generate_txt(),
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    async def generate_csv():
        yield "\ufeff"
        yield (
            "phone_number,country_code,carrier,source,purpose,batch_id,account_id,account_name,"
            "is_deleted,created_at\n"
        )
        async for row in result:
            # 流式 Row 用列序取号码，避免 _mapping 键与 ORM 列名不一致时仍带 + 导出
            ca = row[9]
            yield ",".join(
                [
                    export_phone_plain_digits(row[0]),
                    str(row[1] or ""),
                    str(row[2] or ""),
                    str(row[3] or ""),
                    str(row[4] or ""),
                    str(row[5] or ""),
                    str(row[6] or ""),
                    str(row[7] or "").replace(",", " "),
                    "1" if row[8] else "0",
                    ca.isoformat() if ca else "",
                ]
            ) + "\n"

    filename = f"private_library_numbers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
