"""
短信相关的数据模式
"""
from typing import Optional
from pydantic import BaseModel, Field, validator


class SMSSendRequest(BaseModel):
    """发送短信请求"""
    phone_number: str = Field(..., description="目标电话号码（E.164格式，如+8613800138000）")
    message: str = Field(..., min_length=1, max_length=1000, description="短信内容")
    sender_id: Optional[str] = Field(None, max_length=20, description="发送方ID（可选）")
    channel_id: Optional[int] = Field(None, description="指定通道ID（可选）")
    callback_url: Optional[str] = Field(None, description="状态回调URL（可选）")
    http_username: Optional[str] = Field(None, max_length=100, description="HTTP通道账户（可选）")
    http_password: Optional[str] = Field(None, max_length=255, description="HTTP通道密码（可选）")
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        """验证电话号码格式"""
        if not v.startswith('+'):
            raise ValueError('Phone number must start with + (E.164 format)')
        if len(v) < 8 or len(v) > 20:
            raise ValueError('Phone number length must be between 8 and 20')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "phone_number": "+8613800138000",
                "message": "Your verification code is 123456",
                "sender_id": "MyApp"
            }
        }


class SMSSendResponse(BaseModel):
    """发送短信响应"""
    success: bool
    message_id: Optional[str] = None
    status: Optional[str] = None
    cost: Optional[float] = None
    currency: Optional[str] = None
    message_count: Optional[int] = None
    error: Optional[dict] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message_id": "msg_1234567890abcdef",
                "status": "queued",
                "cost": 0.05,
                "currency": "USD",
                "message_count": 1
            }
        }


class SMSStatusResponse(BaseModel):
    """短信状态响应"""
    message_id: str
    status: str
    phone_number: str
    submit_time: str
    sent_time: Optional[str] = None
    delivery_time: Optional[str] = None
    error_message: Optional[str] = None
    cost: Optional[float] = None
    currency: Optional[str] = None


class BatchSMSRequest(BaseModel):
    """批量发送短信请求"""
    phone_numbers: list[str] = Field(..., min_items=1, max_items=1000, description="电话号码列表")
    message: str = Field(..., min_length=1, max_length=1000, description="短信内容（无 messages 时使用；多文案时作占位）")
    sender_id: Optional[str] = Field(None, max_length=20, description="发送方ID（可选）")
    callback_url: Optional[str] = Field(None, description="状态回调URL（可选）")
    channel_id: Optional[int] = Field(None, description="指定通道ID（可选）")
    batch_name: Optional[str] = Field(None, max_length=200, description="发送任务名称（可选，用于任务列表展示）")
    messages: Optional[list[str]] = Field(None, description="多文案按号码轮发；非空时按序号取模选用")
    
    class Config:
        json_schema_extra = {
            "example": {
                "phone_numbers": ["+8613800138000", "+8613800138001"],
                "message": "Batch message content",
                "sender_id": "MyApp"
            }
        }


class BatchSMSResponse(BaseModel):
    """批量发送短信响应"""
    success: bool
    total: int
    succeeded: int
    failed: int
    messages: list[dict]
    batch_id: Optional[int] = Field(None, description="关联 sms_batches.id，可在发送任务页查看进度")


class SMSApprovalSubmitRequest(BaseModel):
    """短信审核提交请求"""
    phone_number: str = Field(..., description="目标电话号码（E.164格式）")
    message: str = Field(..., min_length=1, max_length=1000, description="短信内容")

    @validator('phone_number')
    def validate_phone_number(cls, v):
        if not v.startswith('+'):
            raise ValueError('Phone number must start with + (E.164 format)')
        if len(v) < 8 or len(v) > 20:
            raise ValueError('Phone number length must be between 8 and 20')
        return v

