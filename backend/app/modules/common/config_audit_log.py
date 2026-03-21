"""
系统配置变更审计日志模型
"""
from sqlalchemy import Column, Integer, String, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.database import Base


class ConfigAuditLog(Base):
    """配置变更记录"""
    __tablename__ = "config_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), nullable=False, index=True, comment="配置键")
    action = Column(String(20), nullable=False, comment="操作: update/create/delete")
    old_value = Column(Text, comment="变更前的值")
    new_value = Column(Text, comment="变更后的值")
    admin_id = Column(Integer, comment="操作人ID")
    admin_name = Column(String(100), comment="操作人用户名（冗余）")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<ConfigAuditLog({self.action} {self.config_key} by {self.admin_name})>"
