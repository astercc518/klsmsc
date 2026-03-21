"""
短信模板相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TemplateCategory(str, Enum):
    """模板分类"""
    VERIFICATION = "verification"
    NOTIFICATION = "notification"
    MARKETING = "marketing"


class TemplateStatus(str, Enum):
    """模板状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISABLED = "disabled"


class TemplateCreate(BaseModel):
    """创建模板"""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    category: TemplateCategory = Field(..., description="模板分类")
    content: str = Field(..., min_length=1, max_length=1000, description="模板内容")
    variables: Optional[List[str]] = Field(default=None, description="变量列表")
    
    @validator('content')
    def validate_content(cls, v):
        """验证模板内容"""
        if not v or not v.strip():
            raise ValueError("模板内容不能为空")
        return v.strip()
    
    @validator('variables')
    def validate_variables(cls, v, values):
        """验证变量是否在内容中"""
        if v:
            content = values.get('content', '')
            for var in v:
                placeholder = f"{{{var}}}"
                if placeholder not in content:
                    raise ValueError(f"变量 {var} 未在模板内容中使用")
        return v


class TemplateUpdate(BaseModel):
    """更新模板"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="模板名称")
    category: Optional[TemplateCategory] = Field(None, description="模板分类")
    content: Optional[str] = Field(None, min_length=1, max_length=1000, description="模板内容")
    variables: Optional[List[str]] = Field(None, description="变量列表")


class TemplateApprove(BaseModel):
    """审核模板"""
    status: TemplateStatus = Field(..., description="审核状态")
    reject_reason: Optional[str] = Field(None, description="拒绝原因")
    
    @validator('reject_reason')
    def validate_reject_reason(cls, v, values):
        """如果拒绝，必须填写拒绝原因"""
        if values.get('status') == TemplateStatus.REJECTED and not v:
            raise ValueError("拒绝时必须填写拒绝原因")
        return v


class TemplateResponse(BaseModel):
    """模板响应"""
    id: int
    account_id: int
    name: str
    category: TemplateCategory
    content: str
    variables: Optional[List[str]]
    status: TemplateStatus
    reject_reason: Optional[str]
    usage_count: int
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    """模板列表响应"""
    total: int
    items: List[TemplateResponse]
    page: int
    page_size: int
