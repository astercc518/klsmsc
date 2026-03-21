"""
审核服务模块
"""
import hashlib
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.sms_batch import SmsBatch
from app.modules.sms.sms_template import SmsTemplate
from app.utils.logger import get_logger

logger = get_logger(__name__)

class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _calculate_hash(self, content: str) -> str:
        """计算内容哈希 (SHA256)"""
        # 归一化：去除首尾空格
        normalized = content.strip()
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    async def is_content_approved(self, account_id: int, content: str) -> bool:
        """检查内容是否在白名单"""
        content_hash = self._calculate_hash(content)
        query = select(SmsTemplate).where(
            SmsTemplate.account_id == account_id,
            SmsTemplate.content_hash == content_hash,
            SmsTemplate.status == 'approved'
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def submit_batch(
        self,
        account_id: int,
        file_path: str,
        content: str,
        total_count: int,
        total_cost: float,
        batch_id: str
    ) -> SmsBatch:
        """
        提交群发批次
        如果内容在白名单中，自动通过；否则待审核。
        """
        is_approved = await self.is_content_approved(account_id, content)
        status = 'approved' if is_approved else 'pending_audit' # approved means ready to send queue
        # 如果是approved，其实可以直接变为sending或queued，这里简化状态机
        # 实际逻辑：如果approved，Bot端可能会直接触发发送任务
        
        # 如果 approved，可以直接设为 sending 并返回，由调用方触发Celery
        if is_approved:
            status = 'sending' 
            # 注意：实际发送逻辑需要调用 QueueManager，这里只负责状态记录
        
        batch = SmsBatch(
            id=batch_id,
            account_id=account_id,
            file_path=file_path,
            content=content,
            total_count=total_count,
            total_cost=total_cost,
            status=status
        )
        self.db.add(batch)
        await self.db.commit()
        return batch

    async def approve_batch(self, batch_id: str, admin_id: int) -> Optional[SmsBatch]:
        """审核通过批次"""
        result = await self.db.execute(
            select(SmsBatch).where(SmsBatch.id == batch_id)
        )
        batch = result.scalar_one_or_none()
        
        if not batch or batch.status != 'pending_audit':
            return None
            
        # 1. 更新批次状态
        batch.status = 'sending'
        batch.audit_by = admin_id
        batch.audit_at = datetime.now()
        
        # 2. 添加到白名单
        content_hash = self._calculate_hash(batch.content)
        # 检查是否已存在
        tpl_query = select(SmsTemplate).where(
            SmsTemplate.account_id == batch.account_id,
            SmsTemplate.content_hash == content_hash
        )
        tpl_result = await self.db.execute(tpl_query)
        existing_tpl = tpl_result.scalar_one_or_none()
        
        if not existing_tpl:
            new_tpl = SmsTemplate(
                account_id=batch.account_id,
                content_hash=content_hash,
                content_text=batch.content,
                status='approved'
            )
            self.db.add(new_tpl)
            
        await self.db.commit()
        return batch

    async def reject_batch(self, batch_id: str, admin_id: int, reject_reason: Optional[str] = None) -> Optional[SmsBatch]:
        """驳回批次"""
        result = await self.db.execute(
            select(SmsBatch).where(SmsBatch.id == batch_id)
        )
        batch = result.scalar_one_or_none()
        
        if not batch:
            return None
            
        batch.status = 'rejected'
        batch.audit_by = admin_id
        batch.audit_at = datetime.now()
        if reject_reason:
            batch.reject_reason = reject_reason
        await self.db.commit()
        return batch
