"""语音外呼、主叫号码、挂机短信、DNC 等扩展模型"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Enum,
    DateTime,
    ForeignKey,
    Float,
    Boolean,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class VoiceCallerId(Base):
    """主叫号码池（外显号码）"""

    __tablename__ = "voice_caller_ids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(
        INTEGER(unsigned=True),
        ForeignKey("accounts.id"),
        nullable=False,
        comment="业务账户",
    )
    voice_account_id = Column(
        Integer, ForeignKey("voice_accounts.id"), nullable=True, comment="语音子账户可选"
    )
    number_e164 = Column(String(32), nullable=False, comment="E.164 或带+号码")
    label = Column(String(128), nullable=True)
    trunk_ref = Column(String(64), nullable=True, comment="Trunk 侧标识")
    voice_route_id = Column(
        Integer,
        ForeignKey("voice_routes.id"),
        nullable=True,
        comment="可选绑定出局/批价路由，与计费路由对齐",
    )
    status = Column(
        Enum("active", "disabled", name="voice_caller_id_status_enum"),
        default="active",
    )
    created_at = Column(DateTime, server_default=func.now())

    account = relationship("Account", backref="voice_caller_ids")
    # 与 VoiceAccount.default_caller（指向 voice_caller_ids.id）区分，必须指定 foreign_keys
    voice_account = relationship(
        "VoiceAccount",
        foreign_keys=[voice_account_id],
        back_populates="caller_ids",
    )


class VoiceOutboundCampaign(Base):
    """外呼任务"""

    __tablename__ = "voice_outbound_campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(INTEGER(unsigned=True), ForeignKey("accounts.id"), nullable=False)
    voice_account_id = Column(Integer, ForeignKey("voice_accounts.id"), nullable=True)
    name = Column(String(200), nullable=False)
    status = Column(
        Enum(
            "draft",
            "running",
            "paused",
            "completed",
            "cancelled",
            name="voice_campaign_status_enum",
        ),
        default="draft",
    )
    timezone = Column(String(64), default="Asia/Shanghai", comment="任务时区")
    window_start = Column(String(8), nullable=True, comment="HH:MM 本地可呼起始")
    window_end = Column(String(8), nullable=True, comment="HH:MM 结束")
    max_concurrent = Column(Integer, default=1)
    caller_id_mode = Column(
        Enum("fixed", "round_robin", "random", name="voice_campaign_caller_mode_enum"),
        default="fixed",
    )
    fixed_caller_id_id = Column(Integer, ForeignKey("voice_caller_ids.id"), nullable=True)
    # AI 外呼：ivr=仅语音导航；ai=对接 ASR/LLM（由网关与 dialplan 实现）
    ai_mode = Column(
        String(16),
        nullable=True,
        default="ivr",
        comment="ivr 或 ai",
    )
    ai_prompt = Column(Text, nullable=True, comment="AI 外呼营销提示词对话脚本")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    account = relationship("Account", backref="voice_outbound_campaigns")
    fixed_caller = relationship("VoiceCallerId", foreign_keys=[fixed_caller_id_id])


class VoiceOutboundContact(Base):
    """外呼名单"""

    __tablename__ = "voice_outbound_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(
        Integer, ForeignKey("voice_outbound_campaigns.id"), nullable=False, index=True
    )
    phone_e164 = Column(String(32), nullable=False)
    status = Column(
        Enum(
            "pending",
            "dialing",
            "completed",
            "failed",
            "skipped",
            name="voice_contact_status_enum",
        ),
        default="pending",
    )
    attempt_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    campaign = relationship("VoiceOutboundCampaign", backref="contacts")


class VoiceHangupSmsRule(Base):
    """挂机短信规则"""

    __tablename__ = "voice_hangup_sms_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(INTEGER(unsigned=True), ForeignKey("accounts.id"), nullable=True)
    voice_account_id = Column(Integer, ForeignKey("voice_accounts.id"), nullable=True)
    campaign_id = Column(
        Integer, ForeignKey("voice_outbound_campaigns.id"), nullable=True
    )
    name = Column(String(128), nullable=False)
    enabled = Column(Boolean, default=True)
    match_answered_only = Column(Boolean, default=True, comment="仅接通后发送")
    template_body = Column(Text, nullable=False, comment="支持变量 {callee} {duration} {campaign_name}")
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    account = relationship("Account", backref="voice_hangup_sms_rules")


class VoiceDncNumber(Base):
    """语音禁呼号码（DNC）"""

    __tablename__ = "voice_dnc_numbers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(INTEGER(unsigned=True), ForeignKey("accounts.id"), nullable=False)
    phone_e164 = Column(String(32), nullable=False)
    source = Column(String(64), nullable=True, comment="导入来源说明")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("account_id", "phone_e164", name="uq_voice_dnc_account_phone"),
    )


class VoiceCdrWebhookLog(Base):
    """CDR Webhook 投递日志（幂等与排错、失败重放）"""

    __tablename__ = "voice_cdr_webhook_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String(128), unique=True, nullable=False)
    payload_hash = Column(String(64), nullable=True)
    raw_payload = Column(Text, nullable=True, comment="原始 JSON，供重试与对账")
    retry_count = Column(Integer, default=0, comment="已重试次数")
    status = Column(
        Enum("received", "processed", "failed", name="voice_cdr_webhook_status_enum"),
        default="received",
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    processed_at = Column(DateTime, nullable=True)
