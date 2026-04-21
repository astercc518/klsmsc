"""
Telegram消息服务 - 处理消息记录持久化
"""
from datetime import datetime
from typing import Optional, Any, Dict
import json
from bot.utils import logger
import os
import httpx

class MessageService:
    @staticmethod
    async def log_message(
        tg_user_id: int,
        direction: str,
        content: str,
        tg_username: Optional[str] = None,
        tg_chat_id: Optional[int] = None,
        message_type: str = "text",
        message_id: Optional[int] = None,
        reply_to_message_id: Optional[int] = None,
        extra_data: Optional[Dict] = None
    ):
        """记录消息到数据库（通过内部API解耦）"""
        try:
            # 内部后端API地址，默认 smsc-api:8000
            backend_url = os.getenv("API_URL", "http://api:8000")
            url = f"{backend_url.rstrip('/')}/api/v1/internal/bot/messages"
            
            payload = {
                "tg_user_id": tg_user_id,
                "direction": direction,
                "content": content,
                "tg_username": tg_username,
                "tg_chat_id": tg_chat_id,
                "message_type": message_type,
                "message_id": message_id,
                "reply_to_message_id": reply_to_message_id,
                "extra_data": extra_data
            }

            secret = os.environ.get("TELEGRAM_STAFF_API_SECRET") or ""
            headers = {"X-Internal-Token": secret} if secret else {}
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    logger.warning(f"记录Telegram消息API返回失败: {response.status_code}")
                    return False
            return True
        except Exception as e:
            logger.error(f"发送Telegram留痕消息到API失败: {e}")
            return False

    @staticmethod
    async def log_incoming_background(update: Any) -> None:
        """后台执行入站留痕，避免阻塞 Bot 主处理链（降低回复延迟）。"""
        try:
            await MessageService.log_incoming(update)
        except Exception as e:
            logger.warning("入站消息留痕失败(已忽略): {}", e)

    @staticmethod
    async def log_incoming(update: Any):
        """记录收到消息"""
        if not update.effective_user or not (update.message or update.callback_query):
            return
            
        user = update.effective_user
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        
        content = ""
        msg_type = "text"
        msg_id = None
        
        if update.callback_query:
            content = f"[Callback] {update.callback_query.data}"
            msg_type = "callback"
        elif update.message:
            msg_id = update.message.message_id
            if update.message.text:
                content = update.message.text
                if content.startswith('/'):
                    msg_type = "command"
            elif update.message.photo:
                content = "[Photo]"
                msg_type = "photo"
            elif update.message.document:
                content = f"[Document] {update.message.document.file_name}"
                msg_type = "document"
            else:
                content = "[Other Media]"
                msg_type = "media"

        await MessageService.log_message(
            tg_user_id=user.id,
            direction="incoming",
            content=content,
            tg_username=user.username,
            tg_chat_id=update.effective_chat.id if update.effective_chat else None,
            message_type=msg_type,
            message_id=msg_id,
            extra_data={"update_id": update.update_id}
        )

    @staticmethod
    async def log_outgoing(user_id: int, content: str, chat_id: Optional[int] = None, **kwargs):
        """记录发出消息"""
        await MessageService.log_message(
            tg_user_id=user_id,
            direction="outgoing",
            content=content,
            tg_chat_id=chat_id,
            message_type="text",
            extra_data=kwargs
        )
