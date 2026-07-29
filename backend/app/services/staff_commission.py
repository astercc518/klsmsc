"""员工本月业绩（利润）聚合。

原实现对 sms_logs 当月分区做一次 `SUM(profit) GROUP BY sales_id`，实测 **38s**：
`profit` 是 STORED 生成列且不在 idx_sms_report_cov2 内，聚合它会让覆盖索引失效、
退化成整月逐行回表。38s 还超过 worker 的 30s 读超时（WORKER_DB_READ_TIMEOUT_SEC），
导致 25 分钟一次的预热任务每轮都被 2013 斩断 → 缓存永远由某个倒霉的管理员冷算填上。

这里按天切开：已完结的天读 sms_daily_stats 日聚合（整月几千行），只有「今天」实时
扫明细。口径与原查询一致 —— profit ≡ selling_price - cost_price（生成列定义），
两段都内连 channels 剔除虚拟通道、且同样不区分退款（与原 SUM(profit) 相同）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.account import Account
from app.modules.sms.channel import Channel
from app.modules.sms.sms_daily_stat import SMSDailyStat
from app.modules.sms.sms_log import SMSLog
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _accumulate(dst: Dict[int, float], rows) -> None:
    for sales_id, profit in rows:
        if sales_id is None:
            continue
        dst[sales_id] = dst.get(sales_id, 0.0) + float(profit or 0)


async def _live_profit_since(
    db: AsyncSession, start_dt: datetime, sales_id: Optional[int] = None
):
    """明细聚合。用 SUM(selling_price) - SUM(cost_price) 而非 SUM(profit)，前者能走覆盖索引。"""
    query = (
        select(
            Account.sales_id,
            (func.sum(SMSLog.selling_price) - func.sum(SMSLog.cost_price)).label("total_profit"),
        )
        .select_from(SMSLog)
        .join(Account, SMSLog.account_id == Account.id)
        .join(Channel, SMSLog.channel_id == Channel.id)
        .where(
            SMSLog.submit_time >= start_dt,
            SMSLog.status == "delivered",
            Channel.protocol != "VIRTUAL",
        )
        .group_by(Account.sales_id)
    )
    if sales_id is not None:
        query = query.where(Account.sales_id == sales_id)
    else:
        # 只给全员聚合上 hint：单个销售时优化器可以走 accounts → idx_account_time 嵌套循环，
        # 强制 submit_time 打头的覆盖索引反而更慢。
        try:
            from app.services.reports_service import ReportsService, _COV_INDEX

            if await ReportsService._has_cov_index(db):
                query = query.with_hint(SMSLog, f"FORCE INDEX ({_COV_INDEX})")
        except Exception as exc:  # 索引探测失败不该拖垮聚合，交给优化器自己选
            logger.warning("覆盖索引探测失败，按默认执行计划聚合员工业绩: {}", exc)
    return (await db.execute(query)).all()


async def _rollup_profit(
    db: AsyncSession, first_day: date, last_day: date, sales_id: Optional[int] = None
):
    """日聚合表求和；channel_id=0（无通道）行内连不上 channels，与明细侧 JOIN 语义一致。"""
    query = (
        select(
            Account.sales_id,
            func.sum(SMSDailyStat.total_revenue - SMSDailyStat.total_cost).label("total_profit"),
        )
        .select_from(SMSDailyStat)
        .join(Account, SMSDailyStat.account_id == Account.id)
        .join(Channel, SMSDailyStat.channel_id == Channel.id)
        .where(
            SMSDailyStat.stat_date >= first_day,
            SMSDailyStat.stat_date <= last_day,
            SMSDailyStat.status == "delivered",
            Channel.protocol != "VIRTUAL",
        )
        .group_by(Account.sales_id)
    )
    if sales_id is not None:
        query = query.where(Account.sales_id == sales_id)
    return (await db.execute(query)).all()


async def get_monthly_commission_map(
    db: AsyncSession, *, now: Optional[datetime] = None, sales_id: Optional[int] = None
) -> Dict[int, float]:
    """返回 {sales_id: 本月业绩(利润)}；给了 sales_id 就只算这一个人。

    日聚合覆盖不全时整月回落明细查询。
    """
    now = now or datetime.now()
    today = now.date()
    first_day = today.replace(day=1)
    yesterday = today - timedelta(days=1)
    today_start = datetime.combine(today, datetime.min.time())

    use_rollup = False
    if first_day <= yesterday:
        try:
            from app.services.sms_daily_stats import has_complete_daily_stats

            use_rollup = await has_complete_daily_stats(db, first_day, yesterday)
        except Exception as exc:
            logger.warning("员工业绩日聚合覆盖检查失败，回退明细查询: {}", exc)

    comm_map: Dict[int, float] = {}
    if use_rollup:
        _accumulate(comm_map, await _rollup_profit(db, first_day, yesterday, sales_id))
        _accumulate(comm_map, await _live_profit_since(db, today_start, sales_id))
    else:
        # 月初当天，或日聚合尚未回填完整：直接扫本月明细
        _accumulate(
            comm_map,
            await _live_profit_since(
                db, datetime.combine(first_day, datetime.min.time()), sales_id
            ),
        )
    return comm_map


async def get_sales_monthly_profit(
    db: AsyncSession, sales_id: int, *, now: Optional[datetime] = None
) -> float:
    """单个销售的本月业绩(利润)，口径与员工管理页一致。"""
    comm_map = await get_monthly_commission_map(db, now=now, sales_id=sales_id)
    return comm_map.get(sales_id, 0.0)
