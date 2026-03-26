"""
语音账户数据模型
"""
from sqlalchemy import (
    Column, Integer, String, Enum, DateTime, 
    ForeignKey, DECIMAL, Text, JSON, Boolean
)
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class VoiceAccount(Base):
    """语音账户表 - 关联OKCC系统"""
    __tablename__ = "voice_accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联本地账户
    account_id = Column(
        INTEGER(unsigned=True), 
        ForeignKey("accounts.id"), 
        nullable=False,
        comment="关联本地账户ID"
    )
    # 归属员工（可与业务账户 sales_id 一致或单独指定）
    sales_id = Column(
        Integer,
        ForeignKey("admin_users.id"),
        nullable=True,
        comment="归属员工/销售 admin_users.id",
    )
    
    # OKCC / 自建 SIP 凭据（自建时优先使用 sip_username）
    okcc_account = Column(String(100), comment="OKCC登录账号或兼容字段")
    okcc_password = Column(String(255), comment="OKCC密码（加密存储）")
    sip_username = Column(String(100), nullable=True, comment="SIP 注册用户名")
    external_id = Column(String(100), unique=True, comment="外部语音平台账户ID")
    default_caller_id_id = Column(
        Integer,
        ForeignKey("voice_caller_ids.id"),
        nullable=True,
        comment="默认外显主叫号码",
    )
    
    # 业务信息
    country_code = Column(String(10), nullable=False, comment="国家代码")
    template_id = Column(Integer, ForeignKey("account_templates.id"), comment="开户模板ID")
    
    # 余额（同步自OKCC）
    balance = Column(DECIMAL(10, 2), default=0, comment="OKCC余额")
    
    # 统计信息
    total_calls = Column(Integer, default=0, comment="总通话数")
    total_minutes = Column(Integer, default=0, comment="总通话分钟数")
    
    # 状态
    status = Column(
        Enum("active", "suspended", "closed", name="voice_account_status_enum"),
        default="active",
        comment="状态"
    )
    
    # 同步信息
    last_sync_at = Column(DateTime, comment="最后同步时间")
    sync_error = Column(Text, comment="同步错误信息")
    
    # 外呼配额（0 表示不限制，由 Worker 与名单状态近似 enforcement）
    max_concurrent_calls = Column(
        Integer,
        default=0,
        comment="账户级最大并发外呼路数，0 不限制",
    )
    daily_outbound_limit = Column(
        Integer,
        default=0,
        comment="每日外呼尝试上限，0 不限制",
    )

    # 额外数据
    extra_data = Column(JSON, comment="额外数据")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    account = relationship("Account", backref="voice_accounts")
    sales_user = relationship("AdminUser", foreign_keys=[sales_id])
    template = relationship("AccountTemplate")
    # 主叫池归属本语音子账户（与 default_caller 指向同一表的不同外键区分）
    caller_ids = relationship(
        "VoiceCallerId",
        foreign_keys="VoiceCallerId.voice_account_id",
        back_populates="voice_account",
    )
    default_caller = relationship(
        "VoiceCallerId",
        foreign_keys=[default_caller_id_id],
        post_update=True,
    )
    
    def __repr__(self):
        return f"<VoiceAccount(id={self.id}, okcc={self.okcc_account}, status={self.status})>"


class VoiceRechargeLog(Base):
    """语音充值记录"""
    __tablename__ = "voice_recharge_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    voice_account_id = Column(
        Integer, 
        ForeignKey("voice_accounts.id"), 
        nullable=False,
        comment="语音账户ID"
    )
    
    # 充值信息
    amount = Column(DECIMAL(10, 2), nullable=False, comment="充值金额")
    transaction_id = Column(String(100), comment="OKCC交易ID")
    
    # 状态
    status = Column(
        Enum("pending", "success", "failed", name="voice_recharge_status_enum"),
        default="pending",
        comment="状态"
    )
    
    # 备注
    remark = Column(Text, comment="备注")
    error_message = Column(Text, comment="错误信息")
    
    # 操作人
    operator_id = Column(INTEGER(unsigned=True), ForeignKey("admin_users.id"), comment="操作人ID")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, comment="完成时间")
    
    # 关系
    voice_account = relationship("VoiceAccount", backref="recharge_logs")
    operator = relationship("AdminUser")
