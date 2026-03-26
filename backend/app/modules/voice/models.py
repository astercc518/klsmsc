"""语音业务模块模型"""
from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, Float, Text
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
    # 与 FreeSWITCH/网关出局配置对齐，供运维侧双写与对账
    trunk_profile = Column(String(128), nullable=True, comment="FS 网关 profile 或 Trunk 名")
    dial_prefix = Column(String(32), nullable=True, comment="出局拨号前缀")
    notes = Column(Text, nullable=True, comment="备注")
    
    created_at = Column(DateTime, server_default=func.now())

class VoiceCall(Base):
    """语音通话记录 (CDR)"""
    __tablename__ = 'voice_calls'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String(100), unique=True, nullable=False)
    provider_call_id = Column(String(128), nullable=True, comment="上游通话ID")
    
    account_id = Column(Integer, nullable=False)
    voice_account_id = Column(Integer, ForeignKey("voice_accounts.id"), nullable=True)
    outbound_campaign_id = Column(
        Integer, ForeignKey("voice_outbound_campaigns.id"), nullable=True
    )
    
    caller = Column(String(32), comment='主叫')
    callee = Column(String(32), comment='被叫')
    direction = Column(String(16), nullable=True, comment="inbound/outbound")
    sip_extension = Column(String(32), nullable=True, comment="分机号")
    
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    answer_time = Column(DateTime, nullable=True)
    duration = Column(Integer, comment='时长(秒)')
    billsec = Column(Integer, nullable=True, comment='计费秒数')
    
    status = Column(Enum('initiated', 'ringing', 'answered', 'busy', 'failed', 'completed', name='call_status_enum'))
    hangup_cause = Column(String(64), nullable=True)
    recording_url = Column(String(512), nullable=True)
    hangup_sms_message_id = Column(String(128), nullable=True, comment="挂机短信 message_id")
    voice_route_id = Column(Integer, ForeignKey("voice_routes.id"), nullable=True, comment="批价所用路由")
    
    cost = Column(Float, default=0.0)
    
    created_at = Column(DateTime, server_default=func.now())

    voice_account = relationship("VoiceAccount", backref="voice_calls")
    outbound_campaign = relationship("VoiceOutboundCampaign", backref="voice_calls")
