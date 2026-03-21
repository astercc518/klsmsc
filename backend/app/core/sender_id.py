"""
发送方ID管理器模块
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.sender_id import SenderID
from app.modules.sms.channel import Channel
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SenderIDManager:
    """发送方ID管理器"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_sender_id(
        self,
        account_id: int,
        country_code: str,
        channel_id: int,
        preferred_sid: Optional[str] = None
    ) -> Optional[str]:
        """
        获取发送方ID
        
        优先级:
        1. 用户指定的SID（需验证权限）
        2. 账户+国家+通道专属SID
        3. 账户+通道通用SID（不限国家）
        4. 通道默认SID
        
        Args:
            account_id: 账户ID
            country_code: 国家代码
            channel_id: 通道ID
            preferred_sid: 用户指定的SID（可选）
            
        Returns:
            发送方ID或None
        """
        # 1. 如果指定了SID，验证权限和可用性
        if preferred_sid:
            sid = await self._validate_sid(
                preferred_sid, account_id, country_code, channel_id
            )
            if sid:
                logger.info(f"使用指定SID: {sid}")
                return sid
            else:
                logger.warning(f"指定的SID不可用: {preferred_sid}")
        
        # 2. 查询账户+国家+通道专属SID
        result = await self.db.execute(
            select(SenderID).where(
                SenderID.account_id == account_id,
                SenderID.country_code == country_code,
                SenderID.channel_id == channel_id,
                SenderID.status == 'active'
            ).order_by(SenderID.is_default.desc())
        )
        sender_id = result.scalar_one_or_none()
        if sender_id:
            logger.info(f"使用账户专属SID: {sender_id.sid}")
            return sender_id.sid
        
        # 3. 查询账户+通道通用SID（不限国家）
        result = await self.db.execute(
            select(SenderID).where(
                SenderID.account_id == account_id,
                SenderID.country_code.is_(None),
                SenderID.channel_id == channel_id,
                SenderID.status == 'active'
            ).order_by(SenderID.is_default.desc())
        )
        sender_id = result.scalar_one_or_none()
        if sender_id:
            logger.info(f"使用账户通用SID: {sender_id.sid}")
            return sender_id.sid
        
        # 4. 获取通道默认SID
        result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id)
        )
        channel = result.scalar_one_or_none()
        if channel and channel.default_sender_id:
            logger.info(f"使用通道默认SID: {channel.default_sender_id}")
            return channel.default_sender_id
        
        logger.warning(f"未找到可用的SID")
        return None
    
    async def _validate_sid(
        self,
        sid: str,
        account_id: int,
        country_code: str,
        channel_id: int
    ) -> Optional[str]:
        """验证SID是否可用"""
        result = await self.db.execute(
            select(SenderID).where(
                SenderID.sid == sid,
                SenderID.channel_id == channel_id,
                SenderID.status == 'active'
            ).where(
                (SenderID.country_code == country_code) | (SenderID.country_code.is_(None))
            ).where(
                (SenderID.account_id == account_id) | (SenderID.account_id.is_(None))
            )
        )
        sender_id = result.scalar_one_or_none()
        return sender_id.sid if sender_id else None

