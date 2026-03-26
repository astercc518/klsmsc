"""
安全日志相关的 Pydantic Schemas
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SecurityEventType(str, Enum):
    """安全事件类型"""
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    API_KEY_CREATE = "api_key_create"
    API_KEY_DELETE = "api_key_delete"
    PERMISSION_CHANGE = "permission_change"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class SecurityLevel(str, Enum):
    """安全级别"""
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


class SecurityLogResponse(BaseModel):
    """安全日志响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: Optional[int]
    event_type: SecurityEventType
    level: SecurityLevel
    ip_address: Optional[str]
    user_agent: Optional[str]
    details: Optional[Dict[str, Any]]
    created_at: datetime


class SecurityLogListResponse(BaseModel):
    """安全日志列表响应"""
    total: int
    items: List[SecurityLogResponse]
    page: int
    page_size: int


class LoginAttemptResponse(BaseModel):
    """登录尝试响应（ORM 字段为 attempted_at，对外 JSON 仍为 created_at）"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    username: Optional[str] = None
    ip_address: Optional[str] = None
    success: bool
    failure_reason: Optional[str] = None
    created_at: datetime = Field(validation_alias="attempted_at")


class LoginAttemptListResponse(BaseModel):
    """登录记录分页"""
    total: int
    items: List[LoginAttemptResponse]
    page: int
    page_size: int


class SecurityStats(BaseModel):
    """安全统计"""
    total_events: int
    login_attempts_today: int
    failed_logins_today: int
    suspicious_activities: int
    rate_limit_exceeded: int
