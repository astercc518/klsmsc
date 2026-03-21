"""
账户专属定价模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class AccountPricing(Base):
    """账户专属定价表"""
    __tablename__ = "account_pricing"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, comment="账户ID")
    country_code = Column(String(10), nullable=False, comment="国家代码")
    business_type = Column(String(20), nullable=False, default='sms', comment="业务类型")
    price = Column(DECIMAL(10, 4), nullable=False, comment="单价")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    def __repr__(self):
        return f"<AccountPricing(acc={self.account_id}, country={self.country_code}, price={self.price})>"
