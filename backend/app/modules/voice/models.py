"""语音业务模块模型 (Placeholder)"""
from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class VoiceRoute(Base):
    """语音路由"""
    __tablename__ = 'voice_routes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    country_code = Column(String(10), nullable=False)
    provider_id = Column(Integer, comment='供应商ID')
    priority = Column(Integer, default=0)
    cost_per_minute = Column(Float, default=0.0)
    
    created_at = Column(DateTime, server_default=func.now())

class VoiceCall(Base):
    """语音通话记录 (CDR)"""
    __tablename__ = 'voice_calls'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String(100), unique=True, nullable=False)
    
    account_id = Column(Integer, nullable=False)
    
    caller = Column(String(20), comment='主叫')
    callee = Column(String(20), comment='被叫')
    
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration = Column(Integer, comment='时长(秒)')
    
    status = Column(Enum('initiated', 'ringing', 'answered', 'busy', 'failed', 'completed', name='call_status_enum'))
    
    cost = Column(Float, default=0.0)
    
    created_at = Column(DateTime, server_default=func.now())
