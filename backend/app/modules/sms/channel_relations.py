"""通道关系模型 - 管理通道与国家、SID的关系绑定"""
from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ChannelCountry(Base):
    """通道-国家关联表 - 定义通道支持哪些国家"""
    __tablename__ = 'channel_countries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(INTEGER(unsigned=True), ForeignKey('channels.id'), nullable=False, comment='通道ID')
    country_code = Column(String(10), nullable=False, comment='国家代码(ISO 3166-1 alpha-2)')
    country_name = Column(String(100), comment='国家名称')
    
    # 状态
    status = Column(Enum('active', 'inactive', name='channel_country_status_enum'),
                   default='active', comment='状态')
    
    # 优先级（同一国家多个通道时使用）
    priority = Column(Integer, default=0, comment='优先级，数字越大优先级越高')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    channel = relationship("Channel", backref="supported_countries")
    
    # 索引
    __table_args__ = (
        Index('idx_channel_country', 'channel_id', 'country_code', unique=True),
        Index('idx_country_status', 'country_code', 'status'),
    )


class ChannelCountrySenderId(Base):
    """通道-国家-SID关联表 - 一个通道在一个国家有哪些可用的SID"""
    __tablename__ = 'channel_country_sender_ids'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(INTEGER(unsigned=True), ForeignKey('channels.id'), nullable=False, comment='通道ID')
    country_code = Column(String(10), nullable=False, comment='国家代码')
    sender_id = Column(String(50), nullable=False, comment='发送方ID(SID)')
    
    # SID类型
    sid_type = Column(Enum('numeric', 'alpha', 'shortcode', name='sid_type_enum'),
                     default='alpha', comment='SID类型')
    
    # 状态
    status = Column(Enum('active', 'inactive', 'pending', 'rejected', name='sid_status_enum'),
                   default='active', comment='状态')
    
    # 是否默认SID
    is_default = Column(Boolean, default=False, comment='是否默认SID')
    
    # 审核信息
    approved_at = Column(DateTime, comment='审核通过时间')
    approved_by = Column(INTEGER(unsigned=True), ForeignKey('admin_users.id'), comment='审核人ID')
    reject_reason = Column(String(500), comment='拒绝原因')
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    channel = relationship("Channel", backref="country_sender_ids")
    approver = relationship("AdminUser", foreign_keys=[approved_by])
    
    # 索引
    __table_args__ = (
        Index('idx_channel_country_sid', 'channel_id', 'country_code', 'sender_id', unique=True),
        Index('idx_country_sid', 'country_code', 'sender_id'),
        Index('idx_channel_sid_status', 'status'),
    )
