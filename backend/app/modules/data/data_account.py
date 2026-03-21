"""
数据账户数据模型
"""
from sqlalchemy import (
    Column, Integer, String, Enum, DateTime, 
    ForeignKey, DECIMAL, Text, JSON
)
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class DataAccount(Base):
    """数据账户表 - 关联外部数据平台"""
    __tablename__ = "data_accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联本地账户
    account_id = Column(
        INTEGER(unsigned=True), 
        ForeignKey("accounts.id"), 
        nullable=False,
        comment="关联本地账户ID"
    )
    
    # 数据平台信息
    platform_account = Column(String(100), comment="数据平台账号")
    platform_token = Column(String(255), comment="数据平台Token")
    external_id = Column(String(100), unique=True, comment="数据平台账户ID")
    
    # 业务信息
    country_code = Column(String(10), nullable=False, comment="国家代码")
    template_id = Column(Integer, ForeignKey("account_templates.id"), comment="开户模板ID")
    
    # 余额（同步自数据平台）
    balance = Column(DECIMAL(10, 2), default=0, comment="数据平台余额")
    
    # 统计信息
    total_extracted = Column(Integer, default=0, comment="总提取数量")
    total_spent = Column(DECIMAL(10, 2), default=0, comment="总消费金额")
    
    # 状态
    status = Column(
        Enum("active", "suspended", "closed", name="data_account_status_enum"),
        default="active",
        comment="状态"
    )
    
    # 同步信息
    last_sync_at = Column(DateTime, comment="最后同步时间")
    sync_error = Column(Text, comment="同步错误信息")
    
    # 额外数据
    extra_data = Column(JSON, comment="额外数据")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    account = relationship("Account", backref="data_accounts")
    template = relationship("AccountTemplate")
    
    def __repr__(self):
        return f"<DataAccount(id={self.id}, platform={self.platform_account}, status={self.status})>"


class DataExtractionLog(Base):
    """数据提取记录"""
    __tablename__ = "data_extraction_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    data_account_id = Column(
        Integer, 
        ForeignKey("data_accounts.id"), 
        nullable=False,
        comment="数据账户ID"
    )
    
    # 提取信息
    extraction_id = Column(String(100), comment="平台提取ID")
    count = Column(Integer, nullable=False, comment="提取数量")
    unit_price = Column(DECIMAL(10, 4), comment="单价")
    total_cost = Column(DECIMAL(10, 2), comment="总费用")
    
    # 筛选条件
    filters = Column(JSON, comment="筛选条件")
    
    # 状态
    status = Column(
        Enum("pending", "success", "failed", name="extraction_status_enum"),
        default="pending",
        comment="状态"
    )
    
    # 备注
    error_message = Column(Text, comment="错误信息")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, comment="完成时间")
    
    # 关系
    data_account = relationship("DataAccount", backref="extraction_logs")
