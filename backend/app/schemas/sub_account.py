"""
子账户相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SubAccountRole(str, Enum):
    """子账户角色"""
    VIEWER = "viewer"
    OPERATOR = "operator"
    MANAGER = "manager"


class SubAccountStatus(str, Enum):
    """子账户状态"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class SubAccountCreate(BaseModel):
    """创建子账户"""
    username: str = Field(..., min_length=3, max_length=100, description="用户名")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    password: str = Field(..., min_length=8, description="密码")
    role: SubAccountRole = Field(default=SubAccountRole.OPERATOR, description="角色")
    permissions: Optional[Dict[str, Any]] = Field(None, description="详细权限")
    rate_limit: Optional[int] = Field(None, ge=1, le=10000, description="请求限制")
    daily_limit: Optional[int] = Field(None, ge=1, description="每日发送限制")
    ip_whitelist: Optional[List[str]] = Field(None, description="IP白名单")
    description: Optional[str] = Field(None, max_length=500, description="备注")


class SubAccountUpdate(BaseModel):
    """更新子账户"""
    email: Optional[str] = Field(None, max_length=255)
    role: Optional[SubAccountRole] = None
    permissions: Optional[Dict[str, Any]] = None
    status: Optional[SubAccountStatus] = None
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    daily_limit: Optional[int] = Field(None, ge=1)
    ip_whitelist: Optional[List[str]] = None
    description: Optional[str] = Field(None, max_length=500)


class SubAccountResponse(BaseModel):
    """子账户响应"""
    id: int
    parent_account_id: int
    username: str
    email: Optional[str]
    role: SubAccountRole
    permissions: Optional[Dict[str, Any]]
    status: SubAccountStatus
    rate_limit: Optional[int]
    daily_limit: Optional[int]
    ip_whitelist: Optional[List[str]]
    total_sent: int
    last_login_at: Optional[datetime]
    last_login_ip: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SubAccountListResponse(BaseModel):
    """子账户列表响应"""
    total: int
    items: List[SubAccountResponse]
    page: int
    page_size: int


class SubAccountStats(BaseModel):
    """子账户统计"""
    total_sub_accounts: int
    active_sub_accounts: int
    suspended_sub_accounts: int
    total_sent_by_subs: int
