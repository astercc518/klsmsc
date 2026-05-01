"""数据业务模块 Pydantic Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date


# ============ 定价模板 ============

class PricingTemplateCreate(BaseModel):
    country_code: str = Field("*", description="国家代码(*=全部)")
    source: str = Field(..., description="来源: credential/penetration/social_eng/telemarketing/otp")
    purpose: str = Field(..., description="用途: bc/part_time/dating/finance/stock")
    freshness: str = Field(..., description="时效: 3day/7day/30day/history")
    price_per_number: str = Field(..., description="售价(每号码)")
    cost_per_number: str = Field("0", description="成本(每号码)")
    currency: str = "USD"
    remarks: Optional[str] = None
    name: Optional[str] = None


class PricingTemplateUpdate(BaseModel):
    country_code: Optional[str] = None
    source: Optional[str] = None
    purpose: Optional[str] = None
    freshness: Optional[str] = None
    price_per_number: Optional[str] = None
    cost_per_number: Optional[str] = None
    currency: Optional[str] = None
    remarks: Optional[str] = None
    status: Optional[str] = None
    name: Optional[str] = None


class PricingTemplateBatchCreate(BaseModel):
    """批量创建/更新定价模板"""
    items: List[PricingTemplateCreate]


# ============ 商品相关 ============

class ProductCreate(BaseModel):
    product_code: str
    product_name: str
    description: Optional[str] = None
    filter_criteria: dict
    price_per_number: str = "0.001"
    currency: str = "USD"
    min_purchase: int = 100
    max_purchase: int = 100000
    product_type: str = "data_only"
    sms_quota: Optional[int] = None
    sms_unit_price: Optional[str] = None
    bundle_price: Optional[str] = None
    bundle_discount: Optional[str] = None


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    description: Optional[str] = None
    filter_criteria: Optional[dict] = None
    price_per_number: Optional[str] = None
    min_purchase: Optional[int] = None
    max_purchase: Optional[int] = None
    status: Optional[str] = None
    product_type: Optional[str] = None
    sms_quota: Optional[int] = None
    sms_unit_price: Optional[str] = None
    bundle_price: Optional[str] = None
    bundle_discount: Optional[str] = None


# ============ 号码导入 ============

class NumberImportParams(BaseModel):
    """号码导入时携带的分类信息"""
    source: str = Field(..., description="来源")
    purpose: str = Field(..., description="用途")
    data_date: Optional[date] = Field(None, description="数据采集日期，默认今天")
    default_tags: Optional[str] = Field(None, description="默认标签，逗号分隔")


# ============ 订单相关 ============

class DataOrderCreate(BaseModel):
    product_id: Optional[int] = None
    filter_criteria: Optional[dict] = None
    quantity: int
    carrier: Optional[str] = None


class DataBuyAndSend(BaseModel):
    product_id: Optional[int] = None
    filter_criteria: Optional[dict] = None
    quantity: int
    message: str
    messages: Optional[List[str]] = None
    carrier: Optional[str] = None
    channel_id: Optional[int] = None


class ComboBuyRequest(BaseModel):
    """购买数据+短信组合套餐"""
    product_id: int
    quantity: int


class OrderCancelRequest(BaseModel):
    reason: Optional[str] = None


class OrderRefundRequest(BaseModel):
    reason: Optional[str] = None
    refund_amount: Optional[str] = None


# ============ 筛选相关 ============

class FilterCriteria(BaseModel):
    country: Optional[str] = None
    carrier: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    purpose: Optional[str] = None
    freshness: Optional[str] = None
    status: Optional[str] = "active"
    exclude_used_days: Optional[int] = None


# ============ 号码批量操作 ============

class NumberBatchTagRequest(BaseModel):
    number_ids: List[int]
    tags: List[str]
    mode: str = "add"


class NumberBatchStatusRequest(BaseModel):
    number_ids: List[int]
    status: str


# ============ 数据账户 ============

class DataAccountCreate(BaseModel):
    account_id: int = Field(..., description="关联本地账户ID")
    country_code: str = Field("", description="国家代码")
    balance: float = Field(0, description="初始余额")
    remarks: str = Field("", description="备注")

class DataAccountUpdate(BaseModel):
    country_code: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None

class DataAccountRecharge(BaseModel):
    amount: float = Field(..., gt=0, description="充值金额")
    remarks: str = Field("", description="充值备注")
