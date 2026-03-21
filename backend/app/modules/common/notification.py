"""
通知模型（P1-3）
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, TIMESTAMP, Text, JSON
from sqlalchemy.sql import func
from app.database import Base
import enum


class NotificationType(str, enum.Enum):
    """通知类型"""
    SYSTEM = "system"
    BALANCE = "balance"
    SMS = "sms"
    SECURITY = "security"


class NotificationPriority(str, enum.Enum):
    """通知优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Notification(Base):
    """通知表"""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True, comment="通知ID")
    account_id = Column(Integer, nullable=False, index=True, comment="账户ID")
    
    # 通知内容
    title = Column(String(200), nullable=False, comment="标题")
    content = Column(Text, nullable=False, comment="内容")
    notification_type = Column(
        String(50),
        nullable=False,
        default="system",
        comment="通知类型"
    )
    priority = Column(
        String(50),
        nullable=False,
        default="normal",
        comment="优先级"
    )
    
    # 状态
    is_read = Column(Boolean, default=False, nullable=False, comment="是否已读")
    read_at = Column(TIMESTAMP, comment="阅读时间")
    
    # 扩展
    action_url = Column(String(500), comment="操作链接")
    extra_data = Column(JSON, comment="额外数据")
    
    # 时间
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="软删除标记")
    
    def __repr__(self):
        return f"<Notification(id={self.id}, title='{self.title}', is_read={self.is_read})>"
