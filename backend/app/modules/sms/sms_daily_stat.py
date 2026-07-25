"""按日预聚合的短信发送统计模型。

明细表 ``sms_logs`` 按月可达千万行。管理后台的常用发送统计按日期、账户、通道和
状态压缩后查询，避免每次打开页面都扫描整月明细；国家维度保留明细查询与缓存。
"""
from sqlalchemy import BigInteger, Column, Date, DateTime, DECIMAL, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class SMSDailyStat(Base):
    """短信每日聚合行；channel_id=0 表示 NULL，country_code 预留且紧凑聚合使用空串。"""

    __tablename__ = "sms_daily_stats"
    __table_args__ = (
        Index("idx_sms_daily_stats_channel", "stat_date", "channel_id"),
        Index("idx_sms_daily_stats_country", "stat_date", "country_code"),
    )

    stat_date = Column(Date, primary_key=True, nullable=False)
    account_id = Column(Integer, primary_key=True, nullable=False)
    channel_id = Column(Integer, primary_key=True, nullable=False, default=0)
    country_code = Column(String(3), primary_key=True, nullable=False, default="")
    status = Column(String(16), primary_key=True, nullable=False)
    submit_total = Column(BigInteger, nullable=False, default=0)
    priced_count = Column(BigInteger, nullable=False, default=0)
    total_cost = Column(DECIMAL(24, 6), nullable=False, default=0)
    total_revenue = Column(DECIMAL(24, 6), nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class SMSDailyStatsCoverage(Base):
    """记录哪些自然日已经完整生成聚合，避免把“尚未回填”误判成零数据。"""

    __tablename__ = "sms_daily_stats_coverage"

    stat_date = Column(Date, primary_key=True, nullable=False)
    refreshed_at = Column(DateTime, nullable=False, server_default=func.now())
