"""
结算相关 Celery 任务
"""
from datetime import datetime, timedelta
import asyncio

from app.workers.celery_app import celery_app
from app.database import AsyncSessionLocal
from app.core.commission import calculate_sales_commission, create_commission_settlement
from app.modules.common.admin_user import AdminUser
from sqlalchemy import select
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """在 Celery 同步 worker 中执行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name='settlement_commission_monthly_task')
def settlement_commission_monthly_task(year: int = None, month: int = None):
    """
    每月销售佣金结算任务。
    默认结算上月数据；可指定 year/month 结算某月。

    每月 1 日 02:00 执行（在 celery beat 中配置）。
    """
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        # 默认上月
        first_of_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month = first_of_this - timedelta(days=1)
        year = last_month.year
        month = last_month.month

    period_start = datetime(year, month, 1, 0, 0, 0)
    if month == 12:
        period_end = datetime(year + 1, 1, 1, 0, 0, 0) - timedelta(seconds=1)
    else:
        period_end = datetime(year, month + 1, 1, 0, 0, 0) - timedelta(seconds=1)

    async def _do():
        async with AsyncSessionLocal() as db:
            result = await calculate_sales_commission(db, period_start, period_end, sales_id=None)
            created = 0
            for item in result:
                if item['commission_amount'] <= 0:
                    continue
                sett = await create_commission_settlement(
                    db, period_start, period_end, item['sales_id']
                )
                if sett:
                    created += 1
                    logger.info(f"销售佣金结算单已创建: {sett.settlement_no}, 销售={item['sales_name']}, 金额={item['commission_amount']:.2f}")
            return {"created": created, "period": f"{year}-{month:02d}"}

    return _run_async(_do())


@celery_app.task(name='settlement_refresh_monthly_commission_task')
def settlement_refresh_monthly_commission_task():
    """
    刷新各销售的本月累计佣金（用于展示）。
    每日 01:00 执行。
    """
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def _do():
        async with AsyncSessionLocal() as db:
            result = await calculate_sales_commission(db, month_start, now, sales_id=None)
            for item in result:
                sales = await db.get(AdminUser, item['sales_id'])
                if sales:
                    from decimal import Decimal
                    sales.monthly_commission = Decimal(str(round(item['commission_amount'], 2)))
            await db.commit()
            return {"updated": len(result)}

    return _run_async(_do())
