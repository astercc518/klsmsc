"""
Telegram消息服务 - 处理消息记录持久化
"""
from datetime import datetime
from typing import Optional, Any, Dict
import json
from sqlalchemy import select
from bot.utils import get_session, logger
from app.modules.common.telegram_message import TelegramMessage
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.account import Account

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
        """记录消息到数据库"""
        try:
            async with get_session() as db:
                # 尝试查找关联账户
                account_id = None
                account_name = None
                
                binding_query = select(TelegramBinding, Account).join(
                    Account, TelegramBinding.account_id == Account.id
                ).where(
                    TelegramBinding.tg_id == tg_user_id
                )
                result = await db.execute(binding_query)
                row = result.first()
                if row:
                    binding, account = row
                    account_id = account.id
                    account_name = account.account_name

                # 创建消息记录
                msg = TelegramMessage(
                    tg_user_id=str(tg_user_id),
                    tg_username=tg_username,
                    tg_chat_id=str(tg_chat_id) if tg_chat_id else None,
                    direction=direction,
                    message_type=message_type,
                    content=content,
                    account_id=account_id,
                    account_name=account_name,
                    message_id=str(message_id) if message_id else None,
                    reply_to_message_id=str(reply_to_message_id) if reply_to_message_id else None,
                    extra_data=json.dumps(extra_data) if extra_data else None,
                    created_at=datetime.now()
                )
                db.add(msg)
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"记录Telegram消息失败: {e}")
            return False

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
