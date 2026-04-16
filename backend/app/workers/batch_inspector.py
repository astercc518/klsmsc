"""
批次健康巡检 Worker (Inspector)

定期检查状态为 processing 且长时间未更新的批次，根据实际 sms_logs 记录校准其进度和状态。
"""
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from app.workers.celery_app import celery_app
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_log import SMSLog
from app.utils.logger import get_logger
from app.workers.sms_worker import _get_worker_session, _run_async
from app.modules.sms.batch_utils import update_batch_progress

logger = get_logger(__name__)

@celery_app.task(name='inspect_batches_task')
def inspect_batches_task():
    """定期执行的巡检任务"""
    return _run_async(_do_inspect_batches())

async def _do_inspect_batches():
    db = _get_worker_session()
    try:
        # 1. 查找超过 15 分钟未更新且仍在 processing 状态的非虚拟批次
        # (虚拟通道通常由特定的延迟任务处理，巡检重点放在由于 Worker 崩溃导致的同步卡死)
        cutoff = datetime.now() - timedelta(minutes=15)
        
        result = await db.execute(
            select(SmsBatch).where(
                and_(
                    SmsBatch.status == BatchStatus.PROCESSING,
                    SmsBatch.updated_at < cutoff
                )
            )
        )
        stuck_batches = result.scalars().all()
        
        if not stuck_batches:
            logger.debug("未发现卡死的批次")
            return {"stuck_found": 0}
            
        logger.info(f"发现 {len(stuck_batches)} 个疑似卡死的批次，开始校准...")
        
        reconciled = 0
        for batch in stuck_batches:
            try:
                # 调用统一的进度校准逻辑
                await update_batch_progress(db, batch.id)
                
                # 重新查询状态
                await db.refresh(batch)
                
                # 如果校准后仍然是 processing 且确实由于某种原因卡住了(例如所有任务都发完了但没切状态)
                # 检查是否所有号码都有终态
                total = batch.total_count or 0
                res_counts = await db.execute(
                    select(func.count(SMSLog.id)).where(
                        and_(
                            SMSLog.batch_id == batch.id,
                            SMSLog.status.in_(['delivered', 'failed', 'expired', 'rejected'])
                        )
                    )
                )
                finished_count = res_counts.scalar() or 0
                
                if total > 0 and finished_count >= total and batch.status == BatchStatus.PROCESSING:
                    batch.status = BatchStatus.COMPLETED
                    if not batch.completed_at:
                        batch.completed_at = datetime.now()
                    logger.info(f"批次 {batch.id} 所有短信已完成，强制切换状态为 COMPLETED")
                
                await db.commit()
                reconciled += 1
            except Exception as e:
                logger.error(f"校准批次 {batch.id} 失败: {e}")
                await db.rollback()
                
        return {"stuck_found": len(stuck_batches), "reconciled": reconciled}
    finally:
        await db.close()
