"""
子账户模型（P2-2）
"""
from sqlalchemy import Column, Integer, String, Enum, TIMESTAMP, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
import enum


class SubAccountRole(str, enum.Enum):
    """子账户角色"""
    VIEWER = "viewer"           # 查看者（只读）
    OPERATOR = "operator"       # 操作员（发送+查看）
    MANAGER = "manager"         # 管理员（完全权限）


class SubAccountStatus(str, enum.Enum):
    """子账户状态"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class SubAccount(Base):
    """子账户表"""
    __tablename__ = "sub_accounts"
    
    id = Column(Integer, primary_key=True, index=True, comment="子账户ID")
    parent_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True, comment="父账户ID")
    
    # 基本信息
    # username 在租户内唯一（与 parent_account_id 联合 unique）
    username = Column(String(100), nullable=False, index=True, comment="用户名（租户内唯一）")
    email = Column(String(255), comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    
    # 角色与权限
    role = Column(
        Enum(SubAccountRole),
        nullable=False,
        default=SubAccountRole.OPERATOR,
        comment="角色"
    )
    permissions = Column(JSON, comment="详细权限配置（JSON）")
    
    # 状态
    status = Column(
        Enum(SubAccountStatus),
        nullable=False,
        default=SubAccountStatus.ACTIVE,
        comment="状态"
    )
    
    # 限制配置
    rate_limit = Column(Integer, comment="请求频率限制（继承父账户或自定义）")
    daily_limit = Column(Integer, comment="每日发送限制")
    ip_whitelist = Column(JSON, comment="IP白名单")
    
    # 统计
    total_sent = Column(Integer, default=0, comment="总发送数")
    last_login_at = Column(TIMESTAMP, comment="最后登录时间")
    last_login_ip = Column(String(50), comment="最后登录IP")
    
    # 备注
    description = Column(String(500), comment="备注")
    
    # 时间
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="软删除标记")
    
    __table_args__ = (
        UniqueConstraint('parent_account_id', 'username', name='uq_sub_accounts_parent_username'),
    )

    def __repr__(self):
        return f"<SubAccount(id={self.id}, username='{self.username}', role='{self.role}')>"
