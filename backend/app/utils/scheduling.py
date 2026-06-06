"""定时发送 eta 时区处理。

前端用 value-format="YYYY-MM-DD HH:mm:ss" 提交「北京 wall-clock」字符串，
Pydantic 解析成 naive datetime。直接把 naive datetime 传给 Celery
apply_async(eta=...) 会被序列化时按 UTC 处理（Celery 的 maybe_make_aware
对 naive 一律当 UTC，即使 enable_utc=False / timezone=Asia/Shanghai），
导致定时任务被推迟 8 小时（线上事故：批次 712 选 17:30 实际排到次日 01:30）。

修复：把 naive 的北京 wall-clock 显式 localize 到应用配置的时区，得到带
偏移的 aware datetime，Celery 即按正确的绝对时间触发。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.workers.celery_app import celery_app


def localize_eta(naive_dt: datetime) -> datetime:
    """把前端提交的 naive 本地时间标成应用时区的 aware datetime。

    已带 tzinfo 的直接返回（不重复转换）。
    """
    if naive_dt is None or naive_dt.tzinfo is not None:
        return naive_dt
    tz_name = celery_app.conf.timezone or "Asia/Shanghai"
    return naive_dt.replace(tzinfo=ZoneInfo(tz_name))
