"""结算系统模型"""
from sqlalchemy import Column, Integer, String, Enum, Text, Numeric, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Settlement(Base):
    """结算单表 - 供应商结算"""
    __tablename__ = 'settlements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_no = Column(String(50), unique=True, nullable=False, comment='结算单号')
    
    # 关联
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, comment='供应商ID')
    
    # 结算周期
    period_start = Column(DateTime, nullable=False, comment='结算周期开始')
    period_end = Column(DateTime, nullable=False, comment='结算周期结束')
    
    # 汇总数据
    total_sms_count = Column(Integer, default=0, comment='总短信条数')
    total_success_count = Column(Integer, default=0, comment='成功条数')
    total_failed_count = Column(Integer, default=0, comment='失败条数')
    
    # 金额
    total_cost = Column(Numeric(14, 4), default=0, comment='总成本金额')
    adjustment_amount = Column(Numeric(14, 4), default=0, comment='调整金额(正为增加,负为减少)')
    final_amount = Column(Numeric(14, 4), default=0, comment='最终结算金额')
    currency = Column(String(10), default='USD', comment='币种')
    
    # 结算类型
    settlement_type = Column(Enum('auto', 'manual', name='settlement_type_enum'), 
                            default='auto', comment='结算类型：auto-自动生成,manual-手动创建')
    
    # 状态
    status = Column(Enum('draft', 'pending', 'confirmed', 'paid', 'cancelled', name='settlement_status_enum'), 
                   default='draft', comment='状态：draft-草稿,pending-待确认,confirmed-已确认,paid-已支付,cancelled-已取消')
    
    # 确认信息
    confirmed_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='确认人ID')
    confirmed_at = Column(DateTime, comment='确认时间')
    
    # 支付信息
    payment_method = Column(String(50), comment='支付方式')
    payment_reference = Column(String(100), comment='支付凭证/流水号')
    payment_proof = Column(String(255), comment='支付凭证图片')
    paid_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='支付人ID')
    paid_at = Column(DateTime, comment='支付时间')
    
    # 备注
    notes = Column(Text, comment='备注')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系（单向：Settlement->Supplier，避免 supplier.py 导入 settlement 时循环导入）
    supplier = relationship("Supplier")
    details = relationship("SettlementDetail", back_populates="settlement")
    logs = relationship("SettlementLog", back_populates="settlement", order_by="SettlementLog.created_at.desc()")


class SettlementDetail(Base):
    """结算明细表"""
    __tablename__ = 'settlement_details'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, ForeignKey('settlements.id'), nullable=False, comment='结算单ID')
    
    # 维度
    channel_id = Column(INTEGER(unsigned=True), ForeignKey('channels.id'), comment='通道ID')
    country_code = Column(String(10), nullable=False, comment='国家代码')
    country_name = Column(String(100), comment='国家名称')
    operator_code = Column(String(20), comment='运营商代码')
    operator_name = Column(String(100), comment='运营商名称')
    
    # 数量
    sms_count = Column(Integer, default=0, comment='短信条数')
    success_count = Column(Integer, default=0, comment='成功条数')
    failed_count = Column(Integer, default=0, comment='失败条数')
    
    # 金额
    unit_cost = Column(Numeric(10, 6), default=0, comment='单价')
    total_cost = Column(Numeric(14, 4), default=0, comment='小计金额')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    
    # 关系
    settlement = relationship("Settlement", back_populates="details")
    channel = relationship("Channel", backref="settlement_details")


class SettlementLog(Base):
    """结算操作日志"""
    __tablename__ = 'settlement_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, ForeignKey('settlements.id'), nullable=False, comment='结算单ID')
    
    # 操作信息
    action = Column(Enum('create', 'update', 'confirm', 'pay', 'cancel', 'adjust', name='settlement_action_enum'), 
                   nullable=False, comment='操作类型')
    
    # 状态变更
    old_status = Column(String(20), comment='旧状态')
    new_status = Column(String(20), comment='新状态')
    
    # 操作人
    operator_id = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='操作人ID')
    operator_name = Column(String(100), comment='操作人名称')
    
    # 描述
    description = Column(Text, comment='操作描述')
    extra_data = Column(JSON, comment='额外数据')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    
    # 关系
    settlement = relationship("Settlement", back_populates="logs")


class CustomerBill(Base):
    """客户账单表 - 客户结算"""
    __tablename__ = 'customer_bills'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_no = Column(String(50), unique=True, nullable=False, comment='账单号')
    
    # 关联
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), nullable=False, comment='账户ID')
    
    # 账单周期
    period_start = Column(DateTime, nullable=False, comment='账单周期开始')
    period_end = Column(DateTime, nullable=False, comment='账单周期结束')
    
    # 汇总数据
    total_sms_count = Column(Integer, default=0, comment='总短信条数')
    total_success_count = Column(Integer, default=0, comment='成功条数')
    
    # 金额
    total_amount = Column(Numeric(14, 4), default=0, comment='总金额(应收)')
    paid_amount = Column(Numeric(14, 4), default=0, comment='已付金额')
    balance_amount = Column(Numeric(14, 4), default=0, comment='余额抵扣')
    outstanding_amount = Column(Numeric(14, 4), default=0, comment='未付金额')
    currency = Column(String(10), default='USD', comment='币种')
    
    # 状态
    status = Column(Enum('draft', 'sent', 'paid', 'partial', 'overdue', 'cancelled', name='bill_status_enum'), 
                   default='draft', comment='状态')
    
    # 发送信息
    sent_at = Column(DateTime, comment='发送时间')
    due_date = Column(DateTime, comment='到期日期')
    
    # 备注
    notes = Column(Text, comment='备注')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    account = relationship("Account", backref="bills")
    details = relationship("CustomerBillDetail", back_populates="bill")


class CustomerBillDetail(Base):
    """客户账单明细"""
    __tablename__ = 'customer_bill_details'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey('customer_bills.id'), nullable=False, comment='账单ID')
    
    # 维度
    country_code = Column(String(10), nullable=False, comment='国家代码')
    country_name = Column(String(100), comment='国家名称')
    
    # 数量
    sms_count = Column(Integer, default=0, comment='短信条数')
    success_count = Column(Integer, default=0, comment='成功条数')
    
    # 金额
    unit_price = Column(Numeric(10, 6), default=0, comment='单价')
    total_amount = Column(Numeric(14, 4), default=0, comment='小计金额')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    
    # 关系
    bill = relationship("CustomerBill", back_populates="details")


class SalesCommissionSettlement(Base):
    """销售佣金结算单"""
    __tablename__ = 'sales_commission_settlements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_no = Column(String(50), unique=True, nullable=False, comment='结算单号')
    
    # 关联
    sales_id = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), nullable=False, comment='销售ID')
    
    # 结算周期
    period_start = Column(DateTime, nullable=False, comment='周期开始')
    period_end = Column(DateTime, nullable=False, comment='周期结束')
    
    # 汇总数据
    total_sms_count = Column(Integer, default=0, comment='总短信条数')
    total_revenue = Column(Numeric(14, 4), default=0, comment='客户消费总额(营收)')
    commission_rate = Column(Numeric(5, 2), default=0, comment='佣金比例(%)')
    commission_amount = Column(Numeric(14, 4), default=0, comment='佣金金额')
    currency = Column(String(10), default='USD', comment='币种')
    
    # 状态
    status = Column(Enum('draft', 'confirmed', 'paid', 'cancelled', name='commission_status_enum'),
                    default='draft', comment='状态')
    
    # 支付信息
    payment_method = Column(String(50), comment='支付方式')
    payment_reference = Column(String(100), comment='支付凭证/流水号')
    paid_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='支付人ID')
    paid_at = Column(DateTime, comment='支付时间')
    notes = Column(Text, comment='备注')
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    sales = relationship("AdminUser", foreign_keys=[sales_id])
    details = relationship("SalesCommissionDetail", back_populates="settlement")


class SalesCommissionDetail(Base):
    """销售佣金明细 - 按客户汇总"""
    __tablename__ = 'sales_commission_details'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, ForeignKey('sales_commission_settlements.id'), nullable=False, comment='结算单ID')
    
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), nullable=False, comment='客户ID')
    total_sms_count = Column(Integer, default=0, comment='短信条数')
    total_revenue = Column(Numeric(14, 4), default=0, comment='客户消费金额')
    commission_rate = Column(Numeric(5, 2), default=0, comment='佣金比例(%)')
    commission_amount = Column(Numeric(14, 4), default=0, comment='佣金金额')
    
    created_at = Column(DateTime, server_default=func.now())
    
    settlement = relationship("SalesCommissionSettlement", back_populates="details")
    account = relationship("Account")


class ProfitReport(Base):
    """利润报表 - 每日汇总"""
    __tablename__ = 'profit_reports'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(DateTime, nullable=False, comment='报表日期')
    
    # 维度
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), comment='供应商ID')
    channel_id = Column(INTEGER(unsigned=True), ForeignKey('channels.id'), comment='通道ID')
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), comment='账户ID')
    country_code = Column(String(10), comment='国家代码')
    
    # 数量
    total_sms_count = Column(Integer, default=0, comment='总短信条数')
    success_count = Column(Integer, default=0, comment='成功条数')
    failed_count = Column(Integer, default=0, comment='失败条数')
    
    # 金额
    total_cost = Column(Numeric(14, 4), default=0, comment='总成本')
    total_revenue = Column(Numeric(14, 4), default=0, comment='总营收')
    gross_profit = Column(Numeric(14, 4), default=0, comment='毛利润')
    profit_margin = Column(Numeric(6, 4), default=0, comment='利润率')
    currency = Column(String(10), default='USD', comment='币种')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    
    # 唯一约束 - 确保每天每个维度只有一条记录
    __table_args__ = (
        # UniqueConstraint('report_date', 'supplier_id', 'channel_id', 'account_id', 'country_code', name='uq_profit_report'),
    )
