"""
Telegram 绑定关系模型
"""
from sqlalchemy import Column, Integer, BigInteger, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class TelegramBinding(Base):
    """Telegram 绑定关系表 (One-to-Many)"""
    __tablename__ = "telegram_bindings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, nullable=False, index=True, comment="Telegram User ID")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, comment="账户ID")
    is_active = Column(Boolean, default=False, comment="是否当前活跃账户")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    def __repr__(self):
        return f"<TelegramBinding(tg={self.tg_id}, acc={self.account_id}, active={self.is_active})>"
