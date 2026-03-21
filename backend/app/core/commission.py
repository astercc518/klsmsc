"""
销售佣金计算服务

根据 SMSLog 中客户消费（selling_price）及 Account.sales_id 归属，
按销售 commission_rate 计算佣金。
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settlement import SalesCommissionSettlement, SalesCommissionDetail
from app.modules.sms.sms_log import SMSLog
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser


def generate_commission_settlement_no() -> str:
    """生成销售佣金结算单号"""
    now = datetime.now()
    return f"SC{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"


async def calculate_sales_commission(
    db: AsyncSession,
    period_start: datetime,
    period_end: datetime,
    sales_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    计算指定周期内各销售的佣金。

    逻辑：SMSLog 按 account_id 关联 Account，取 sales_id；
    仅统计 status='delivered' 的短信（成功送达才计佣金）；
    佣金 = 客户消费(selling_price) × commission_rate / 100

    Args:
        db: 数据库会话
        period_start: 周期开始
        period_end: 周期结束
        sales_id: 可选，仅计算指定销售

    Returns:
        列表，每项含 sales_id, sales_name, total_revenue, commission_rate, commission_amount, details(按客户)
    """
    # 1. 获取有 commission_rate > 0 的销售
    sales_query = select(AdminUser).where(
        AdminUser.role == 'sales',
        AdminUser.status == 'active',
        AdminUser.commission_rate > 0,
    )
    if sales_id:
        sales_query = sales_query.where(AdminUser.id == sales_id)
    sales_result = await db.execute(sales_query)
    sales_list = sales_result.scalars().all()

    if not sales_list:
        return []

    results = []
    for sales in sales_list:
        # 2. 该销售名下的客户
        accounts_query = select(Account.id).where(
            Account.sales_id == sales.id,
            Account.is_deleted == False,
        )
        accounts_result = await db.execute(accounts_query)
        account_ids = [a[0] for a in accounts_result.all()]

        if not account_ids:
            continue

        # 3. 统计该周期内这些客户的消费（仅 delivered）
        stats_query = select(
            SMSLog.account_id,
            func.count(SMSLog.id).label('sms_count'),
            func.coalesce(func.sum(SMSLog.selling_price), 0).label('total_revenue'),
        ).where(
            SMSLog.account_id.in_(account_ids),
            SMSLog.status == 'delivered',
            SMSLog.submit_time >= period_start,
            SMSLog.submit_time < period_end,
        ).group_by(SMSLog.account_id)

        stats_result = await db.execute(stats_query)
        stats_rows = stats_result.all()

        total_revenue = sum(float(r.total_revenue or 0) for r in stats_rows)
        total_sms = sum(r.sms_count or 0 for r in stats_rows)
        commission_rate = float(sales.commission_rate or 0)
        commission_amount = total_revenue * (commission_rate / 100)

        details = []
        for row in stats_rows:
            rev = float(row.total_revenue or 0)
            comm = rev * (commission_rate / 100)
            details.append({
                'account_id': row.account_id,
                'sms_count': row.sms_count or 0,
                'total_revenue': rev,
                'commission_amount': comm,
            })

        results.append({
            'sales_id': sales.id,
            'sales_name': sales.real_name or sales.username,
            'commission_rate': commission_rate,
            'total_sms_count': total_sms,
            'total_revenue': total_revenue,
            'commission_amount': commission_amount,
            'details': details,
        })

    return results


async def create_commission_settlement(
    db: AsyncSession,
    period_start: datetime,
    period_end: datetime,
    sales_id: int,
) -> Optional[SalesCommissionSettlement]:
    """
    为指定销售创建佣金结算单（若该周期已有则返回 None）

    Returns:
        新建的结算单，或 None（已存在或无需结算）
    """
    # 检查是否已存在
    exist = await db.execute(
        select(SalesCommissionSettlement).where(
            SalesCommissionSettlement.sales_id == sales_id,
            SalesCommissionSettlement.period_start == period_start,
            SalesCommissionSettlement.period_end == period_end,
        )
    )
    if exist.scalar_one_or_none():
        return None

    calc_data = await calculate_sales_commission(db, period_start, period_end, sales_id)
    if not calc_data:
        return None

    data = calc_data[0]
    if data['commission_amount'] <= 0:
        return None

    settlement = SalesCommissionSettlement(
        settlement_no=generate_commission_settlement_no(),
        sales_id=sales_id,
        period_start=period_start,
        period_end=period_end,
        total_sms_count=data['total_sms_count'],
        total_revenue=Decimal(str(data['total_revenue'])),
        commission_rate=Decimal(str(data['commission_rate'])),
        commission_amount=Decimal(str(data['commission_amount'])),
        currency='USD',
        status='draft',
    )
    db.add(settlement)
    await db.flush()

    for d in data['details']:
        detail = SalesCommissionDetail(
            settlement_id=settlement.id,
            account_id=d['account_id'],
            total_sms_count=d['sms_count'],
            total_revenue=Decimal(str(d['total_revenue'])),
            commission_rate=Decimal(str(data['commission_rate'])),
            commission_amount=Decimal(str(d['commission_amount'])),
        )
        db.add(detail)

    await db.commit()
    await db.refresh(settlement)
    return settlement


async def update_monthly_commission_for_sales(
    db: AsyncSession,
    sales_id: int,
    period_start: datetime,
    period_end: datetime,
) -> float:
    """
    计算指定销售在指定周期内的佣金，并更新 AdminUser.monthly_commission。
    注意：monthly_commission 通常表示「本月累计」，此处用于定时任务刷新。
    若业务上「每月15日结算」后清零，可在此或单独任务中处理。

    Returns:
        佣金金额
    """
    calc_data = await calculate_sales_commission(db, period_start, period_end, sales_id)
    if not calc_data:
        return 0.0

    amount = calc_data[0]['commission_amount']
    sales = await db.get(AdminUser, sales_id)
    if sales:
        sales.monthly_commission = Decimal(str(amount))
        await db.commit()
    return amount
