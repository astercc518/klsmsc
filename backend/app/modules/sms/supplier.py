"""供应商管理模型"""
from sqlalchemy import Column, Integer, String, Enum, Text, Numeric, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Supplier(Base):
    """供应商表 - 上游通道提供商"""
    __tablename__ = 'suppliers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_code = Column(String(50), unique=True, nullable=False, comment='供应商编码')
    supplier_name = Column(String(100), nullable=False, comment='供应商名称')
    supplier_group = Column(String(100), comment='供应商群组名称')
    telegram_group_id = Column(String(50), comment='Telegram群组ID，用于短信审核转发，如 -1001234567890')
    supplier_type = Column(Enum('direct', 'aggregator', name='supplier_type_enum'), 
                          default='direct', comment='供应商类型：direct-直连,aggregator-聚合')
    
    # 业务分类
    business_type = Column(String(20), default='sms', comment='业务类型：sms/voice/data')
    country = Column(String(100), comment='国家/地区')
    resource_type = Column(String(50), comment='资源类型：验证码/营销/通知/国际等')
    cost_price = Column(Numeric(10, 6), default=0, comment='成本价(每条)')
    cost_currency = Column(String(10), default='USD', comment='成本币种')
    
    # 联系信息
    contact_person = Column(String(50), comment='联系人')
    contact_email = Column(String(100), comment='联系邮箱')
    contact_phone = Column(String(30), comment='联系电话')
    contact_address = Column(String(255), comment='联系地址')
    
    # API配置
    api_endpoint = Column(String(255), comment='API地址')
    api_key = Column(String(255), comment='API密钥')
    api_secret = Column(String(255), comment='API密钥(加密)')
    protocol = Column(Enum('HTTP', 'SMPP', 'SOAP', name='supplier_protocol_enum'), 
                     default='HTTP', comment='协议类型')
    
    # 状态与配置
    status = Column(Enum('active', 'inactive', 'suspended', name='supplier_status_enum'), 
                   default='active', comment='状态')
    priority = Column(Integer, default=0, comment='优先级，数字越大优先级越高')
    
    # 结算配置
    settlement_currency = Column(String(10), default='USD', comment='结算币种')
    settlement_period = Column(Enum('daily', 'weekly', 'monthly', name='settlement_period_enum'), 
                              default='monthly', comment='结算周期')
    settlement_day = Column(Integer, default=1, comment='结算日(1-31)')
    payment_method = Column(Enum('prepaid', 'postpaid', name='payment_method_enum'), 
                           default='postpaid', comment='付款方式：prepaid-预付,postpaid-后付')
    credit_limit = Column(Numeric(12, 4), default=0, comment='信用额度')
    current_balance = Column(Numeric(12, 4), default=0, comment='当前余额')
    
    # 合同信息
    contract_start_date = Column(DateTime, comment='合同开始日期')
    contract_end_date = Column(DateTime, comment='合同结束日期')
    contract_file = Column(String(255), comment='合同文件路径')
    
    # 备注
    notes = Column(Text, comment='备注')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
    
    # 关系（供应商结算模块已移除，不在此挂载反向关系）
    channels = relationship("SupplierChannel", back_populates="supplier")
    rates = relationship("SupplierRate", back_populates="supplier")


class SupplierChannel(Base):
    """供应商-通道关联表"""
    __tablename__ = 'supplier_channels'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, comment='供应商ID')
    channel_id = Column(INTEGER(unsigned=True), ForeignKey('channels.id'), nullable=False, comment='通道ID')
    supplier_channel_code = Column(String(50), comment='供应商侧通道编码')
    
    # 状态
    status = Column(Enum('active', 'inactive', name='supplier_channel_status_enum'), 
                   default='active', comment='状态')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    supplier = relationship("Supplier", back_populates="channels")
    channel = relationship("Channel", backref="supplier_channels")


class SupplierRate(Base):
    """供应商费率表 - 成本价管理"""
    __tablename__ = 'supplier_rates'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, comment='供应商ID')
    
    # 业务类型
    business_type = Column(String(20), default='sms', nullable=False, comment='业务类型：sms/voice/data')
    
    # 路由条件
    country_code = Column(String(10), nullable=False, comment='国家代码(MCC)')
    resource_type = Column(String(50), default='card', comment='资源类型/发送方式')
    business_scope = Column(String(50), default='otp', comment='业务范围：otp/marketing/gambling等')
    mcc = Column(String(10), comment='移动国家代码')
    mnc = Column(String(10), comment='移动网络代码(运营商)')
    operator_name = Column(String(100), comment='运营商名称')
    
    # 语音计费模式（仅 business_type='voice' 时有效）
    billing_model = Column(String(20), comment='语音计费模式：1+1/6+6/30+6/60+1/60+60')
    line_desc = Column(String(100), comment='语音线路描述（如：电力/快递/卡线）')

    # 价格
    cost_price = Column(Numeric(10, 6), nullable=False, comment='成本价(每条/每分钟)')
    sell_price = Column(Numeric(10, 6), default=0, comment='售价(每条/每分钟)')
    remark = Column(String(255), comment='备注')
    currency = Column(String(10), default='USD', comment='币种')
    
    # 生效时间
    effective_date = Column(DateTime, server_default=func.now(), comment='生效日期')
    expire_date = Column(DateTime, comment='失效日期')
    
    # 状态
    status = Column(Enum('active', 'inactive', name='rate_status_enum'), 
                   default='active', comment='状态')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    supplier = relationship("Supplier", back_populates="rates")


class SellRate(Base):
    """销售费率表 - 对客户的售价管理"""
    __tablename__ = 'sell_rates'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    rate_deck_id = Column(Integer, ForeignKey('rate_decks.id'), comment='费率表ID(可选，用于费率表分组)')
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), comment='账户ID(可选，用于专属费率)')
    
    # 路由条件
    country_code = Column(String(10), nullable=False, comment='国家代码(MCC)')
    mcc = Column(String(10), comment='移动国家代码')
    mnc = Column(String(10), comment='移动网络代码(运营商)')
    operator_name = Column(String(100), comment='运营商名称')
    
    # 价格
    sell_price = Column(Numeric(10, 6), nullable=False, comment='销售价(每条)')
    currency = Column(String(10), default='USD', comment='币种')
    
    # 生效时间
    effective_date = Column(DateTime, server_default=func.now(), comment='生效日期')
    expire_date = Column(DateTime, comment='失效日期')
    
    # 状态
    status = Column(Enum('active', 'inactive', name='sell_rate_status_enum'), 
                   default='active', comment='状态')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    rate_deck = relationship("RateDeck", back_populates="rates")
    account = relationship("Account", backref="custom_rates")


class RateDeck(Base):
    """费率表 - 用于管理不同的价格组"""
    __tablename__ = 'rate_decks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    deck_name = Column(String(100), nullable=False, comment='费率表名称')
    deck_code = Column(String(50), unique=True, nullable=False, comment='费率表编码')
    description = Column(Text, comment='描述')
    
    # 类型
    deck_type = Column(Enum('standard', 'premium', 'wholesale', 'custom', name='deck_type_enum'), 
                      default='standard', comment='费率表类型')
    
    # 加价策略
    markup_type = Column(Enum('fixed', 'percentage', name='markup_type_enum'), 
                        default='percentage', comment='加价方式：fixed-固定金额,percentage-百分比')
    markup_value = Column(Numeric(10, 4), default=0, comment='加价值')
    
    # 默认费率
    is_default = Column(Boolean, default=False, comment='是否为默认费率表')
    
    # 状态
    status = Column(Enum('active', 'inactive', name='deck_status_enum'), 
                   default='active', comment='状态')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
    
    # 关系
    rates = relationship("SellRate", back_populates="rate_deck")
    accounts = relationship("AccountRateDeck", back_populates="rate_deck")


class AccountRateDeck(Base):
    """账户-费率表关联"""
    __tablename__ = 'account_rate_decks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), nullable=False, comment='账户ID')
    rate_deck_id = Column(Integer, ForeignKey('rate_decks.id'), nullable=False, comment='费率表ID')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    
    # 关系
    account = relationship("Account", backref="rate_deck_assignments")
    rate_deck = relationship("RateDeck", back_populates="accounts")
