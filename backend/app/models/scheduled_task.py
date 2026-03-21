"""
定时发送任务模型（P2-1）
"""
from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, Boolean, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base
import enum


class TaskStatus(str, enum.Enum):
    """任务状态"""
    PENDING = "pending"          # 待执行
    RUNNING = "running"          # 执行中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"      # 已取消


class TaskFrequency(str, enum.Enum):
    """执行频率"""
    ONCE = "once"               # 单次
    DAILY = "daily"             # 每天
    WEEKLY = "weekly"           # 每周
    MONTHLY = "monthly"         # 每月


class ScheduledTask(Base):
    """定时发送任务表"""
    __tablename__ = "scheduled_tasks"
    
    id = Column(Integer, primary_key=True, index=True, comment="任务ID")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True, comment="账户ID")
    
    # 任务信息
    task_name = Column(String(200), nullable=False, comment="任务名称")
    template_id = Column(Integer, comment="模板ID")
    
    # 发送配置
    phone_numbers = Column(JSON, nullable=False, comment="手机号列表（JSON）")
    content = Column(Text, comment="短信内容（如不使用模板）")
    sender_id = Column(String(20), comment="发送方ID")
    
    # 定时配置
    frequency = Column(
        Enum(TaskFrequency),
        nullable=False,
        default=TaskFrequency.ONCE,
        comment="执行频率"
    )
    scheduled_time = Column(TIMESTAMP, nullable=False, comment="计划执行时间")
    last_run_time = Column(TIMESTAMP, comment="上次执行时间")
    next_run_time = Column(TIMESTAMP, comment="下次执行时间")
    
    # 重复配置（用于weekly/monthly）
    repeat_config = Column(JSON, comment="重复配置（如每周一、每月1号）")
    
    # 状态
    status = Column(
        Enum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        comment="任务状态"
    )
    
    # 执行统计
    total_runs = Column(Integer, default=0, comment="总执行次数")
    success_runs = Column(Integer, default=0, comment="成功次数")
    failed_runs = Column(Integer, default=0, comment="失败次数")
    
    # 错误信息
    last_error = Column(Text, comment="最后错误信息")
    
    # 时间
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="软删除标记")
    
    def __repr__(self):
        return f"<ScheduledTask(id={self.id}, name='{self.task_name}', status='{self.status}')>"
