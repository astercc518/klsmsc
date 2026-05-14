"""短链点击明细模型

每次点击写一行；用于区分真人 vs 机器扫描，并展示原始 IP/UA。
聚合计数仍由 short_link_logs.click_count 维护（保留旧逻辑零回退）。
"""
from sqlalchemy import BigInteger, Boolean, Column, Index, String, TIMESTAMP
from sqlalchemy.sql import func

from app.database import Base


class ShortLinkClick(Base):
    __tablename__ = "short_link_clicks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    token = Column(String(8), nullable=False)
    short_link_log_id = Column(BigInteger, nullable=True)
    clicked_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    client_ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    is_bot = Column(Boolean, nullable=False, default=False)
    bot_reason = Column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_short_link_clicks_log_time", "short_link_log_id", "clicked_at"),
        Index("idx_short_link_clicks_token_time", "token", "clicked_at"),
    )
