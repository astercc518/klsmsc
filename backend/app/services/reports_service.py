"""
业务报表服务
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, and_, or_, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.modules.sms.supplier import Supplier, SupplierChannel
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.modules.data.models import DataOrder
from app.utils.logger import get_logger

logger = get_logger(__name__)

class ReportsService:
    @staticmethod
    async def get_business_report(
        db: AsyncSession,
        dimension: str,
        business_type: str = "all",
        time_range: str = "today",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取多维度业务报表
        """
        # 1. 确定时间范围
        start_dt, end_dt = ReportsService._get_time_range_dates(time_range, start_date, end_date)
        
        results = []
        
        # 2. 短信业务统计
        if business_type in ["all", "sms"]:
            sms_stats = await ReportsService._get_sms_stats(db, dimension, start_dt, end_dt)
            results.extend(sms_stats)
            
        # 3. 数据业务统计
        if business_type in ["all", "data"]:
            data_stats = await ReportsService._get_data_stats(db, dimension, start_dt, end_dt)
            # 合并结果（如果维度相同，可以合并行，这里简单起见，按业务类型分开返回或合作为新格式）
            results.extend(data_stats)
            
        return results

    @staticmethod
    def _get_time_range_dates(time_range: str, start_date: Optional[str], end_date: Optional[str]):
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if time_range == "today":
            return today, now
        elif time_range == "this_week":
            # 本周一
            monday = today - timedelta(days=today.weekday())
            return monday, now
        elif time_range == "this_month":
            first_day = today.replace(day=1)
            return first_day, now
        elif time_range == "last_month":
            last_month_end = today.replace(day=1) - timedelta(seconds=1)
            last_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            return last_month_start, last_month_end + timedelta(seconds=1)
        elif time_range == "custom" and start_date and end_date:
            s = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            e = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            return s, e
        
        return today, now

    @staticmethod
    async def _get_sms_stats(db: AsyncSession, dimension: str, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        """短信业务聚合查询"""
        columns = [
            func.count(SMSLog.id).label("total_count"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered_count"),
            func.sum(SMSLog.selling_price).label("revenue"),
            func.sum(SMSLog.cost_price).label("cost"),
            func.sum(SMSLog.profit).label("profit")
        ]
        
        group_by = []
        select_extra = []
        
        if dimension == "customer":
            group_by = [Account.id, Account.account_name]
            select_extra = [Account.id.label("dim_id"), Account.account_name.label("dim_name")]
            query = select(*select_extra, *columns).join(Account, SMSLog.account_id == Account.id)
        elif dimension == "employee":
            group_by = [AdminUser.id, AdminUser.username]
            select_extra = [AdminUser.id.label("dim_id"), AdminUser.username.label("dim_name")]
            query = select(*select_extra, *columns).join(Account, SMSLog.account_id == Account.id).join(AdminUser, Account.sales_id == AdminUser.id)
        elif dimension == "channel":
            group_by = [Channel.id, Channel.channel_name]
            select_extra = [Channel.id.label("dim_id"), Channel.channel_name.label("dim_name")]
            query = select(*select_extra, *columns).join(Channel, SMSLog.channel_id == Channel.id)
        elif dimension == "supplier":
            group_by = [Supplier.id, Supplier.supplier_name]
            select_extra = [Supplier.id.label("dim_id"), Supplier.supplier_name.label("dim_name")]
            query = select(*select_extra, *columns)\
                .join(Channel, SMSLog.channel_id == Channel.id)\
                .join(SupplierChannel, Channel.id == SupplierChannel.channel_id)\
                .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
        elif dimension == "country":
            group_by = [SMSLog.country_code]
            select_extra = [SMSLog.country_code.label("dim_id"), SMSLog.country_code.label("dim_name")]
            query = select(*select_extra, *columns)
        else:
            return []

        query = query.where(and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt))\
                     .group_by(*group_by)
        
        result = await db.execute(query)
        rows = result.all()
        
        return [
            {
                "business_type": "sms",
                "dim_id": row.dim_id,
                "dim_name": row.dim_name,
                "count": row.total_count or 0,
                "delivered": row.delivered_count or 0,
                "revenue": float(row.revenue or 0),
                "cost": float(row.cost or 0),
                "profit": float(row.profit or 0),
                "success_rate": round(row.delivered_count / row.total_count * 100, 2) if row.total_count and row.total_count > 0 else 0
            }
            for row in rows
        ]

    @staticmethod
    async def _get_data_stats(db: AsyncSession, dimension: str, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        """数据业务聚合查询"""
        # 数据业务主要在 DataOrder 中体现
        from sqlalchemy import Numeric
        columns = [
            func.sum(DataOrder.quantity).label("total_count"),
            func.sum(func.cast(DataOrder.total_price, Numeric(14, 4))).label("revenue")
        ]
        
        group_by = []
        select_extra = []
        
        if dimension == "customer":
            group_by = [Account.id, Account.account_name]
            select_extra = [Account.id.label("dim_id"), Account.account_name.label("dim_name")]
            query = select(*select_extra, *columns).join(Account, DataOrder.account_id == Account.id)
        elif dimension == "employee":
            group_by = [AdminUser.id, AdminUser.username]
            select_extra = [AdminUser.id.label("dim_id"), AdminUser.username.label("dim_name")]
            query = select(*select_extra, *columns).join(Account, DataOrder.account_id == Account.id).join(AdminUser, Account.sales_id == AdminUser.id)
        elif dimension == "country":
            # 改进：处理 JSON 中的国家代码。MySQL/MariaDB 使用 JSON_EXTRACT
            # 优先从 JSON 提取，如果不存在则为 'Unknown'
            country_expr = func.coalesce(
                func.nullif(func.json_unquote(func.json_extract(DataOrder.filter_criteria, '$.country')), ''),
                'Unknown'
            )
            group_by = [country_expr]
            select_extra = [country_expr.label("dim_id"), country_expr.label("dim_name")]
            query = select(*select_extra, *columns)
        else:
            # 数据业务不支持 supplier/channel 维度
            return []

        query = query.where(and_(DataOrder.created_at >= start_dt, DataOrder.created_at < end_dt, DataOrder.status == 'completed'))\
                     .group_by(*group_by)
        
        result = await db.execute(query)
        rows = result.all()
        
        # 数据业务成本估算：通常数据业务毛利较高，这里假设成本为收入的 40% (作为占位，实际应从采购成本表获取)
        COST_RATIO = 0.4
        
        return [
            {
                "business_type": "data",
                "dim_id": row.dim_id,
                "dim_name": str(row.dim_name) if row.dim_name else "Unknown",
                "count": int(row.total_count or 0),
                "delivered": int(row.total_count or 0),
                "revenue": float(row.revenue or 0),
                "cost": float(row.revenue or 0) * COST_RATIO,
                "profit": float(row.revenue or 0) * (1 - COST_RATIO),
                "success_rate": 100.0
            }
            for row in rows
        ]
