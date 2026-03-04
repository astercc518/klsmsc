"""
通道数据模型
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Enum, Boolean, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.database import Base


class Channel(Base):
    """通道表"""
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="通道ID")
    channel_code = Column(String(50), unique=True, nullable=False, comment="通道编码")
    channel_name = Column(String(100), nullable=False, comment="通道名称")
    protocol = Column(
        Enum("SMPP", "HTTP", name="channel_protocol"),
        nullable=False,
        comment="协议类型"
    )
    host = Column(String(255), comment="主机地址")
    port = Column(Integer, comment="端口号")
    username = Column(String(100), comment="用户名")
    password = Column(String(255), comment="密码（加密存储）")
    api_url = Column(String(500), comment="HTTP API地址")
    api_key = Column(String(255), comment="HTTP API密钥")
    
    default_sender_id = Column(String(20), nullable=False, comment="默认发送方ID(必填)")
    cost_rate = Column(DECIMAL(10, 4), default=0.0000, comment="通道基础成本价")
    
    # 速率控制
    max_tps = Column(Integer, default=100, comment="下发总速度(条/秒)")
    concurrency = Column(Integer, default=1, comment="并发数")
    rate_control_window = Column(Integer, default=1000, comment="速率控制窗口(毫秒)")
    
    priority = Column(Integer, nullable=False, default=0, comment="优先级")
    weight = Column(Integer, nullable=False, default=100, comment="权重")
    
    status = Column(
        Enum("active", "inactive", "maintenance", name="channel_status"),
        nullable=False,
        default="active",
        comment="通道状态"
    )
    
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    is_deleted = Column(Boolean, nullable=False, default=False, comment="软删除标记")
    
    def __repr__(self):
        return f"<Channel(id={self.id}, code={self.channel_code}, status={self.status})>"
