"""
安全日志模型（P2-4）
"""
from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, Boolean, JSON
from sqlalchemy.sql import func
from app.database import Base
import enum


class SecurityEventType(str, enum.Enum):
    """安全事件类型"""
    LOGIN = "login"                      # 登录
    LOGIN_FAILED = "login_failed"        # 登录失败
    LOGOUT = "logout"                    # 登出
    PASSWORD_CHANGE = "password_change"  # 密码修改
    API_KEY_CREATE = "api_key_create"    # API密钥创建
    API_KEY_DELETE = "api_key_delete"    # API密钥删除
    PERMISSION_CHANGE = "permission_change"  # 权限变更
    SUSPICIOUS_ACTIVITY = "suspicious_activity"  # 可疑活动
    IP_BLOCKED = "ip_blocked"            # IP封禁
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"  # 超过频率限制


class SecurityLevel(str, enum.Enum):
    """安全级别"""
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


class SecurityLog(Base):
    """安全日志表"""
    __tablename__ = "security_logs"
    
    id = Column(Integer, primary_key=True, index=True, comment="日志ID")
    account_id = Column(Integer, index=True, comment="账户ID")
    
    # 事件信息
    event_type = Column(
        Enum(SecurityEventType),
        nullable=False,
        index=True,
        comment="事件类型"
    )
    level = Column(
        Enum(SecurityLevel),
        nullable=False,
        default=SecurityLevel.INFO,
        comment="安全级别"
    )
    
    # 详细信息
    title = Column(String(200), nullable=False, comment="标题")
    description = Column(Text, comment="描述")
    details = Column(JSON, comment="详细数据（JSON）")
    
    # 来源信息
    ip_address = Column(String(50), comment="IP地址")
    user_agent = Column(String(500), comment="User Agent")
    location = Column(String(200), comment="地理位置")
    
    # 关联信息
    related_id = Column(Integer, comment="关联业务ID")
    related_type = Column(String(50), comment="关联业务类型")
    
    # 处理状态
    is_resolved = Column(Boolean, default=False, comment="是否已处理")
    resolved_at = Column(TIMESTAMP, comment="处理时间")
    resolved_by = Column(Integer, comment="处理人ID")
    resolution_note = Column(Text, comment="处理备注")
    
    # 时间
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, index=True, comment="创建时间")
    
    def __repr__(self):
        return f"<SecurityLog(id={self.id}, type='{self.event_type}', level='{self.level}')>"


class LoginAttempt(Base):
    """登录尝试记录表"""
    __tablename__ = "login_attempts"
    
    id = Column(Integer, primary_key=True, index=True, comment="ID")
    username = Column(String(100), index=True, comment="用户名")
    ip_address = Column(String(50), index=True, comment="IP地址")
    
    # 结果
    success = Column(Boolean, nullable=False, comment="是否成功")
    failure_reason = Column(String(200), comment="失败原因")
    
    # 来源信息
    user_agent = Column(String(500), comment="User Agent")
    
    # 时间
    attempted_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, index=True, comment="尝试时间")
    
    def __repr__(self):
        return f"<LoginAttempt(username='{self.username}', success={self.success})>"
