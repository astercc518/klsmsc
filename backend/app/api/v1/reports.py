"""
报表统计API路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.sql import text
from sqlalchemy import case
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.modules.common.account import Account
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.core.auth import api_key_header, AuthService
from app.utils.logger import get_logger
from app.services.reports_service import ReportsService

logger = get_logger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])


# Schemas
class StatisticsResponse(BaseModel):
    total_sent: int
    total_delivered: int
    total_failed: int
    total_pending: int = 0  # pending + queued
    success_rate: float
    total_cost: float
    total_revenue: float = 0.0  # 销售收入（selling_price 汇总）
    total_profit: float = 0.0   # 毛利（revenue - cost）
    currency: str


class SuccessRateResponse(BaseModel):
    overall_rate: float
    by_channel: list
    by_country: list


# 依赖注入
async def get_current_account(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """获取当前认证账户"""
    return await AuthService.verify_api_key(api_key, db)


@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取发送统计
    
    - **start_date**: 开始日期 (可选，默认30天前)
    - **end_date**: 结束日期 (可选，默认今天)
    """
    # 默认时间范围：最近30天
    if not end_date:
        end_date = datetime.now().date().isoformat()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)  # 包含结束日期
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid date format")
    
    # 查询统计
    query = select(
        func.count(SMSLog.id).label("total_sent"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
        func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
        func.sum(case((or_(SMSLog.status == "pending", SMSLog.status == "queued"), 1), else_=0)).label("total_pending"),
        func.sum(SMSLog.cost_price).label("total_cost"),
        func.sum(SMSLog.selling_price).label("total_revenue")
    ).where(
        and_(
            SMSLog.account_id == account.id,
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt
        )
    )
    
    result = await db.execute(query)
    row = result.first()
    
    total_sent = row.total_sent or 0
    total_delivered = row.total_delivered or 0
    total_failed = row.total_failed or 0
    total_pending = row.total_pending or 0
    total_cost = float(row.total_cost or 0)
    total_revenue = float(row.total_revenue or 0)
    total_profit = total_revenue - total_cost
    success_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
    
    logger.info(f"查询统计: 账户={account.id}, 总计={total_sent}, 成功率={success_rate:.2f}%")
    
    return StatisticsResponse(
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_failed=total_failed,
        total_pending=total_pending,
        success_rate=round(success_rate, 2),
        total_cost=round(total_cost, 4),
        total_revenue=round(total_revenue, 4),
        total_profit=round(total_profit, 4),
        currency=account.currency or "USD"
    )


@router.get("/success-rate", response_model=SuccessRateResponse)
async def get_success_rate(
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取成功率分析
    
    - 总体成功率
    - 按通道统计
    - 按国家统计
    """
    # 默认时间范围：最近30天
    if not end_date:
        end_date = datetime.now().date().isoformat()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid date format")
    
    # 总体成功率
    total_query = select(
        func.count(SMSLog.id).label("total"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered")
    ).where(
        and_(
            SMSLog.account_id == account.id,
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt
        )
    )
    
    total_result = await db.execute(total_query)
    total_row = total_result.first()
    total = total_row.total or 0
    delivered = total_row.delivered or 0
    overall_rate = (delivered / total * 100) if total > 0 else 0.0
    
    # 按通道统计
    channel_query = select(
        Channel.id,
        Channel.channel_code,
        Channel.channel_name,
        func.count(SMSLog.id).label("total"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered")
    ).join(
        SMSLog, Channel.id == SMSLog.channel_id
    ).where(
        and_(
            SMSLog.account_id == account.id,
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt
        )
    ).group_by(Channel.id, Channel.channel_code, Channel.channel_name)
    
    channel_result = await db.execute(channel_query)
    by_channel = []
    for row in channel_result:
        total_count = row.total or 0
        delivered_count = row.delivered or 0
        rate = (delivered_count / total_count * 100) if total_count > 0 else 0.0
        
        by_channel.append({
            "channel_id": row.id,
            "channel_code": row.channel_code,
            "channel_name": row.channel_name,
            "total": total_count,
            "delivered": delivered_count,
            "success_rate": round(rate, 2)
        })
    
    # 按国家统计（Top 10）
    country_query = select(
        SMSLog.country_code,
        func.count(SMSLog.id).label("total"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered")
    ).where(
        and_(
            SMSLog.account_id == account.id,
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt,
            SMSLog.country_code.isnot(None)
        )
    ).group_by(SMSLog.country_code).order_by(func.count(SMSLog.id).desc()).limit(10)
    
    country_result = await db.execute(country_query)
    by_country = []
    for row in country_result:
        total_count = row.total or 0
        delivered_count = row.delivered or 0
        rate = (delivered_count / total_count * 100) if total_count > 0 else 0.0
        
        by_country.append({
            "country_code": row.country_code,
            "total": total_count,
            "delivered": delivered_count,
            "success_rate": round(rate, 2)
        })
    
    logger.info(f"查询成功率: 账户={account.id}, 总体={overall_rate:.2f}%")
    
    return SuccessRateResponse(
        overall_rate=round(overall_rate, 2),
        by_channel=by_channel,
        by_country=by_country
    )


@router.get("/daily-stats")
async def get_daily_stats(
    days: int = Query(7, ge=1, le=90, description="天数（1-90）"),
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取每日统计（用于图表）"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days-1)
    
    # 使用SQL聚合按日期统计（含成本、收入、利润）
    query = text("""
        SELECT 
            DATE(submit_time) as date,
            COUNT(*) as total_sent,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as total_delivered,
            SUM(cost_price) as total_cost,
            SUM(selling_price) as total_revenue
        FROM sms_logs
        WHERE account_id = :account_id
            AND submit_time >= :start_date
            AND submit_time < :end_date
        GROUP BY DATE(submit_time)
        ORDER BY date ASC
    """)
    
    result = await db.execute(
        query,
        {
            "account_id": account.id,
            "start_date": start_date,
            "end_date": end_date + timedelta(days=1)
        }
    )
    
    daily_stats = []
    for row in result:
        total_sent = row.total_sent or 0
        total_delivered = row.total_delivered or 0
        success_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
        
        cost = float(row.total_cost or 0)
        revenue = float(row.total_revenue or 0)
        daily_stats.append({
            "date": row.date.isoformat() if row.date else None,
            "total_sent": total_sent,
            "total_delivered": total_delivered,
            "success_rate": round(success_rate, 2),
            "total_cost": cost,
            "total_revenue": revenue,
            "total_profit": round(revenue - cost, 4)
        })
    
    return {
        "success": True,
        "days": days,
        "statistics": daily_stats
    }

@router.get("/admin/business")
async def get_business_report(
    dimension: str = Query(..., description="聚合维度: customer/employee/supplier/channel/country"),
    business_type: str = Query("all", description="业务类型: all/sms/data"),
    time_range: str = Query("today", description="时间范围: today/this_week/this_month/last_month/custom"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    admin: Account = Depends(AuthService.get_current_admin), # 仅管理员可看全量报表
    db: AsyncSession = Depends(get_db)
):
    """运营中心业务报表"""
    try:
        report_data = await ReportsService.get_business_report(
            db, dimension, business_type, time_range, start_date, end_date
        )
        return {
            "success": True,
            "dimension": dimension,
            "time_range": time_range,
            "data": report_data
        }
    except Exception as e:
        logger.error(f"获取业务报表失败: {str(e)}", exc_info=e)
        return {"success": False, "message": str(e)}
