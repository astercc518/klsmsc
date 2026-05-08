"""
短链追踪记录模型

每条 sms_log 发送前若消息含 {{TRACK_URL=...}} 占位符，
则生成一条 short_link_logs 记录，token 全局唯一。
"""
from sqlalchemy import BigInteger, Column, Index, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from app.database import Base


class ShortLinkLog(Base):
    __tablename__ = "short_link_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    token = Column(String(8), nullable=False, unique=True, comment="Base62短链token")
    sms_log_id = Column(BigInteger, nullable=False, comment="关联sms_logs.id")
    domain_id = Column(BigInteger, nullable=True, comment="关联short_link_domains.id")
    original_url = Column(Text, nullable=False, comment="重定向目标URL")
    click_count = Column(Integer, nullable=False, default=0, comment="点击次数")
    last_click_at = Column(TIMESTAMP, nullable=True, comment="最近点击时间")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_short_link_sms_log_id", "sms_log_id"),
        Index("idx_short_link_domain_created", "domain_id", "created_at"),
    )
