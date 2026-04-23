"""
SMS 批次处理工具函数
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, func as sa_func, update as _sa_upd
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.channel import Channel
# 预注册关联表元数据，避免 ORM 在部分入口（仅 import batch_utils）时外键解析失败
from app.modules.sms.sms_template import SmsTemplate  # noqa: F401
from app.modules.common.account import Account  # noqa: F401
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _mimic_smpp_expired_dlr_message() -> str:
    """
    虚拟通道「超时/未送达」类终态对外展示：仿 SMPP DLR 一行格式。
    从 sms_worker.py 迁移。
    """
    import random
    return f"SMPP DLR: stat=EXPIRED err={random.randint(1, 999):03d}"


def _norm_status_val(status: Any) -> str:
    """Enum / str 统一为小写字符串，便于比对。"""
    if status is None:
        return ""
    v = getattr(status, "value", status)
    v = getattr(v, "value", v)
    return str(v or "").lower()


def _norm_err(msg: Optional[str]) -> Optional[str]:
    s = (msg or "").strip()
    return s if s else None


def _same_completed_at(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a == b


def _batch_targets_unchanged(
    batch: SmsBatch,
    *,
    new_success: int,
    new_delivered: int,
    new_failed: int,
    new_processing: int,
    new_progress: int,
    new_status: Any,
    new_completed_at: Any,
    new_error: Optional[str],
) -> bool:
    """与当前 ORM 已加载值比对；无变化则跳过写库，避免无意义刷新 updated_at。"""
    if int(batch.success_count or 0) != int(new_success):
        return False
    if int(getattr(batch, 'delivered_count', None) or 0) != int(new_delivered):
        return False
    if int(batch.failed_count or 0) != int(new_failed):
        return False
    if int(batch.processing_count or 0) != int(new_processing):
        return False
    if int(batch.progress or 0) != int(new_progress):
        return False
    if _norm_status_val(batch.status) != _norm_status_val(new_status):
        return False
    if not _same_completed_at(batch.completed_at, new_completed_at):
        return False
    if _norm_err(batch.error_message) != _norm_err(new_error):
        return False
    return True


async def update_batch_progress(db, batch_id: int) -> bool:
    """
    更新批次的发送进度和状态。
    计算 SMSLog 中各状态的数量，同步到 SmsBatch 记录。

    返回 True 表示已执行有实质变更的写库并 commit；False 表示聚合结果与当前批次行一致，已跳过 commit（防抖）。
    """
    if not batch_id:
        return False

    try:
        stats = await db.execute(
            select(
                SMSLog.status,
                sa_func.count().label("cnt"),
            ).where(SMSLog.batch_id == batch_id).group_by(SMSLog.status)
        )
        counts = {row.status: row.cnt for row in stats}
        log_total = sum(counts.values())

        sent = counts.get("sent", 0) + counts.get("delivered", 0)
        failed = counts.get("failed", 0) + counts.get("expired", 0)
        done = sent + failed
        pending_cnt = counts.get("pending", 0) + counts.get("queued", 0)

        batch_result = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
        batch = batch_result.scalar_one_or_none()
        if not batch:
            return False

        total = batch.total_count or log_total

        # ---------- 虚拟通道 ≤2% pending 兜底（会改 sms_logs，视为必有实质变更）----------
        if log_total >= total and pending_cnt > 0 and pending_cnt <= total * 0.02:
            pend_rows = (
                await db.execute(
                    select(SMSLog.message_id, Channel.protocol)
                    .select_from(SMSLog)
                    .outerjoin(Channel, SMSLog.channel_id == Channel.id)
                    .where(
                        SMSLog.batch_id == batch_id,
                        SMSLog.status.in_(["pending", "queued"]),
                    )
                )
            ).all()

            all_virtual_pending = bool(pend_rows) and all(
                r.protocol == "VIRTUAL" for r in pend_rows
            )

            if all_virtual_pending:
                now_ts = datetime.now()
                virt_ids = [r.message_id for r in pend_rows]
                await db.execute(
                    _sa_upd(SMSLog)
                    .where(SMSLog.message_id.in_(virt_ids))
                    .values(
                        status="expired",
                        error_message=_mimic_smpp_expired_dlr_message(),
                        sent_time=now_ts,
                    )
                )
                await db.commit()

                stats2 = await db.execute(
                    select(SMSLog.status, sa_func.count().label("cnt"))
                    .where(SMSLog.batch_id == batch_id).group_by(SMSLog.status)
                )
                counts2 = {r.status: r.cnt for r in stats2}
                sent2 = counts2.get("sent", 0) + counts2.get("delivered", 0)
                failed2 = counts2.get("failed", 0) + counts2.get("expired", 0)

                batch.success_count = sent2
                batch.delivered_count = counts2.get("delivered", 0)
                batch.failed_count = failed2
                batch.processing_count = 0
                batch.progress = 100
                batch.status = BatchStatus.COMPLETED
                batch.completed_at = datetime.now()
                batch.error_message = (
                    f"部分失败: {failed2}/{total}" if failed2 > 0 else None
                )
                await db.commit()
                logger.info(f"批次虚拟通道兜底完成: batch={batch_id}, 清理 {pending_cnt} 条遗留 pending")
                return True

            logger.debug(
                f"批次存在非虚拟待发(≤2%)，跳过自动过期: batch={batch_id}, pending={pending_cnt}"
            )

        # ---------- 计算目标字段（局部变量），末尾与 batch 比对防抖 ----------
        new_success = int(sent)
        new_delivered = int(counts.get("delivered", 0))
        new_failed = int(failed)
        new_processing = max(0, int(total) - int(done))
        new_progress = min(100, int(done * 100 / max(int(total), 1)))
        new_status: Any = batch.status
        new_completed_at: Any = batch.completed_at
        new_error: Optional[str] = batch.error_message

        if batch.status == BatchStatus.COMPLETED and (pending_cnt > 0 or done < log_total):
            new_status = BatchStatus.PROCESSING
            new_completed_at = None
            logger.warning(
                f"批次 {batch_id} 从 completed 回退为 processing："
                f"pending+queued={pending_cnt}, done={done}, log_total={log_total}, total={total}"
            )

        if log_total >= total and done >= log_total:
            if failed == 0:
                new_status = BatchStatus.COMPLETED
            elif sent == 0:
                new_status = BatchStatus.FAILED
            else:
                new_status = BatchStatus.COMPLETED
                new_error = f"部分失败: {failed}/{total}"
            # 已在同终态时不反复刷 completed_at，否则每次与 now() 比较都会误判为「有变化」
            if (
                _norm_status_val(batch.status) == _norm_status_val(new_status)
                and batch.completed_at is not None
            ):
                new_completed_at = batch.completed_at
            else:
                new_completed_at = datetime.now()

        elif log_total >= total and pending_cnt > 0 and pending_cnt <= total * 0.02:
            # 非虚拟：仅纠批次状态（与历史逻辑一致）
            if _norm_status_val(new_status) != "processing":
                new_status = BatchStatus.PROCESSING
            new_completed_at = None

        elif log_total >= total and batch.status == BatchStatus.COMPLETED:
            pass

        else:
            if _norm_status_val(new_status) not in ("completed", "failed", "cancelled"):
                new_status = BatchStatus.PROCESSING
            new_completed_at = None
            if new_error and "部分失败" in new_error:
                new_error = None

        if _batch_targets_unchanged(
            batch,
            new_success=new_success,
            new_delivered=new_delivered,
            new_failed=new_failed,
            new_processing=new_processing,
            new_progress=new_progress,
            new_status=new_status,
            new_completed_at=new_completed_at,
            new_error=new_error,
        ):
            return False

        batch.success_count = new_success
        batch.delivered_count = new_delivered
        batch.failed_count = new_failed
        batch.processing_count = new_processing
        batch.progress = new_progress
        batch.status = new_status
        batch.completed_at = new_completed_at
        batch.error_message = new_error

        await db.commit()
        return True

    except Exception as e:
        logger.warning(f"更新批次进度失败: batch_id={batch_id}, {e}")
        await db.rollback()
        return False


async def publish_batch_pipeline_progress(
    batch_id: int,
    *,
    total: int,
    inserted: int,
    queued: int,
) -> None:
    """
    大批量购数并发送等任务的「中途」进度：单条 UPDATE sms_batches，无 COUNT 聚合。

    使用独立短会话提交，避免与 Worker 主事务绑定；读者可立刻看到 progress/total_count。
    进度按落库约 50%、入队约 49% 线性铺开，封顶 99；任务收尾仍由 update_batch_progress 按 sms_logs 终态覆盖。
    """
    if not batch_id or total <= 0:
        return
    ins = max(0, min(int(inserted), total))
    q = max(0, min(int(queued), total))
    # 浮点避免整除台阶过粗
    p = int(min(99, (ins * 50.0 / total) + (q * 49.0 / total)))

    try:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as pub_db:
            await pub_db.execute(
                _sa_upd(SmsBatch)
                .where(SmsBatch.id == batch_id, SmsBatch.is_deleted == False)
                .values(
                    progress=p,
                    total_count=sa_func.greatest(
                        sa_func.coalesce(SmsBatch.total_count, 0), int(total)
                    ),
                    updated_at=datetime.now(),
                )
            )
            await pub_db.commit()
    except Exception as e:
        logger.warning(
            f"中途批次进度发布失败（忽略，不影响主流程）: batch_id={batch_id}, {e}"
        )
