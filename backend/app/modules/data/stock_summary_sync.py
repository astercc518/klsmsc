"""
公海库存汇总表 data_stock_summaries 同步工具。
提供增量更新与全量对账功能。
"""
from __future__ import annotations
from sqlalchemy import select, func, update, insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.data.models import DataStockSummary
from typing import Optional


def norm_dim(v: Optional[str]) -> str:
    return str(v or "").strip()


async def update_stock_summary_delta(
    db: AsyncSession,
    *,
    country_code: str,
    carrier: str,
    source: str = "",
    purpose: str = "",
    freshness: str = "history",
    status: str = "active",
    batch_id: Optional[str] = None,
    delta: int,
) -> None:
    """
    更新单维度桶的库存增量。
    """
    cc = norm_dim(country_code)
    car = norm_dim(carrier) or "Unknown"
    src = norm_dim(source)
    pur = norm_dim(purpose)
    fre = norm_dim(freshness) or "history"
    sta = norm_dim(status) or "active"
    bid = norm_dim(batch_id) if batch_id else None

    # 先查是否存在
    q = select(DataStockSummary).where(
        DataStockSummary.country_code == cc,
        DataStockSummary.carrier == car,
        DataStockSummary.source == src,
        DataStockSummary.purpose == pur,
        DataStockSummary.freshness == fre,
        DataStockSummary.status == sta,
        DataStockSummary.batch_id == bid,
    )
    row = (await db.execute(q)).scalar_one_or_none()

    if row:
        row.total_count = max(0, row.total_count + delta)
    elif delta > 0:
        db.add(
            DataStockSummary(
                country_code=cc,
                carrier=car,
                source=src,
                purpose=pur,
                freshness=fre,
                status=sta,
                batch_id=bid,
                total_count=delta,
            )
        )


async def update_stock_summary_from_batch(db: AsyncSession, batch_id: str, delta: int = 1):
    """
    根据批次 ID 增量更新汇总表。用于导入完成后的统计。
    delta = 1 表示增加（导入），delta = -1 表示扣减（售出/删除）。
    """
    from app.modules.data.models import DataNumber
    from app.api.v1.data.helpers import compute_freshness
    
    # 按维度统计该批次下的分布
    q = select(
        DataNumber.country_code,
        DataNumber.carrier,
        DataNumber.source,
        DataNumber.purpose,
        DataNumber.data_date,
        DataNumber.status,
        func.count().label("cnt")
    ).where(
        DataNumber.batch_id == batch_id,
        DataNumber.account_id.is_(None)
    ).group_by(
        DataNumber.country_code,
        DataNumber.carrier,
        DataNumber.source,
        DataNumber.purpose,
        DataNumber.data_date,
        DataNumber.status
    )
    
    result = await db.execute(q)
    for row in result.fetchall():
        cc, car, src, pur, ddate, sta, count = row
        fre = compute_freshness(ddate)
        await update_stock_summary_delta(
            db,
            country_code=cc,
            carrier=car,
            source=src,
            purpose=pur,
            freshness=fre,
            status=sta,
            batch_id=batch_id,
            delta=count * delta
        )

async def refresh_public_stock_summary(db: AsyncSession):
    """
    全量刷新公海库存汇总表。
    耗时较长（千万级 GROUP BY），建议仅在凌晨任务中使用。
    """
    # 物理清空
    from sqlalchemy import delete
    await db.execute(delete(DataStockSummary))
    
    # 聚合插入
    insert_sql = """
    INSERT INTO data_stock_summaries (country_code, carrier, source, purpose, freshness, status, batch_id, total_count)
    SELECT 
        COALESCE(country_code, '??'), 
        COALESCE(carrier, 'Unknown'), 
        COALESCE(source, ''), 
        COALESCE(purpose, ''),
        (CASE 
            WHEN data_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) THEN '30d'
            WHEN data_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) THEN '90d'
            ELSE 'history' 
        END) as freshness,
        COALESCE(status, 'active'), 
        batch_id,
        COUNT(*)
FROM data_numbers
WHERE account_id IS NULL
GROUP BY 1, 2, 3, 4, 5, 6, 7;
    """
    from sqlalchemy import text
    await db.execute(text(insert_sql))
    await db.commit()
