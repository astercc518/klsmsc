"""
账户数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, Boolean, TIMESTAMP, Text, ForeignKey, BigInteger, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class AccountChannel(Base):
    """账户-通道关联表"""
    __tablename__ = "account_channels"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, comment="账户ID")
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False, comment="通道ID")
    # country_code 为空(NULL/'')=该账户全国家默认通道（向后兼容旧绑定）；
    # 指定 ISO2(如 US)=仅该国家走此通道，实现"每账户每国家独立选通道"
    country_code = Column(String(10), nullable=True, comment="国家代码(ISO2)；空=全国默认，指定=该国家专用通道")
    is_default = Column(Boolean, default=False, comment="是否默认通道")
    priority = Column(Integer, default=0, comment="优先级")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    
    # 关联
    account = relationship("Account", back_populates="account_channels")
    channel = relationship("Channel")
    
    def __repr__(self):
        return f"<AccountChannel(account_id={self.account_id}, channel_id={self.channel_id})>"


class Account(Base):
    """账户表"""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="账户ID")
    account_name = Column(String(100), nullable=False, comment="账户名称")
    email = Column(String(255), unique=True, comment="邮箱")
    tg_username = Column(String(100), comment="Telegram用户名")
    tg_id = Column(BigInteger, comment="Telegram ID")
    country_code = Column(String(10), comment="国家代码")
    business_type = Column(
        Enum("sms", "voice", "data", name="account_business_type"),
        nullable=False,
        default="sms",
        comment="业务类型：sms短信/voice语音/data数据"
    )
    services = Column(String(100), nullable=False, default="sms", comment="开通业务：sms,voice,data 逗号分隔")
    # 接入协议配置
    protocol = Column(
        Enum("HTTP", "SMPP", name="account_protocol"),
        nullable=False,
        default="HTTP",
        comment="接入协议：HTTP API接口/SMPP直连"
    )
    smpp_system_id = Column(String(20), unique=True, comment="SMPP System ID")
    smpp_password = Column(String(64), comment="SMPP Password")
    # 计费配置
    payment_type = Column(
        Enum("prepaid", "postpaid", name="account_payment_type"),
        nullable=False,
        default="prepaid",
        comment="付费方式：prepaid预付费/postpaid后付费"
    )
    unit_price = Column(DECIMAL(10, 4), nullable=True, default=None, comment="短信单价(USD/条)；NULL=未配置时由 account_pricing/country_pricing 兜底")
    password_hash = Column(String(255), comment="密码哈希")
    balance = Column(DECIMAL(12, 4), nullable=False, default=0.0000, comment="账户余额")
    currency = Column(String(10), nullable=False, default="USD", comment="币种")
    sales_id = Column(Integer, ForeignKey("admin_users.id"), comment="归属销售ID")
    status = Column(
        Enum("active", "suspended", "closed", name="account_status"),
        nullable=False,
        default="active",
        comment="账户状态"
    )
    api_key = Column(String(64), unique=True, comment="API密钥")
    api_secret = Column(String(128), comment="API密钥（加密存储）")
    ip_whitelist = Column(Text, comment="IP白名单（JSON数组）")
    rate_limit = Column(Integer, default=1000, comment="TPS 限速（条/秒）")
    smpp_max_binds = Column(Integer, default=5, comment="SMPP 最大并发绑定数")
    low_balance_threshold = Column(DECIMAL(12, 4), nullable=True, default=100.0000, comment="余额预警阈值")
    # Webhook配置
    webhook_url = Column(String(255), nullable=True, comment="Webhook回调地址")
    webhook_secret = Column(String(128), nullable=True, comment="Webhook签名密钥")
    
    company_name = Column(String(200), nullable=True, comment="公司名称")
    contact_person = Column(String(100), nullable=True, comment="联系人")
    contact_phone = Column(String(50), nullable=True, comment="联系电话")
    created_by = Column(Integer, ForeignKey("admin_users.id"), nullable=True, comment="创建者管理员ID")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    last_login_at = Column(TIMESTAMP, nullable=True, comment="最近登录时间")
    activity_score = Column(Integer, nullable=False, default=100, comment="活跃度分数")
    activity_updated_at = Column(TIMESTAMP, nullable=True, comment="活跃度最后更新时间")
    activity_zero_since = Column(TIMESTAMP, nullable=True, comment="活跃度为0开始时间")
    is_deleted = Column(Boolean, nullable=False, default=False, comment="软删除标记")
    # 客户门户展示控制（部分销售要求对其客户隐藏敏感项；仅影响客户门户显示，不影响计费/路由）
    hide_price = Column(Boolean, nullable=False, default=False, server_default="0", comment="客户门户隐藏价格(单价/剩余条数估算)")
    hide_tg = Column(Boolean, nullable=False, default=False, server_default="0", comment="客户门户隐藏TG(自绑TG卡片+归属商务联系TG)")
    supplier_url = Column(String(500), nullable=True, comment="供应商系统登录地址")
    supplier_credentials = Column(JSON, nullable=True, comment="供应商系统凭据(系统地址/客户名/坐席号/域名等)")

    # 关联
    sales = relationship("AdminUser", foreign_keys=[sales_id], backref="customers")
    account_channels = relationship("AccountChannel", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(id={self.id}, name={self.account_name}, balance={self.balance})>"
