"""
路由规则数据模型
"""
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.database import Base


class RoutingRule(Base):
    """路由规则表"""
    __tablename__ = "routing_rules"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="规则ID")
    channel_id = Column(Integer, nullable=False, comment="通道ID")
    country_code = Column(String(3), nullable=False, comment="国家代码")
    priority = Column(Integer, nullable=False, default=0, comment="优先级")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用")
    banned_words = Column(Text, nullable=True, comment="该国家专属违禁词，逗号或换行分隔")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    
    def __repr__(self):
        return f"<RoutingRule(id={self.id}, country={self.country_code}, channel_id={self.channel_id})>"

