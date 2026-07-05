"""
Webhook回调Worker
"""
import asyncio
import httpx
import hmac
import hashlib
import ipaddress
import json
import os
import socket
import time
import redis as _redis_sync
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from app.workers.celery_app import celery_app
from app.utils.logger import get_logger
from app.modules.common.account import Account
from app.modules.sms.sms_log import SMSLog
from app.database import AsyncSessionLocal
from sqlalchemy import select

logger = get_logger(__name__)

# webhook 整体超时：HTTP 调用本身已限制 30s，留点余量给 DB 查询
_WEBHOOK_TASK_TIMEOUT = float(os.getenv("WORKER_WEBHOOK_TASK_TIMEOUT_SEC", "60"))

# 只发终态回调（默认开）：sent/accepted 等中间态对下游 DLR 是冗余，且会让回调量翻倍、
# 大批量时打爆 webhook_tasks 队列。开启后仅发终态(delivered/failed/undeliv/...)。
# 设 WEBHOOK_TERMINAL_ONLY=0 可恢复"每个状态都发"的旧行为。
_WEBHOOK_TERMINAL_ONLY = os.getenv("WEBHOOK_TERMINAL_ONLY", "1").strip().lower() in ("1", "true", "yes", "on")
# 已受理但未到终态的中间状态——开启"只发终态"时跳过这些；其余(含未知状态)一律放行，避免误丢真回执
_NON_TERMINAL_WEBHOOK_STATUSES = frozenset({
    "sent", "submitted", "accepted", "queued", "enroute", "en_route",
    "processing", "pending", "buffered", "scheduled", "in_progress",
})


def _webhook_status_worth_sending(status) -> bool:
    """开启"只发终态"时，过滤掉 sent/accepted 等中间态回调。"""
    if not _WEBHOOK_TERMINAL_ONLY:
        return True
    return str(status or "").strip().lower() not in _NON_TERMINAL_WEBHOOK_STATUSES


def validate_webhook_url(url: str) -> Tuple[bool, str]:
    """
    SSRF 防护：校验 webhook URL 不指向内网/本机/链路本地/云元数据等敏感地址。

    Returns: (ok, error_reason)。ok=True 表示安全可外联。

    防御点：
    - 只允许 http/https
    - 拒绝 host 是 IP 字面量直接命中私网/回环/链路本地/保留段
    - 解析 DNS 后逐个 IP 校验（防止 DNS rebinding 与 *.localhost 指向 127.x）
    """
    if not url or not isinstance(url, str):
        return False, "webhook_url 为空"
    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        return False, f"webhook_url 解析失败: {e}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"仅允许 http/https 协议（当前: {scheme or '空'}）"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "webhook_url 缺少 host"

    # 解析所有 A/AAAA 记录；任何一个落在禁段都拒绝（防 DNS rebinding 在多记录间漂移）
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"webhook_url DNS 解析失败: {e}"

    seen_addrs = set()
    for info in infos:
        addr = info[4][0]
        if addr in seen_addrs:
            continue
        seen_addrs.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, f"无法解析地址: {addr}"
        # 一刀切拒绝所有非公网 IP（私网/回环/链路本地/多播/保留/未指定）
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, f"webhook_url 指向受限地址段: {addr}"

    if not seen_addrs:
        return False, "webhook_url DNS 解析为空"
    return True, ""


# ---------------------------------------------------------------------------
# P0 韧性加固：三段硬超时 + per-endpoint 熔断 + per-account 在途信号量（背压）
# 目的：独立 worker 之上再叠一层「单个慢/死客户不耗尽整池」的弹性隔离。
# 全部 fail-open：Redis 抖动时只是退化为不限流/不熔断，绝不阻断真实回执。
# ---------------------------------------------------------------------------

# 三段硬超时：替掉单一 timeout=10s。connect 快失败防 SYN 黑洞；read 限制慢响应钉死协程。
_HTTP_TIMEOUT = httpx.Timeout(
    connect=float(os.getenv("WEBHOOK_HTTP_CONNECT_TIMEOUT", "3")),
    read=float(os.getenv("WEBHOOK_HTTP_READ_TIMEOUT", "5")),
    write=float(os.getenv("WEBHOOK_HTTP_WRITE_TIMEOUT", "3")),
    pool=float(os.getenv("WEBHOOK_HTTP_POOL_TIMEOUT", "2")),
)

# 熔断器：单账户(端点)累计失败 ≥ 阈值则 open，冷却期内直接快速失败、零网络连接。
_CB_FAIL_THRESHOLD = int(os.getenv("WEBHOOK_CB_FAIL_THRESHOLD", "20"))
_CB_OPEN_SECONDS = int(os.getenv("WEBHOOK_CB_OPEN_SECONDS", "300"))
# 在途信号量：单账户最多 K 个在途推送，超过即背压（让该账户回执延迟重试，不抢占他人槽位）。
_ACCT_MAX_INFLIGHT = int(os.getenv("WEBHOOK_ACCT_MAX_INFLIGHT", "8"))

# 同步 redis 客户端：与 asyncio loop 无绑定，可在 Celery 每任务新建 loop 间安全复用（单例）。
_sync_redis_client = None


def _get_sync_redis():
    global _sync_redis_client
    if _sync_redis_client is None:
        from app.config import settings as _s
        _sync_redis_client = _redis_sync.Redis.from_url(
            _s.REDIS_URL, decode_responses=True,
            socket_timeout=1.0, socket_connect_timeout=1.0,
        )
    return _sync_redis_client


class _BackpressureReject(Exception):
    """单账户在途推送超限，触发背压（延迟重试，不丢）。"""


def _cb_allow(account_id) -> bool:
    """熔断闸门：open 且冷却未到 → 拒绝(快速失败)；冷却到期 → 放一个半开探针。Redis 故障 fail-open。"""
    try:
        r = _get_sync_redis()
        key = f"wh:cb:{account_id}"
        if r.hget(key, "state") == "open":
            ou = r.hget(key, "open_until")
            if ou and time.time() < float(ou):
                return False
            r.hset(key, "state", "half_open")  # 冷却到期，放探针试探对端是否恢复
        return True
    except Exception:
        return True


def _cb_record(account_id, ok: bool):
    """记录一次推送结果：成功即关闭熔断；失败累加，达阈值则 open 并设冷却。Redis 故障静默。"""
    try:
        r = _get_sync_redis()
        key = f"wh:cb:{account_id}"
        if ok:
            r.delete(key)
        else:
            n = r.hincrby(key, "fails", 1)
            r.expire(key, _CB_OPEN_SECONDS + 60)
            if n >= _CB_FAIL_THRESHOLD:
                r.hset(key, mapping={"state": "open", "open_until": str(time.time() + _CB_OPEN_SECONDS)})
    except Exception:
        pass


@contextmanager
def _acct_slot(account_id):
    """per-account 在途信号量。超限抛 _BackpressureReject；Redis 故障 fail-open（不限流）。"""
    r = None
    key = f"wh:inflight:{account_id}"
    held = False
    try:
        r = _get_sync_redis()
        n = r.incr(key)
        held = True
        if n == 1:
            r.expire(key, 60)  # 防进程崩溃致计数泄漏的兜底过期
        if n > _ACCT_MAX_INFLIGHT:
            r.decr(key)
            held = False
            raise _BackpressureReject(account_id)
    except _BackpressureReject:
        raise
    except Exception as e:
        logger.debug(f"inflight 信号量 redis 异常，fail-open 放行: {e}")
        held = False
    try:
        yield
    finally:
        if held and r is not None:
            try:
                r.decr(key)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# P1：DLX 延迟阶梯重试 + per-account 令牌桶限流
# ---------------------------------------------------------------------------

# 失败重试延迟阶梯，与 celery_app 的 webhook.retry.* 队列一一对应。穷尽后入 DLQ。
_RETRY_QUEUES = ['webhook.retry.1m', 'webhook.retry.5m', 'webhook.retry.30m',
                 'webhook.retry.2h', 'webhook.retry.6h']
_DLQ_QUEUE = 'webhook.dlq'
_THROTTLE_QUEUE = 'webhook.throttle'

# 令牌桶限流（per-account）。WEBHOOK_RATE_PER_SEC<=0 时关闭。
_RATE_PER_SEC = float(os.getenv("WEBHOOK_RATE_PER_SEC", "50"))
_RATE_BURST = float(os.getenv("WEBHOOK_RATE_BURST", "100"))
# 全局令牌桶（P2）：护住推送总出口——带宽/Redis/下游对端总压，兜底所有账户合计速率。
_GLOBAL_RATE_PER_SEC = float(os.getenv("WEBHOOK_GLOBAL_RATE_PER_SEC", "500"))
_GLOBAL_BURST = float(os.getenv("WEBHOOK_GLOBAL_BURST", "1000"))
_RATE_LUA = """
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1]); local ts = tonumber(data[2])
local rate = tonumber(ARGV[1]); local burst = tonumber(ARGV[2]); local now = tonumber(ARGV[3])
if tokens == nil then tokens = burst; ts = now end
tokens = math.min(burst, tokens + math.max(0, now - ts) * rate)
local allowed = 0
if tokens >= 1 then tokens = tokens - 1; allowed = 1 end
redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], math.ceil(burst / rate) + 10)
return allowed
"""
_rate_script = None


def _token_take(key: str, rate: float, burst: float) -> bool:
    """通用令牌桶取一枚令牌。rate<=0 关闭；Redis 故障 fail-open。"""
    if rate <= 0:
        return True
    try:
        r = _get_sync_redis()
        global _rate_script
        if _rate_script is None:
            _rate_script = r.register_script(_RATE_LUA)
        return bool(_rate_script(keys=[key], args=[rate, burst, time.time()]))
    except Exception:
        return True


def _rate_allow(account_id) -> bool:
    """两道令牌桶：先全局(护总出口)后 per-account(护单客户公平)，任一不足即限流。"""
    if not _token_take("wh:rate:__global__", _GLOBAL_RATE_PER_SEC, _GLOBAL_BURST):
        return False
    return _token_take(f"wh:rate:{account_id}", _RATE_PER_SEC, _RATE_BURST)


def _requeue_delayed(args, queue_name):
    """把任务重投到指定延迟队列（消息躺到 TTL 后死信回 webhook_tasks）。"""
    try:
        send_webhook_task.apply_async(args=args, queue=queue_name)
    except Exception as e:
        logger.error(f"Webhook 重投 {queue_name} 失败: {e}")


def _to_dlq(account_id, message_id, status, data, error):
    """穷尽重试 → 落 DLQ（retry_no 归零便于手动重放）+ 审计日志。"""
    try:
        send_webhook_task.apply_async(
            args=[account_id, message_id, status, data, 0], queue=_DLQ_QUEUE)
    except Exception as e:
        logger.error(f"Webhook 入 DLQ 失败: {e}")
    logger.warning(
        f"Webhook 穷尽重试丢入 DLQ: account={account_id} mid={message_id} "
        f"status={status} last_error={error}")


@celery_app.task(
    name='send_webhook', bind=True, max_retries=3,
    soft_time_limit=int(os.getenv("WORKER_WEBHOOK_SOFT_TIMEOUT_SEC", "55")),
    time_limit=int(os.getenv("WORKER_WEBHOOK_HARD_TIMEOUT_SEC", "75")),
)
def send_webhook_task(self, account_id: int, message_id: str, status: str, data: Dict, retry_no: int = 0):
    """
    发送Webhook回调任务

    Args:
        account_id: 账户ID
        message_id: 消息ID
        status: 状态 (sent/delivered/failed)
        data: 额外数据
        retry_no: 当前重试序号（DLX 阶梯重投时递增；首次入队为 0）

    重试不再用 Celery countdown，而是把消息投到 webhook.retry.* 延迟队列，
    到 TTL 后死信回 webhook_tasks 重投——消息躺在 broker（落盘），不占 worker 内存、重启不丢。
    """
    # 只发终态：跳过 sent/accepted 等中间态（兜底拦截绕过 trigger_webhook 的直连 apply_async 调用）
    if not _webhook_status_worth_sending(status):
        return {"success": True, "skipped": True, "reason": f"non-terminal status: {status}"}
    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                asyncio.wait_for(
                    _send_webhook_async(account_id, message_id, status, data),
                    timeout=_WEBHOOK_TASK_TIMEOUT,
                )
            )
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Webhook发送异常: {str(e)}", exc_info=e)
        result = {"success": False, "error": str(e), "retriable": True}

    # 限流：短延迟(10s)重投，不增加重试计数
    if result.get("throttle"):
        _requeue_delayed([account_id, message_id, status, data, retry_no], _THROTTLE_QUEUE)
        return result

    # 成功 / 跳过 / 明确不可重试（账户或短信记录不存在等）→ 直接返回，不重试
    if result.get("success") or result.get("skipped") or not result.get("retriable"):
        return result

    # 失败且可重试 → DLX 延迟阶梯；穷尽 → DLQ
    if retry_no < len(_RETRY_QUEUES):
        q = _RETRY_QUEUES[retry_no]
        _requeue_delayed([account_id, message_id, status, data, retry_no + 1], q)
        logger.info(f"Webhook 第 {retry_no + 1} 次重试入延迟队列 {q}: mid={message_id} err={result.get('error')}")
    else:
        _to_dlq(account_id, message_id, status, data, result.get("error"))
    return result


async def _send_webhook_async(account_id: int, message_id: str, status: str, data: Dict) -> Dict:
    """
    异步发送Webhook回调
    """
    # Celery 每个任务新建并关闭 event loop（见 send_webhook_task）。不能用全局 AsyncSessionLocal——
    # 其连接池里的 asyncmy 连接绑定到首次创建它的 loop，跨 loop 复用会触发
    # "Future attached to a different loop" / "Event loop is closed"。
    # 在本任务 loop 内自建 NullPool 引擎、用完即弃，与 record_link_click_task 同模式。
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool
    from app.config import settings as _settings

    _eng = create_async_engine(
        _settings.SQLALCHEMY_DATABASE_URL, echo=False, poolclass=NullPool,
    )
    _factory = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
    try:
      async with _factory() as db:
        # 查询账户
        result = await db.execute(
            select(Account).where(Account.id == account_id)
        )
        account = result.scalar_one_or_none()
        
        if not account:
            return {"success": False, "error": "Account not found"}
        
        # 获取Webhook URL
        webhook_url = account.webhook_url
        
        # 如果没有配置webhook_url，跳过回调
        if not webhook_url:
            logger.debug(f"账户 {account_id} 未配置Webhook URL，跳过回调")
            return {"success": True, "skipped": True, "reason": "No webhook URL configured"}

        # SSRF 防护：发送前再校验一次（即便入库时漏了，这里兜底）。
        # 不重试——指向内网的 URL 重试再多次也是错，避免反复扫探内网。
        ok, reason = validate_webhook_url(webhook_url)
        if not ok:
            logger.warning(
                f"Webhook回调拒绝（疑似 SSRF）: account={account_id} url={webhook_url} reason={reason}"
            )
            return {
                "success": True,  # 标 True 防止 Celery 重试；但 skipped 字段告知调用方
                "skipped": True,
                "reason": f"webhook_url 被安全策略拒绝: {reason}",
            }

        # 令牌桶限流：超过 per-account 速率 → throttle，交由 10s 短延迟队列稍后重投（不计失败）。
        # 防「已配 URL 的客户瞬间十万回执」把推送池/对端打爆——gate 拦不住这种有效流量过载。
        if not _rate_allow(account_id):
            logger.info(f"Webhook 限流(account={account_id})，10s 后重投 mid={message_id}")
            return {"success": False, "throttle": True, "error": "rate_limited"}

        # 熔断闸门：对端连续失败 → open，冷却期内直接快速失败，连 SMSLog 查询/签名/网络都不做，
        # 给对端冷却、给自己省资源。返回 retriable=True 走既有重试延后再试。
        if not _cb_allow(account_id):
            logger.warning(f"Webhook 熔断中(open)，暂不推送 account={account_id} mid={message_id}")
            return {"success": False, "error": "circuit_open", "retriable": True}

        # 查询短信记录获取详细信息
        result = await db.execute(
            select(SMSLog).where(SMSLog.message_id == message_id)
        )
        sms_log = result.scalar_one_or_none()
        
        if not sms_log:
            return {"success": False, "error": "SMS log not found"}
        
        # 构造回调数据
        # 注意：sms_logs 表未存储 error_code / sender_id；前者保留位以兼容字段表，后者从 batch 取
        sender_id_val: Optional[str] = None
        if sms_log.batch_id:
            try:
                from app.modules.sms.sms_batch import SmsBatch
                batch_row = await db.execute(
                    select(SmsBatch.sender_id).where(SmsBatch.id == sms_log.batch_id)
                )
                sender_id_val = batch_row.scalar_one_or_none()
            except Exception:
                sender_id_val = None

        callback_data = {
            "message_id": message_id,
            "status": status,
            "phone_number": sms_log.phone_number,
            "country_code": sms_log.country_code,
            "submit_time": sms_log.submit_time.isoformat() if sms_log.submit_time else None,
            "sent_time": sms_log.sent_time.isoformat() if sms_log.sent_time else None,
            "delivery_time": sms_log.delivery_time.isoformat() if sms_log.delivery_time else None,
            "error_code": None,
            "error_message": sms_log.error_message,
            "channel_id": sms_log.channel_id,
            "sender_id": sender_id_val,
            "timestamp": datetime.now().isoformat()
        }

        # 生成HMAC-SHA256签名（与文档示例一致：sort_keys=True, ensure_ascii=False）
        secret = account.api_secret or account.api_key
        signature_payload = json.dumps(callback_data, sort_keys=True, ensure_ascii=False)
        signature = _generate_signature(secret, signature_payload)
        
        # 发送HTTP POST
        # 用 content= 而不是 json= 把已序列化好的字节直接发出，确保收方对 body 重新计算 HMAC 时
        # 字节序列与我们签名时完全一致（避免 httpx 默认紧凑 separators 与 json.dumps 默认空格 separators 的差异）
        try:
            # 背压：限制单账户在途推送数，一个慢/卡的客户最多占 _ACCT_MAX_INFLIGHT 个槽，不波及他人。
            with _acct_slot(account_id):
                # follow_redirects=False：防止 302 跳到内网（30x → http://127.0.0.1 仍是 SSRF）。
                # 三段硬超时：connect/read/write 分别限制，杜绝慢连接钉死协程/句柄。
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=False) as client:
                    response = await client.post(
                        webhook_url,
                        content=signature_payload.encode("utf-8"),
                        headers={
                            "Content-Type": "application/json; charset=utf-8",
                            "X-Signature": f"sha256={signature}",
                            "X-Timestamp": str(int(datetime.now().timestamp())),
                            "User-Agent": "SMS-Gateway-Webhook/1.0"
                        }
                    )

                ok = response.status_code == 200
                _cb_record(account_id, ok)   # 成功→关闭熔断；非200→计入失败
                if ok:
                    logger.info(f"Webhook回调成功: {message_id} -> {webhook_url}")
                    return {"success": True}
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(f"Webhook回调返回非200: {error_msg}")
                return {"success": False, "error": error_msg, "retriable": True}

        except _BackpressureReject:
            logger.info(f"Webhook 背压(账户在途超限)，延迟重试 account={account_id} mid={message_id}")
            return {"success": False, "error": "backpressure", "retriable": True}
        except httpx.TimeoutException:
            _cb_record(account_id, False)
            error_msg = "Webhook请求超时"
            logger.warning(f"{error_msg}: {webhook_url}")
            return {"success": False, "error": error_msg, "retriable": True}
        except Exception as e:
            _cb_record(account_id, False)
            error_msg = f"Webhook请求异常: {str(e)}"
            logger.error(error_msg, exc_info=e)
            return {"success": False, "error": error_msg, "retriable": True}
    finally:
        await _eng.dispose()


def _generate_signature(secret: str, payload: str) -> str:
    """
    生成HMAC-SHA256签名
    
    Args:
        secret: 密钥
        payload: 请求体（JSON字符串）
        
    Returns:
        hex格式的签名
    """
    return hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


# 区分「未传 account_id」与「显式传入」：Celery 中 _run_async 每任务新建并关闭事件循环，
# 若在此使用全局 AsyncSessionLocal，会与 asyncmy 连接绑定的 loop 冲突（Future attached to a different loop）。
_ACCOUNT_ID_ARG_UNSET = object()


# ── 入队前账户预检（防空转）───────────────────────────────────────────────
# 绝大多数账户未配置 webhook_url。若每条终态回执都无脑 send_webhook_task.delay，
# 任务进 worker 后要新建事件循环+NullPool 引擎、查库，才发现"无 URL 跳过"——纯空转烧 CPU
# （实测单个高发量账户可把 worker-webhook 顶到数百 % CPU，全是 skip）。
# 这里在入队前用 60s 进程内缓存的账户白名单先拦一道，只有真正配了 webhook 的账户才入队。
# 口径与 sms_worker._account_has_webhook 一致；刷新失败时 fail-open 放行，宁可多入队也不丢真回执。
_WEBHOOK_ACCT_CACHE: dict = {"ids": frozenset(), "exp": 0.0}
_WEBHOOK_ACCT_TTL = float(os.getenv("WEBHOOK_ACCT_CACHE_TTL_SEC", "60"))


async def _refresh_webhook_account_ids(db) -> frozenset:
    rows = await db.execute(
        select(Account.id).where(
            Account.webhook_url.isnot(None), Account.webhook_url != "",
            # 排除软删除/已关闭账户：删除客户残留的 webhook_url 不应再触发回执推送。
            Account.is_deleted == False, Account.status != "closed",
        )
    )
    return frozenset(r[0] for r in rows.all())


async def _account_has_webhook_cached(account_id, db=None) -> bool:
    """账户是否配置了有效 webhook_url（60s 进程内缓存）。
    db 为空时自建 NullPool 会话刷新——用于 trigger_webhook 的 account_id 直传分支，
    该分支刻意不持有全局会话（避免跨事件循环复用连接池）。刷新失败 → fail-open 返回 True。"""
    if not account_id:
        return False
    now = time.monotonic()
    if now >= _WEBHOOK_ACCT_CACHE["exp"]:
        try:
            if db is not None:
                ids = await _refresh_webhook_account_ids(db)
            else:
                from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
                from sqlalchemy.pool import NullPool
                from app.config import settings as _settings
                _eng = create_async_engine(
                    _settings.SQLALCHEMY_DATABASE_URL, echo=False, poolclass=NullPool,
                )
                try:
                    _factory = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
                    async with _factory() as _db:
                        ids = await _refresh_webhook_account_ids(_db)
                finally:
                    await _eng.dispose()
            _WEBHOOK_ACCT_CACHE["ids"] = ids
            _WEBHOOK_ACCT_CACHE["exp"] = now + _WEBHOOK_ACCT_TTL
        except Exception as e:
            logger.warning(f"刷新 webhook 账户缓存失败，本次放行入队: {e}")
            return True
    return account_id in _WEBHOOK_ACCT_CACHE["ids"]


async def trigger_webhook(
    message_id: str,
    status: str,
    data: Optional[Dict] = None,
    *,
    account_id: Any = _ACCOUNT_ID_ARG_UNSET,
):
    """
    触发Webhook回调

    Args:
        message_id: 消息ID
        status: 状态 (sent/delivered/failed)
        data: 额外数据
        account_id: 若调用方已持有账户 ID（如 worker 内已有 sms_log），应传入以避免打开全局引擎会话
    """
    # 只发终态：在入队前就拦掉中间态(如发送路径的 'sent')，避免无谓占用 webhook_tasks 队列
    if not _webhook_status_worth_sending(status):
        logger.debug(f"跳过非终态Webhook(只发终态): {message_id} status={status}")
        return
    if account_id is not _ACCOUNT_ID_ARG_UNSET:
        if not account_id:
            logger.warning(f"无法触发Webhook: 无账户ID: {message_id}")
            return
        if not await _account_has_webhook_cached(account_id):
            logger.debug(f"账户 {account_id} 未配置 webhook，跳过入队: {message_id}")
            return
        send_webhook_task.delay(account_id, message_id, status, data or {})
        logger.debug(f"Webhook回调任务已入队: {message_id}, 状态: {status}")
        return

    # 查询短信记录获取账户ID（API 等仍在全局引擎所在 loop 上运行）
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.modules.sms.sms_log import SMSLog

        result = await db.execute(select(SMSLog).where(SMSLog.message_id == message_id))
        sms_log = result.scalar_one_or_none()

        if not sms_log or not sms_log.account_id:
            logger.warning(f"无法触发Webhook: 短信记录不存在或无账户ID: {message_id}")
            return

        if not await _account_has_webhook_cached(sms_log.account_id, db=db):
            logger.debug(f"账户 {sms_log.account_id} 未配置 webhook，跳过入队: {message_id}")
            return

        send_webhook_task.delay(sms_log.account_id, message_id, status, data or {})
        logger.debug(f"Webhook回调任务已入队: {message_id}, 状态: {status}")


# 在状态更新时调用此函数
def notify_status_change(message_id: str, status: str, **kwargs):
    """
    通知状态变更（同步调用，内部会异步处理）
    
    Args:
        message_id: 消息ID
        status: 新状态
        **kwargs: 额外数据
    """
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            asyncio.wait_for(trigger_webhook(message_id, status, kwargs), timeout=_WEBHOOK_TASK_TIMEOUT)
        )
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 短链点击计数任务
# ---------------------------------------------------------------------------

@celery_app.task(name="record_link_click_task", ignore_result=True)
def record_link_click_task(token: str, client_ip: str, user_agent: str):
    """
    原子累加短链点击次数 + 写一条点击明细（含 IP/UA、UA 判定、IP 扇出判定）。

    机器判定有两条线：
    1. UA 分类器（classify_user_agent）— 命中已知 bot/CLI/扫描器签名。
    2. IP 扇出（Redis）— 同一 IP 在 IP_FANOUT_WINDOW 秒内点击 ≥ IP_FANOUT_THRESHOLD
       个不同 token 视为扫描器；命中后会**回写**之前同一窗口内已落表的同 IP 行
       （它们的 is_bot 改 1，bot_reason 改 'ip_fanout'）。这能识破伪装成
       Mobile Safari/Chrome 的运营商反诈/营销扫描——它们 UA 真但 IP 复用。
    """
    import asyncio as _asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool
    from sqlalchemy import select as _sel, update as _upd, and_
    from datetime import datetime as _dt, timedelta as _td
    from app.modules.sms.short_link_log import ShortLinkLog
    from app.modules.sms.short_link_click import ShortLinkClick
    from app.utils.bot_ua import classify_user_agent
    from app.utils.bot_ip import classify_client_ip
    from app.config import settings as _s

    # 调参（2026-05 强化版）：
    # - IP_FANOUT_WINDOW: 60s 内同一 IP 收集不同 token 数
    # - IP_FANOUT_THRESHOLD: 阈值 5（旧版 3）。CGNAT 出口（中国移动 / Viettel /
    #   学校企业 NAT）真人扇出常见 3-4 个 token，阈值 3 会误伤；扫描器一旦扇出
    #   多到 5+ 就是确凿信号。
    # - RETRO_FLIP_WINDOW: 命中扇出后只回写最近 10s 内的同 IP 点击为 bot，而非
    #   旧版的整个 60s 窗口。原因：扫描器的"扇出 burst"本身就在几秒内完成，
    #   把窗口缩到 10s 既能抓 burst，又不会把 30s 前点击的早期真人翻成 bot。
    IP_FANOUT_WINDOW = 60
    IP_FANOUT_THRESHOLD = 5
    RETRO_FLIP_WINDOW = 10

    ua_is_bot, ua_reason = classify_user_agent(user_agent)
    ip_norm = (client_ip or "").strip()
    ip_static_is_bot, ip_static_reason = classify_client_ip(ip_norm)

    async def _do():
        eng = create_async_engine(
            _s.SQLALCHEMY_DATABASE_URL,
            echo=False,
            poolclass=NullPool,
        )

        # IP 扇出：用 Redis SET 记录该 IP 近 IP_FANOUT_WINDOW 秒访问过的不同 token
        # 注意：不能复用 app.utils.cache.get_redis_client() 单例 —— 那个 client 绑定到
        # 创建它的 event loop；Celery 每个 task 都新建 loop，导致 "Event loop is closed"。
        # 这里在本任务的 loop 内创建独立的短命 client，与下方 async engine 同生共灭。
        ip_is_bot = False
        retro_flip_ip = False
        if ip_norm:
            try:
                import redis.asyncio as _aioredis
                _r = _aioredis.Redis.from_url(_s.REDIS_URL, decode_responses=False)
                try:
                    fkey = f"sl:ipset:{ip_norm}".encode()
                    await _r.sadd(fkey, token.encode())
                    await _r.expire(fkey, IP_FANOUT_WINDOW)
                    distinct = await _r.scard(fkey)
                    if distinct and int(distinct) >= IP_FANOUT_THRESHOLD:
                        ip_is_bot = True
                        retro_flip_ip = True
                finally:
                    await _r.aclose()
            except Exception as e:
                logger.warning(f"ip_fanout redis check failed (token={token}, ip={ip_norm}): {e}")

        is_bot = bool(ua_is_bot or ip_static_is_bot or ip_is_bot)
        # reason 优先级：UA > 静态 IP 名单（google_scanner 等）> IP 扇出。
        # 把更具体的命中原因放前面，便于后台按规则名分类排查。
        if ua_is_bot:
            reason = ua_reason
        elif ip_static_is_bot:
            reason = ip_static_reason
        elif ip_is_bot:
            reason = "ip_fanout"
        else:
            reason = ""

        try:
            factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
            async with factory() as db:
                sl_id = (
                    await db.execute(
                        _sel(ShortLinkLog.id).where(ShortLinkLog.token == token)
                    )
                ).scalar_one_or_none()

                await db.execute(
                    _upd(ShortLinkLog)
                    .where(ShortLinkLog.token == token)
                    .values(
                        click_count=ShortLinkLog.click_count + 1,
                        last_click_at=_dt.now(),
                    )
                )
                db.add(ShortLinkClick(
                    token=token,
                    short_link_log_id=sl_id,
                    clicked_at=_dt.now(),
                    client_ip=(ip_norm or None) and ip_norm[:64],
                    user_agent=(user_agent or "")[:512] or None,
                    is_bot=is_bot,
                    bot_reason=(reason or None),
                ))

                # 回写：把同 IP 在 RETRO_FLIP_WINDOW（10s）内已落表却被判为人的早期点击，
                # 翻成 ip_fanout。窗口刻意比 IP_FANOUT_WINDOW(60s) 短得多，只抓扫描器
                # 在几秒内的扇出 burst，避免把同 NAT 下早 30~60s 点击的真人误翻。
                # 限定 is_bot=False 才更新（避免覆盖更具体的 UA 原因）。
                if retro_flip_ip and ip_norm:
                    cutoff = _dt.now() - _td(seconds=RETRO_FLIP_WINDOW)
                    await db.execute(
                        _upd(ShortLinkClick)
                        .where(and_(
                            ShortLinkClick.client_ip == ip_norm,
                            ShortLinkClick.clicked_at >= cutoff,
                            ShortLinkClick.is_bot == False,  # noqa: E712
                        ))
                        .values(is_bot=True, bot_reason="ip_fanout")
                    )

                await db.commit()
        finally:
            await eng.dispose()

    loop = _asyncio.new_event_loop()
    try:
        loop.run_until_complete(_do())
    except Exception as exc:
        logger.warning(f"record_link_click_task failed for token={token}: {exc}")
    finally:
        loop.close()
