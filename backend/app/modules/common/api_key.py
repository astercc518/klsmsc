"""
API密钥模型（支持多密钥管理）
"""
from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, Boolean, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base
import enum


class ApiKeyStatus(str, enum.Enum):
    """API密钥状态"""
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class ApiKeyPermission(str, enum.Enum):
    """API密钥权限"""
    READ_ONLY = "read_only"      # 只读（查询）
    READ_WRITE = "read_write"    # 读写（发送+查询）
    FULL = "full"                # 完全权限（包括充值、配置）


class ApiKey(Base):
    """API密钥表（多密钥管理）"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True, comment="密钥ID")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True, comment="账户ID")
    
    # 密钥信息
    key_name = Column(String(100), nullable=False, comment="密钥名称")
    api_key = Column(String(64), unique=True, nullable=False, index=True, comment="API Key")
    api_secret = Column(String(128), nullable=False, comment="API Secret（加密存储）")
    
    # 权限配置
    permission = Column(
        Enum(ApiKeyPermission), 
        nullable=False, 
        default=ApiKeyPermission.READ_WRITE,
        comment="权限级别"
    )
    ip_whitelist = Column(JSON, comment="IP白名单（JSON数组）")
    rate_limit = Column(Integer, default=1000, comment="每分钟请求限制")
    
    # 状态与统计
    status = Column(
        Enum(ApiKeyStatus),
        nullable=False,
        default=ApiKeyStatus.ACTIVE,
        comment="密钥状态"
    )
    usage_count = Column(Integer, default=0, comment="使用次数")
    last_used_at = Column(TIMESTAMP, comment="最后使用时间")
    last_used_ip = Column(String(50), comment="最后使用IP")
    
    # 有效期
    expires_at = Column(TIMESTAMP, comment="过期时间")
    
    # 备注
    description = Column(Text, comment="密钥描述")
    
    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="软删除标记")
    
    def __repr__(self):
        return f"<ApiKey(id={self.id}, name='{self.key_name}', status='{self.status}')>"
