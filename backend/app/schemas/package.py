"""
套餐相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum


class PackageType(str, Enum):
    """套餐类型"""
    SMS_BUNDLE = "sms_bundle"
    TIME_BASED = "time_based"
    PREPAID = "prepaid"
    POSTPAID = "postpaid"
    DATA_BUNDLE = "data_bundle"
    COMBO_BUNDLE = "combo_bundle"


class PackageStatus(str, Enum):
    """套餐状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class PackageResponse(BaseModel):
    """套餐响应"""
    id: int
    package_name: str
    package_type: PackageType
    description: Optional[str]
    price: Decimal
    currency: str
    sms_quota: Optional[int]
    data_quota: Optional[int] = None
    data_filter_criteria: Optional[Dict[str, Any]] = None
    bundle_discount: Optional[Decimal] = None
    validity_days: Optional[int]
    features: Optional[Dict[str, Any]]
    rate_limit: Optional[int]
    discount_percent: Optional[Decimal]
    status: PackageStatus
    sort_order: int
    is_featured: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PackageListResponse(BaseModel):
    """套餐列表响应"""
    total: int
    items: List[PackageResponse]
    page: int
    page_size: int


class AccountPackageResponse(BaseModel):
    """账户套餐响应"""
    id: int
    account_id: int
    package_id: int
    package_name: str
    sms_used: int
    sms_remaining: Optional[int]
    data_used: Optional[int] = None
    data_remaining: Optional[int] = None
    start_date: datetime
    end_date: datetime
    is_active: bool
    purchase_price: Optional[Decimal]
    created_at: datetime
    
    class Config:
        from_attributes = True


class PurchasePackageRequest(BaseModel):
    """购买套餐请求"""
    package_id: int = Field(..., description="套餐ID")
    payment_method: Optional[str] = Field(None, description="支付方式")
