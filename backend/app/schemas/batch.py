"""
批量发送相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class BatchStatus(str, Enum):
    """批量任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SmsBatchCreate(BaseModel):
    """创建批量任务"""
    batch_name: str = Field(..., min_length=1, max_length=200, description="批次名称")
    template_id: Optional[int] = Field(None, description="模板ID（使用模板时必填）")
    sender_id: Optional[str] = Field(None, max_length=20, description="发送方ID")
    send_config: Optional[Dict[str, Any]] = Field(default=None, description="发送配置")


class SmsBatchResponse(BaseModel):
    """批量任务响应"""
    id: int
    account_id: int
    batch_name: str
    template_id: Optional[int]
    file_path: Optional[str]
    file_size: Optional[int]
    total_count: int
    success_count: int
    failed_count: int
    processing_count: int
    status: BatchStatus
    error_message: Optional[str]
    sender_id: Optional[str]
    progress: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SmsBatchListResponse(BaseModel):
    """批次列表响应"""
    total: int
    items: List[SmsBatchResponse]
    page: int
    page_size: int


class SmsBatchStats(BaseModel):
    """批次统计"""
    total_batches: int
    pending_batches: int
    processing_batches: int
    completed_batches: int
    failed_batches: int
    total_messages: int
    success_messages: int
    failed_messages: int


class BatchUploadResponse(BaseModel):
    """上传响应"""
    batch_id: int
    file_name: str
    file_size: int
    total_count: int
    message: str
