"""
批次健康巡检 Worker (Inspector)

定期检查状态为 processing 且长时间未更新的批次，根据实际 sms_logs 记录校准其进度和状态。
同时检测 COMPLETED 批次中虚拟通道 DLR 任务丢失导致的 sent 状态积压，并自动触发修复。

Go 网关全异步后：SMPP 条目不再在网关内同步改库，pending 可能停留较久且可跳过 queued，
经 sms_result_queue 异步变为 sent/failed；巡检阈值须显著放宽，避免误杀正常大队列批次。
可通过环境变量 BATCH_INSPECT_STUCK_MINUTES / BATCH_INSPECT_SMPP_ORPHAN_MINUTES 覆盖（默认 30）。

`update_batch_progress` 已做数值防抖：无实质变化时不写 sms_batches，**updated_at 仅在计数/状态真变时刷新**。
停滞批次巡检恢复为高效的 **sms_batches.updated_at** 条件；若仍有 pending/queued 则执行超时斩杀。
"""
import os
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func, update as _sa_upd_log
from app.workers.celery_app import celery_app
from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_log import SMSLog
from app.utils.logger import get_logger
from app.workers.sms_worker import _make_session, _run_async
from app.modules.sms.batch_utils import update_batch_progress
from app.config import settings

logger = get_logger(__name__)

# 默认 30 分钟：与 Go 异步回写、万级队列积压相匹配；过短会误判「卡死」或把仍在队列中的 SMPP 标为过期
_STUCK_BATCH_MINUTES = int(os.environ.get("BATCH_INSPECT_STUCK_MINUTES", "30"))
_SMPP_ORPHAN_MINUTES = int(os.environ.get("BATCH_INSPECT_SMPP_ORPHAN_MINUTES", "30"))
# SMPP pending 重派发阈值：消息卡 pending 超过此分钟数（且未达 orphan 过期阈值）即视为派发阶段丢失，
# 重新投递回 sms_send_smpp 真正发出去。比 orphan 过期更早介入，把"静默丢失→expired"变为"自动补发"。
_SMPP_REDISPATCH_MINUTES = int(os.environ.get("BATCH_INSPECT_SMPP_REDISPATCH_MINUTES", "5"))
# 派发丢行(分片插库时撞死锁1213/掉线2013整片不入库)对齐 total_count 的空闲阈值。
# 该场景判据强(全部 sms_logs 终态 + 无 pending/queued + log_total<total),远比"杀 pending"安全,
# 故用短得多的空闲即可触发,把"卡 99% 等 30 分钟"缩短到 ~5 分钟自愈。
_LOSTROW_RECONCILE_MINUTES = int(os.environ.get("BATCH_INSPECT_LOSTROW_MINUTES", "5"))

# SMPP 发送队列名（legacy 共用 FIFO，由 Go 网关消费）。
_SMPP_SEND_QUEUE = "sms_send_smpp"
# 每通道队列开关：开启后在途守门必须把各 sms_send_smpp.{id} 队列深度一并计入，
# 否则 backlog 全在每通道队列、legacy 为空 → 守门失效 → 在途批次被误判卡死斩杀(丢消息)。
_SMPP_PER_CHANNEL_QUEUES = os.environ.get("SMPP_PER_CHANNEL_QUEUES", "0").strip().lower() in (
    "1", "true", "yes", "on",
)
_SMPP_QUEUE_PREFIX = "sms_send_smpp."
# 在途守门阈值：sms_send_smpp 堆积超过此数量时，认定网关仍在排空、SMPP pending/queued 仍在途，
# 暂缓一切对 SMPP 记录的斩杀/过期。0 = 只要队列非空就守门。
# [事故根因] 批次 1118-1120 共 9 万条排在共用队列尾部，30 分钟内未轮到网关消费，
# 却被「30 分钟空闲即斩杀」当成卡死全标 failed——比网关真正取到只早了约 30 秒。
_SMPP_QUEUE_ALIVE_THRESHOLD = int(os.environ.get("BATCH_INSPECT_SMPP_QUEUE_ALIVE", "0"))

# 结果回写队列：process_sms_result_task 消费它，把 pending→sent/failed 写回 sms_logs。
# [事故根因 1638/1639] sms_send_smpp 已排空(发送队列守门=0、未生效)，但结果回写队列积压 15w，
# pending 的 log 迟迟翻不成 sent；批次空闲超 30min 被「超时斩杀」全标 failed，9 分钟后回写追上
# 又把 log 改回 sent，主记录却永久卡 failed。这说明在途守门只盯发送队列有盲区：回写滞后期间
# 「pending」多半是「已提交上游、回写没追上」而非「卡死/丢失」，同样不能斩杀。
# 超此积压量即认定回写滞后，暂缓对 pending 的斩杀/过期。-1=探测失败→回退旧行为（不守门）。
_RESULT_WRITEBACK_QUEUE = "sms_result_queue"
_RESULT_BACKLOG_ALIVE_THRESHOLD = int(os.environ.get("BATCH_INSPECT_RESULT_BACKLOG_ALIVE", "500"))

# 反向校准窗口：被斩杀标 FAILED 的批次，若回写追上后底层实际有 sent/delivered，说明此前是
# 「回写滞后误判」而非真失败 —— 在此窗口内的 FAILED 批次重算进度自愈翻回 COMPLETED。
# 韧性兜底：即便守门偶有疏漏，下一轮巡检也能把误杀的批次纠回，不再依赖「斩杀那刻没出错」。
_REVERSE_RECONCILE_HOURS = int(os.environ.get("BATCH_INSPECT_REVERSE_HOURS", "6"))
# RabbitMQ 管理 API 端口：在途守门用它读队列「ready+unacked」总量。
# [事故根因 1551/1553] Python 按 chunk 把最多 2000 条 SMS 打成「一条整包 AMQP 消息」投递，
# 网关每通道 consumer prefetch=16，整包一被取走即变 unacked、要逐条按通道 TPS 慢慢吐(30 TPS≈67s/包)。
# AMQP passive queue_declare 只回 message_count(=ready，**不含 unacked**)，于是 6000 条正攥在
# 网关里慢慢发，message_count 却显示 0 → 守门误判「无积压」→ 30 分钟空闲斩杀。
# 管理 API 的 messages 字段 = ready+unacked，能看见网关攥住的在途整包，根治该盲区。
_RABBITMQ_MGMT_PORT = int(os.environ.get("RABBITMQ_MGMT_PORT", "15672"))


def _smpp_queue_total_via_mgmt(queues: list) -> Optional[int]:
    """用 RabbitMQ 管理 API 求 queues 的「messages = ready + unacked」总量；探测失败返回 None。

    必须算上 unacked：网关 prefetch 把整包(最多 2000 条 SMS)取走后即为 unacked、正按通道 TPS
    慢慢吐，AMQP message_count 看不见它们。漏掉 unacked 会让守门把在途批次误判为卡死（1551/1553）。

    单次请求列出本 vhost 全部队列(只取 name,messages 两列)再按名求和——与 SMPP 通道数无关，
    避免逐队列 N 次 HTTP；任一异常即返回 None 由调用方回退 AMQP message_count 探测。
    """
    import json as _json
    import urllib.request as _ur
    import urllib.parse as _up
    import base64 as _b64

    host = settings.RABBITMQ_HOST or "rabbitmq"
    vhost = _up.quote(settings.RABBITMQ_VHOST or "/", safe="")  # "/" → %2F
    auth = _b64.b64encode(f"{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASSWORD}".encode()).decode()
    url = f"http://{host}:{_RABBITMQ_MGMT_PORT}/api/queues/{vhost}?columns=name,messages"
    req = _ur.Request(url, headers={"Authorization": f"Basic {auth}"})
    try:
        with _ur.urlopen(req, timeout=4) as resp:
            rows = _json.loads(resp.read().decode())
    except Exception as e:
        logger.debug(f"inspect: 管理 API 读队列列表异常，回退 AMQP 探测: {e}")
        return None
    if not isinstance(rows, list):
        return None
    wanted = set(queues)
    by_name = {r.get("name"): int(r.get("messages") or 0) for r in rows if isinstance(r, dict)}
    return sum(by_name.get(q, 0) for q in wanted)


def _smpp_send_queue_depth(extra_queues: Optional[list] = None) -> int:
    """读取 SMPP 发送队列总堆积条数（legacy + 传入的每通道队列）；-1 表示探测失败（未知）。

    用于区分『消息仍在网关队列排队在途』与『真卡死/丢失』：队列非空时网关只是积压、并未死，
    此时绝不能把排队中的 SMPP pending/queued 误判为超时。探测失败回退旧行为（按时间斩杀）。

    优先走管理 API 取 ready+unacked 总量（含网关 prefetch 攥住的在途整包）；管理 API 不可用时
    回退 AMQP passive 探测——后者只能拿 message_count(ready)，会漏 unacked，但聊胜于无。

    extra_queues — 每通道队列名列表(sms_send_smpp.{id})；逐个探测求和，
    单个不存在(尚无消息→未声明)按 0 计，不影响其它队列。
    """
    queues = [_SMPP_SEND_QUEUE] + list(extra_queues or [])

    mgmt_total = _smpp_queue_total_via_mgmt(queues)
    if mgmt_total is not None:
        return mgmt_total

    total = 0
    probed_any = False
    for qname in queues:
        try:
            with celery_app.connection_for_read() as conn:
                q = conn.default_channel.queue_declare(queue=qname, passive=True)
                total += int(q.message_count)
                probed_any = True
        except Exception as e:
            # legacy 队列探测失败=未知，回退旧行为；每通道队列不存在(未声明)按 0 计入。
            if qname == _SMPP_SEND_QUEUE:
                logger.debug(f"inspect: 读取 {qname} 队列深度失败: {e}")
                return -1
            logger.debug(f"inspect: 每通道队列 {qname} 不存在/探测失败，按 0 计: {e}")
    return total if probed_any else -1


def _result_writeback_backlog() -> int:
    """读取结果回写队列(sms_result_queue)堆积条数；-1 表示探测失败(未知)。

    优先走管理 API 取 ready+unacked（与 SMPP 守门同口径）；不可用时回退 AMQP message_count。
    用于区分『pending 是回写没追上(已提交上游)』与『真卡死/丢失』——前者绝不能斩杀。
    """
    mgmt = _smpp_queue_total_via_mgmt([_RESULT_WRITEBACK_QUEUE])
    if mgmt is not None:
        return mgmt
    try:
        with celery_app.connection_for_read() as conn:
            q = conn.default_channel.queue_declare(queue=_RESULT_WRITEBACK_QUEUE, passive=True)
            return int(q.message_count)
    except Exception as e:
        logger.debug(f"inspect: 读取 {_RESULT_WRITEBACK_QUEUE} 队列深度失败: {e}")
        return -1


async def _active_smpp_channel_queue_names(db) -> list:
    """每通道队列开启时，列出活跃 SMPP 通道对应的 sms_send_smpp.{id} 队列名(供在途守门求和)。"""
    if not _SMPP_PER_CHANNEL_QUEUES:
        return []
    from app.modules.sms.channel import Channel as _Ch
    rows = (
        await db.execute(
            select(_Ch.id).where(
                and_(_Ch.protocol == "SMPP", _Ch.status == "active", _Ch.is_deleted == False)
            )
        )
    ).scalars().all()
    return [f"{_SMPP_QUEUE_PREFIX}{cid}" for cid in rows]


async def _batch_has_smpp_pending(db, batch_id) -> bool:
    """批次是否还有 SMPP 通道的 pending/queued 记录（用于在途守门时判断要不要暂缓斩杀）。"""
    from app.modules.sms.channel import Channel as _Ch
    cnt = (
        await db.execute(
            select(func.count(SMSLog.id))
            .select_from(SMSLog)
            .join(_Ch, SMSLog.channel_id == _Ch.id)
            .where(
                and_(
                    SMSLog.batch_id == batch_id,
                    SMSLog.status.in_(["pending", "queued"]),
                    _Ch.protocol == "SMPP",
                )
            )
        )
    ).scalar() or 0
    return cnt > 0


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
            # 覆盖三类批次：
            # 1) processing 批次（近 48h 创建）— 正常进度推进
            # 2) completed 批次（近 24h 完成）— 覆盖 DLR 延迟到达：批次虽被标 completed，
            #    后续仍会陆续收到 DLR 更新 sms_logs.status=delivered，sms_batches.delivered_count
            #    必须随之刷新，否则前端"送达率"停留在错误快照。
            # 3) cancelled 批次（近 24h 完成）— 客户中途取消但已 submit 给上游的部分仍会陆续
            #    回 DLR；若不刷新 sms_batches 计数，「送达率」就会卡在 0（batch 538 事故）。
            #    24h 窗口配合 channels.dlr_sent_timeout_hours（默认 72h）：上游推迟达 1 天的 DLR
            #    仍会反映到批次汇总；再晚的属于异常，由人工 SQL 回填或调低通道 DLR 超时阈值处理。
            now = datetime.now()
            proc_ids = (
                await db.execute(
                    select(SmsBatch.id).where(
                        and_(
                            SmsBatch.status == BatchStatus.PROCESSING,
                            SmsBatch.is_deleted == False,
                            SmsBatch.created_at >= now - timedelta(hours=48),
                        )
                    ).order_by(SmsBatch.id.desc()).limit(100)
                )
            ).scalars().all()
            recent_done_ids = (
                await db.execute(
                    select(SmsBatch.id).where(
                        and_(
                            SmsBatch.status.in_([BatchStatus.COMPLETED, BatchStatus.CANCELLED]),
                            SmsBatch.is_deleted == False,
                            SmsBatch.completed_at >= now - timedelta(hours=24),
                        )
                    ).order_by(SmsBatch.id.desc()).limit(200)
                )
            ).scalars().all()
            all_ids = list(proc_ids) + [bid for bid in recent_done_ids if bid not in set(proc_ids)]
            updated = 0
            for bid in all_ids:
                try:
                    if await update_batch_progress(db, bid):
                        updated += 1
                except Exception as e:
                    logger.debug(f"sync_progress: batch {bid} 跳过: {e}")
            return {"scanned": len(all_ids), "processing": len(proc_ids), "recent_done": len(recent_done_ids), "updated": updated}
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
            # 1. 停滞 processing 批次：updated_at 早于阈值（依赖 batch_utils 防抖后「真变才刷」）。
            #    两档:派发丢行对齐 total_count 用短空闲(_LOSTROW_RECONCILE_MINUTES)快速自愈;
            #    杀 pending/queued 等激进操作仍需长空闲(_STUCK_BATCH_MINUTES),避免误杀在途 SMPP。
            now_ = datetime.now()
            scan_cutoff = now_ - timedelta(minutes=min(_STUCK_BATCH_MINUTES, _LOSTROW_RECONCILE_MINUTES))
            stuck_cutoff = now_ - timedelta(minutes=_STUCK_BATCH_MINUTES)

            result = await db.execute(
                select(SmsBatch).where(
                    and_(
                        SmsBatch.status == BatchStatus.PROCESSING,
                        SmsBatch.is_deleted == False,
                        SmsBatch.updated_at < scan_cutoff,
                    )
                ).limit(200)
            )
            stuck_batches = result.scalars().all()

            if not stuck_batches:
                logger.debug("未发现卡死的批次")
            else:
                logger.info(f"发现 {len(stuck_batches)} 个疑似卡死的批次，开始校准...")

            # 在途守门信号（每轮巡检读一次）：SMPP 发送队列仍有积压时，网关只是排空慢、并未死，
            # 排队中的 SMPP pending/queued 不得被斩杀/过期。-1=探测失败→回退旧的按时间收割。
            # 每通道队列开启时把各 sms_send_smpp.{id} 一并计入，否则 backlog 全在每通道队列、
            # legacy 为空会导致守门失效、在途批次被误杀。
            _smpp_extra_queues = await _active_smpp_channel_queue_names(db)
            _smpp_backlog = _smpp_send_queue_depth(_smpp_extra_queues)
            _smpp_inflight = _smpp_backlog > _SMPP_QUEUE_ALIVE_THRESHOLD
            if _smpp_inflight:
                logger.info(
                    f"inspect: sms_send_smpp 仍积压 {_smpp_backlog} 条，本轮暂缓斩杀/过期 SMPP 在途记录"
                )

            # 结果回写守门：sms_result_queue 积压时，pending 多为「已提交上游、回写没追上」，
            # 不得斩杀/过期（事故 1638/1639）。-1=探测失败→不守门，回退旧的按时间收割。
            _result_backlog = _result_writeback_backlog()
            _result_lagging = _result_backlog > _RESULT_BACKLOG_ALIVE_THRESHOLD
            if _result_lagging:
                logger.info(
                    f"inspect: sms_result_queue 积压 {_result_backlog} 条，结果回写滞后，"
                    f"本轮暂缓斩杀/过期仍 pending 的记录（多为已提交上游、回写未追上）"
                )

            reconciled = 0
            stuck_force_failed = 0
            for batch in stuck_batches:
                try:
                    # 选中时的空闲程度(用于区分短空闲快速对齐 vs 长空闲才允许激进斩杀)
                    orig_updated = batch.updated_at
                    idle_long = orig_updated is not None and orig_updated < stuck_cutoff

                    # 调用统一的进度校准逻辑
                    await update_batch_progress(db, batch.id)

                    # 重新查询状态
                    await db.refresh(batch)

                    # 绝对收口：停滞超过 BATCH_INSPECT_STUCK_MINUTES 的批次，无视 batch_utils 内 2% 虚拟兜底限制，
                    # 将仍卡在 pending/queued 的记录收口，避免进度永久卡在 ~97%。仅长空闲档执行。
                    # [治本 1638/1639] 收口写 expired（"超时未知"）而非 failed（"发送失败"）：超时只是
                    # 我们放弃等待，不是上游拒收的正面证据；时钟不能制造"发送失败"这种结论。expired 仍可被
                    # 后续真实回写(_apply_sms_result_row_to_db 无终态保护)覆盖回 sent/delivered，故误判可自愈。
                    # 且只碰 sent_time IS NULL 的记录——已拿到上游提交结果的(情况iii)绝不动。
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
                    # 在途守门：网关发送队列仍有积压时，本批的 SMPP pending/queued 极可能仍排队等消费，
                    # 并非真卡死。跳过斩杀，留给队列自然排空（或排空后再由下方 orphan 兜底）。
                    _smpp_inflight_guard = (
                        pend_q > 0
                        and batch.status == BatchStatus.PROCESSING
                        and idle_long
                        and _smpp_inflight
                        and await _batch_has_smpp_pending(db, batch.id)
                    )
                    # 结果回写守门：回写队列积压时，pending 多半是「已提交上游、回写没追上」，
                    # 斩杀会把真实已发的消息误标 failed（事故 1638/1639）。暂缓，等回写追上。
                    _result_lag_guard = (
                        pend_q > 0
                        and batch.status == BatchStatus.PROCESSING
                        and idle_long
                        and _result_lagging
                    )
                    if _smpp_inflight_guard:
                        logger.warning(
                            f"inspect: 批次 {batch.id} 有 SMPP pending/queued，但 sms_send_smpp 仍积压 "
                            f"{_smpp_backlog} 条，判定为在途、暂缓斩杀（等队列排空）"
                        )
                    elif _result_lag_guard:
                        logger.warning(
                            f"inspect: 批次 {batch.id} 有 {pend_q} 条 pending/queued，但 sms_result_queue 仍积压 "
                            f"{_result_backlog} 条，判定为回写滞后(多已提交上游)、暂缓斩杀（等回写追上）"
                        )
                    elif pend_q > 0 and batch.status == BatchStatus.PROCESSING and idle_long:
                        _timeout_msg = "超时未在时限内收到上游提交结果，标记为未知(expired)；如后续回执到达将自动覆盖"
                        _now_ts = datetime.now()
                        _r_exp = await db.execute(
                            _sa_upd_log(SMSLog)
                            .where(
                                SMSLog.batch_id == batch.id,
                                SMSLog.status.in_(["pending", "queued"]),
                                SMSLog.sent_time.is_(None),  # 已拿到提交结果的(情况iii)绝不动
                            )
                            .values(
                                status="expired",
                                error_message=_timeout_msg,
                                sent_time=_now_ts,
                            )
                        )
                        await db.commit()
                        await update_batch_progress(db, batch.id)
                        await db.refresh(batch)
                        _exp_cnt = int(_r_exp.rowcount or 0)
                        stuck_force_failed += _exp_cnt
                        logger.warning(
                            f"inspect: 停滞批次 {batch.id} 超时收口 {_exp_cnt} 条 pending/queued → expired"
                            f"（共 {pend_q} 条待处理，已提交未回写的不动）"
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

                    # 派发阶段丢失：sms_logs 实际记录数 < total_count，且无任何 pending/queued 积压。
                    # 说明部分消息在 batch_worker 写库/入队前就被丢弃，永远不会出现在 sms_logs。
                    # batch_utils 的完成判断依赖 log_total >= total，此时永远无法满足 → 批次永久卡住。
                    # 修复：将 total_count 对齐实际记录数，让 update_batch_progress 下一轮完成校准。
                    if batch.status == BatchStatus.PROCESSING and pend_q == 0 and total > 0:
                        log_total_cnt = (
                            await db.execute(
                                select(func.count(SMSLog.id)).where(SMSLog.batch_id == batch.id)
                            )
                        ).scalar() or 0
                        if 0 < log_total_cnt < total:
                            lost = total - log_total_cnt
                            batch.total_count = log_total_cnt
                            logger.warning(
                                f"inspect: 批次 {batch.id} 派发丢失 {lost} 条（total_count {total}→{log_total_cnt}）"
                                f"，对齐 total_count 后重新校准"
                            )
                            await db.commit()
                            await update_batch_progress(db, batch.id)
                            await db.refresh(batch)

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

            # 2.5 SMPP pending 重派发（修复"派发阶段丢失致整批卡 99%/100 条静默 pending"）：
            # pending 期望等价于"从未成功 submit 到上游"——submit 到 socket 成功的消息在会话断连时
            # 会被 Go 网关 OnClosed 标为 sent（非 pending），故 pending 重发期望安全、无重复风险；
            # 与下方 expire 的本质区别：① 直接针对消息、不等整批 updated_at 停滞（854 因回执持续刷新
            # updated_at 拖了 2 小时才被 expire，正是此门控之过）；② 只补 pending、绝不碰 queued
            # （queued 可能已提交，重发有重复风险）。Redis NX 保证每条在可恢复窗口内至多重派发一次，
            # 超 _SMPP_ORPHAN_MINUTES 仍 pending 才由下方 expire 兜底。
            # [双发护栏 1638/1639] 上面"pending=未提交"的前提在结果回写积压时不成立：消息其实已 submit、
            # sent 状态正堵在 sms_result_queue 没落库，DB 仍显示 pending。此时重派发=对上游双发/双扣费。
            # 故回写滞后(_result_lagging)时整段跳过，等回写追上再判定。
            try:
                _rd_hi = datetime.now() - timedelta(minutes=_SMPP_REDISPATCH_MINUTES)  # 卡超此才补（避开在途新消息）
                _rd_lo = datetime.now() - timedelta(minutes=_SMPP_ORPHAN_MINUTES)      # 早于此放弃补发，交 expire
                from app.modules.sms.channel import Channel as _RDCh
                from app.utils.smpp_payload import smpp_payload_public_dict as _rd_pl

                if _result_lagging:
                    logger.info(
                        f"inspect: sms_result_queue 积压 {_result_backlog} 条，跳过本轮 SMPP pending 重派发"
                        f"（pending 可能是已提交上游、回写未追上，重派发会双发）"
                    )
                    _rd_rows = []
                else:
                    _rd_rows = (await db.execute(
                        select(SMSLog, SmsBatch.status)
                        .select_from(SMSLog)
                        .join(_RDCh, SMSLog.channel_id == _RDCh.id)
                        .join(SmsBatch, SMSLog.batch_id == SmsBatch.id)
                        .where(
                            and_(
                                _RDCh.protocol == "SMPP",
                                SMSLog.status == "pending",
                                SMSLog.sent_time.is_(None),
                                SMSLog.submit_time.isnot(None),
                                SMSLog.submit_time < _rd_hi,
                                SMSLog.submit_time >= _rd_lo,
                                SmsBatch.status == BatchStatus.PROCESSING,
                                SmsBatch.is_deleted == False,
                            )
                        )
                        .limit(2000)
                    )).all()

                if _rd_rows:
                    from app.utils.cache import get_redis_client
                    from app.utils.queue import QueueManager
                    _rc = await get_redis_client()
                    _rd_payloads = []
                    for _rd_row, _rd_bstat in _rd_rows:
                        try:
                            # NX + 30min TTL：每条在可恢复窗口内至多补发一次，杜绝慢/挂网关下的重复 submit
                            _rd_fresh = await _rc.set(
                                f"smsc:smpp_redispatch:{_rd_row.message_id}", "1",
                                nx=True, ex=_SMPP_ORPHAN_MINUTES * 60,
                            )
                        except Exception:
                            _rd_fresh = True  # Redis 故障不阻断补发
                        if _rd_fresh:
                            _rd_payloads.append(_rd_pl(_rd_row, getattr(_rd_bstat, "value", str(_rd_bstat or ""))))
                    if _rd_payloads:
                        for _rd_i in range(0, len(_rd_payloads), 500):
                            QueueManager.queue_sms_batch_smpp(_rd_payloads[_rd_i:_rd_i + 500])
                        logger.warning(
                            f"inspect: SMPP pending 重派发 {len(_rd_payloads)} 条 → sms_send_smpp（派发阶段丢失自动补发）"
                        )
            except Exception as _rd_err:
                logger.error(f"inspect: SMPP pending 重派发异常: {_rd_err}")

            # 3. SMPP SubmitSMResp 丢失清理（兜底，Go 网关 OnClosed 应已处理大部分）
            # 仅清理「批次本身已停滞（updated_at 早于阈值）」的孤儿 queued/pending 记录，
            # 且 submit_time 早于阈值：兼容 pending→sent 不经 queued 的新路径，窗口须与队列积压一致。
            smpp_orphan_cutoff = datetime.now() - timedelta(minutes=_SMPP_ORPHAN_MINUTES)
            from sqlalchemy import update as _sa_upd2

            # 停滞批次：sms_batches.updated_at 早于阈值（与防抖后的进度刷新语义一致）
            stale_batch_ids_res = await db.execute(
                select(SmsBatch.id).where(
                    and_(
                        SmsBatch.status == BatchStatus.PROCESSING,
                        SmsBatch.is_deleted == False,
                        SmsBatch.updated_at < smpp_orphan_cutoff,
                    )
                ).limit(200)
            )
            stale_batch_ids = stale_batch_ids_res.scalars().all()

            smpp_orphan_cleaned = 0
            if _smpp_inflight:
                # 在途守门：发送队列仍积压时，pending/queued 大多仍排队等网关消费，不做过期收割，
                # 避免与第 1 步同样的「排队中被误判超时」。待队列排空后下一轮再兜底。
                logger.info(
                    f"inspect: sms_send_smpp 积压 {_smpp_backlog} 条，跳过本轮 SMPP 孤儿过期清理"
                )
                stale_batch_ids = []
            elif _result_lagging:
                # 结果回写守门：回写队列积压时 pending 多为已提交上游、回写没追上，不做过期收割
                # （与第 1 步同源盲区，事故 1638/1639）。待回写追上后下一轮再兜底。
                logger.info(
                    f"inspect: sms_result_queue 积压 {_result_backlog} 条，跳过本轮 SMPP 孤儿过期清理"
                )
                stale_batch_ids = []
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
            # 同样受在途守门：发送队列/结果回写队列仍积压时这些消息可能仍在途，不收割。
            if not _smpp_inflight and not _result_lagging:
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

            # 4. 反向校准（误杀自愈）：近窗口内被标 FAILED、但底层实际已有 sent/delivered 的批次，
            #    重算进度翻回 COMPLETED。真失败批 sent/delivered=0，绝不会被翻案（update_batch_progress
            #    仅在 done>=log_total 且 sent>0 时判 COMPLETED；sent==0 仍判 FAILED）。
            reverse_healed = 0
            try:
                revive_cutoff = datetime.now() - timedelta(hours=_REVERSE_RECONCILE_HOURS)
                revive_ids = (
                    await db.execute(
                        select(SMSLog.batch_id)
                        .where(
                            SMSLog.status.in_(["sent", "delivered"]),
                            SMSLog.batch_id.in_(
                                select(SmsBatch.id).where(
                                    and_(
                                        SmsBatch.status == BatchStatus.FAILED,
                                        SmsBatch.is_deleted == False,
                                        SmsBatch.completed_at >= revive_cutoff,
                                    )
                                )
                            ),
                        )
                        .group_by(SMSLog.batch_id)
                        .limit(200)
                    )
                ).scalars().all()
                for bid in revive_ids:
                    if not bid:
                        continue
                    try:
                        await update_batch_progress(db, bid)
                        b_now = (
                            await db.execute(select(SmsBatch.status).where(SmsBatch.id == bid))
                        ).scalar()
                        b_now_val = getattr(b_now, "value", b_now)
                        if str(b_now_val).lower() != "failed":
                            reverse_healed += 1
                            logger.warning(
                                f"inspect: 批次 {bid} 底层实际有成功记录，FAILED→{b_now_val} 反向校准自愈"
                                f"（此前疑似回写滞后被误杀）"
                            )
                    except Exception as _re:
                        logger.error(f"inspect: 批次 {bid} 反向校准失败: {_re}")
                        await db.rollback()
            except Exception as _rev_err:
                logger.error(f"inspect: 反向校准扫描异常: {_rev_err}")

            return {
                "stuck_found": len(stuck_batches),
                "reconciled": reconciled,
                "stuck_force_failed": stuck_force_failed,
                "virtual_dlr_repaired": virtual_repair_count,
                "smpp_orphan_cleaned": smpp_orphan_cleaned,
                "reverse_healed": reverse_healed,
            }
    finally:
        await eng.dispose()


@celery_app.task(name='refresh_staff_commission_cache_task')
def refresh_staff_commission_cache_task():
    """每 25 分钟预热员工月度业绩缓存，避免首次打开员工管理页需全表扫描 sms_logs"""
    return _run_async(_do_refresh_staff_commission_cache())


async def _do_refresh_staff_commission_cache():
    import json as _json
    from sqlalchemy import select, func, and_
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.channel import Channel
    from app.modules.common.account import Account
    from app.utils.cache import get_redis_client

    eng, Session = _make_session()
    try:
        async with Session() as db:
            first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            comm_query = (
                select(Account.sales_id, func.sum(SMSLog.profit).label("total_profit"))  # profit 已是整条(含分段)总利润，勿再乘 message_count（审计 P0-1）
                .select_from(SMSLog)
                .join(Account, SMSLog.account_id == Account.id)
                .join(Channel, SMSLog.channel_id == Channel.id)
                .where(
                    and_(
                        SMSLog.submit_time >= first_day,
                        SMSLog.status == "delivered",
                        Channel.protocol != "VIRTUAL",
                    )
                )
                .group_by(Account.sales_id)
            )
            comm_result = await db.execute(comm_query)
            comm_map = {r.sales_id: float(r.total_profit or 0) for r in comm_result}

        ym = datetime.now().strftime("%Y-%m")
        redis = await get_redis_client()
        await redis.setex(f"admin:monthly_commission:{ym}", 1800, _json.dumps(comm_map))
        logger.info(f"员工月度业绩缓存已刷新: {len(comm_map)} 个销售, month={ym}")
        return {"refreshed": len(comm_map), "month": ym}
    finally:
        await eng.dispose()


@celery_app.task(name='refresh_admin_dashboard_cache_task')
def refresh_admin_dashboard_cache_task():
    """每 4 分钟预热管理员仪表板缓存。

    /admin/dashboard 对 sms_logs(当月分区 650w+ 行)做十几条全表聚合，冷算 ~60-120s；
    缓存 TTL 300s 但此前并无预热，每 5 分钟自然过期后下一个请求即撞冷算 → 前端 120s 超时报错。
    这里把 super_admin/admin/finance/tech 四个全局角色(共享 role 维度缓存)提前算好写回，让用户常态命中。
    sales 角色按 account_id 过滤(走 idx_account_time)冷算成本低，不在预热范围。
    """
    # _run_async 默认 60s 超时会半途砍掉冷算(全表聚合 ~60-120s)；本任务独占路由锁、无并发，
    # 给它 200s 预算，足够算完且 <240s 调度周期。
    return _run_async(_do_refresh_admin_dashboard_cache(), timeout=200)


async def _do_refresh_admin_dashboard_cache():
    from types import SimpleNamespace
    from app.api.v1.admin import get_admin_dashboard, _dashboard_preheat_force
    from app.utils.cache import get_redis_client

    redis = await get_redis_client()
    # 单实例锁：周期 240s 但冷算可能 ~50s，避免 beat 抖动/上一轮未完导致并发预热叠加冲击 DB
    if not await redis.set("admin_dashboard:preheat:lock", "1", nx=True, ex=230):
        logger.info("仪表板缓存预热跳过：上一轮仍在进行")
        return {"skipped": True}
    # 抢路由的单飞锁：预热用 ContextVar 强制重算(绕过缓存读)，必须独占该锁，否则会与某个
    # 在线请求(它抢到锁后也会冷算)并发双重全表扫描，撞 net_write_timeout=60s → 2013。
    # 持锁期间在线请求拿不到锁 → 走 stale / 轮询等本任务写好缓存，全局仅一个计算者。
    _route_lock = "admin_dashboard:role:super_admin:lock"
    if not await redis.set(_route_lock, "1", nx=True, ex=240):
        logger.info("仪表板缓存预热跳过：已有在线请求在计算")
        await redis.delete("admin_dashboard:preheat:lock")
        return {"skipped": True, "reason": "route_locked"}
    # 仪表板十几条全表聚合冷算可达 ~60-120s；worker 默认 asyncmy read_timeout=30s 会半途撕连接(2013)。
    # 本任务独占路由锁、绝无并发争用，给它分钟级读超时单独计算。
    eng, Session = _make_session(read_timeout=180)
    # 置 ContextVar 强制 get_admin_dashboard 跳过缓存读、重算并覆盖；不删旧键 →
    # 重算期间在线请求仍命中旧热缓存(240s<300s TTL 保证不过期)，绝不与预热并发冷扫描同一分区。
    token = _dashboard_preheat_force.set(True)
    try:
        # super_admin 与 admin 角色的 payload 完全一致(同为全局视图、权限位相同)，只冷算一次
        # 再镜像到 admin 键，省掉一遍十几条 sms_logs 全表聚合。
        # finance/tech 较少访问，由路由的 stale 兜底逻辑覆盖，不在预热范围。
        fake_admin = SimpleNamespace(role="super_admin", id=None, username="__preheat__")
        try:
            async with Session() as db:
                await get_admin_dashboard(fake_admin, db)  # 内部写 super_admin 的 live+stale 缓存
        except Exception as e:
            # 冷算可能撞 (2013) MySQL 连接超时/并发争用；记日志即可，旧热缓存+stale 兜底，下一轮自愈
            logger.warning(f"仪表板缓存预热计算失败(将于下轮重试): {e}")
            return {"warmed": 0, "error": str(e)[:120]}
        val = await redis.get("admin_dashboard:role:super_admin")
        if val:
            await redis.setex("admin_dashboard:role:admin", 300, val)
            await redis.setex("admin_dashboard:role:admin:stale", 86400, val)
            logger.info("管理员仪表板缓存预热完成: super_admin + admin")
            return {"warmed": 2}
        logger.warning("仪表板缓存预热: super_admin 计算后未取到缓存值")
        return {"warmed": 0}
    finally:
        _dashboard_preheat_force.reset(token)
        await eng.dispose()
        for _k in (_route_lock, "admin_dashboard:preheat:lock"):
            try:
                await redis.delete(_k)
            except Exception:
                pass


@celery_app.task(name='refresh_business_report_cache_task')
def refresh_business_report_cache_task():
    """预热业务报表缓存，避免管理员首次打开报表页等待 ~17s 扫 sms_logs。"""
    return _run_async(_do_refresh_business_report_cache())


async def _do_refresh_business_report_cache():
    from app.services.reports_service import ReportsService

    eng, Session = _make_session()
    try:
        warmed = 0
        # 覆盖前端会展示的常用组合（last_month 数据已冻结，缓存值有意义）
        targets = [
            (dim, biz, tr)
            for dim in ("customer", "employee", "channel", "supplier", "country")
            for biz in ("sms", "all")
            for tr in ("last_month", "this_month")
        ]
        for dim, biz, tr in targets:
            try:
                async with Session() as db:
                    await ReportsService.get_business_report(db, dim, biz, tr)
                warmed += 1
            except Exception as e:
                logger.warning(f"业务报表预热失败 {dim}/{biz}/{tr}: {e}")
        logger.info(f"业务报表缓存预热完成: {warmed}/{len(targets)} 项")
        return {"warmed": warmed, "total": len(targets)}
    finally:
        await eng.dispose()


@celery_app.task(name="refresh_sms_daily_stats_task")
def refresh_sms_daily_stats_task():
    """每 5 分钟重建最近 3 天的发送统计聚合（覆盖延迟到达的 DLR 状态）。"""
    return _run_async(_do_refresh_sms_daily_stats(), timeout=180)


async def _do_refresh_sms_daily_stats():
    import redis.asyncio as aioredis

    from app.services.sms_daily_stats import refresh_daily_stats

    # Celery 的 _run_async 每次创建新事件循环，不能复用 app.utils.cache 的全局客户端；
    # 否则前一个任务关闭 loop 后会报 Event loop is closed。任务内使用独立短连接。
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    lock_key = "sms_daily_stats:refresh:lock"
    try:
        if not await redis.set(lock_key, "1", nx=True, ex=240):
            return {"skipped": True, "reason": "locked"}

        eng, Session = _make_session(read_timeout=180)
        today = datetime.now().date()
        start_date = today - timedelta(days=2)
        try:
            async with Session() as db:
                rows = await refresh_daily_stats(db, start_date, today)
        finally:
            await eng.dispose()
        # 页面热缓存最长 15 分钟，自然过期即可。不要在大键空间用 SCAN 全库找缓存键，
        # 实测 SQL 仅 0.4s，而两次 SCAN 会额外阻塞约 90s。
        logger.info("发送统计日聚合刷新完成: {} ~ {}, {} 行", start_date, today, rows)
        return {
            "success": True,
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "rows": rows,
        }
    except Exception as exc:
        logger.warning("发送统计日聚合刷新失败: {}", exc)
        return {"success": False, "error": str(exc)[:200]}
    finally:
        try:
            await redis.delete(lock_key)
        except Exception:
            pass
        await redis.aclose()
