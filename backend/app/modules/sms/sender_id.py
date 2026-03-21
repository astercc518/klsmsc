"""发送方ID模型"""
from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class SenderID(Base):
    __tablename__ = 'sender_ids'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True, comment='账户ID')
    country_code = Column(String(10), nullable=True, comment='国家代码')
    channel_id = Column(Integer, ForeignKey('channels.id'), nullable=False, comment='通道ID')
    sid = Column(String(50), nullable=False, comment='发送方ID')
    status = Column(Enum('active', 'inactive', 'pending', 'rejected', name='sender_id_status'), default='pending', comment='状态')
    is_default = Column(Boolean, default=False, comment='是否默认')
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
