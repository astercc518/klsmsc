"""短信每日预聚合的覆盖判断与刷新逻辑。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sms.sms_daily_stat import SMSDailyStatsCoverage


CURRENT_DAY_MAX_AGE = timedelta(minutes=30)


async def has_complete_daily_stats(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    *,
    now: datetime | None = None,
) -> bool:
    """区间为闭区间；覆盖完整且今天的数据足够新时才允许走聚合表。"""
    if end_date < start_date:
        return False

    expected_days = (end_date - start_date).days + 1
    row = (
        await db.execute(
            select(
                func.count(SMSDailyStatsCoverage.stat_date).label("covered"),
            ).where(
                SMSDailyStatsCoverage.stat_date >= start_date,
                SMSDailyStatsCoverage.stat_date <= end_date,
            )
        )
    ).first()
    if int(row.covered or 0) != expected_days:
        return False

    check_now = now or datetime.now()
    if start_date <= check_now.date() <= end_date:
        refreshed_at = (
            await db.execute(
                select(SMSDailyStatsCoverage.refreshed_at).where(
                    SMSDailyStatsCoverage.stat_date == check_now.date()
                )
            )
        ).scalar_one_or_none()
        if refreshed_at is None or refreshed_at < check_now - CURRENT_DAY_MAX_AGE:
            return False
    return True


async def refresh_daily_stats(db: AsyncSession, start_date: date, end_date: date) -> int:
    """原子重建闭区间内的日聚合，并返回写入的聚合行数。

    DELETE 与 INSERT 位于同一事务；InnoDB 读者在提交前仍看到旧版本，不会遇到空窗。
    """
    if end_date < start_date:
        return 0

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

    try:
        await db.execute(
            text(
                "DELETE FROM sms_daily_stats "
                "WHERE stat_date >= :start_date AND stat_date <= :end_date"
            ),
            {"start_date": start_date, "end_date": end_date},
        )
        result = await db.execute(
            text(
                """
                INSERT INTO sms_daily_stats (
                    stat_date, account_id, channel_id, country_code, status,
                    submit_total, priced_count, total_cost, total_revenue, updated_at
                )
                SELECT
                    DATE(submit_time),
                    account_id,
                    COALESCE(channel_id, 0),
                    '',
                    CAST(status AS CHAR),
                    COUNT(*),
                    COUNT(selling_price),
                    COALESCE(SUM(cost_price), 0),
                    COALESCE(SUM(selling_price), 0),
                    NOW()
                FROM sms_logs FORCE INDEX (idx_sms_report_cov2)
                WHERE submit_time >= :start_dt AND submit_time < :end_dt
                GROUP BY
                    DATE(submit_time), account_id, COALESCE(channel_id, 0),
                    status
                """
            ),
            {"start_dt": start_dt, "end_dt": end_dt},
        )

        coverage_rows = []
        day = start_date
        while day <= end_date:
            coverage_rows.append({"stat_date": day})
            day += timedelta(days=1)
        await db.execute(
            text(
                """
                INSERT INTO sms_daily_stats_coverage (stat_date, refreshed_at)
                VALUES (:stat_date, NOW())
                ON DUPLICATE KEY UPDATE refreshed_at = NOW()
                """
            ),
            coverage_rows,
        )
        await db.commit()
        return int(result.rowcount or 0)
    except Exception:
        await db.rollback()
        raise
