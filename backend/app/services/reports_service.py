"""
业务报表服务
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.modules.sms.supplier import Supplier, SupplierChannel
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.modules.data.models import DataOrder
from app.utils.cache import get_cache_manager
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
        """获取多维度业务报表（带 Redis 缓存）"""
        start_dt, end_dt = ReportsService._get_time_range_dates(time_range, start_date, end_date)

        # 缓存：完全在过去（end_dt <= 今天 00:00）按 24h，否则 60s
        today_zero = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ttl = 24 * 3600 if end_dt <= today_zero else 60
        cache_key = (
            f"report:business:{dimension}:{business_type}:"
            f"{start_dt.strftime('%Y%m%d%H%M')}:{end_dt.strftime('%Y%m%d%H%M')}"
        )
        cm = await get_cache_manager()
        cached = await cm.get(cache_key)
        if cached is not None:
            return cached

        results: List[Dict[str, Any]] = []
        if business_type in ["all", "sms"]:
            results.extend(await ReportsService._get_sms_stats(db, dimension, start_dt, end_dt))
        if business_type in ["all", "data"]:
            results.extend(await ReportsService._get_data_stats(db, dimension, start_dt, end_dt))

        await cm.set(cache_key, results, ttl=ttl)
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
        """
        短信业务聚合查询。
        策略：先按外键(account_id/channel_id/country_code)在 sms_logs 上聚合（覆盖索引扫描），
        再在 Python 里二次聚合到目标维度并补名称，避免在 3M 行级别上做 JOIN。
        """
        agg_count = func.count(SMSLog.id).label("total_count")
        agg_delivered = func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered_count")
        agg_revenue = func.sum(SMSLog.selling_price).label("revenue")
        agg_cost = func.sum(SMSLog.cost_price).label("cost")
        agg_profit = func.sum(SMSLog.profit).label("profit")

        time_filter = and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt)

        # === 第一步：按 sms_logs 自带列聚合 ===
        if dimension == "country":
            # 国家维度直接出结果
            query = (
                select(
                    SMSLog.country_code.label("dim_id"),
                    agg_count, agg_delivered, agg_revenue, agg_cost, agg_profit,
                )
                .where(time_filter)
                .group_by(SMSLog.country_code)
            )
            rows = (await db.execute(query)).all()
            return [ReportsService._fmt_sms_row(r.dim_id, r.dim_id or "Unknown", r) for r in rows]

        if dimension in ("customer", "employee"):
            base_col = SMSLog.account_id
        elif dimension in ("channel", "supplier"):
            base_col = SMSLog.channel_id
        else:
            return []

        query = (
            select(base_col.label("fk"), agg_count, agg_delivered, agg_revenue, agg_cost, agg_profit)
            .where(time_filter)
            .group_by(base_col)
        )
        rows = (await db.execute(query)).all()
        if not rows:
            return []

        fk_ids = [r.fk for r in rows if r.fk is not None]

        # === 第二步：根据维度补名称 / 二次聚合 ===
        if dimension == "customer":
            name_map = await ReportsService._fetch_account_names(db, fk_ids)
            return [
                ReportsService._fmt_sms_row(r.fk, name_map.get(r.fk, f"Account#{r.fk}"), r)
                for r in rows if r.fk is not None
            ]

        if dimension == "channel":
            name_map = await ReportsService._fetch_channel_names(db, fk_ids)
            return [
                ReportsService._fmt_sms_row(r.fk, name_map.get(r.fk, f"Channel#{r.fk}"), r)
                for r in rows if r.fk is not None
            ]

        if dimension == "employee":
            # account_id -> sales_id 映射
            sales_map = await ReportsService._fetch_account_sales_map(db, fk_ids)
            # 在 Python 里按 sales_id 重新聚合
            buckets: Dict[int, Dict[str, float]] = {}
            for r in rows:
                sid = sales_map.get(r.fk)
                if sid is None:
                    continue
                b = buckets.setdefault(sid, {"count": 0, "delivered": 0, "revenue": 0.0, "cost": 0.0, "profit": 0.0})
                b["count"] += int(r.total_count or 0)
                b["delivered"] += int(r.delivered_count or 0)
                b["revenue"] += float(r.revenue or 0)
                b["cost"] += float(r.cost or 0)
                b["profit"] += float(r.profit or 0)
            admin_map = await ReportsService._fetch_admin_names(db, list(buckets.keys()))
            return [
                {
                    "business_type": "sms",
                    "dim_id": sid,
                    "dim_name": admin_map.get(sid, f"Admin#{sid}"),
                    "count": b["count"],
                    "delivered": b["delivered"],
                    "revenue": b["revenue"],
                    "cost": b["cost"],
                    "profit": b["profit"],
                    "success_rate": round(b["delivered"] / b["count"] * 100, 2) if b["count"] > 0 else 0,
                }
                for sid, b in buckets.items()
            ]

        if dimension == "supplier":
            # channel_id -> supplier_id 映射
            sup_map = await ReportsService._fetch_channel_supplier_map(db, fk_ids)
            buckets: Dict[int, Dict[str, float]] = {}
            for r in rows:
                sup_id = sup_map.get(r.fk)
                if sup_id is None:
                    continue
                b = buckets.setdefault(sup_id, {"count": 0, "delivered": 0, "revenue": 0.0, "cost": 0.0, "profit": 0.0})
                b["count"] += int(r.total_count or 0)
                b["delivered"] += int(r.delivered_count or 0)
                b["revenue"] += float(r.revenue or 0)
                b["cost"] += float(r.cost or 0)
                b["profit"] += float(r.profit or 0)
            sup_name_map = await ReportsService._fetch_supplier_names(db, list(buckets.keys()))
            return [
                {
                    "business_type": "sms",
                    "dim_id": sup_id,
                    "dim_name": sup_name_map.get(sup_id, f"Supplier#{sup_id}"),
                    "count": b["count"],
                    "delivered": b["delivered"],
                    "revenue": b["revenue"],
                    "cost": b["cost"],
                    "profit": b["profit"],
                    "success_rate": round(b["delivered"] / b["count"] * 100, 2) if b["count"] > 0 else 0,
                }
                for sup_id, b in buckets.items()
            ]

        return []

    @staticmethod
    def _fmt_sms_row(dim_id: Any, dim_name: Any, row: Any) -> Dict[str, Any]:
        cnt = int(row.total_count or 0)
        delivered = int(row.delivered_count or 0)
        return {
            "business_type": "sms",
            "dim_id": dim_id,
            "dim_name": dim_name,
            "count": cnt,
            "delivered": delivered,
            "revenue": float(row.revenue or 0),
            "cost": float(row.cost or 0),
            "profit": float(row.profit or 0),
            "success_rate": round(delivered / cnt * 100, 2) if cnt > 0 else 0,
        }

    @staticmethod
    async def _fetch_account_names(db: AsyncSession, ids: List[int]) -> Dict[int, str]:
        if not ids:
            return {}
        rows = (await db.execute(select(Account.id, Account.account_name).where(Account.id.in_(ids)))).all()
        return {r.id: r.account_name for r in rows}

    @staticmethod
    async def _fetch_account_sales_map(db: AsyncSession, ids: List[int]) -> Dict[int, int]:
        if not ids:
            return {}
        rows = (await db.execute(
            select(Account.id, Account.sales_id).where(Account.id.in_(ids), Account.sales_id.isnot(None))
        )).all()
        return {r.id: r.sales_id for r in rows}

    @staticmethod
    async def _fetch_admin_names(db: AsyncSession, ids: List[int]) -> Dict[int, str]:
        if not ids:
            return {}
        rows = (await db.execute(
            select(AdminUser.id, AdminUser.username, AdminUser.real_name).where(AdminUser.id.in_(ids))
        )).all()
        return {r.id: (r.real_name or r.username) for r in rows}

    @staticmethod
    async def _fetch_channel_names(db: AsyncSession, ids: List[int]) -> Dict[int, str]:
        if not ids:
            return {}
        rows = (await db.execute(select(Channel.id, Channel.channel_name).where(Channel.id.in_(ids)))).all()
        return {r.id: r.channel_name for r in rows}

    @staticmethod
    async def _fetch_channel_supplier_map(db: AsyncSession, channel_ids: List[int]) -> Dict[int, int]:
        if not channel_ids:
            return {}
        rows = (await db.execute(
            select(SupplierChannel.channel_id, SupplierChannel.supplier_id)
            .where(SupplierChannel.channel_id.in_(channel_ids))
        )).all()
        return {r.channel_id: r.supplier_id for r in rows}

    @staticmethod
    async def _fetch_supplier_names(db: AsyncSession, ids: List[int]) -> Dict[int, str]:
        if not ids:
            return {}
        rows = (await db.execute(select(Supplier.id, Supplier.supplier_name).where(Supplier.id.in_(ids)))).all()
        return {r.id: r.supplier_name for r in rows}

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
