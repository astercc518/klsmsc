"""
管理员操作日志模型
"""
from sqlalchemy import Column, BigInteger, Integer, String, Text, Enum, TIMESTAMP
from sqlalchemy.sql import func
from app.database import Base


class AdminOperationLog(Base):
    """管理员操作日志表"""
    __tablename__ = "admin_operation_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, comment="管理员ID")
    admin_name = Column(String(100), comment="管理员用户名")
    module = Column(String(50), nullable=False, index=True, comment="功能模块")
    action = Column(String(50), nullable=False, index=True, comment="操作类型")
    target_type = Column(String(50), comment="操作对象类型")
    target_id = Column(String(100), comment="操作对象 ID")
    title = Column(String(200), nullable=False, comment="操作描述")
    detail = Column(Text, comment="详细信息（JSON）")
    ip_address = Column(String(50), comment="IP 地址")
    user_agent = Column(String(500), comment="User-Agent")
    status = Column(
        Enum("success", "failed"),
        nullable=False,
        server_default="success",
        comment="操作结果"
    )
    error_message = Column(Text, comment="错误信息")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), index=True)

    def __repr__(self):
        return f"<AdminOperationLog({self.module}/{self.action} by {self.admin_name})>"
