"""
通道管理API路由
"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.modules.common.account import Account
from app.modules.sms.channel import Channel
from app.core.auth import api_key_header, AuthService
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def get_current_account(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """获取当前认证账户"""
    return await AuthService.verify_api_key(api_key, db)


@router.get("/list")
async def list_channels(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取可用通道列表
    
    如果账户已绑定通道，只返回绑定的通道；否则返回所有可用通道
    """
    from app.modules.common.account import AccountChannel
    
    logger.info(f"查询通道列表: 账户={account.id}")
    
    # 1. 检查账户是否绑定了通道
    bound_result = await db.execute(
        select(AccountChannel, Channel)
        .join(Channel, AccountChannel.channel_id == Channel.id)
        .where(
            AccountChannel.account_id == account.id,
            Channel.status == 'active',
            Channel.is_deleted == False
        )
        .order_by(AccountChannel.priority)
    )
    bound_channels = bound_result.all()
    
    # 2. 如果绑定了通道，只返回绑定的通道
    if bound_channels:
        return {
            "success": True,
            "total": len(bound_channels),
            "bound": True,  # 标记：已绑定通道
            "channels": [
                {
                    "id": ch.id,
                    "code": ch.channel_code,
                    "name": ch.channel_name,
                    "protocol": ch.protocol,
                    "status": ch.status
                }
                for _, ch in bound_channels
            ]
        }
    
    # 3. 未绑定通道，返回所有可用通道
    result = await db.execute(
        select(Channel).where(
            Channel.status == 'active',
            Channel.is_deleted == False
        ).order_by(Channel.priority.desc())
    )
    channels = result.scalars().all()
    
    return {
        "success": True,
        "total": len(channels),
        "bound": False,  # 标记：未绑定通道
        "channels": [
            {
                "id": ch.id,
                "code": ch.channel_code,
                "name": ch.channel_name,
                "protocol": ch.protocol,
                "status": ch.status
            }
            for ch in channels
        ]
    }


@router.get("/{channel_id}")
async def get_channel_info(
    channel_id: int,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取通道详细信息
    """
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    
    if not channel:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Channel not found")
    
    return {
        "success": True,
        "channel": {
            "id": channel.id,
            "code": channel.channel_code,
            "name": channel.channel_name,
            "protocol": channel.protocol,
            "status": channel.status,
            "priority": channel.priority,
            "weight": channel.weight
        }
    }
