"""
管理员用户数据模型
"""
from sqlalchemy import Column, Integer, String, Enum, Boolean, TIMESTAMP, BigInteger, DECIMAL
from sqlalchemy.sql import func
from app.database import Base


class AdminUser(Base):
    """管理员用户表"""
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="管理员ID")
    tg_id = Column(BigInteger, index=True, comment="Telegram ID")
    tg_username = Column(String(100), comment="Telegram用户名")
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    real_name = Column(String(100), comment="真实姓名")
    email = Column(String(255), comment="邮箱")
    phone = Column(String(20), comment="手机号")
    commission_rate = Column(DECIMAL(5, 2), default=0, comment="佣金比例(%)")
    monthly_commission = Column(DECIMAL(10, 2), default=0, comment="本月佣金")
    role = Column(
        Enum("super_admin", "admin", "finance", "sales", "tech", name="admin_role"),
        nullable=False,
        default="sales",
        comment="角色"
    )
    status = Column(
        Enum("active", "inactive", "locked", name="admin_status"),
        nullable=False,
        default="active",
        comment="状态"
    )
    last_login_at = Column(TIMESTAMP, comment="最后登录时间")
    login_failed_count = Column(Integer, nullable=False, default=0, comment="登录失败次数")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    
    def __repr__(self):
        return f"<AdminUser(id={self.id}, username={self.username}, role={self.role})>"
