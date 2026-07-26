"""
销售授信流水（账本）数据模型

记录销售(AdminUser role=sales)授信额度的每一次变动，用于对账与审计：
  - limit_change：管理员调整额度上限（提额/降额）
  - recharge    ：销售用授信给客户充值（credit_used 增加）
  - settlement  ：管理员结算冲销（销售线下还款后 credit_used 减回，腾出额度）

每条都快照记录变动后的 credit_limit_after / credit_used_after，账本可独立回放；
recharge 类型携带 account_id 与 related_balance_log_id，可与客户余额流水互相印证。
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, TIMESTAMP, Text, BigInteger
from sqlalchemy.sql import func
from app.database import Base


class SalesCreditLog(Base):
    """销售授信流水表"""
    __tablename__ = "sales_credit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="记录ID")
    sales_id = Column(Integer, nullable=False, comment="销售(AdminUser)ID（逻辑关联 admin_users.id，按本仓日志表约定不设 DB 外键）")
    change_type = Column(
        Enum("limit_change", "recharge", "settlement", name="sales_credit_change_type"),
        nullable=False,
        comment="变动类型：limit_change=调整额度上限/recharge=授信充值/settlement=结算冲销",
    )
    amount = Column(DECIMAL(12, 4), nullable=False, comment="本次变动金额(正数,方向由 change_type 决定)")
    credit_limit_after = Column(DECIMAL(12, 4), nullable=False, comment="变动后额度上限")
    credit_used_after = Column(DECIMAL(12, 4), nullable=False, comment="变动后已用授信")
    account_id = Column(Integer, nullable=True, comment="关联客户账户ID(recharge 时)")
    related_balance_log_id = Column(BigInteger, nullable=True, comment="关联客户余额流水ID(recharge 时)")
    operator_id = Column(Integer, nullable=True, comment="操作人ID(充值=销售本人/调额结算=管理员)")
    operator_name = Column(String(50), nullable=True, comment="操作人用户名快照")
    idempotency_key = Column(String(64), nullable=True, unique=True, comment="幂等键(防重复充值)")
    description = Column(Text, nullable=True, comment="备注")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")

    def __repr__(self):
        return f"<SalesCreditLog(id={self.id}, sales_id={self.sales_id}, type={self.change_type}, amount={self.amount})>"
