"""
余额变动记录数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, TIMESTAMP, Text, ForeignKey, BigInteger
from sqlalchemy.sql import func
from app.database import Base


class BalanceLog(Base):
    """余额变动记录表"""
    __tablename__ = "balance_logs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="记录ID")
    account_id = Column(Integer, nullable=False, comment="账户ID")
    change_type = Column(
        Enum("charge", "refund", "deposit", "withdraw", "adjustment", name="balance_change_type"),
        nullable=False,
        comment="变动类型"
    )
    amount = Column(DECIMAL(12, 4), nullable=False, comment="变动金额")
    balance_after = Column(DECIMAL(12, 4), nullable=False, comment="变动后余额")
    description = Column(Text, comment="描述")
    related_order_id = Column(BigInteger, ForeignKey("recharge_orders.id"), comment="关联充值工单ID")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    
    def __repr__(self):
        return f"<BalanceLog(id={self.id}, account_id={self.account_id}, amount={self.amount})>"
