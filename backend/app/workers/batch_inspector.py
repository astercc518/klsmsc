"""
批次健康巡检 Worker (Inspector)

定期检查状态为 processing 且长时间未更新的批次，根据实际 sms_logs 记录校准其进度和状态。
同时检测 COMPLETED 批次中虚拟通道 DLR 任务丢失导致的 sent 状态积压，并自动触发修复。

Go 网关全异步后：SMPP 条目不再在网关内同步改库，pending 可能停留较久且可跳过 queued，
经 sms_result_queue 异步变为 sent/failed；巡检阈值须显著放宽，避免误杀正常大队列批次。
可通过环境变量 BATCH_INSPECT_STUCK_MINUTES / BATCH_INSPECT_SMPP_ORPHAN_MINUTES 覆盖（默认 30）。

对「停滞」批次：以 **pending/queued 的最早 submit_time** 早于 BATCH_INSPECT_STUCK_MINUTES 为准（不再仅用
sms_batches.updated_at——否则 sync_processing_batch_progress_task 每 30s 调用 update_batch_progress 会不断刷新
updated_at，导致永远选不中「卡进度」批次）。若仍有 pending/queued，将批量标 failed 并校准进度。
"""
import os
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func, update as _sa_upd_log
from app.workers.celery_app import celery_app
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_log import SMSLog
from app.utils.logger import get_logger
from app.workers.sms_worker import _make_session, _run_async
from app.modules.sms.batch_utils import update_batch_progress

logger = get_logger(__name__)

# 默认 30 分钟：与 Go 异步回写、万级队列积压相匹配；过短会误判「卡死」或把仍在队列中的 SMPP 标为过期
_STUCK_BATCH_MINUTES = int(os.environ.get("BATCH_INSPECT_STUCK_MINUTES", "30"))
_SMPP_ORPHAN_MINUTES = int(os.environ.get("BATCH_INSPECT_SMPP_ORPHAN_MINUTES", "30"))


@celery_app.task(name='sync_processing_batch_progress_task')
def sync_processing_batch_progress_task():
    """每30秒同步 PROCESSING 批次进度（轻量，专为 SMPP/Go 网关写 sent 不经 Python worker 设计）"""
    return _run_async(_do_sync_processing_progress())


async def _do_sync_processing_progress():
    from datetime import timedelta
    from sqlalchemy import and_
    eng, Session = _make_session()
    try:
        async with Session() as db:
            proc_ids = (
                await db.execute(
                    select(SmsBatch.id).where(
                        and_(
                            SmsBatch.status == BatchStatus.PROCESSING,
                            SmsBatch.is_deleted == False,
                            SmsBatch.created_at >= datetime.now() - timedelta(hours=48),
                        )
                    ).order_by(SmsBatch.id.desc()).limit(100)
                )
            ).scalars().all()
            synced = 0
            for bid in proc_ids:
                try:
                    await update_batch_progress(db, bid)
                    synced += 1
                except Exception as e:
                    logger.debug(f"sync_progress: batch {bid} 跳过: {e}")
            return {"synced": synced}
    finally:
        await eng.dispose()


@celery_app.task(name='inspect_batches_task')
def inspect_batches_task():
    """定期执行的巡检任务"""
    return _run_async(_do_inspect_batches())

async def _do_inspect_batches():
    """使用与 sms_worker 一致的独立引擎/会话，避免跨事件循环复用连接池。"""
    eng, Session = _make_session()
    try:
        async with Session() as db:
            # 1. 查找「仍有 pending/queued 且最早一条待发提交时间」早于阈值的 processing 批次。
            # 注意：不能仅用 sms_batches.updated_at——sync_processing_batch_progress_task 会周期性
            # update_batch_progress，updated_at 一直被刷新，超时斩杀永远触发不了。
            cutoff = datetime.now() - timedelta(minutes=_STUCK_BATCH_MINUTES)

            pend_stale_sq = (
                select(SMSLog.batch_id.label("bid"))
                .where(
                    SMSLog.batch_id.isnot(None),
                    SMSLog.status.in_(["pending", "queued"]),
                    SMSLog.submit_time.isnot(None),
                )
                .group_by(SMSLog.batch_id)
                .having(func.min(SMSLog.submit_time) < cutoff)
            ).subquery()

            result = await db.execute(
                select(SmsBatch)
                .join(pend_stale_sq, SmsBatch.id == pend_stale_sq.c.bid)
                .where(
                    SmsBatch.status == BatchStatus.PROCESSING,
                    SmsBatch.is_deleted == False,
                )
                .limit(200)
            )
            stuck_batches = result.scalars().all()

            if not stuck_batches:
                logger.debug("未发现卡死的批次")
            else:
                logger.info(f"发现 {len(stuck_batches)} 个疑似卡死的批次，开始校准...")

            reconciled = 0
            stuck_force_failed = 0
            for batch in stuck_batches:
                try:
                    # 调用统一的进度校准逻辑
                    await update_batch_progress(db, batch.id)

                    # 重新查询状态
                    await db.refresh(batch)

                    # 绝对斩杀：停滞超过 BATCH_INSPECT_STUCK_MINUTES 的批次，无视 batch_utils 内 2% 虚拟兜底限制，
                    # 将仍卡在 pending/queued 的记录标为 failed，避免进度永久卡在 ~97%。
                    pend_q = (
                        await db.execute(
                            select(func.count(SMSLog.id)).where(
                                and_(
                                    SMSLog.batch_id == batch.id,
                                    SMSLog.status.in_(["pending", "queued"]),
                                )
                            )
                        )
                    ).scalar() or 0
                    if pend_q > 0 and batch.status == BatchStatus.PROCESSING:
                        _timeout_msg = "Timeout or dropped by gateway"
                        _now_ts = datetime.now()
                        await db.execute(
                            _sa_upd_log(SMSLog)
                            .where(
                                SMSLog.batch_id == batch.id,
                                SMSLog.status.in_(["pending", "queued"]),
                            )
                            .values(
                                status="failed",
                                error_message=_timeout_msg,
                                sent_time=_now_ts,
                            )
                        )
                        await db.commit()
                        await update_batch_progress(db, batch.id)
                        await db.refresh(batch)
                        stuck_force_failed += int(pend_q)
                        logger.warning(
                            f"inspect: 停滞批次 {batch.id} 超时斩杀 {pend_q} 条 pending/queued → failed"
                        )

                    # 如果校准后仍然是 processing 且确实由于某种原因卡住了
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

            # 2. 检查近期 COMPLETED 批次中是否有虚拟通道 sent 状态积压
            #    [历史根因] 旧版同步批量/CSV 路径曾误在入队后标 COMPLETED；现由 batch_utils 纠偏。
            #    DLR 任务可能因 RabbitMQ ETA/countdown 未被 worker 消费（如 consumer 断连）而积压。
            #    批次已 COMPLETED → inspect_batches_task 原本不会检测 → DLR 永久丢失 → 送达率 0%
            #    修复策略：对 sent 超 60s 且占比 >10% 的 COMPLETED 虚拟通道批次，重新触发 DLR 任务。
            virtual_dlr_cutoff = datetime.now() - timedelta(seconds=60)
            recent_cutoff = datetime.now() - timedelta(minutes=30)

            completed_batches_result = await db.execute(
                select(SmsBatch).where(
                    and_(
                        SmsBatch.status == BatchStatus.COMPLETED,
                        SmsBatch.completed_at >= recent_cutoff,
                    )
                )
            )
            completed_batches = completed_batches_result.scalars().all()

            virtual_repair_count = 0
            for batch in completed_batches:
                try:
                    # 统计发送超过 60s 仍为 sent 的记录
                    sent_rows = (
                        await db.execute(
                            select(SMSLog.message_id, SMSLog.channel_id, SMSLog.sent_time).where(
                                and_(
                                    SMSLog.batch_id == batch.id,
                                    SMSLog.status == "sent",
                                    SMSLog.sent_time <= virtual_dlr_cutoff,
                                )
                            )
                        )
                    ).all()

                    if not sent_rows:
                        continue

                    total = batch.total_count or 1
                    sent_ratio = len(sent_rows) / total

                    # 超过 10% 的 sent 积压才触发修复，避免正常短批次误触发
                    if sent_ratio < 0.10:
                        continue

                    # 按通道分组，仅对虚拟通道执行修复
                    from collections import defaultdict
                    by_cid = defaultdict(list)
                    for r in sent_rows:
                        if r.channel_id:
                            by_cid[r.channel_id].append(r.message_id)

                    from app.modules.sms.channel import Channel
                    from app.workers.sms_worker import virtual_dlr_batch_generate_task
                    for cid, mids in by_cid.items():
                        prot_row = await db.execute(
                            select(Channel.protocol).where(Channel.id == cid)
                        )
                        prot = prot_row.scalar_one_or_none()
                        pv = getattr(prot, "value", prot)
                        pv = getattr(pv, "value", pv)
                        if str(pv or "").upper() != "VIRTUAL":
                            continue

                        chunk_size = 500
                        for bi, start in enumerate(range(0, len(mids), chunk_size)):
                            chunk = mids[start:start + chunk_size]
                            virtual_dlr_batch_generate_task.apply_async(
                                args=[chunk, cid, batch.id],
                                countdown=bi * 2,
                                queue="sms_send",
                            )
                        virtual_repair_count += 1
                        logger.warning(
                            f"inspect: COMPLETED批次={batch.id} 发现 {len(mids)} 条虚拟通道sent积压"
                            f"（{sent_ratio:.1%}），已触发DLR修复 channel_id={cid}"
                        )
                except Exception as e:
                    logger.error(f"检查COMPLETED批次 {batch.id} 虚拟DLR积压失败: {e}")

            # 3. SMPP SubmitSMResp 丢失清理（兜底，Go 网关 OnClosed 应已处理大部分）
            # 仅清理「批次本身已停滞（updated_at 早于阈值）」的孤儿 queued/pending 记录，
            # 且 submit_time 早于阈值：兼容 pending→sent 不经 queued 的新路径，窗口须与队列积压一致。
            smpp_orphan_cutoff = datetime.now() - timedelta(minutes=_SMPP_ORPHAN_MINUTES)
            from sqlalchemy import update as _sa_upd2

            # 停滞批次：与上文一致，用「最早 pending/queued 的 submit_time」判定，避免 updated_at 被同步任务刷没
            orphan_pend_sq = (
                select(SMSLog.batch_id.label("bid"))
                .where(
                    SMSLog.batch_id.isnot(None),
                    SMSLog.status.in_(["pending", "queued"]),
                    SMSLog.submit_time.isnot(None),
                )
                .group_by(SMSLog.batch_id)
                .having(func.min(SMSLog.submit_time) < smpp_orphan_cutoff)
            ).subquery()
            stale_batch_ids_res = await db.execute(
                select(SmsBatch.id)
                .join(orphan_pend_sq, SmsBatch.id == orphan_pend_sq.c.bid)
                .where(
                    SmsBatch.status == BatchStatus.PROCESSING,
                    SmsBatch.is_deleted == False,
                )
                .limit(200)
            )
            stale_batch_ids = stale_batch_ids_res.scalars().all()

            smpp_orphan_cleaned = 0
            if stale_batch_ids:
                r_smpp = await db.execute(
                    _sa_upd2(SMSLog)
                    .where(
                        and_(
                            SMSLog.batch_id.in_(stale_batch_ids),
                            SMSLog.status.in_(['queued', 'pending']),
                            SMSLog.sent_time.is_(None),
                            SMSLog.submit_time < smpp_orphan_cutoff,
                            SMSLog.submit_time.isnot(None),
                        )
                    )
                    .values(
                        status='expired',
                        error_message='SMPP SubmitSMResp丢失: 会话断连导致提交回执未收到，超时标记',
                    )
                )
                smpp_orphan_cleaned = r_smpp.rowcount

            # 无批次归属的孤儿单条消息（batch_id IS NULL），继续用时间兜底清理
            r_smpp_standalone = await db.execute(
                _sa_upd2(SMSLog)
                .where(
                    and_(
                        SMSLog.batch_id.is_(None),
                        SMSLog.status.in_(['queued', 'pending']),
                        SMSLog.sent_time.is_(None),
                        SMSLog.submit_time < smpp_orphan_cutoff,
                        SMSLog.submit_time.isnot(None),
                    )
                )
                .values(
                    status='expired',
                    error_message='SMPP SubmitSMResp丢失: 会话断连导致提交回执未收到，超时标记',
                )
            )
            smpp_orphan_cleaned += r_smpp_standalone.rowcount

            if smpp_orphan_cleaned > 0:
                await db.commit()
                logger.warning(f"inspect: SMPP孤儿queued清理 {smpp_orphan_cleaned} 条 → expired")
                # 触发受影响批次的进度更新
                affected_batches = (
                    await db.execute(
                        select(SMSLog.batch_id)
                        .where(
                            SMSLog.status == 'expired',
                            SMSLog.error_message.like('%SubmitSMResp丢失%'),
                            SMSLog.submit_time >= smpp_orphan_cutoff - timedelta(hours=48),
                        )
                        .distinct()
                        .limit(50)
                    )
                ).scalars().all()
                for bid in affected_batches:
                    if bid:
                        try:
                            await update_batch_progress(db, bid)
                        except Exception:
                            pass

            return {
                "stuck_found": len(stuck_batches),
                "reconciled": reconciled,
                "stuck_force_failed": stuck_force_failed,
                "virtual_dlr_repaired": virtual_repair_count,
                "smpp_orphan_cleaned": smpp_orphan_cleaned,
            }
    finally:
        await eng.dispose()
