"""
账户相关的数据模式
"""
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from decimal import Decimal


class AccountBalanceResponse(BaseModel):
    """账户余额响应"""
    account_id: int
    balance: float
    currency: str
    low_balance_threshold: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "account_id": 1,
                "balance": 1250.50,
                "currency": "USD",
                "low_balance_threshold": 100.0
            }
        }


class AccountInfoResponse(BaseModel):
    """账户信息响应"""
    id: int
    account_name: str
    email: Optional[str] = None
    balance: float
    currency: str
    status: str
    services: str = "sms"
    company_name: Optional[str] = None
    contact_person: Optional[str] = None
    rate_limit: Optional[int] = None
    tg_id: Optional[int] = None
    tg_username: Optional[str] = None
    unit_price: Optional[float] = None  # 短信单价(USD/条)，用于前端预估费用
    created_at: str
    # 仪表盘等展示用
    client_name: Optional[str] = None  # 客户名称：优先公司名称，否则账户名
    country_code: Optional[str] = None  # 国家/地区代码
    remaining_sms_estimate: Optional[int] = None  # 按单价估算剩余可发条数（余额/单价向下取整）
    sales_tg_username: Optional[str] = None  # 归属商务 Telegram，便于客户联系


class AccountCreateRequest(BaseModel):
    """创建账户请求"""
    account_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    company_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "account_name": "测试公司",
                "email": "test@example.com",
                "password": "password123",
                "company_name": "Test Company Ltd.",
                "contact_person": "张三"
            }
        }


class AccountLoginRequest(BaseModel):
    """账户登录请求"""
    email: str  # 支持邮箱或用户名
    password: str


class AccountLoginResponse(BaseModel):
    """账户登录响应"""
    success: bool
    token: Optional[str] = None
    account_id: Optional[int] = None
    error: Optional[str] = None

