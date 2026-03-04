"""
Telegram 用户数据模型
"""
from sqlalchemy import Column, Integer, String, BigInteger, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class TelegramUser(Base):
    """Telegram 用户表"""
    __tablename__ = "telegram_users"
    
    tg_id = Column(BigInteger, primary_key=True, comment="Telegram User ID")
    username = Column(String(100), comment="TG用户名")
    first_name = Column(String(100), comment="TG昵称")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True, comment="关联账户ID")
    lang_code = Column(String(10), default="en", comment="语言偏好")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    last_active_at = Column(TIMESTAMP, comment="最后活跃时间")
    
    def __repr__(self):
        return f"<TelegramUser(tg_id={self.tg_id}, account_id={self.account_id})>"
