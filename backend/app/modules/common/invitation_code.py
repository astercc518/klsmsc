"""
邀请码数据模型
"""
from sqlalchemy import Column, Integer, String, Enum, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class InvitationCode(Base):
    """邀请码表"""
    __tablename__ = "invitation_codes"
    
    code = Column(String(32), primary_key=True, comment="授权码")
    sales_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False, comment="归属销售ID")
    pricing_config = Column(JSON, comment="定价配置")  # 新增
    status = Column(
        Enum("unused", "used", "expired", name="invite_status"),
        nullable=False,
        default="unused",
        comment="状态"
    )
    used_by_account_id = Column(Integer, ForeignKey("accounts.id"), comment="激活者账户ID")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    expires_at = Column(TIMESTAMP, comment="过期时间")
    used_at = Column(TIMESTAMP, comment="使用时间")
    
    def __repr__(self):
        return f"<InvitationCode(code={self.code}, status={self.status})>"
