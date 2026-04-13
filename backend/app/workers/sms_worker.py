"""
短信发送Worker
"""
import contextlib
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple
from sqlalchemy import select
from celery.exceptions import Retry

from app.workers.celery_app import celery_app
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import settings

_worker_engine = None
_worker_session_factory = None
_http_client = None


def _get_worker_engine():
    """进程级单例引擎，避免每次任务新建连接池"""
    global _worker_engine, _worker_session_factory
    if _worker_engine is None:
        _worker_engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URL,
            echo=False,
            pool_size=20,
            max_overflow=15,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        _worker_session_factory = async_sessionmaker(
            _worker_engine, class_=AsyncSession, expire_on_commit=False
        )
    return _worker_engine, _worker_session_factory


def _get_worker_session():
    """复用进程级引擎的会话"""
    _, factory = _get_worker_engine()
    return factory()


def _get_http_client():
    """进程级单例 httpx 客户端，复用 TCP/TLS 连接"""
    global _http_client
    import httpx
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
                keepalive_expiry=120,
            ),
            http2=False,
        )
    return _http_client
from app.utils.logger import get_logger
import asyncio

logger = get_logger(__name__)


def _mimic_smpp_expired_dlr_message() -> str:
    """
    虚拟通道「超时/未送达」类终态对外展示：仿 SMPP DLR 一行格式，
    避免出现 Virtual / Worker / simulated 等内部字样，与客户可见的「真实回执」口径一致。
    """
    import random

    return f"SMPP DLR: stat=EXPIRED err={random.randint(1, 999):03d}"


def _smpp_dlr_hold_seconds(channel: Optional[Channel] = None) -> float:
    """
    SMPP 发送成功后保持 TCP 的秒数上限（与 config 中 SMPP_DLR_SOCKET_HOLD_SECONDS 上界一致）。
    通道级 smpp_dlr_socket_hold_seconds 非空时优先（快慢通道分别调参）。
    """
    cap = float(getattr(settings, "SMPP_DLR_SOCKET_HOLD_SECONDS", 300) or 300)
    # 与 pydantic Field le=86400 对齐
    cap_max = 86400.0
    cap = max(60.0, min(cap, cap_max))
    try:
        if channel is not None:
            ch_hold = getattr(channel, "smpp_dlr_socket_hold_seconds", None)
            if ch_hold is not None and int(ch_hold) > 0:
                return float(max(60, min(int(ch_hold), int(cap_max))))
    except (TypeError, ValueError):
        pass
    return cap
# 按通道复用单连接：多数上游同一账号仅允许 1 条并发 bind，旧逻辑每条任务新建连接会导致第 2 条起 bind 失败，
# 直至延迟断开释放会话（约 5 分钟），现象与「首条成功、其余失败、过一会又正常」一致。
_smpp_cleanup_lock = threading.Lock()
# channel_id -> (adapter, deadline)
_smpp_disconnect_map: Dict[int, Tuple[Any, float]] = {}
# channel_id -> 当前复用的适配器（与 disconnect_map 中对象为同一引用）
_smpp_channel_adapter: Dict[int, Any] = {}
_smpp_channel_locks_guard = threading.Lock()
_smpp_channel_send_locks: Dict[int, threading.Lock] = {}
# Celery 各子进程共用的 Redis 同步客户端（用于 SMPP 跨进程互斥）
_smpp_sync_redis = None


def _get_smpp_sync_redis():
    """Worker 进程内懒加载同步 Redis（供 SMPP 分布式锁）"""
    global _smpp_sync_redis
    if _smpp_sync_redis is not None:
        return _smpp_sync_redis
    import redis as redis_sync

    _smpp_sync_redis = redis_sync.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=False,
        socket_connect_timeout=3,
        socket_timeout=60,
    )
    return _smpp_sync_redis


@contextlib.contextmanager
def _smpp_cross_process_lock(channel_id: int) -> Iterator[bool]:
    """
    跨 Celery 子进程串行化同一 SMPP 通道的 bind/发送。
    若关闭或未连上 Redis，yield False（与旧版行为一致，多 worker 仍可能并发 bind）。
    """
    if not settings.SMPP_REDIS_CLUSTER_LOCK:
        yield False
        return

    lock = None
    held = False
    try:
        r = _get_smpp_sync_redis()
        lock = r.lock(
            f"smpp:bind:{channel_id}",
            timeout=300,
            blocking_timeout=240,
            thread_local=False,
        )
        if lock.acquire(blocking=True):
            held = True
        else:
            logger.error(f"SMPP 等待 Redis 全局锁超时 channel_id={channel_id}")
    except Exception as e:
        logger.warning(
            f"SMPP Redis 集群锁不可用，退回仅进程内锁（多 worker 时仍可能对上游并发 bind）: {e}"
        )

    try:
        yield held
    finally:
        if lock is not None and held:
            try:
                lock.release()
            except Exception:
                pass


def _get_smpp_channel_lock(channel_id: int) -> threading.Lock:
    """同一通道发送串行化，避免多任务同时操作同一 SMPP socket"""
    with _smpp_channel_locks_guard:
        if channel_id not in _smpp_channel_send_locks:
            _smpp_channel_send_locks[channel_id] = threading.Lock()
        return _smpp_channel_send_locks[channel_id]


def _smpp_schedule_delayed_disconnect(adapter, channel_id: int, channel: Optional[Channel] = None):
    """按通道刷新延迟断开时间：同通道多次发送共用一个连接，只保留最后一次 idle 后的断开点"""
    if not adapter or not getattr(adapter, "client", None):
        return
    with _smpp_cleanup_lock:
        _smpp_disconnect_map[channel_id] = (adapter, time.time() + _smpp_dlr_hold_seconds(channel))
    # 启动清理线程（仅首次）
    if not hasattr(_smpp_schedule_delayed_disconnect, "_cleanup_started"):
        def _cleanup_loop():
            while True:
                time.sleep(30)
                now = time.time()
                due: List[Tuple[int, Any]] = []
                with _smpp_cleanup_lock:
                    for cid in list(_smpp_disconnect_map.keys()):
                        adapter_ref, deadline = _smpp_disconnect_map[cid]
                        if deadline <= now:
                            _smpp_disconnect_map.pop(cid, None)
                            due.append((cid, adapter_ref))
                for cid, adapter_ref in due:
                    lock = _get_smpp_channel_lock(cid)
                    with lock:
                        cur = _smpp_channel_adapter.get(cid)
                        if cur is adapter_ref:
                            try:
                                adapter_ref._disconnect_sync()
                            except Exception as e:
                                logger.warning(f"SMPP 延迟断开失败: {e}")
                            _smpp_channel_adapter.pop(cid, None)
                        else:
                            # 已被新会话替换或已摘除，仍关闭旧 socket，避免泄漏
                            try:
                                adapter_ref._disconnect_sync()
                            except Exception:
                                pass

        t = threading.Thread(target=_cleanup_loop, daemon=True, name="smpp-dlr-cleanup")
        t.start()
        _smpp_schedule_delayed_disconnect._cleanup_started = True


def _send_via_smpp_sync(sms_log: SMSLog, channel: Channel) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    在线程池/同步上下文中持锁发送 SMPP，复用同通道连接。
    返回 (success, upstream_message_id, error_message)。

    说明：Celery prefork 下每个子进程有独立的连接池与 threading.Lock；上游单会话时多进程会并发 bind，
    导致 ESME 13。开启 SMPP_REDIS_CLUSTER_LOCK 时用 Redis 全局锁串行化，并在成功后断开以释放 bind。
    """
    from app.workers.adapters.smpp_adapter import SMPPAdapter

    with _smpp_cross_process_lock(channel.id) as cluster_lock_held:
        lock = _get_smpp_channel_lock(channel.id)
        with lock:
            adapter = _smpp_channel_adapter.get(channel.id)
            usable = (
                adapter is not None
                and getattr(adapter, "connected", False)
                and getattr(adapter, "client", None) is not None
            )
            if not usable:
                if adapter is not None:
                    try:
                        adapter._disconnect_sync()
                    except Exception:
                        pass
                    _smpp_channel_adapter.pop(channel.id, None)
                adapter = SMPPAdapter(channel)
                if not adapter._connect_sync():
                    err = adapter.last_error or "SMPP connection failed"
                    return False, None, err
                _smpp_channel_adapter[channel.id] = adapter
                logger.info(f"SMPP 新建并绑定连接: channel={channel.channel_code} id={channel.id}")

            ok, mid, err = adapter._send_sync(sms_log)
            if ok:
                if cluster_lock_held:
                    # 多 worker 时必须在释放 Redis 锁前断开 TCP，否则下一进程 bind 时上游会话仍被占用 → ESME 13
                    try:
                        adapter._disconnect_sync()
                    except Exception:
                        pass
                    _smpp_channel_adapter.pop(channel.id, None)
                    with _smpp_cleanup_lock:
                        ent = _smpp_disconnect_map.get(channel.id)
                        if ent and ent[0] is adapter:
                            _smpp_disconnect_map.pop(channel.id, None)
                    logger.warning(
                        f"SMPP 集群锁模式已断开连接（{channel.channel_code}），"
                        f"本连接无法继续接收 deliver_sm；若依赖 SMPP 推送 DLR，请 "
                        f"worker-sms --concurrency=1 且 SMPP_REDIS_CLUSTER_LOCK=false，或配置上游 HTTP report/回调"
                    )
                else:
                    _smpp_schedule_delayed_disconnect(adapter, channel.id, channel)
                    logger.debug(f"SMPP 复用连接发送成功: channel={channel.channel_code} id={channel.id}")
            else:
                # 发送失败时连接可能已不可用，关闭并移出池，避免后续任务死复用
                try:
                    adapter._disconnect_sync()
                except Exception:
                    pass
                _smpp_channel_adapter.pop(channel.id, None)
                with _smpp_cleanup_lock:
                    ent = _smpp_disconnect_map.get(channel.id)
                    if ent and ent[0] is adapter:
                        _smpp_disconnect_map.pop(channel.id, None)
            return ok, mid, err


_worker_loop: Optional[asyncio.AbstractEventLoop] = None
_worker_loop_lock = threading.Lock()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    """进程级单例事件循环，确保 async engine 连接池始终绑定同一 loop"""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        with _worker_loop_lock:
            if _worker_loop is None or _worker_loop.is_closed():
                _worker_loop = asyncio.new_event_loop()
    return _worker_loop


_run_async_lock = threading.Lock()


def _run_async(coro):
    """在 Celery 同步 worker 中安全地执行异步协程。
    prefork 模式下复用进程级事件循环；threads 模式下多线程共享时用锁串行化。
    """
    loop = _get_worker_loop()
    with _run_async_lock:
        return loop.run_until_complete(coro)


@celery_app.task(name='send_sms_task', bind=True, max_retries=3)
def send_sms_task(self, message_id: str, http_credentials: dict = None):
    """
    发送短信任务
    
    Args:
        message_id: 消息ID
        http_credentials: HTTP通道凭据（可选），包含 username 和 password
    """
    logger.info(f"开始处理短信发送任务: {message_id}")
    current_queue = (self.request.delivery_info or {}).get('routing_key', 'sms_send')
    
    try:
        result = _run_async(_send_sms_async(message_id, http_credentials, _current_queue=current_queue))

        if isinstance(result, dict) and result.get("_reroute_smpp"):
            logger.info(f"SMPP 通道任务重路由到 sms_send_smpp 队列: {message_id}")
            send_sms_task.apply_async(
                args=[message_id, http_credentials],
                queue='sms_send_smpp',
            )
            return {"success": True, "rerouted": "sms_send_smpp"}

        if isinstance(result, dict) and result.get("_rate_limited"):
            wait_sec = result.get("_wait_sec", 0.5)
            logger.info(f"通道限速，{wait_sec}s 后重试: {message_id}")
            raise self.retry(countdown=wait_sec, max_retries=200)

        if (
            isinstance(result, dict)
            and result.get("error") == "Message not found"
            and self.request.retries < self.max_retries
        ):
            countdown = 2 + int(self.request.retries) * 3
            logger.warning(
                f"短信记录尚未提交可见，{countdown}s 后重试: {message_id} (第{self.request.retries + 1}次)"
            )
            raise self.retry(countdown=countdown)
        return result

    except Retry:
        raise
    except Exception as e:
        logger.error(f"发送短信失败: {message_id}, 错误: {str(e)}", exc_info=e)
        
        if self.request.retries < self.max_retries:
            logger.info(f"将重试发送: {message_id}, 重试次数: {self.request.retries + 1}")
            raise self.retry(exc=e, countdown=60)
        else:
            logger.error(f"达到最大重试次数，标记为失败: {message_id}")
            _run_async(_mark_failed(message_id, str(e)))
            return {"success": False, "error": str(e)}


async def _send_sms_async(message_id: str, http_credentials: dict = None, *, _current_queue: str = 'sms_send') -> dict:
    """
    异步发送短信
    
    Args:
        message_id: 消息ID
        http_credentials: HTTP通道凭据（可选），包含 username 和 password
        _current_queue: 当前任务所在队列，用于 SMPP 通道重路由判断
    """
    db = _get_worker_session()
    try:
        # 查询短信记录
        result = await db.execute(
            select(SMSLog).where(SMSLog.message_id == message_id)
        )
        sms_log = result.scalar_one_or_none()
        
        if not sms_log:
            logger.error(f"短信记录不存在: {message_id}")
            return {"success": False, "error": "Message not found"}
        
        # 查询通道（若未指定则自动路由）
        channel = None
        if sms_log.channel_id:
            result = await db.execute(
                select(Channel).where(Channel.id == sms_log.channel_id)
            )
            channel = result.scalar_one_or_none()

        if not channel:
            try:
                from app.core.router import RoutingEngine
                router = RoutingEngine(db)
                country = sms_log.country_code or "PH"
                channel = await router.select_channel(country)
                if channel:
                    sms_log.channel_id = channel.id
            except Exception as route_err:
                logger.warning(f"自动路由失败: {message_id}, {route_err}")

        if not channel:
            logger.error(f"无可用通道: {message_id}, channel_id={sms_log.channel_id}")
            sms_log.status = 'failed'
            sms_log.error_message = "No available channel"
            await db.commit()
            return {"success": False, "error": "No available channel"}
        
        logger.info(f"使用通道: {channel.channel_code} ({channel.protocol})")

        # SMPP 通道需在专用线程池 worker 中处理，避免多进程并发 bind
        # 如果当前任务运行在 sms_send 队列（prefork worker），返回重路由标记
        if channel.protocol == 'SMPP' and _current_queue != 'sms_send_smpp':
            await db.close()
            return {"_reroute_smpp": True}

        if channel.protocol != 'VIRTUAL':
            from app.utils.rate_limiter import acquire_send_slot
            max_tps = channel.max_tps or 100
            allowed, wait_ms = acquire_send_slot(channel.id, max_tps)
            if not allowed:
                await db.close()
                return {"_rate_limited": True, "_wait_sec": round(wait_ms / 1000, 2)}

        # 更新状态为发送中
        sms_log.status = 'sent'
        sms_log.sent_time = datetime.now()
        await db.commit()
        
        # 根据通道协议发送
        if channel.protocol == 'VIRTUAL':
            success = await _send_via_virtual(sms_log, channel)
        elif channel.protocol == 'HTTP':
            success = await _send_via_http(sms_log, channel, http_credentials)
        elif channel.protocol == 'SMPP':
            success = await _send_via_smpp(sms_log, channel)
        else:
            logger.warning(f"不支持的协议: {channel.protocol}")
            success = False

        # 发送成功后立刻提交：submit_sm_resp 写入的 upstream_message_id 必须先落库。
        # deliver_sm 常在同一秒内到达，DLR 在独立线程读库；若仍停留在未提交的会话里，会大量出现「SMPP DLR: 未找到」且界面长期「送达等待中」。
        if success:
            await db.commit()
        
        # 更新状态
        if success:
            sms_log.status = 'sent'  # 先标记为已发送，等待DLR
            sms_log.sent_time = datetime.now()
            logger.info(f"短信发送成功: {message_id}")
            
            # 触发Webhook回调（sent状态）
            try:
                from app.workers.webhook_worker import trigger_webhook
                await trigger_webhook(
                    message_id,
                    'sent',
                    {
                        'phone_number': sms_log.phone_number,
                        'country_code': sms_log.country_code,
                        'channel_id': sms_log.channel_id
                    },
                    account_id=sms_log.account_id,
                )
            except Exception as e:
                logger.warning(f"触发Webhook失败: {str(e)}")
        else:
            sms_log.status = 'failed'
            # 保留详细错误信息，只有未设置时才使用默认值
            if not sms_log.error_message:
                sms_log.error_message = "Send failed"
            logger.error(f"短信发送失败: {message_id}, 错误: {sms_log.error_message}")
            
            # 触发Webhook回调（failed状态）
            try:
                from app.workers.webhook_worker import trigger_webhook
                await trigger_webhook(
                    message_id,
                    'failed',
                    {
                        'phone_number': sms_log.phone_number,
                        'country_code': sms_log.country_code,
                        'error_message': sms_log.error_message
                    },
                    account_id=sms_log.account_id,
                )
            except Exception as e:
                logger.warning(f"触发Webhook失败: {str(e)}")
        
        await db.commit()

        # 更新批次进度
        if sms_log.batch_id:
            await _update_batch_progress(db, sms_log.batch_id)
        
        return {"success": success, "message_id": message_id, "status": sms_log.status}
    finally:
        await db.close()


async def _update_batch_progress(db, batch_id: int):
    """更新批次的发送进度和状态"""
    try:
        from app.modules.sms.sms_batch import SmsBatch, BatchStatus
        from sqlalchemy import func as sa_func

        stats = await db.execute(
            select(
                SMSLog.status,
                sa_func.count().label('cnt')
            ).where(SMSLog.batch_id == batch_id).group_by(SMSLog.status)
        )
        counts = {row.status: row.cnt for row in stats}
        log_total = sum(counts.values())
        sent = counts.get('sent', 0) + counts.get('delivered', 0)
        failed = counts.get('failed', 0) + counts.get('expired', 0)
        done = sent + failed

        batch_result = await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))
        batch = batch_result.scalar_one_or_none()
        if not batch:
            return

        total = batch.total_count or log_total
        pending_cnt = counts.get('pending', 0) + counts.get('queued', 0)

        batch.success_count = sent
        batch.failed_count = failed
        batch.processing_count = total - done
        batch.progress = int(done * 100 / max(total, 1))

        if log_total >= total and done >= log_total:
            if failed == 0:
                batch.status = BatchStatus.COMPLETED
            elif sent == 0:
                batch.status = BatchStatus.FAILED
            else:
                batch.status = BatchStatus.COMPLETED
                batch.error_message = f"部分失败: {failed}/{total}"
            batch.completed_at = datetime.now()
        elif log_total >= total and pending_cnt > 0 and pending_cnt <= total * 0.02:
            # 仅虚拟通道：少量 pending 多为「countdown 模拟提交/DLR」在 Worker 重启后丢失，可收口为 expired。
            # 真实通道（HTTP/SMPP）待发为 queued：任务仍在 RabbitMQ sms_send/sms_send_smpp 中排队属常态，
            # 若此处一并过期会误杀队列尾部，并出现「Worker restart…」类与真实回执无关的 error_message。
            from sqlalchemy import update as _sa_upd

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
            if not all_virtual_pending:
                logger.warning(
                    f"批次存在非虚拟待发(≤2%)，跳过自动过期（避免误杀真实通道队列尾部）: "
                    f"batch={batch_id}, pending={pending_cnt}"
                )
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
            pass
        else:
            batch.status = BatchStatus.PROCESSING
            batch.completed_at = None
            batch.error_message = None

        await db.commit()

        # P0-FIX: 失败短信退款
        if failed > 0 and done >= total:
            await _refund_failed_sms(db, batch_id, batch.account_id)

    except Exception as e:
        logger.warning(f"更新批次进度失败: batch_id={batch_id}, {e}")


async def _refund_failed_sms(db, batch_id: int, account_id: int):
    """批次完成后，对发送失败的短信执行退款"""
    try:
        from sqlalchemy import func as sa_func
        from app.modules.common.account import Account
        from app.modules.common.balance_log import BalanceLog
        from sqlalchemy import update as sa_update

        result = await db.execute(
            select(sa_func.sum(SMSLog.selling_price)).where(
                SMSLog.batch_id == batch_id, SMSLog.status == 'failed'
            )
        )
        refund_amount = float(result.scalar() or 0)
        if refund_amount <= 0:
            return

        await db.execute(
            sa_update(Account).where(Account.id == account_id)
            .values(balance=Account.balance + refund_amount)
        )
        bal = await db.execute(select(Account.balance).where(Account.id == account_id))
        db.add(BalanceLog(
            account_id=account_id, change_type='refund', amount=refund_amount,
            balance_after=float(bal.scalar()),
            description=f"短信发送失败退款: batch_id={batch_id}"
        ))
        await db.commit()
        logger.info(f"失败退款完成: batch={batch_id}, 退款={refund_amount}")
    except Exception as e:
        logger.error(f"退款失败: batch={batch_id}, {e}")


async def _send_via_virtual(sms_log: SMSLog, channel: Channel) -> bool:
    """
    虚拟通道：不实际发送短信，立即标记为 sent，
    然后安排延迟 Celery 任务生成模拟回执（delivered/failed）。
    """
    import uuid
    try:
        virtual_msg_id = f"VIRT-{uuid.uuid4().hex[:12]}"
        sms_log.upstream_message_id = virtual_msg_id
        logger.info(f"虚拟通道发送: {sms_log.message_id} via {channel.channel_code}, virt_id={virtual_msg_id}")

        cfg = channel.get_virtual_config()
        delay_min = max(1, cfg.get("dlr_delay_min", 3))
        delay_max = max(delay_min, cfg.get("dlr_delay_max", 30))

        import random
        delay = random.uniform(delay_min, delay_max)

        from app.workers.celery_app import celery_app as _celery
        _celery.send_task(
            "virtual_dlr_generate",
            args=[sms_log.message_id, channel.id],
            countdown=delay,
        )
        return True
    except Exception as e:
        logger.error(f"虚拟通道处理异常: {sms_log.message_id}, {e}")
        return False


async def _send_via_http(sms_log: SMSLog, channel: Channel, http_credentials: dict = None) -> bool:
    """
    通过HTTP发送短信
    
    Args:
        sms_log: 短信记录
        channel: 通道配置
        http_credentials: HTTP凭据（可选），包含 username 和 password，优先级高于通道配置
    """
    import httpx
    
    try:
        logger.info(f"通过HTTP发送短信: {sms_log.message_id} via {channel.channel_code}")
        
        # 使用通道的默认发送方ID作为extno，如果为空则不传
        extno = channel.default_sender_id or ""
        
        # 如果没有配置 api_url，使用模拟模式
        if not channel.api_url:
            logger.info(f"HTTP通道未配置api_url，使用模拟模式: {sms_log.message_id}")
            if http_credentials:
                logger.info(f"模拟HTTP发送 (使用自定义凭据: {http_credentials.get('username', 'N/A')})")
            logger.info(f"模拟HTTP发送成功: {sms_log.message_id} -> {sms_log.phone_number}")
            return True
        
        # 确定使用哪个凭据
        # 优先级: 1. API请求传入的http_credentials  2. 通道username/password字段  3. 通道api_key字段(JSON格式)
        http_account = None
        http_password = None
        
        if http_credentials:
            http_account = http_credentials.get("username") or http_credentials.get("account")
            http_password = http_credentials.get("password")
            if http_account:
                logger.info(f"使用API请求传入的HTTP凭据: {http_account}")
        
        # 如果没有自定义凭据，使用通道的 username/password 字段
        if not http_account and channel.username:
            http_account = channel.username
            http_password = channel.password
            logger.info(f"使用通道配置的HTTP凭据: {http_account}")
        
        # 如果还是没有，从通道api_key字段解析（JSON格式，兼容旧配置）
        # 格式: {"account": "888998", "password": "xxx"}
        if not http_account and channel.api_key:
            try:
                import json
                api_config = json.loads(channel.api_key)
                http_account = api_config.get("account")
                http_password = api_config.get("password")
                if http_account:
                    logger.info(f"使用通道api_key配置的HTTP凭据: {http_account}")
            except json.JSONDecodeError:
                logger.warning(f"通道api_key不是有效的JSON格式: {channel.api_key}")
        
        # 处理手机号：去掉+号
        mobile = sms_log.phone_number
        if mobile.startswith('+'):
            mobile = mobile[1:]
        
        # 按照上游接口格式构造请求参数
        # 格式: {"action":"send","account":"123456","password":"123456","mobile":"15100000000","content":"内容","extno":"10690","atTime":"2022-12-05 18:00:00"}
        payload = {
            "action": "send",
            "account": http_account or "",
            "password": http_password or "",
            "mobile": mobile,
            "content": sms_log.message,
            "extno": extno
        }
        
        # 如果有定时发送时间，添加atTime参数
        scheduled_time = getattr(sms_log, 'scheduled_time', None)
        if scheduled_time:
            payload["atTime"] = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SMSC-Gateway/1.0"
        }
        
        logger.info(f"HTTP请求URL: {channel.api_url}")
        logger.info(f"HTTP请求参数: {payload}")
        
        client = _get_http_client()
        response = await client.post(
            channel.api_url,
            json=payload,
            headers=headers
        )

        response_text = response.text
        logger.info(f"HTTP响应: status={response.status_code}, body={response_text[:500]}")

        if response.status_code in [200, 201]:
            try:
                resp_data = response.json()
                api_status = resp_data.get('status')
                balance = resp_data.get('balance', 0)
                result_list = resp_data.get('list', [])

                status_errors = {
                    0: "成功", 2: "IP错误", 3: "账号密码错误", 5: "其它错误",
                    6: "接入点错误", 7: "账号状态异常(已停用)", 11: "系统内部错误",
                    34: "请求参数有误", 100: "系统内部错误"
                }
                result_errors = {
                    0: "提交成功", 10: "原发号码错误(extno错误)",
                    15: "余额不足", 100: "系统内部错误"
                }

                if api_status == 0:
                    if result_list:
                        first_result = result_list[0]
                        mid = (first_result.get('mid') or first_result.get('msgid') or
                               first_result.get('taskid') or first_result.get('message_id') or
                               first_result.get('id') or '')
                        result_code = first_result.get('result', first_result.get('status', -1))
                        if isinstance(result_code, str) and result_code.isdigit():
                            result_code = int(result_code)

                        if result_code == 0:
                            logger.info(f"HTTP发送成功: {sms_log.message_id}, upstream_id={mid}, balance={balance}")
                            sms_log.upstream_message_id = mid or None
                            return True
                        else:
                            error_desc = result_errors.get(result_code, f"未知错误({result_code})")
                            logger.error(f"HTTP发送失败(提交错误): {sms_log.message_id}, result={result_code}, 错误: {error_desc}")
                            sms_log.error_message = f"上游错误: {error_desc}"
                            return False
                    else:
                        mid = (resp_data.get('mid') or resp_data.get('msgid') or
                               resp_data.get('taskid') or resp_data.get('message_id') or
                               resp_data.get('id') or '')
                        if mid:
                            sms_log.upstream_message_id = str(mid)
                            logger.info(f"HTTP发送成功(无明细): {sms_log.message_id}, upstream_id={mid}")
                        else:
                            logger.info(f"HTTP发送成功(无明细): {sms_log.message_id}, balance={balance} (无上游ID，DLR可能无法匹配)")
                        return True
                else:
                    error_desc = status_errors.get(api_status, f"未知错误({api_status})")
                    logger.error(f"HTTP发送失败(API错误): {sms_log.message_id}, status={api_status}, 错误: {error_desc}")
                    sms_log.error_message = f"上游API错误: {error_desc}"
                    return False

            except Exception as e:
                if '<returnsms>' in response_text:
                    import re
                    status_match = re.search(r'<returnstatus>(\w+)</returnstatus>', response_text)
                    message_match = re.search(r'<message>([^<]*)</message>', response_text)
                    return_status = status_match.group(1) if status_match else 'Unknown'
                    return_message = message_match.group(1) if message_match else ''
                    if return_status.lower() == 'success':
                        logger.info(f"HTTP发送成功(XML): {sms_log.message_id}")
                        return True
                    else:
                        logger.error(f"HTTP发送失败(XML): {sms_log.message_id}, status={return_status}, message={return_message}")
                        sms_log.error_message = f"上游XML错误: status={return_status}, code={return_message}"
                        return False
                else:
                    logger.error(f"HTTP响应解析失败: {sms_log.message_id}, error={e}, body={response_text[:200]}")
                    sms_log.error_message = f"响应解析失败: {str(e)}"
                    return False
        else:
            logger.error(f"HTTP发送失败: {response.status_code} {response.text}")
            return False
        
    except Exception as e:
        logger.error(f"HTTP发送异常: {str(e)}", exc_info=e)
        return False


async def _send_via_smpp(sms_log: SMSLog, channel: Channel) -> bool:
    """
    通过 SMPP 发送短信（同 Worker 进程内按 channel_id 复用连接，避免上游单会话限制导致连续失败）
    """
    smpp_success = False
    try:
        logger.info(f"通过SMPP发送短信: {sms_log.message_id} via {channel.channel_code}")
        loop = asyncio.get_running_loop()
        success, channel_message_id, error_message = await loop.run_in_executor(
            None, _send_via_smpp_sync, sms_log, channel
        )
        smpp_success = success

        if success:
            if channel_message_id:
                sms_log.upstream_message_id = channel_message_id
            logger.info(f"SMPP发送成功: {sms_log.message_id} -> {channel_message_id}")
            return True
        sms_log.error_message = error_message or "SMPP send failed"
        logger.error(f"SMPP发送失败: {sms_log.message_id}, 错误: {error_message}")
        return False

    except Exception as e:
        error_msg = str(e)
        logger.error(f"SMPP发送异常: {error_msg}", exc_info=e)
        if sms_log:
            sms_log.error_message = error_msg
        return False


async def _mark_failed(message_id: str, error_message: str):
    """标记短信为失败状态"""
    db = _get_worker_session()
    try:
        result = await db.execute(
            select(SMSLog).where(SMSLog.message_id == message_id)
        )
        sms_log = result.scalar_one_or_none()
        if sms_log:
            sms_log.status = 'failed'
            sms_log.error_message = error_message
            await db.commit()
            logger.info(f"已标记为失败: {message_id}")
    finally:
        await db.close()


@celery_app.task(name='process_dlr_task')
def process_dlr_task(dlr_data: dict):
    """
    处理送达回执(DLR)任务
    
    Args:
        dlr_data: DLR数据
    """
    logger.info(f"处理DLR: {dlr_data}")
    
    try:
        _run_async(_process_dlr_async(dlr_data))
        return {"success": True}
        
    except Exception as e:
        logger.error(f"处理DLR失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _process_dlr_async(dlr_data: dict):
    """
    异步处理DLR
    """
    db = _get_worker_session()
    try:
        message_id = dlr_data.get('message_id')
        status = dlr_data.get('status')
        
        result = await db.execute(
            select(SMSLog).where(SMSLog.message_id == message_id)
        )
        sms_log = result.scalar_one_or_none()
        
        if not sms_log:
            logger.warning(f"DLR对应的短信记录不存在: {message_id}")
            return
        
        sms_log.status = status
        if status == 'delivered':
            sms_log.delivery_time = datetime.now()
        elif status == 'failed':
            sms_log.error_message = dlr_data.get('error_message', 'Delivery failed')
        
        await db.commit()
        logger.info(f"DLR处理完成: {message_id}, 状态: {status}")
        
        # 注水触发（delivered 时）
        if status == 'delivered' and sms_log.account_id:
            try:
                from app.utils.water_trigger import trigger_water_single
                await trigger_water_single(
                    db, sms_log.id, sms_log.message,
                    sms_log.country_code, sms_log.account_id,
                    channel_id=sms_log.channel_id,
                )
            except Exception as e:
                logger.warning(f"DLR注水触发异常: {e}")

        try:
            from app.workers.webhook_worker import trigger_webhook
            await trigger_webhook(
                message_id,
                status,
                {
                    'phone_number': sms_log.phone_number,
                    'country_code': sms_log.country_code,
                    'error_message': dlr_data.get('error_message') if status == 'failed' else None
                },
                account_id=sms_log.account_id,
            )
        except Exception as e:
            logger.warning(f"触发Webhook失败: {str(e)}")
    finally:
        await db.close()


# ============ 定时拉取 DLR 报告 ============

@celery_app.task(name='fetch_dlr_reports_task')
def fetch_dlr_reports_task():
    """
    定时拉取上游 DLR 报告
    
    从 Kaola SMS 的 report 接口拉取送达报告
    """
    logger.info("开始拉取 DLR 报告...")
    
    try:
        result = _run_async(_fetch_dlr_reports_async())
        return result
        
    except Exception as e:
        logger.error(f"拉取 DLR 报告失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _fetch_dlr_reports_async():
    """
    异步拉取 DLR 报告

    支持多种上游格式（JSON/XML），使用统一的 DLR 处理模块。
    系统配置 dlr_report_url_override（JSON）可覆盖通道的 report URL，格式：
    {"KAOLA_PH_HTTP": "https://xxx/report"} 或 {"KAOLA_PH_HTTP": {"url": "https://...", "method": "POST"}}
    """
    import httpx
    from app.core.dlr_handler import detect_and_parse_dlr, process_dlr_reports
    from app.modules.common.system_config import SystemConfig

    db = _get_worker_session()
    try:
        # 读取 DLR report URL 覆盖配置（系统配置 -> dlr_report_url_override，类型 json）
        url_overrides = {}
        try:
            cfg_res = await db.execute(
                select(SystemConfig).where(SystemConfig.config_key == 'dlr_report_url_override')
            )
            cfg = cfg_res.scalar_one_or_none()
            if cfg and cfg.config_value:
                raw = cfg.config_value
                url_overrides = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            pass

        # HTTP 通道：有 api_url 的参与拉取
        http_result = await db.execute(
            select(Channel).where(
                Channel.protocol == 'HTTP',
                Channel.status == 'active',
                Channel.is_deleted == False
            )
        )
        channels = list(http_result.scalars().all())
        # SMPP 通道：若 dlr_report_url_override 配置了 report URL，也参与拉取（Kaola 等 SMPP 通道可通过 HTTP report 接口获取 DLR）
        smpp_result = await db.execute(
            select(Channel).where(
                Channel.protocol == 'SMPP',
                Channel.status == 'active',
                Channel.is_deleted == False
            )
        )
        smpp_channels = smpp_result.scalars().all()
        for sc in smpp_channels:
            ov = url_overrides.get(sc.channel_code)
            if ov and (isinstance(ov, str) or (isinstance(ov, dict) and ov.get('url'))):
                channels.append(sc)
        pull_channels = [(c.channel_code, getattr(c, 'api_url', None) or '', bool(c.username or c.password or c.api_key)) for c in channels]
        logger.info(f"DLR 拉取通道列表: {pull_channels}")

        total_success = 0
        total_fail = 0

        for channel in channels:
            # 解析 URL 覆盖（支持 "url" 或 直接字符串）
            override_val = url_overrides.get(channel.channel_code)
            url_override = None
            report_method = 'GET'
            if isinstance(override_val, str):
                url_override = override_val
            elif isinstance(override_val, dict) and override_val.get('url'):
                url_override = override_val['url']
                report_method = (override_val.get('method') or 'GET').upper()

            # HTTP 通道需 api_url；SMPP 通道需 dlr_report_url_override 配置了 report URL
            if not channel.api_url and not url_override:
                continue

            http_account = channel.username or ''
            http_password = channel.password or channel.api_key or ''

            if not http_account:
                logger.warning(f"通道 {channel.channel_code} 未配置 username，跳过 DLR 拉取")
                continue

            report_url = _build_dlr_pull_url(channel, url_override)
            if not report_url:
                logger.warning(f"通道 {channel.channel_code} 无有效 report URL，跳过")
                continue
            params = {
                "action": "report",
                "account": http_account,
                "password": http_password
            }

            try:
                logger.info(f"拉取 DLR: {channel.channel_code}, URL: {report_url}, method: {report_method}")

                pull_timeout = float(getattr(settings, "DLR_PULL_HTTP_TIMEOUT_SECONDS", 60.0) or 60.0)
                async with httpx.AsyncClient(timeout=pull_timeout) as client:
                    if report_method == 'POST':
                        response = await client.post(report_url, params=params)
                    else:
                        response = await client.get(report_url, params=params)

                    # GET 返回 405 时尝试 POST（部分上游仅支持 POST）
                    if response.status_code == 405 and report_method == 'GET':
                        logger.info(f"[{channel.channel_code}] GET 返回 405，尝试 POST")
                        response = await client.post(report_url, params=params)

                    if response.status_code == 200:
                        resp_text = response.text
                        content_type = response.headers.get('content-type', '')

                        if _is_empty_dlr_response(resp_text):
                            logger.info(f"[{channel.channel_code}] DLR 响应为空（上游暂无回执）")
                            continue

                        if _is_error_dlr_response(resp_text):
                            logger.warning(f"[{channel.channel_code}] DLR 响应错误: {resp_text[:200]}")
                            continue

                        reports = detect_and_parse_dlr(resp_text, content_type)

                        if reports:
                            logger.info(f"[{channel.channel_code}] 解析到 {len(reports)} 条 DLR 报告")
                            success, fail = await process_dlr_reports(
                                reports,
                                db,
                                source=f"pull-{channel.channel_code}",
                                channel_id=channel.id,
                            )
                            total_success += success
                            total_fail += fail
                        else:
                            logger.debug(f"[{channel.channel_code}] 无有效 DLR 报告，原始: {resp_text[:200]}")
                    else:
                        logger.warning(f"[{channel.channel_code}] 拉取 DLR 失败: HTTP {response.status_code}")

            except Exception as e:
                logger.error(f"拉取通道 {channel.channel_code} DLR 失败: {str(e)}")

        total = total_success + total_fail
        logger.info(f"DLR 拉取完成: 成功={total_success}, 失败={total_fail}, 总计={total}")
        return {"success": True, "updated": total, "delivered": total_success, "failed": total_fail}
    finally:
        await db.close()


def _build_dlr_pull_url(channel: Channel, url_override: Optional[str] = None) -> str:
    """
    构建 DLR 拉取 URL
    
    根据不同的通道类型构建对应的报告查询 URL。
    若传入 url_override（来自系统配置 dlr_report_url_override），则优先使用。
    """
    if url_override:
        return url_override.strip()

    base_url = channel.api_url or ''

    # Kaola 格式: /smsv2 -> /sms，report 使用 action=report 参数
    if 'kaolasms' in base_url.lower():
        base_url = base_url.replace('/smsv2', '/sms').replace('?action=send', '')
        if '?' in base_url:
            base_url = base_url.split('?')[0]
        return base_url

    # 通用格式: 尝试替换或添加 /report 路径
    if base_url.endswith('/send'):
        return base_url.replace('/send', '/report')

    if base_url.endswith('/sms'):
        return base_url + '/report'

    # 默认直接使用
    return base_url


def _is_empty_dlr_response(resp_text: str) -> bool:
    """
    检查 DLR 响应是否为空
    """
    resp_text = resp_text.strip()
    
    # XML 空响应
    if '<returnsms></returnsms>' in resp_text:
        return True
    if '<returnsms/>' in resp_text:
        return True
    if '<reports></reports>' in resp_text:
        return True
    
    # JSON 空响应
    if resp_text in ['{}', '[]', '{"list":[]}', '{"reports":[]}', '{"data":[]}']:
        return True
    
    # 纯空
    if not resp_text:
        return True
    
    return False


def _is_error_dlr_response(resp_text: str) -> bool:
    """
    检查 DLR 响应是否为错误
    """
    resp_text = resp_text.lower()
    
    # 常见错误标识（含 Kaola 等上游的认证失败返回）
    error_patterns = [
        '<errorstatus>',
        '<error>',
        '"error":',
        'invalid_auth',
        'con_invalid_auth',
        'authentication failed',
        'access denied',
        'unauthorized',
    ]
    
    return any(pattern in resp_text for pattern in error_patterns)


# ============ DLR 超时处理 ============

@celery_app.task(name='dlr_timeout_check_task')
def dlr_timeout_check_task():
    """
    定时检查超时的 sent 记录
    超过指定时间仍为 sent 的记录标记为 timeout
    """
    logger.info("开始检查 DLR 超时记录...")
    try:
        result = _run_async(_dlr_timeout_check_async())
        return result
    except Exception as e:
        logger.error(f"DLR 超时检查失败: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _dlr_timeout_check_async():
    """异步检查并标记超时的 sent 记录（按通道 dlr_sent_timeout_hours，否则用全局 DLR_SENT_TIMEOUT_HOURS）"""
    from datetime import timedelta
    from sqlalchemy import and_, update

    db = _get_worker_session()
    try:
        default_h = int(getattr(settings, "DLR_SENT_TIMEOUT_HOURS", 72) or 72)
        default_h = max(4, min(default_h, 720))

        ch_result = await db.execute(
            select(Channel.id, Channel.dlr_sent_timeout_hours).where(
                Channel.is_deleted == False
            )
        )
        channel_rows = ch_result.all()
        # 显式列出的通道（含仅自定义超时的通道）
        channel_ids = {row[0] for row in channel_rows}
        expired_count = 0

        for ch_id, custom_h in channel_rows:
            h = int(custom_h) if custom_h is not None and int(custom_h) > 0 else default_h
            h = max(4, min(h, 720))
            cutoff = datetime.now() - timedelta(hours=h)
            stmt = (
                update(SMSLog)
                .where(
                    and_(
                        SMSLog.channel_id == ch_id,
                        SMSLog.status == 'sent',
                        SMSLog.sent_time < cutoff,
                        SMSLog.sent_time.isnot(None),
                    )
                )
                .values(
                    status='expired',
                    error_message=f'DLR 超时: 超过{h}小时未收到终态回执',
                )
            )
            r = await db.execute(stmt)
            expired_count += r.rowcount

        # 无 channel_id、或通道已删除/未在表中的记录，用全局默认小时数
        from sqlalchemy import or_, true as sql_true

        cutoff_default = datetime.now() - timedelta(hours=default_h)
        if channel_ids:
            misc_where = or_(
                SMSLog.channel_id.is_(None),
                ~SMSLog.channel_id.in_(list(channel_ids)),
            )
        else:
            misc_where = sql_true()

        stmt_misc = (
            update(SMSLog)
            .where(
                and_(
                    SMSLog.status == 'sent',
                    SMSLog.sent_time < cutoff_default,
                    SMSLog.sent_time.isnot(None),
                    misc_where,
                )
            )
            .values(
                status='expired',
                error_message=f'DLR 超时: 超过{default_h}小时未收到终态回执',
            )
        )
        r2 = await db.execute(stmt_misc)
        expired_count += r2.rowcount

        await db.commit()

        if expired_count > 0:
            logger.info(f"DLR 超时: 标记 {expired_count} 条记录为 expired（默认阈值 {default_h}h）")
        else:
            logger.debug("DLR 超时检查: 无超时记录")

        return {"success": True, "expired": expired_count}
    finally:
        await db.close()


# ============ 虚拟通道回执生成任务 ============

@celery_app.task(name="virtual_dlr_generate", bind=True, max_retries=3,
                 autoretry_for=(Exception,), retry_backoff=2, retry_backoff_max=30)
def virtual_dlr_generate_task(self, message_id: str, channel_id: int):
    """延迟生成虚拟通道的模拟回执（单条，兼容旧逻辑）"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_virtual_dlr(message_id, channel_id))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


@celery_app.task(name="virtual_submit_simulate", bind=True, max_retries=2,
                 autoretry_for=(Exception,), retry_backoff=5, retry_backoff_max=60,
                 soft_time_limit=10 * 60, time_limit=12 * 60,
                 acks_late=True, reject_on_worker_lost=True)
def virtual_submit_simulate_task(self, message_ids: list, channel_id: int, batch_id: int = None):
    """模拟虚拟通道上游提交：将 pending 状态批量更新为 sent"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_virtual_submit(message_ids, channel_id, batch_id))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


async def _do_virtual_submit(message_ids: list, channel_id: int, batch_id: int = None):
    """批量将 pending 消息更新为 sent，模拟上游提交完成"""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
    from sqlalchemy import update as sa_update
    from app.modules.sms.sms_batch import SmsBatch

    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, echo=False,
        pool_size=2, max_overflow=1, pool_pre_ping=True, pool_recycle=300,
    )
    factory = async_sessionmaker(eng, class_=_AS, expire_on_commit=False)
    updated = 0
    now = datetime.now()

    try:
        async with factory() as db:
            if batch_id:
                _bs = (await db.execute(select(SmsBatch.status).where(SmsBatch.id == batch_id))).scalar_one_or_none()
                if _bs in ('cancelled', 'failed'):
                    logger.info(f"虚拟提交跳过: batch={batch_id} 已{_bs}")
                    return {"updated": 0, "skipped": True}
            for chunk_start in range(0, len(message_ids), 200):
                chunk_ids = message_ids[chunk_start:chunk_start + 200]
                result = await db.execute(
                    sa_update(SMSLog)
                    .where(
                        SMSLog.message_id.in_(chunk_ids),
                        SMSLog.status == "pending",
                    )
                    .values(status="sent", sent_time=now)
                )
                updated += result.rowcount
                await db.commit()

            if batch_id:
                await _update_batch_progress(db, batch_id)

        logger.info(
            f"虚拟通道提交模拟完成: batch={batch_id}, updated={updated}/{len(message_ids)}"
        )
        return {"updated": updated}
    except Exception as e:
        logger.error(f"虚拟通道提交模拟异常: batch={batch_id}, {e}")
        raise
    finally:
        await eng.dispose()


@celery_app.task(name="virtual_dlr_batch_generate", bind=True, max_retries=2,
                 autoretry_for=(Exception,), retry_backoff=5, retry_backoff_max=60,
                 soft_time_limit=15 * 60, time_limit=20 * 60,
                 acks_late=True, reject_on_worker_lost=True)
def virtual_dlr_batch_generate_task(self, message_ids: list, channel_id: int, batch_id: int = None):
    """批量生成虚拟通道回执，一个任务处理一整个分片（最多500条）"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_virtual_dlr_batch(message_ids, channel_id, batch_id))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


async def _do_virtual_dlr_batch(message_ids: list, channel_id: int, batch_id: int = None):
    """批量处理虚拟DLR：一个DB连接处理整个分片"""
    import random
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
    from app.modules.sms.sms_batch import SmsBatch

    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, echo=False,
        pool_size=2, max_overflow=1, pool_pre_ping=True, pool_recycle=300,
    )
    factory = async_sessionmaker(eng, class_=_AS, expire_on_commit=False)
    delivered = 0
    failed_cnt = 0
    expired_cnt = 0

    try:
        async with factory() as db:
            if batch_id:
                _bs = (await db.execute(select(SmsBatch.status).where(SmsBatch.id == batch_id))).scalar_one_or_none()
                if _bs in ('cancelled', 'failed'):
                    logger.info(f"虚拟DLR跳过: batch={batch_id} 已{_bs}")
                    return {"delivered": 0, "failed": 0, "expired": 0, "skipped": True}

            ch_result = await db.execute(
                select(Channel).where(Channel.id == channel_id)
            )
            channel = ch_result.scalar_one_or_none()
            cfg = channel.get_virtual_config() if channel else {}

            delivery_rate_min = cfg.get("delivery_rate_min", 80)
            delivery_rate_max = cfg.get("delivery_rate_max", 90)
            fail_rate_min = cfg.get("fail_rate_min", 5)
            fail_rate_max = cfg.get("fail_rate_max", 15)
            fail_codes = cfg.get("fail_codes", ["UNDELIV"])

            delivery_base = random.uniform(delivery_rate_min, delivery_rate_max)
            fail_base = random.uniform(fail_rate_min, fail_rate_max)
            delivery_rate = max(0.0, min(100.0, delivery_base + random.gauss(0, 1.5)))
            fail_rate = max(0.0, min(100.0 - delivery_rate, fail_base + random.gauss(0, 0.8)))

            now = datetime.now()

            delivered_items = []

            for chunk_start in range(0, len(message_ids), 100):
                chunk_ids = message_ids[chunk_start:chunk_start + 100]
                result = await db.execute(
                    select(SMSLog).where(
                        SMSLog.message_id.in_(chunk_ids),
                        SMSLog.status.in_(["sent", "pending", "queued"]),
                    )
                )
                logs = result.scalars().all()

                for sms_log in logs:
                    if not sms_log.sent_time:
                        sms_log.sent_time = now
                    roll = random.uniform(0, 100)
                    if roll < delivery_rate:
                        sms_log.status = "delivered"
                        sms_log.delivery_time = now
                        sms_log.error_message = None
                        delivered += 1
                        delivered_items.append((sms_log.id, sms_log.message, sms_log.country_code, sms_log.account_id))
                    elif roll < delivery_rate + fail_rate:
                        sms_log.status = "failed"
                        code = random.choice(fail_codes) if fail_codes else "UNDELIV"
                        sms_log.error_message = f"SMPP DLR: stat={code} err={random.randint(1,99):03d}"
                        failed_cnt += 1
                    else:
                        sms_log.status = "expired"
                        sms_log.error_message = _mimic_smpp_expired_dlr_message()
                        expired_cnt += 1

                await db.commit()

            if batch_id:
                await _update_batch_progress(db, batch_id)

            # 注水触发：对 delivered 消息按概率调度点击任务
            if delivered_items:
                from app.utils.water_trigger import trigger_water_for_delivered
                await trigger_water_for_delivered(db, delivered_items, channel_id, batch_id)

        logger.info(
            f"虚拟DLR批量完成: batch={batch_id}, "
            f"delivered={delivered}, failed={failed_cnt}, expired={expired_cnt}"
        )
        return {"delivered": delivered, "failed": failed_cnt, "expired": expired_cnt}
    except Exception as e:
        logger.error(f"虚拟DLR批量异常: batch={batch_id}, {e}")
        raise
    finally:
        await eng.dispose()


async def _do_virtual_dlr(message_id: str, channel_id: int):
    """根据虚拟通道配置，随机决定回执状态并更新 SMSLog（单条兼容）"""
    import random
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL, echo=False,
        pool_size=1, max_overflow=0, pool_pre_ping=True, pool_recycle=300,
    )
    factory = async_sessionmaker(eng, class_=_AS, expire_on_commit=False)
    try:
        async with factory() as db:
            result = await db.execute(
                select(SMSLog).where(SMSLog.message_id == message_id)
            )
            sms_log = result.scalar_one_or_none()
            if not sms_log:
                logger.warning(f"虚拟DLR: 未找到记录 {message_id}")
                return {"success": False, "reason": "not_found"}

            if sms_log.status not in ("sent", "pending", "queued"):
                return {"success": True, "status": sms_log.status}

            ch_result = await db.execute(
                select(Channel).where(Channel.id == channel_id)
            )
            channel = ch_result.scalar_one_or_none()
            cfg = channel.get_virtual_config() if channel else {}

            delivery_rate_min = cfg.get("delivery_rate_min", 80)
            delivery_rate_max = cfg.get("delivery_rate_max", 90)
            fail_rate_min = cfg.get("fail_rate_min", 5)
            fail_rate_max = cfg.get("fail_rate_max", 15)
            fail_codes = cfg.get("fail_codes", ["UNDELIV"])

            delivery_base = random.uniform(delivery_rate_min, delivery_rate_max)
            fail_base = random.uniform(fail_rate_min, fail_rate_max)

            delivery_rate = delivery_base + random.gauss(0, 1.5)
            fail_rate = fail_base + random.gauss(0, 0.8)
            delivery_rate = max(0.0, min(100.0, delivery_rate))
            fail_rate = max(0.0, min(100.0 - delivery_rate, fail_rate))

            roll = random.uniform(0, 100)
            if roll < delivery_rate:
                new_status = "delivered"
                sms_log.delivery_time = datetime.now()
                sms_log.error_message = None
            elif roll < delivery_rate + fail_rate:
                new_status = "failed"
                code = random.choice(fail_codes) if fail_codes else "UNDELIV"
                err_no = f"{random.randint(1,99):03d}"
                sms_log.error_message = f"SMPP DLR: stat={code} err={err_no}"
            else:
                new_status = "expired"
                sms_log.error_message = _mimic_smpp_expired_dlr_message()

            sms_log.status = new_status
            await db.commit()

            if sms_log.batch_id:
                await _update_batch_progress(db, sms_log.batch_id)

            return {"success": True, "message_id": message_id, "status": new_status}
    except Exception as e:
        logger.error(f"虚拟DLR异常: {message_id}, {e}")
        raise
    finally:
        await eng.dispose()


