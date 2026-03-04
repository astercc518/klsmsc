"""
批量发送任务模型
"""
from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, Boolean, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base
import enum


class BatchStatus(str, enum.Enum):
    """批量任务状态"""
    PENDING = "pending"          # 待处理
    PROCESSING = "processing"    # 处理中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"      # 已取消


class SmsBatch(Base):
    """批量发送任务表"""
    __tablename__ = "sms_batches"
    
    id = Column(Integer, primary_key=True, index=True, comment="批次ID")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True, comment="账户ID")
    
    # 批次信息
    batch_name = Column(String(200), nullable=False, comment="批次名称")
    template_id = Column(Integer, ForeignKey("sms_templates.id"), comment="使用的模板ID")
    
    # 文件信息
    file_path = Column(String(500), comment="上传的CSV文件路径")
    file_size = Column(Integer, comment="文件大小（字节）")
    
    # 统计信息
    total_count = Column(Integer, default=0, comment="总条数")
    success_count = Column(Integer, default=0, comment="成功数")
    failed_count = Column(Integer, default=0, comment="失败数")
    processing_count = Column(Integer, default=0, comment="处理中数")
    
    # 状态
    status = Column(
        Enum(BatchStatus),
        nullable=False,
        default=BatchStatus.PENDING,
        comment="批次状态"
    )
    
    # 错误信息
    error_message = Column(Text, comment="错误信息")
    error_details = Column(JSON, comment="详细错误列表")
    
    # 发送配置
    sender_id = Column(String(20), comment="发送方ID")
    send_config = Column(JSON, comment="发送配置（优先级、延迟等）")
    
    # 进度
    progress = Column(Integer, default=0, comment="进度百分比 0-100")
    
    # 时间
    started_at = Column(TIMESTAMP, comment="开始处理时间")
    completed_at = Column(TIMESTAMP, comment="完成时间")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="软删除标记")
    
    def __repr__(self):
        return f"<SmsBatch(id={self.id}, name='{self.batch_name}', status='{self.status}', progress={self.progress}%)>"
