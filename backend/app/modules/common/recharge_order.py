"""
充值工单数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, TIMESTAMP, ForeignKey, BigInteger
from sqlalchemy.sql import func
from app.database import Base


class RechargeOrder(Base):
    """充值工单表"""
    __tablename__ = "recharge_orders"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="工单ID")
    order_no = Column(String(64), nullable=False, unique=True, comment="工单号")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, comment="申请账户")
    amount = Column(DECIMAL(12, 4), nullable=False, comment="申请金额")
    currency = Column(String(10), nullable=False, default="USD", comment="币种")
    payment_proof = Column(String(500), comment="支付凭证图片URL/FileID")
    status = Column(
        Enum("pending", "finance_approved", "completed", "rejected", name="recharge_status"),
        nullable=False,
        default="pending",
        comment="状态"
    )
    finance_audit_by = Column(Integer, comment="财务审核人")
    finance_audit_at = Column(TIMESTAMP, comment="财务审核时间")
    tech_audit_by = Column(Integer, comment="技术执行人")
    tech_audit_at = Column(TIMESTAMP, comment="技术执行时间")
    reject_reason = Column(String(255), comment="驳回原因")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    
    def __repr__(self):
        return f"<RechargeOrder(id={self.id}, amount={self.amount}, status={self.status})>"
