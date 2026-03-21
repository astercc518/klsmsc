"""
国家计费规则数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Date, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.database import Base


class CountryPricing(Base):
    """计费规则表"""
    __tablename__ = "country_pricing"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="规则ID")
    channel_id = Column(Integer, nullable=False, comment="通道ID")
    country_code = Column(String(3), nullable=False, comment="国家代码")
    country_name = Column(String(100), comment="国家名称")
    price_per_sms = Column(DECIMAL(10, 4), nullable=False, comment="每条短信价格")
    currency = Column(String(10), nullable=False, default="USD", comment="币种")
    effective_date = Column(Date, nullable=False, server_default=func.current_date(), comment="生效日期")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    
    def __repr__(self):
        return f"<CountryPricing(id={self.id}, country={self.country_code}, price={self.price_per_sms})>"

