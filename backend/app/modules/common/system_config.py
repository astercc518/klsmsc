"""
系统配置模型
"""
from sqlalchemy import Column, Integer, String, Enum, TIMESTAMP, Text, Boolean
from sqlalchemy.sql import func
from app.database import Base


class SystemConfig(Base):
    """系统配置表"""
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), nullable=False, unique=True, comment="配置键")
    config_value = Column(Text, comment="配置值")
    config_type = Column(
        Enum('string', 'number', 'boolean', 'json', name="config_type"),
        nullable=False,
        default='string',
        comment="值类型"
    )
    category = Column(
        String(50),
        nullable=False,
        default='general',
        server_default='general',
        index=True,
        comment="分类: general/sms/telegram/notification/security"
    )
    description = Column(Text, comment="配置说明")
    is_public = Column(Boolean, nullable=False, default=False, comment="是否公开")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, comment="更新人ID")
    
    def __repr__(self):
        return f"<SystemConfig(key={self.config_key}, category={self.category})>"
