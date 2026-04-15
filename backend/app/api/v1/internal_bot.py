from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import json

from app.database import get_db
from app.modules.common.telegram_message import TelegramMessage
from app.modules.common.telegram_binding import TelegramBinding
from app.modules.common.account import Account
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

class BotMessageLogRequest(BaseModel):
    tg_user_id: int
    direction: str
    content: str
    tg_username: Optional[str] = None
    tg_chat_id: Optional[int] = None
    message_type: str = "text"
    message_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    extra_data: Optional[Dict[str, Any]] = None

@router.post("/messages")
async def log_bot_message(
    request: BotMessageLogRequest,
    db: AsyncSession = Depends(get_db)
):
    """供内部 Bot 服务调用的消息留痕接口"""
    try:
        account_id = None
        account_name = None
        
        binding_query = select(TelegramBinding, Account).join(
            Account, TelegramBinding.account_id == Account.id
        ).where(
            TelegramBinding.tg_id == request.tg_user_id
        )
        result = await db.execute(binding_query)
        row = result.first()
        if row:
            binding, account = row
            account_id = account.id
            account_name = account.account_name

        msg = TelegramMessage(
            tg_user_id=str(request.tg_user_id),
            tg_username=request.tg_username,
            tg_chat_id=str(request.tg_chat_id) if request.tg_chat_id else None,
            direction=request.direction,
            message_type=request.message_type,
            content=request.content,
            account_id=account_id,
            account_name=account_name,
            message_id=str(request.message_id) if request.message_id else None,
            reply_to_message_id=str(request.reply_to_message_id) if request.reply_to_message_id else None,
            extra_data=json.dumps(request.extra_data) if request.extra_data else None,
            created_at=datetime.now()
        )
        db.add(msg)
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"处理内部Bot日记请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
