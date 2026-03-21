"""
定时任务相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TaskFrequency(str, Enum):
    """执行频率"""
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledTaskCreate(BaseModel):
    """创建定时任务"""
    task_name: str = Field(..., min_length=1, max_length=200, description="任务名称")
    template_id: Optional[int] = Field(None, description="模板ID")
    phone_numbers: List[str] = Field(..., min_items=1, description="手机号列表")
    content: Optional[str] = Field(None, max_length=500, description="短信内容")
    sender_id: Optional[str] = Field(None, max_length=20, description="发送方ID")
    frequency: TaskFrequency = Field(default=TaskFrequency.ONCE, description="执行频率")
    scheduled_time: datetime = Field(..., description="计划执行时间")
    repeat_config: Optional[Dict[str, Any]] = Field(None, description="重复配置")
    
    @validator('phone_numbers')
    def validate_phones(cls, v):
        if len(v) > 1000:
            raise ValueError("单次最多支持1000个手机号")
        return v


class ScheduledTaskUpdate(BaseModel):
    """更新定时任务"""
    task_name: Optional[str] = Field(None, min_length=1, max_length=200)
    scheduled_time: Optional[datetime] = None
    frequency: Optional[TaskFrequency] = None
    status: Optional[TaskStatus] = None
    repeat_config: Optional[Dict[str, Any]] = None


class ScheduledTaskResponse(BaseModel):
    """定时任务响应"""
    id: int
    account_id: int
    task_name: str
    template_id: Optional[int]
    phone_numbers: List[str]
    content: Optional[str]
    sender_id: Optional[str]
    frequency: TaskFrequency
    scheduled_time: datetime
    last_run_time: Optional[datetime]
    next_run_time: Optional[datetime]
    repeat_config: Optional[Dict[str, Any]]
    status: TaskStatus
    total_runs: int
    success_runs: int
    failed_runs: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ScheduledTaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    items: List[ScheduledTaskResponse]
    page: int
    page_size: int


class ScheduledTaskStats(BaseModel):
    """任务统计"""
    total_tasks: int
    pending_tasks: int
    running_tasks: int
    completed_tasks: int
    failed_tasks: int
