"""
API密钥相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ApiKeyPermission(str, Enum):
    """API密钥权限"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    FULL = "full"


class ApiKeyStatus(str, Enum):
    """API密钥状态"""
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class ApiKeyCreate(BaseModel):
    """创建API密钥"""
    key_name: str = Field(..., min_length=1, max_length=100, description="密钥名称")
    permission: ApiKeyPermission = Field(default=ApiKeyPermission.READ_WRITE, description="权限级别")
    ip_whitelist: Optional[List[str]] = Field(default=None, description="IP白名单")
    rate_limit: Optional[int] = Field(default=1000, ge=1, le=10000, description="每分钟请求限制")
    expires_days: Optional[int] = Field(default=None, ge=1, le=3650, description="有效期（天）")
    description: Optional[str] = Field(default=None, max_length=500, description="描述")


class ApiKeyUpdate(BaseModel):
    """更新API密钥"""
    key_name: Optional[str] = Field(None, min_length=1, max_length=100)
    permission: Optional[ApiKeyPermission] = None
    ip_whitelist: Optional[List[str]] = None
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    status: Optional[ApiKeyStatus] = None
    description: Optional[str] = Field(None, max_length=500)


class ApiKeyResponse(BaseModel):
    """API密钥响应"""
    id: int
    account_id: int
    key_name: str
    api_key: str
    permission: ApiKeyPermission
    ip_whitelist: Optional[List[str]]
    rate_limit: int
    status: ApiKeyStatus
    usage_count: int
    last_used_at: Optional[datetime]
    last_used_ip: Optional[str]
    expires_at: Optional[datetime]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeyResponse):
    """创建密钥响应（包含secret）"""
    api_secret: str  # 仅在创建时返回一次


class ApiKeyListResponse(BaseModel):
    """密钥列表响应"""
    total: int
    items: List[ApiKeyResponse]
    page: int
    page_size: int


class ApiKeyStats(BaseModel):
    """密钥统计"""
    total_keys: int
    active_keys: int
    disabled_keys: int
    expired_keys: int
    total_usage: int
