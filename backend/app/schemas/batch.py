"""
批量发送相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field, field_validator
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

    @field_validator("batch_name", mode="before")
    @classmethod
    def batch_name_none_as_empty(cls, v: object) -> str:
        """极少数历史数据 batch_name 可能为 NULL"""
        if v is None:
            return ""
        return str(v)

    @field_validator(
        "total_count",
        "success_count",
        "failed_count",
        "processing_count",
        "progress",
        mode="before",
    )
    @classmethod
    def int_null_as_zero(cls, v: object) -> int:
        """旧数据 NULL 或 JDBC/部分驱动把整型以 str 返回时，避免响应校验 500"""
        if v is None:
            return 0
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return 0
            try:
                return int(float(s))
            except ValueError:
                return 0
        try:
            return int(v)  # Decimal 等
        except (TypeError, ValueError):
            return 0

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


class BatchRetryFailedResponse(BaseModel):
    """失败重发响应"""
    retried: int = Field(..., description="成功重新入队条数")
    skipped: int = Field(0, description="未重发条数（缺数据、计费或入队失败等）")
    errors: List[str] = Field(default_factory=list, description="失败原因摘要（最多若干条）")
    message: str = Field(default="", description="说明")
