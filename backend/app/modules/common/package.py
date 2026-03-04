"""
套餐管理模型（P2-3）
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, TIMESTAMP, Boolean, Text, JSON
from sqlalchemy.sql import func
from app.database import Base
import enum


class PackageType(str, enum.Enum):
    """套餐类型"""
    SMS_BUNDLE = "sms_bundle"       # 短信套餐
    TIME_BASED = "time_based"       # 时长套餐
    PREPAID = "prepaid"             # 预付费
    POSTPAID = "postpaid"           # 后付费
    DATA_BUNDLE = "data_bundle"       # 纯数据套餐
    COMBO_BUNDLE = "combo_bundle"     # 数据+短信组合套餐


class PackageStatus(str, enum.Enum):
    """套餐状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class Package(Base):
    """套餐定义表"""
    __tablename__ = "packages"
    
    id = Column(Integer, primary_key=True, index=True, comment="套餐ID")
    
    # 套餐信息
    package_name = Column(String(200), nullable=False, comment="套餐名称")
    package_type = Column(
        String(50),
        nullable=False,
        comment="套餐类型"
    )
    description = Column(Text, comment="套餐描述")
    
    # 价格与容量
    price = Column(DECIMAL(12, 4), nullable=False, comment="价格")
    currency = Column(String(10), default="USD", comment="货币")
    sms_quota = Column(Integer, comment="短信条数（仅SMS套餐）")
    data_quota = Column(Integer, comment="数据条数(号码数量)")
    data_filter_criteria = Column(JSON, comment="数据筛选条件(国家/标签等)")
    bundle_discount = Column(DECIMAL(5, 2), comment="组合套餐折扣率(%)")
    validity_days = Column(Integer, comment="有效期（天）")
    
    # 功能配置
    features = Column(JSON, comment="功能列表（JSON）")
    rate_limit = Column(Integer, comment="频率限制")
    
    # 优惠配置
    discount_percent = Column(DECIMAL(5, 2), comment="折扣百分比")
    
    # 状态
    status = Column(
        String(50),
        nullable=False,
        default="active",
        comment="状态"
    )
    
    # 排序与展示
    sort_order = Column(Integer, default=0, comment="排序顺序")
    is_featured = Column(Boolean, default=False, comment="是否推荐")
    
    # 时间
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="软删除标记")
    
    def __repr__(self):
        return f"<Package(id={self.id}, name='{self.package_name}', price={self.price})>"


class AccountPackage(Base):
    """账户套餐关联表"""
    __tablename__ = "account_packages"
    
    id = Column(Integer, primary_key=True, index=True, comment="ID")
    account_id = Column(Integer, nullable=False, index=True, comment="账户ID")
    package_id = Column(Integer, nullable=False, comment="套餐ID")
    
    # 使用情况
    sms_used = Column(Integer, default=0, comment="已使用短信数")
    sms_remaining = Column(Integer, comment="剩余短信数")
    data_used = Column(Integer, default=0, comment="已使用数据条数")
    data_remaining = Column(Integer, comment="剩余数据条数")
    
    # 有效期
    start_date = Column(TIMESTAMP, nullable=False, comment="开始日期")
    end_date = Column(TIMESTAMP, nullable=False, comment="结束日期")
    
    # 状态
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 购买信息
    purchase_price = Column(DECIMAL(12, 4), comment="购买价格")
    order_id = Column(String(100), comment="订单ID")
    
    # 时间
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    
    def __repr__(self):
        return f"<AccountPackage(account_id={self.account_id}, package_id={self.package_id})>"
