"""
SMS 批次处理工具函数
"""
from datetime import datetime
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


async def update_batch_progress(db, batch_id: int):
    """
    更新批次的发送进度和状态。
    计算 SMSLog 中各状态的数量，同步到 SmsBatch 记录。
    
    此函数由从异步 Worker 的 DLR 处理逻辑和 API 的 DLR 回调逻辑共同调用。
    """
    if not batch_id:
        return

    try:
        # 统计批次内各状态的短信数量
        stats = await db.execute(
            select(
                SMSLog.status,
                sa_func.count().label('cnt')
            ).where(SMSLog.batch_id == batch_id).group_by(SMSLog.status)
        )
        counts = {row.status: row.cnt for row in stats}
        log_total = sum(counts.values())
        
        # 成功数：已发送(sent) 或 已送达(delivered)
        # 失败数：失败(failed) 或 已过期(expired)
        sent = counts.get('sent', 0) + counts.get('delivered', 0)
        failed = counts.get('failed', 0) + counts.get('expired', 0)
        done = sent + failed

        # 获取批次对象
        batch_result = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
        batch = batch_result.scalar_one_or_none()
        if not batch:
            return

        total = batch.total_count or log_total
        pending_cnt = counts.get('pending', 0) + counts.get('queued', 0)

        # 更新基础统计数据
        batch.success_count = sent
        batch.failed_count = failed
        batch.processing_count = max(0, total - done)
        batch.progress = min(100, int(done * 100 / max(total, 1)))

        # 纠偏：历史代码曾把「仅入队」误标为 completed；若仍有待发或在途未计入 done，必须回退为 processing
        if batch.status == BatchStatus.COMPLETED and (pending_cnt > 0 or done < log_total):
            batch.status = BatchStatus.PROCESSING
            batch.completed_at = None
            logger.warning(
                f"批次 {batch_id} 从 completed 回退为 processing："
                f"pending+queued={pending_cnt}, done={done}, log_total={log_total}, total={total}"
            )

        # 状态切换逻辑
        if log_total >= total and done >= log_total:
            # 全部短信已处理完成（成功或失败）
            if failed == 0:
                batch.status = BatchStatus.COMPLETED
            elif sent == 0:
                batch.status = BatchStatus.FAILED
            else:
                batch.status = BatchStatus.COMPLETED
                batch.error_message = f"部分失败: {failed}/{total}"
            batch.completed_at = datetime.now()
            
        elif log_total >= total and pending_cnt > 0 and pending_cnt <= total * 0.02:
            # 兜底清理：如果剩余极少量短信卡在 pending/queued（通常是 Worker 重启导致虚拟通道任务丢失）
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
            
            # 仅对虚拟通道进行自动过期处理
            all_virtual_pending = bool(pend_rows) and all(
                r.protocol == "VIRTUAL" for r in pend_rows
            )
            
            if not all_virtual_pending:
                logger.debug(
                    f"批次存在非虚拟待发(≤2%)，跳过自动过期: batch={batch_id}, pending={pending_cnt}"
                )
                if batch.status != BatchStatus.PROCESSING:
                    batch.status = BatchStatus.PROCESSING
                batch.completed_at = None
            else:
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
                
                # 重新统计
                stats2 = await db.execute(
                    select(SMSLog.status, sa_func.count().label('cnt'))
                    .where(SMSLog.batch_id == batch_id).group_by(SMSLog.status)
                )
                counts2 = {r.status: r.cnt for r in stats2}
                sent2 = counts2.get('sent', 0) + counts2.get('delivered', 0)
                failed2 = counts2.get('failed', 0) + counts2.get('expired', 0)
                
                batch.success_count = sent2
                batch.failed_count = failed2
                batch.processing_count = 0
                batch.progress = 100
                batch.status = BatchStatus.COMPLETED
                batch.completed_at = datetime.now()
                batch.error_message = f"部分失败: {failed2}/{total}" if failed2 > 0 else None
                logger.info(f"批次虚拟通道兜底完成: batch={batch_id}, 清理 {pending_cnt} 条遗留 pending")
        
        elif log_total >= total and batch.status == BatchStatus.COMPLETED:
            # 已完成状态，且没有新记录，保持现状
            pass
        else:
            # 仍在处理中
            if batch.status not in [BatchStatus.COMPLETED, BatchStatus.FAILED, BatchStatus.CANCELLED]:
                batch.status = BatchStatus.PROCESSING
            batch.completed_at = None
            # 如果之前有“部分失败”文案但任务还在跑（重发等），清理掉它
            if batch.error_message and "部分失败" in batch.error_message:
                batch.error_message = None

        await db.commit()

    except Exception as e:
        logger.warning(f"更新批次进度失败: batch_id={batch_id}, {e}")
        await db.rollback()


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
