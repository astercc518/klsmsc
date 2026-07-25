from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.sms.sms_daily_stat import SMSDailyStatsCoverage
from app.services.sms_daily_stats import has_complete_daily_stats


@pytest.fixture
async def daily_stats_session():
    """只创建本功能的覆盖表，避开项目中 MySQL-only MEDIUMTEXT 模型。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SMSDailyStatsCoverage.__table__.create)
    try:
        async with Session() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_daily_stats_requires_every_day_covered(daily_stats_session):
    daily_stats_session.add_all([
        SMSDailyStatsCoverage(stat_date=date(2026, 6, 1), refreshed_at=datetime(2026, 6, 2)),
        SMSDailyStatsCoverage(stat_date=date(2026, 6, 3), refreshed_at=datetime(2026, 6, 4)),
    ])
    await daily_stats_session.commit()

    assert not await has_complete_daily_stats(
        daily_stats_session, date(2026, 6, 1), date(2026, 6, 3), now=datetime(2026, 7, 21)
    )


@pytest.mark.asyncio
async def test_daily_stats_accepts_complete_past_range(daily_stats_session):
    daily_stats_session.add_all([
        SMSDailyStatsCoverage(stat_date=date(2026, 6, day), refreshed_at=datetime(2026, 6, 30))
        for day in range(1, 4)
    ])
    await daily_stats_session.commit()

    assert await has_complete_daily_stats(
        daily_stats_session, date(2026, 6, 1), date(2026, 6, 3), now=datetime(2026, 7, 21)
    )


@pytest.mark.asyncio
async def test_daily_stats_rejects_stale_current_day(daily_stats_session):
    now = datetime(2026, 7, 21, 12, 0)
    row = SMSDailyStatsCoverage(
        stat_date=now.date(), refreshed_at=now - timedelta(hours=1)
    )
    daily_stats_session.add(row)
    await daily_stats_session.commit()

    assert not await has_complete_daily_stats(
        daily_stats_session, now.date(), now.date(), now=now
    )

    row.refreshed_at = now - timedelta(minutes=5)
    await daily_stats_session.commit()
    assert await has_complete_daily_stats(
        daily_stats_session, now.date(), now.date(), now=now
    )
