"""
批量发送 API
"""
import re
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update
from typing import Optional, List, Dict
from datetime import datetime
import csv
import os
import io

from app.database import get_db
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_template import SmsTemplate
from app.schemas.batch import (
    SmsBatchCreate, SmsBatchResponse, SmsBatchListResponse,
    SmsBatchStats, BatchUploadResponse, BatchRetryFailedResponse,
)
from app.modules.sms.sms_log import SMSLog
from app.core.pricing import PricingEngine
from app.utils.queue import QueueManager
from app.utils.errors import InsufficientBalanceError, PricingNotFoundError
from app.core.auth import get_current_account
from app.modules.common.account import Account
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


async def _maybe_sync_batch_row_from_logs(
    db: AsyncSession,
    batch: SmsBatch,
    patch: Dict[str, int],
    total_by_id: Dict[int, int],
) -> Dict[str, int]:
    """
    列表/详情用 sms_logs 重算的 progress 可能已是 100%，但 sms_batches 行仍 processing（Go 写 sent 不经 Python）。
    此时补跑一次 update_batch_progress 持久化，并返回更新后的展示 patch。
    """
    if batch.status != BatchStatus.PROCESSING or not patch:
        return patch
    if patch.get("progress", 0) < 100 or patch.get("processing_count", 1) != 0:
        return patch
    try:
        from app.modules.sms.batch_utils import update_batch_progress

        await update_batch_progress(db, batch.id)
        await db.refresh(batch)
        new_map = await _smslog_batch_display_patches(
            db, [batch.id], {int(batch.id): int(batch.total_count or total_by_id.get(int(batch.id), 0) or 0)}
        )
        return new_map.get(batch.id, patch)
    except Exception as e:
        logger.debug(f"批次 {batch.id} 列表/详情触发进度持久化跳过: {e}")
        return patch


def _smslog_counts_to_response_patch(m: Dict[str, int], batch_total: int = 0) -> Dict[str, int]:
    """
    将单批 sms_logs 按状态计数转为列表接口覆盖字段。
    当该批存在至少一条日志时，用日志重算 success/failed/processing/progress，修正 data_worker 曾用入队数覆盖 success_count 等问题。
    """
    log_total = sum(m.values())
    dlv = m.get("delivered", 0)
    pq = m.get("pending", 0) + m.get("queued", 0)
    st = m.get("sent", 0)
    fl = m.get("failed", 0) + m.get("expired", 0)
    patch: Dict[str, int] = {
        "delivered_count": dlv,
        "sent_awaiting_receipt_count": pq + st,
    }
    if log_total > 0:
        patch["success_count"] = st + dlv
        patch["failed_count"] = fl
        patch["processing_count"] = pq
        tot = max(int(batch_total or 0), log_total, 1)
        # 与 batch_utils 一致：已进入终态或通道已接受发送的条数占比
        done = dlv + st + fl
        patch["progress"] = min(100, int(done * 100 / tot))
    return patch


async def _smslog_batch_display_patches(
    db: AsyncSession, batch_ids: List[int], batch_total_by_id: Optional[Dict[int, int]] = None
) -> Dict[int, Dict[str, int]]:
    """按批次聚合 sms_logs，生成 model_copy(update=...) 用的字段字典。"""
    if not batch_ids:
        return {}
    stmt = (
        select(SMSLog.batch_id, SMSLog.status, func.count(SMSLog.id))
        .where(SMSLog.batch_id.in_(batch_ids))
        .group_by(SMSLog.batch_id, SMSLog.status)
    )
    rows = (await db.execute(stmt)).all()
    acc: Dict[int, Dict[str, int]] = {int(bid): {} for bid in batch_ids}
    for batch_id, status, cnt in rows:
        if batch_id is None:
            continue
        acc.setdefault(int(batch_id), {})[str(status or "")] = int(cnt or 0)
    totals = batch_total_by_id or {}
    return {
        int(bid): _smslog_counts_to_response_patch(
            acc.get(int(bid), {}), totals.get(int(bid), 0)
        )
        for bid in batch_ids
    }


def _mask_phone_for_export(phone: Optional[str]) -> str:
    """导出 CSV 时手机号脱敏：长号码保留前 3 位与后 5 位，中间 ****（如 919****01595）。"""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    n = len(digits)
    if n == 0:
        return ""
    if n <= 3:
        return "*" * n
    if n >= 12:
        return digits[:3] + "****" + digits[-5:]
    if n >= 8:
        suffix_len = n - 7
        return digits[:3] + "****" + digits[-suffix_len:]
    if n == 7:
        return digits[:2] + "****" + digits[-1]
    if n == 6:
        return digits[:2] + "****" + digits[-2:]
    if n == 5:
        return digits[:2] + "**" + digits[-1]
    return digits[0] + "**" + digits[-1]

# 上传目录配置
UPLOAD_DIR = "/var/smsc/backend/uploads/batches"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _is_data_warehouse_send_batch(batch: SmsBatch) -> bool:
    """
    数据仓库「购数并发送」创建的批次名称以 DataSend- 开头；
    下单时已一并扣除数据费与短信费，失败重发不再重复扣短信费。
    """
    name = (batch.batch_name or "").strip()
    return name.startswith("DataSend-")


@router.post("/batches/upload", response_model=BatchUploadResponse, summary="上传CSV批量发送")
async def upload_batch_file(
    file: UploadFile = File(...),
    batch_name: str = Form(...),
    template_id: Optional[int] = Form(None),
    sender_id: Optional[str] = Form(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    上传CSV文件进行批量发送
    
    CSV格式要求：
    - 第一列：手机号（必填）
    - 其他列：变量值（如果使用模板）
    
    示例：
    ```
    phone,name,code
    +8613800138000,张三,123456
    +8613800138001,李四,654321
    ```
    """
    try:
        # 验证文件类型
        import os as _os
        clean_name = _os.path.basename(file.filename or "upload.csv")
        if not clean_name.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="仅支持CSV文件")
        
        # 读取文件内容
        content = await file.read()
        file_size = len(content)
        
        if file_size > 100 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小不能超过100MB")
        
        # 解析CSV
        csv_content = content.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        # 验证表头
        if 'phone' not in csv_reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV必须包含'phone'列")
        
        # 统计行数
        rows = list(csv_reader)
        total_count = len(rows)
        
        if total_count == 0:
            raise HTTPException(status_code=400, detail="CSV文件为空")
        
        if total_count > 2000000:
            raise HTTPException(status_code=400, detail="单次批量最多支持200万条")
        
        # 如果使用模板，验证模板存在
        if template_id:
            template_query = select(SmsTemplate).where(
                SmsTemplate.id == template_id,
                SmsTemplate.account_id == current_account.id
            )
            template_result = await db.execute(template_query)
            template = template_result.scalar_one_or_none()
            if not template:
                raise HTTPException(status_code=404, detail="模板不存在")
        
        # 保存文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{current_account.id}_{timestamp}_{clean_name}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # 创建批次记录
        batch = SmsBatch(
            account_id=current_account.id,
            batch_name=batch_name,
            template_id=template_id,
            file_path=file_path,
            file_size=file_size,
            total_count=total_count,
            sender_id=sender_id,
            status=BatchStatus.PENDING
        )
        
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        
        logger.info(f"Batch uploaded: id={batch.id}, account={current_account.id}, count={total_count}")
        
        # 触发异步处理任务（Celery）
        from app.workers.batch_worker import process_batch
        process_batch.delay(batch.id)
        
        return BatchUploadResponse(
            batch_id=batch.id,
            file_name=file.filename,
            file_size=file_size,
            total_count=total_count,
            message="上传成功，正在处理中"
        )
        
    except Exception as e:
        logger.error(f"Failed to upload batch: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/batches", response_model=SmsBatchListResponse, summary="查询批次列表")
async def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[BatchStatus] = Query(None),
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询批量发送任务列表"""
    try:
        conditions = [
            SmsBatch.account_id == current_account.id,
            SmsBatch.is_deleted == False
        ]
        
        if status:
            conditions.append(SmsBatch.status == status)
        
        # 总数
        count_query = select(func.count()).select_from(SmsBatch).where(and_(*conditions))
        total = (await db.execute(count_query)).scalar()
        
        # 数据
        offset = (page - 1) * page_size
        query = select(SmsBatch).where(and_(*conditions)).order_by(
            SmsBatch.created_at.desc()
        ).limit(page_size).offset(offset)
        
        result = await db.execute(query)
        batches = result.scalars().all()

        ids = [b.id for b in batches]
        total_by_id = {int(b.id): int(b.total_count or 0) for b in batches}
        patches = await _smslog_batch_display_patches(db, ids, total_by_id)
        items = []
        for b in batches:
            p = patches.get(b.id, {})
            p = await _maybe_sync_batch_row_from_logs(db, b, p, total_by_id)
            patches[b.id] = p
            base = SmsBatchResponse.model_validate(b, from_attributes=True)
            items.append(base.model_copy(update=p))

        return SmsBatchListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list batches: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches/stats", response_model=SmsBatchStats, summary="批次统计")
async def get_batch_stats(
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取批量发送统计"""
    try:
        # 总批次数
        total_query = select(func.count()).select_from(SmsBatch).where(
            SmsBatch.account_id == current_account.id,
            SmsBatch.is_deleted == False
        )
        total = (await db.execute(total_query)).scalar()
        
        # 按状态统计
        pending = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.PENDING,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        processing = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.PROCESSING,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        completed = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.COMPLETED,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        failed = (await db.execute(
            select(func.count()).select_from(SmsBatch).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.status == BatchStatus.FAILED,
                SmsBatch.is_deleted == False
            )
        )).scalar()
        
        # 消息统计
        total_messages = (await db.execute(
            select(func.sum(SmsBatch.total_count)).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.is_deleted == False
            )
        )).scalar() or 0
        
        success_messages = (await db.execute(
            select(func.sum(SmsBatch.success_count)).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.is_deleted == False
            )
        )).scalar() or 0
        
        failed_messages = (await db.execute(
            select(func.sum(SmsBatch.failed_count)).where(
                SmsBatch.account_id == current_account.id,
                SmsBatch.is_deleted == False
            )
        )).scalar() or 0
        
        return SmsBatchStats(
            total_batches=total,
            pending_batches=pending,
            processing_batches=processing,
            completed_batches=completed,
            failed_batches=failed,
            total_messages=total_messages,
            success_messages=success_messages,
            failed_messages=failed_messages
        )
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches/{batch_id}", response_model=SmsBatchResponse, summary="查询批次详情")
async def get_batch(
    batch_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """查询批次详情"""
    query = select(SmsBatch).where(
        SmsBatch.id == batch_id,
        SmsBatch.account_id == current_account.id,
        SmsBatch.is_deleted == False
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()
    
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    try:
        total_by_id = {int(batch.id): int(batch.total_count or 0)}
        patches = await _smslog_batch_display_patches(db, [batch.id], total_by_id)
        p = patches.get(batch.id, {})
        p = await _maybe_sync_batch_row_from_logs(db, batch, p, total_by_id)
        base = SmsBatchResponse.model_validate(batch, from_attributes=True)
        return base.model_copy(update=p)
    except Exception as e:
        logger.exception(f"批次详情序列化失败 batch_id={batch_id}: {e}")
        raise HTTPException(status_code=500, detail="批次数据格式异常，请联系管理员查看日志")


@router.get("/batches/{batch_id}/export", summary="导出批次发送明细 CSV（手机号脱敏）")
async def export_batch_records_csv(
    batch_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """导出该批量任务下短信明细；手机号列已脱敏；不含成本价与利润列。"""

    q_batch = select(SmsBatch).where(
        SmsBatch.id == batch_id,
        SmsBatch.account_id == current_account.id,
        SmsBatch.is_deleted == False,
    )
    result = await db.execute(q_batch)
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    query = (
        select(SMSLog)
        .where(
            SMSLog.batch_id == batch_id,
            SMSLog.account_id == current_account.id,
        )
        .order_by(SMSLog.id.asc())
        .limit(10000)
    )
    rows = (await db.execute(query)).scalars().all()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "消息ID",
            "上游消息ID",
            "手机号(脱敏)",
            "国家",
            "内容",
            "条数",
            "状态",
            "售价",
            "币种",
            "提交时间",
            "发送时间",
            "送达时间",
            "错误信息",
        ]
    )

    for r in rows:
        writer.writerow(
            [
                r.id,
                r.message_id,
                r.upstream_message_id or "",
                _mask_phone_for_export(r.phone_number),
                r.country_code or "",
                (r.message or "")[:200],
                r.message_count,
                r.status,
                float(r.selling_price) if r.selling_price else 0,
                r.currency or "USD",
                r.submit_time.strftime("%Y-%m-%d %H:%M:%S") if r.submit_time else "",
                r.sent_time.strftime("%Y-%m-%d %H:%M:%S") if r.sent_time else "",
                r.delivery_time.strftime("%Y-%m-%d %H:%M:%S") if r.delivery_time else "",
                r.error_message or "",
            ]
        )

    output.seek(0)
    # 仅 ASCII 文件名：Starlette 用 latin-1 编码响应头，批次名含中文会导致 UnicodeEncodeError → 500
    filename_ascii = f"batch_{batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename_ascii}"'},
    )


@router.delete("/batches/{batch_id}", summary="取消批次")
async def cancel_batch(
    batch_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """取消批量发送任务"""
    query = select(SmsBatch).where(
        SmsBatch.id == batch_id,
        SmsBatch.account_id == current_account.id,
        SmsBatch.is_deleted == False
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()
    
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    
    if batch.status in [BatchStatus.COMPLETED, BatchStatus.FAILED]:
        raise HTTPException(status_code=400, detail="该批次已完成，无法取消")
    
    try:
        batch.status = BatchStatus.CANCELLED
        await db.commit()
        
        logger.info(f"Batch cancelled: id={batch_id}")
        
        return {"success": True, "message": "批次已取消"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to cancel batch: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/batches/{batch_id}/retry-failed",
    response_model=BatchRetryFailedResponse,
    summary="失败重发",
)
async def retry_batch_failed(
    batch_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """
    将批次内状态为 failed / expired 的短信重新入队发送（与列表「失败」计数一致，含虚拟超时等 expired）。

    - 普通群发：按当前费率重新扣费（账户按提交计费，发送失败不退款，重发须再次扣费）。
    - 数据仓库购数并发送（批次名 DataSend- 开头）：购数时已含短信费用，重发不再扣费，沿用原记录计费字段。
    """
    from app.api.v1.sms import _refund_line_charge
    from app.modules.sms.batch_utils import update_batch_progress

    q_batch = select(SmsBatch).where(
        SmsBatch.id == batch_id,
        SmsBatch.account_id == current_account.id,
        SmsBatch.is_deleted == False,
    )
    result = await db.execute(q_batch)
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    if batch.status == BatchStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="已取消的批次无法重发")
    if batch.status == BatchStatus.PENDING:
        raise HTTPException(status_code=400, detail="批次尚未开始处理，请稍后再试")

    q_logs = (
        select(SMSLog)
        .where(
            SMSLog.batch_id == batch_id,
            SMSLog.account_id == current_account.id,
            or_(SMSLog.status == "failed", SMSLog.status == "expired"),
        )
        .order_by(SMSLog.id)
    )
    logs_result = await db.execute(q_logs)
    failed_logs: List[SMSLog] = list(logs_result.scalars().all())
    if not failed_logs:
        raise HTTPException(status_code=400, detail="没有可重发的失败记录")

    skip_sms_charge = _is_data_warehouse_send_batch(batch)
    pricing_engine = PricingEngine(db)
    retried = 0
    skipped = 0
    err_lines: List[str] = []
    max_err_show = 12

    for sms_log in failed_logs:
        if not sms_log.channel_id or not sms_log.country_code or not (sms_log.message or "").strip():
            skipped += 1
            if len(err_lines) < max_err_show:
                err_lines.append(
                    f"{sms_log.message_id}: 缺少通道、国家或正文，无法重发"
                )
            continue

        if skip_sms_charge:
            # 数据仓库购数并发送：不重复扣费，保留原 message_count / 价格字段
            sms_log.status = "queued"
            sms_log.error_message = None
            sms_log.sent_time = None
            sms_log.delivery_time = None
            sms_log.upstream_message_id = None
            await db.commit()

            if not QueueManager.queue_sms(sms_log.message_id):
                await db.execute(
                    update(SMSLog)
                    .where(SMSLog.message_id == sms_log.message_id)
                    .values(
                        status="failed",
                        error_message=(
                            "加入发送队列失败，请检查 RabbitMQ 与 Celery worker-sms 是否运行"
                        ),
                    )
                )
                await db.commit()
                skipped += 1
                if len(err_lines) < max_err_show:
                    err_lines.append(f"{sms_log.message_id}: 加入发送队列失败")
                continue

            retried += 1
            continue

        try:
            charge_result = await pricing_engine.calculate_and_charge(
                account_id=current_account.id,
                channel_id=int(sms_log.channel_id),
                country_code=str(sms_log.country_code),
                message=str(sms_log.message),
                mnc=None,
            )
        except InsufficientBalanceError as e:
            req = (e.details or {}).get("required", "")
            avail = (e.details or {}).get("available", "")
            raise HTTPException(
                status_code=402,
                detail=f"余额不足，已成功重发 {retried} 条。需要 {req}，当前可用 {avail}",
            )
        except PricingNotFoundError as e:
            skipped += 1
            if len(err_lines) < max_err_show:
                err_lines.append(f"{sms_log.message_id}: 计费失败（{e.message}）")
            continue

        sms_log.status = "queued"
        sms_log.error_message = None
        sms_log.sent_time = None
        sms_log.delivery_time = None
        sms_log.upstream_message_id = None
        sms_log.message_count = int(charge_result.get("message_count") or 1)
        sms_log.cost_price = charge_result["total_base_cost"]
        sms_log.selling_price = charge_result["total_cost"]
        sms_log.currency = charge_result.get("currency") or "USD"

        await db.commit()

        if not QueueManager.queue_sms(sms_log.message_id):
            await _refund_line_charge(
                db,
                current_account.id,
                float(charge_result["total_cost"]),
                f"失败重发入队失败退款 {sms_log.message_id}",
            )
            await db.execute(
                update(SMSLog)
                .where(SMSLog.message_id == sms_log.message_id)
                .values(
                    status="failed",
                    error_message=(
                        "加入发送队列失败，请检查 RabbitMQ 与 Celery worker-sms 是否运行"
                    ),
                )
            )
            await db.commit()
            skipped += 1
            if len(err_lines) < max_err_show:
                err_lines.append(f"{sms_log.message_id}: 加入发送队列失败")
            continue

        retried += 1

    await update_batch_progress(db, batch_id)

    msg = f"已重发 {retried} 条"
    if skipped:
        msg += f"，{skipped} 条未重发"
    return BatchRetryFailedResponse(
        retried=retried,
        skipped=skipped,
        errors=err_lines,
        message=msg,
    )


@router.post(
    "/batches/{batch_id}/requeue-queued",
    response_model=BatchRetryFailedResponse,
    summary="排队中记录重新入队",
)
async def requeue_batch_queued(
    batch_id: int,
    current_account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """
    将批次内仍为 queued / pending 的短信再次投递到 Celery（不重复扣费）。

    用于 Worker 曾无法连接数据库等异常：任务已从 RabbitMQ 消费但库未更新，
    修复部署后可通过本接口补投递。
    """
    from app.modules.sms.batch_utils import update_batch_progress

    q_batch = select(SmsBatch).where(
        SmsBatch.id == batch_id,
        SmsBatch.account_id == current_account.id,
        SmsBatch.is_deleted == False,
    )
    result = await db.execute(q_batch)
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    if batch.status == BatchStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="已取消的批次无法操作")

    q_logs = (
        select(SMSLog)
        .where(
            SMSLog.batch_id == batch_id,
            SMSLog.account_id == current_account.id,
            or_(SMSLog.status == "queued", SMSLog.status == "pending"),
        )
        .order_by(SMSLog.id)
    )
    logs_result = await db.execute(q_logs)
    stuck_logs: List[SMSLog] = list(logs_result.scalars().all())
    if not stuck_logs:
        raise HTTPException(status_code=400, detail="没有处于排队中的记录")

    retried = 0
    skipped = 0
    err_lines: List[str] = []
    max_err_show = 12

    for sms_log in stuck_logs:
        if not sms_log.message_id:
            skipped += 1
            if len(err_lines) < max_err_show:
                err_lines.append("存在无 message_id 的记录，已跳过")
            continue
        if QueueManager.queue_sms(sms_log.message_id):
            retried += 1
        else:
            skipped += 1
            if len(err_lines) < max_err_show:
                err_lines.append(f"{sms_log.message_id}: 加入发送队列失败")

    await update_batch_progress(db, batch_id)

    msg = f"已重新入队 {retried} 条"
    if skipped:
        msg += f"，{skipped} 条未入队"
    return BatchRetryFailedResponse(
        retried=retried,
        skipped=skipped,
        errors=err_lines,
        message=msg,
    )
