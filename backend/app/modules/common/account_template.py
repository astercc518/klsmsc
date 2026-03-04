"""
开户模板数据模型
"""
from sqlalchemy import Column, Integer, String, Enum, TIMESTAMP, BigInteger, JSON, DECIMAL, Text
from sqlalchemy.sql import func
from app.database import Base


class AccountTemplate(Base):
    """开户模板表"""
    __tablename__ = "account_templates"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="模板ID")
    template_code = Column(String(50), unique=True, nullable=False, comment="模板编码")
    template_name = Column(String(100), nullable=False, comment="模板名称")
    business_type = Column(
        Enum("sms", "voice", "data", name="business_type_enum"),
        nullable=False,
        default="sms",
        comment="业务类型"
    )
    country_code = Column(String(10), nullable=False, comment="国家代码")
    country_name = Column(String(100), comment="国家名称")
    supplier_group_id = Column(BigInteger, comment="供应商TG群ID")
    supplier_group_name = Column(String(100), comment="供应商群名称")
    channel_ids = Column(JSON, comment="关联通道IDs (短信用)")
    external_product_id = Column(String(100), comment="外部产品ID (语音/数据用)")
    default_price = Column(DECIMAL(10, 4), default=0.0, comment="默认售价")
    pricing_rules = Column(JSON, comment="定价规则")
    description = Column(Text, comment="模板描述")
    status = Column(
        Enum("active", "inactive", name="template_status_enum"),
        nullable=False,
        default="active",
        comment="状态"
    )
    created_by = Column(Integer, comment="创建人ID")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    
    def __repr__(self):
        return f"<AccountTemplate(id={self.id}, code={self.template_code}, type={self.business_type})>"
