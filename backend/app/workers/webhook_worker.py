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
        callback_data = {
            "message_id": message_id,
            "status": status,
            "phone_number": sms_log.phone_number,
            "country_code": sms_log.country_code,
            "submit_time": sms_log.submit_time.isoformat() if sms_log.submit_time else None,
            "sent_time": sms_log.sent_time.isoformat() if sms_log.sent_time else None,
            "delivery_time": sms_log.delivery_time.isoformat() if sms_log.delivery_time else None,
            "error_code": sms_log.error_code,
            "error_message": sms_log.error_message,
            "channel_id": sms_log.channel_id,
            "sender_id": sms_log.sender_id,
            "timestamp": datetime.now().isoformat()
        }
        
        # 生成HMAC-SHA256签名
        secret = account.api_secret or account.api_key
        signature = _generate_signature(secret, json.dumps(callback_data, sort_keys=True))
        
        # 发送HTTP POST
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=callback_data,
                    headers={
                        "Content-Type": "application/json",
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
