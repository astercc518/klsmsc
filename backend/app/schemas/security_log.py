"""
安全日志相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field
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
    id: int
    account_id: Optional[int]
    event_type: SecurityEventType
    level: SecurityLevel
    ip_address: Optional[str]
    user_agent: Optional[str]
    details: Optional[Dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True


class SecurityLogListResponse(BaseModel):
    """安全日志列表响应"""
    total: int
    items: List[SecurityLogResponse]
    page: int
    page_size: int


class LoginAttemptResponse(BaseModel):
    """登录尝试响应"""
    id: int
    username: str
    ip_address: str
    success: bool
    failure_reason: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class SecurityStats(BaseModel):
    """安全统计"""
    total_events: int
    login_attempts_today: int
    failed_logins_today: int
    suspicious_activities: int
    rate_limit_exceeded: int
