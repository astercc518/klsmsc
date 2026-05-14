"""
Webhook回调Worker
"""
import asyncio
import httpx
import hmac
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from app.workers.celery_app import celery_app
from app.utils.logger import get_logger
from app.modules.common.account import Account
from app.modules.sms.sms_log import SMSLog
from app.database import AsyncSessionLocal
from sqlalchemy import select

logger = get_logger(__name__)

# webhook 整体超时：HTTP 调用本身已限制 30s，留点余量给 DB 查询
_WEBHOOK_TASK_TIMEOUT = float(os.getenv("WORKER_WEBHOOK_TASK_TIMEOUT_SEC", "60"))


@celery_app.task(
    name='send_webhook', bind=True, max_retries=3,
    soft_time_limit=int(os.getenv("WORKER_WEBHOOK_SOFT_TIMEOUT_SEC", "55")),
    time_limit=int(os.getenv("WORKER_WEBHOOK_HARD_TIMEOUT_SEC", "75")),
)
def send_webhook_task(self, account_id: int, message_id: str, status: str, data: Dict):
    """
    发送Webhook回调任务

    Args:
        account_id: 账户ID
        message_id: 消息ID
        status: 状态 (sent/delivered/failed)
        data: 额外数据
    """
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
        
        if not result['success'] and self.request.retries < self.max_retries:
            # 重试延迟: 1分钟、5分钟、15分钟
            retry_delays = [60, 300, 900]
            delay = retry_delays[min(self.request.retries, len(retry_delays) - 1)]
            logger.info(f"Webhook回调失败，将在 {delay} 秒后重试: {message_id}")
            raise self.retry(countdown=delay, exc=Exception(result.get('error')))
        
        return result
    except Exception as e:
        logger.error(f"Webhook发送异常: {str(e)}", exc_info=e)
        return {"success": False, "error": str(e)}


async def _send_webhook_async(account_id: int, message_id: str, status: str, data: Dict) -> Dict:
    """
    异步发送Webhook回调
    """
    async with AsyncSessionLocal() as db:
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
                
                if response.status_code == 200:
                    logger.info(f"Webhook回调成功: {message_id} -> {webhook_url}")
                    return {"success": True}
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"Webhook回调返回非200: {error_msg}")
                    return {"success": False, "error": error_msg}
                    
        except httpx.TimeoutException:
            error_msg = "Webhook请求超时"
            logger.warning(f"{error_msg}: {webhook_url}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Webhook请求异常: {str(e)}"
            logger.error(error_msg, exc_info=e)
            return {"success": False, "error": error_msg}


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
    if account_id is not _ACCOUNT_ID_ARG_UNSET:
        if not account_id:
            logger.warning(f"无法触发Webhook: 无账户ID: {message_id}")
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
    from app.config import settings as _s

    # 调参：窗口 60 秒，≥3 个不同 token 才视为扇出
    # 阈值=3 的取舍：宁可放过同 NAT 下两个真人 60s 内各点一条，
    # 也不误杀；批次 469 那种 1 秒内同 IP 命中 3+ 个 token 仍跑不掉。
    IP_FANOUT_WINDOW = 60
    IP_FANOUT_THRESHOLD = 3

    ua_is_bot, ua_reason = classify_user_agent(user_agent)
    ip_norm = (client_ip or "").strip()

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

        is_bot = bool(ua_is_bot or ip_is_bot)
        # reason 优先级：UA 已判定 bot 时保留 UA 原因；否则若 IP 扇出 → ip_fanout
        if ua_is_bot:
            reason = ua_reason
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

                # 回写：把同 IP 在窗口内已落表却被判为人的早期点击，全部翻成 ip_fanout。
                # 限定 is_bot=False 才更新（避免覆盖更具体的 UA 原因）。
                if retro_flip_ip and ip_norm:
                    cutoff = _dt.now() - _td(seconds=IP_FANOUT_WINDOW)
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
