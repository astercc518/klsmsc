"""
通知相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class NotificationType(str, Enum):
    """通知类型"""
    SYSTEM = "system"
    BALANCE = "balance"
    SMS = "sms"
    SECURITY = "security"


class NotificationPriority(str, Enum):
    """通知优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationCreate(BaseModel):
    """创建通知"""
    title: str = Field(..., min_length=1, max_length=200, description="标题")
    content: str = Field(..., min_length=1, description="内容")
    notification_type: NotificationType = Field(default=NotificationType.SYSTEM)
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL)
    action_url: Optional[str] = Field(None, max_length=500, description="操作链接")


class NotificationResponse(BaseModel):
    """通知响应"""
    id: int
    account_id: int
    title: str
    content: str
    notification_type: NotificationType
    priority: NotificationPriority
    is_read: bool
    action_url: Optional[str]
    extra_data: Optional[Dict[str, Any]]
    created_at: datetime
    read_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """通知列表响应"""
    total: int
    unread_count: int
    items: List[NotificationResponse]
    page: int
    page_size: int


class NotificationStats(BaseModel):
    """通知统计"""
    total_notifications: int
    unread_notifications: int
    today_notifications: int
