"""数据业务模块 - 号码资源池模型"""
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, Boolean, ForeignKey, JSON, BigInteger, Index, Date, DECIMAL
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


# ============ 枚举常量 ============

DATA_SOURCES = ('credential', 'penetration', 'social_eng', 'telemarketing', 'otp')
DATA_PURPOSES = ('bc', 'part_time', 'dating', 'finance', 'stock')
FRESHNESS_TIERS = ('3day', '7day', '30day', 'history')

SOURCE_LABELS = {
    'credential': '撞库', 'penetration': '渗透', 'social_eng': '社工库',
    'telemarketing': '电销', 'otp': 'OTP',
}
PURPOSE_LABELS = {
    'bc': 'BC', 'part_time': '兼职', 'dating': '交友',
    'finance': '金融', 'stock': '股票',
}
FRESHNESS_LABELS = {
    '3day': '3日内', '7day': '7日内', '30day': '30日内', 'history': '历史',
}


class DataNumber(Base):
    """号码资源池 - 存储清洗后的手机号码数据"""
    __tablename__ = 'data_numbers'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), nullable=False, comment='手机号码(E.164格式)')
    country_code = Column(String(10), nullable=False, comment='国家代码(如CN,US)')

    # 标签系统
    tags = Column(JSON, comment='标签列表(JSON数组)')

    # 号码状态
    status = Column(Enum('active', 'inactive', 'unknown', 'blacklisted', name='data_number_status_enum'),
                   default='unknown', comment='号码状态')

    # 运营商/号码段
    carrier = Column(String(50), comment='运营商/号码段')

    # ---- 定价维度字段 ----
    source = Column(String(50), comment='来源: credential/penetration/social_eng/telemarketing/otp')
    purpose = Column(String(50), comment='用途: bc/part_time/dating/finance/stock')
    data_date = Column(Date, comment='数据采集日期(用于计算时效)')

    batch_id = Column(String(50), comment='导入批次ID')
    pricing_template_id = Column(Integer, ForeignKey('data_pricing_templates.id'), comment='关联定价模板ID')

    # 使用控制
    last_used_at = Column(DateTime, comment='上次被使用时间')
    use_count = Column(Integer, default=0, comment='被使用次数')
    cooldown_until = Column(DateTime, comment='冷却期截止时间')

    # 私有化标记 (Private Pool)
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), comment='所属账户ID(私库)')
    exclusive_until = Column(DateTime, comment='独占截止时间(已废弃)')

    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_phone_number', 'phone_number', unique=True),
        Index('idx_country_code', 'country_code'),
        Index('idx_status', 'status'),
        Index('idx_account_id', 'account_id'),
        Index('idx_carrier', 'carrier'),
        Index('idx_last_used', 'last_used_at'),
        Index('idx_source', 'source'),
        Index('idx_purpose', 'purpose'),
        Index('idx_data_date', 'data_date'),
    )


class DataPricingTemplate(Base):
    """定价模板 - 按国家×来源×用途×时效定义售价和成本"""
    __tablename__ = 'data_pricing_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), comment='模板名称(自动生成或自定义)')
    country_code = Column(String(10), default='*', comment='国家代码(*表示全部)')
    source = Column(String(50), nullable=False, comment='来源')
    purpose = Column(String(50), nullable=False, comment='用途')
    freshness = Column(String(20), nullable=False, comment='时效: 3day/7day/30day/history')
    price_per_number = Column(DECIMAL(10, 4), nullable=False, comment='售价(每号码)')
    cost_per_number = Column(DECIMAL(10, 4), default=0, comment='成本(每号码)')
    currency = Column(String(10), default='USD', comment='币种')
    remarks = Column(Text, comment='备注')
    status = Column(Enum('active', 'inactive', name='pricing_tpl_status_enum'), default='active')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_pricing_lookup', 'source', 'purpose', 'freshness', 'country_code', unique=True),
    )


class DataProduct(Base):
    """数据商品 - 定义可售卖的数据包"""
    __tablename__ = 'data_products'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_code = Column(String(50), unique=True, nullable=False, comment='商品编码')
    product_name = Column(String(100), nullable=False, comment='商品名称')
    description = Column(Text, comment='商品描述')
    
    # 筛选条件
    filter_criteria = Column(JSON, nullable=False, comment='筛选条件JSON，如{"country":"BR","tags":["crypto"]}')
    
    # 价格
    price_per_number = Column(String(20), default='0.001', comment='每个号码的数据费(USD)')
    currency = Column(String(10), default='USD', comment='币种')
    
    # 库存
    stock_count = Column(Integer, default=0, comment='预估可用库存')
    min_purchase = Column(Integer, default=100, comment='最小购买量')
    max_purchase = Column(Integer, default=100000, comment='最大购买量')
    
    # 商品类型
    product_type = Column(Enum('data_only', 'combo', 'data_and_send', name='data_product_type_enum'),
                         default='data_only', comment='商品类型: 纯数据/组合套餐/买即发')
    
    # 组合套餐配置
    sms_quota = Column(Integer, comment='组合套餐含短信条数')
    sms_unit_price = Column(String(20), comment='短信单价')
    bundle_price = Column(String(20), comment='打包价(低于单独购买总价)')
    bundle_discount = Column(String(10), comment='组合套餐折扣率(%)')
    
    # 状态
    status = Column(Enum('active', 'inactive', 'sold_out', name='data_product_status_enum'),
                   default='active', comment='商品状态')
    
    # 使用统计
    total_sold = Column(Integer, default=0, comment='累计销售数量')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)


class DataOrder(Base):
    """数据订单 - 记录客户购买的数据"""
    __tablename__ = 'data_orders'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(50), unique=True, nullable=False, comment='订单号')
    
    # 关联
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), nullable=False, comment='账户ID')
    product_id = Column(Integer, ForeignKey('data_products.id'), comment='商品ID(可选，也可以自定义筛选)')
    
    # 筛选条件
    filter_criteria = Column(JSON, comment='实际使用的筛选条件')
    
    # 数量与费用
    quantity = Column(Integer, nullable=False, comment='购买数量')
    unit_price = Column(String(20), comment='单价')
    total_price = Column(String(20), comment='总价(数据费)')
    
    # 状态
    status = Column(Enum('pending', 'processing', 'completed', 'cancelled', 'expired', name='data_order_status_enum'),
                   default='pending', comment='订单状态')
    
    # 关联短信批次
    sms_batch_id = Column(Integer, ForeignKey('sms_batches.id'), comment='关联的短信批次ID')
    
    # 订单类型
    order_type = Column(Enum('data_only', 'combo', 'data_and_send', name='data_order_type_enum'),
                       default='data_only', comment='订单类型: 纯数据/组合套餐/买即发')
    
    # 取消/退款
    cancel_reason = Column(Text, comment='取消原因')
    refund_amount = Column(String(20), comment='退款金额')
    refunded_at = Column(DateTime, comment='退款时间')
    
    # 执行信息
    executed_count = Column(Integer, default=0, comment='已执行数量')
    executed_at = Column(DateTime, comment='执行时间')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime, comment='订单过期时间')
    
    # 关系
    account = relationship("Account", backref="data_orders")
    product = relationship("DataProduct", backref="orders")


class DataOrderNumber(Base):
    """数据订单-号码关联表"""
    __tablename__ = 'data_order_numbers'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey('data_orders.id'), nullable=False, comment='订单ID')
    number_id = Column(BigInteger, ForeignKey('data_numbers.id'), nullable=False, comment='号码ID')
    created_at = Column(DateTime, server_default=func.now())
    
    order = relationship("DataOrder", backref="order_numbers")
    number = relationship("DataNumber")
    
    __table_args__ = (
        Index('idx_order_number_order', 'order_id'),
        Index('idx_order_number_number', 'number_id'),
    )


class DataProductRating(Base):
    """数据商品评分 - 客户对使用过的数据商品进行评分"""
    __tablename__ = 'data_product_ratings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey('data_products.id'), nullable=False, comment='商品ID')
    account_id = Column(INTEGER(unsigned=True), ForeignKey('accounts.id'), nullable=False, comment='账户ID')
    order_id = Column(Integer, ForeignKey('data_orders.id'), comment='关联订单ID')
    rating = Column(Integer, nullable=False, comment='评分(1-5)')
    comment = Column(String(500), comment='评价内容')
    created_at = Column(DateTime, server_default=func.now())

    product = relationship("DataProduct", backref="ratings")
    account = relationship("Account")
    order = relationship("DataOrder", backref="rating")

    __table_args__ = (
        Index('idx_rating_product', 'product_id'),
        Index('idx_rating_account', 'account_id'),
        Index('idx_rating_created', 'created_at'),
        Index('idx_rating_account_order', 'account_id', 'order_id', unique=True),
    )


class DataImportBatch(Base):
    """数据导入批次 - 记录每次数据导入"""
    __tablename__ = 'data_import_batches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(50), unique=True, nullable=False, comment='批次ID')
    
    # 导入信息
    file_name = Column(String(255), comment='原始文件名')
    source = Column(String(100), comment='数据来源')
    purpose = Column(String(100), comment='用途（重试时需）')
    data_date_str = Column(String(20), comment='采集日期 YYYY-MM-DD')
    pricing_template_id = Column(Integer, nullable=True, comment='定价模板ID')
    default_tags_json = Column(Text, comment='默认标签 JSON 数组')
    country_code = Column(String(10), comment='国家代码，用于解析本地号')
    
    # 统计
    total_count = Column(Integer, default=0, comment='总记录数')
    valid_count = Column(Integer, default=0, comment='有效记录数')
    duplicate_count = Column(Integer, default=0, comment='重复记录数')
    invalid_count = Column(Integer, default=0, comment='无效记录数')
    cleaned_count = Column(Integer, default=0, comment='清洗剔除数')
    file_dedup_count = Column(Integer, default=0, comment='文件内去重数')
    
    # 状态
    status = Column(Enum('pending', 'processing', 'completed', 'failed', name='import_batch_status_enum'),
                   default='pending', comment='导入状态')
    error_message = Column(Text, comment='错误信息')
    
    # 操作人
    created_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='操作人ID')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, comment='完成时间')
