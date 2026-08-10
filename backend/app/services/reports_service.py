"""
业务报表服务
"""
import json as _json
from datetime import datetime, timedelta, date as _date, time as _time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, and_, case, or_, text as _sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.modules.sms.supplier import Supplier, SupplierChannel
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.modules.data.models import DataOrder
from app.utils.cache import get_cache_manager
from app.utils.logger import get_logger
from app.services.sms_finance import net_cost, net_revenue, net_profit
from app.modules.common.balance_log import BalanceLog
from app.config import settings

logger = get_logger(__name__)

# ── 按天聚合缓存 ────────────────────────────────────────────────────────────
# 报表原本对整个区间做一次 GROUP BY：客户维度/上月实测 **81.7s**（优化器选
# idx_account_time，920 万行逐行回表）。按天切开后，已完结的天结果不再变化 →
# 缓存长期复用，每次打开报表只需实时扫「今天」那一小片。
_DAY_ROLLUP_KEY = "report:sms_day:v1:{tag}:{col}:{d}"
_DAY_ROLLUP_TTL_RECENT = 1800        # 昨天：迟到 DLR 仍会把 sent 改成 delivered
_DAY_ROLLUP_TTL_SETTLED = 86400 * 30  # 前天及更早：视为已定稿

# sms_logs 报表覆盖索引。优化器倾向选 idx_account_time（分组列有序、省临时表），
# 但那条索引不含 status/价格列 → 每行都要回表；强制走覆盖索引实测 81.7s → 36s。
# 仅对 account_id / channel_id 分组有效（country_code 不在该索引内）。
_COV_INDEX = "idx_sms_report_cov2"
_cov_index_available: Optional[bool] = None

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
        # v2: 剔除虚拟通道后口径变更，版本号使旧缓存(含虚拟通道)立即失效
        # v7: RCS 从 sms 桶中拆出（sms 不再含 RCS 流量），旧缓存口径不同必须失效
        cache_key = (
            f"report:business:v7:{dimension}:{business_type}:"
            f"{start_dt.strftime('%Y%m%d%H%M')}:{end_dt.strftime('%Y%m%d%H%M')}"
        )
        cm = await get_cache_manager()
        cached = await cm.get(cache_key)
        if cached is not None:
            return cached

        results: List[Dict[str, Any]] = []
        if business_type in ["all", "sms"]:
            results.extend(await ReportsService._get_sms_stats(db, dimension, start_dt, end_dt))
        if business_type in ["all", "rcs"]:
            # RCS 与短信同表(sms_logs)，靠通道协议拆分，见 _get_sms_stats
            results.extend(
                await ReportsService._get_sms_stats(db, dimension, start_dt, end_dt, biz="rcs")
            )
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
            # 前端日期选择器只传 YYYY-MM-DD（end 解析为当天 00:00）。聚合查询用
            # `submit_time < end_dt` 半开区间，若不进位到次日零点，end_date 当天数据
            # 会被整日排除（曾致报表只统计区间首日，与发送记录页相差一整天）。
            # 仅当 end 是纯日期（零点、无时分秒）时进位，保留显式带时间的上界语义。
            if e.hour == 0 and e.minute == 0 and e.second == 0 and e.microsecond == 0:
                e = e + timedelta(days=1)
            return s, e
        
        return today, now

    @staticmethod
    def _rollup_days(start_dt: datetime, end_dt: datetime) -> Optional[List[_date]]:
        """把查询区间切成整天列表；无法整天对齐则返回 None（调用方回落到原始整段查询）。

        覆盖 today / this_week / this_month（上界=now，等价于「算到今天为止」，
        因为不可能有未来时间的记录）、last_month、以及只选日期的 custom 区间。
        显式带时分秒的 custom 上界不整天对齐，按天聚合会多算，必须回落。
        """
        if start_dt.time() != _time.min:
            return None
        now = datetime.now()
        if end_dt.time() == _time.min:
            last = end_dt.date() - timedelta(days=1)          # 半开区间，上界当天不算
        elif end_dt.date() == now.date() and abs((end_dt - now).total_seconds()) <= 120:
            last = now.date()                                  # 上界就是「此刻」
        else:
            return None
        if last < start_dt.date():
            return []
        return [start_dt.date() + timedelta(days=i) for i in range((last - start_dt.date()).days + 1)]

    @staticmethod
    async def _has_cov_index(db: AsyncSession) -> bool:
        """覆盖索引是否存在（其它部署可能没建）。不存在时不能加 FORCE INDEX，否则报 1176。"""
        global _cov_index_available
        if _cov_index_available is None:
            try:
                row = (await db.execute(_sa_text(
                    "SELECT COUNT(*) FROM information_schema.statistics "
                    "WHERE table_schema = DATABASE() AND table_name = 'sms_logs' AND index_name = :ix"
                ), {"ix": _COV_INDEX})).scalar()
                _cov_index_available = bool(row)
            except Exception:
                _cov_index_available = False
        return _cov_index_available

    @staticmethod
    async def _sms_group_rollup(
        db: AsyncSession,
        col_name: str,
        days: List[_date],
        virtual_ids: List[int],
        rcs_ids: Optional[List[int]] = None,
        biz: str = "sms",
    ):
        """按天缓存的分组聚合，返回与原查询同形状的行对象(fk/total_count/delivered_count/revenue/cost/profit)。

        缺失的天用一条 `GROUP BY DATE(submit_time), <col>` 补齐（整月回填实测 ~33s，
        一次性），写回缓存后长期复用；「今天」永远实时算。

        biz='rcs' 只统计 RCS 通道，biz='sms' 排除 RCS 通道（口径见 _get_sms_stats）。
        """
        col = {
            "account_id": SMSLog.account_id,
            "channel_id": SMSLog.channel_id,
            "country_code": SMSLog.country_code,
        }[col_name]
        today = datetime.now().date()
        # 缓存键绑定被剔除的虚拟通道集合：增删虚拟通道会改变历史天口径
        tag = ",".join(str(i) for i in sorted(virtual_ids or ())) or "all"
        # 同理绑定 RCS 通道集合与业务口径。没有 RCS 通道时不加后缀 ——
        # 此时 sms 桶的查询与拆分前完全一致，已预热的历史天缓存继续有效。
        if rcs_ids:
            tag = f"{tag}|{biz}:{','.join(str(i) for i in sorted(rcs_ids))}"

        per_day: Dict[_date, list] = {}
        rc = None
        try:
            import redis.asyncio as aioredis
            rc = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            raws = await rc.mget([_DAY_ROLLUP_KEY.format(tag=tag, col=col_name, d=d.isoformat()) for d in days])
            for d, raw in zip(days, raws or []):
                if raw and d < today:  # 今天永不吃缓存
                    try:
                        per_day[d] = _json.loads(raw)
                    except Exception:
                        pass
        except Exception:
            rc = None

        missing = [d for d in days if d not in per_day]
        if missing:
            conds = [
                SMSLog.submit_time >= datetime.combine(min(missing), _time.min),
                SMSLog.submit_time < datetime.combine(max(missing), _time.min) + timedelta(days=1),
            ]
            if virtual_ids:
                conds.append(or_(SMSLog.channel_id.is_(None), SMSLog.channel_id.notin_(virtual_ids)))
            if biz == "rcs":
                conds.append(SMSLog.channel_id.in_(rcs_ids or []))
            elif rcs_ids:
                conds.append(or_(SMSLog.channel_id.is_(None), SMSLog.channel_id.notin_(rcs_ids)))
            q = (
                select(
                    func.date(SMSLog.submit_time).label("d"),
                    col.label("fk"),
                    func.count(SMSLog.id).label("c"),
                    func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("dl"),
                    net_revenue("rev"),
                    net_cost("cst"),
                )
                .where(and_(*conds))
                .group_by(func.date(SMSLog.submit_time), col)
            )
            # country_code 不在覆盖索引里，强制反而更糟；只给 account_id/channel_id 上 hint
            if col_name in ("account_id", "channel_id") and await ReportsService._has_cov_index(db):
                q = q.with_hint(SMSLog, f"FORCE INDEX ({_COV_INDEX})")

            acc: Dict[_date, list] = {d: [] for d in missing}
            for r in (await db.execute(q)).all():
                dd = r.d if isinstance(r.d, _date) else datetime.strptime(str(r.d), "%Y-%m-%d").date()
                if dd in acc:
                    acc[dd].append([r.fk, int(r.c or 0), int(r.dl or 0), float(r.rev or 0), float(r.cst or 0)])
            for d in missing:
                per_day[d] = acc.get(d, [])
            if rc is not None:
                try:
                    pipe = rc.pipeline()
                    for d in missing:
                        if d >= today:
                            continue
                        ttl = _DAY_ROLLUP_TTL_RECENT if d >= today - timedelta(days=1) else _DAY_ROLLUP_TTL_SETTLED
                        pipe.setex(
                            _DAY_ROLLUP_KEY.format(tag=tag, col=col_name, d=d.isoformat()),
                            ttl, _json.dumps(per_day[d]),
                        )
                    await pipe.execute()
                except Exception:
                    pass
        if rc is not None:
            try:
                await rc.aclose()
            except Exception:
                pass

        merged: Dict[Any, list] = {}
        for d in days:
            for fk, c, dl, rev, cst in per_day.get(d, []):
                b = merged.setdefault(fk, [0, 0, 0.0, 0.0])
                b[0] += c
                b[1] += dl
                b[2] += rev
                b[3] += cst
        return [
            SimpleNamespace(
                fk=fk, dim_id=fk, total_count=c, delivered_count=dl,
                revenue=rev, cost=cst, profit=rev - cst,
            )
            for fk, (c, dl, rev, cst) in merged.items()
        ]

    @staticmethod
    async def _get_sms_stats(
        db: AsyncSession,
        dimension: str,
        start_dt: datetime,
        end_dt: datetime,
        biz: str = "sms",
    ) -> List[Dict[str, Any]]:
        """
        短信 / RCS 业务聚合查询。
        策略：先按外键(account_id/channel_id/country_code)在 sms_logs 上聚合（覆盖索引扫描），
        再在 Python 里二次聚合到目标维度并补名称，避免在 3M 行级别上做 JOIN。

        RCS 复用 sms_logs 落库，唯一可靠的区分依据是通道协议(channels.protocol='RCS')
        —— 账户 business_type 不行：同一账户可能既发短信又发 RCS。
        biz='sms' 排除 RCS 通道，biz='rcs' 只取 RCS 通道，两者互不重叠且合起来等于原口径。
        """
        agg_count = func.count(SMSLog.id).label("total_count")
        agg_delivered = func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered_count")
        # 净额口径：剔除已退补充值(失败已退)行的金额，计数/送达率不受影响
        agg_revenue = net_revenue("revenue")
        agg_cost = net_cost("cost")
        agg_profit = net_profit("profit")

        time_filter = and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt)

        # 剔除虚拟通道(注水/演示流量)，保留 channel_id 为 NULL 的真实失败记录。
        # 不改 sms_logs 任何数据，仅过滤读查询。
        virtual_ids = await ReportsService._fetch_virtual_channel_ids(db)
        if virtual_ids:
            time_filter = and_(
                time_filter,
                or_(SMSLog.channel_id.is_(None), SMSLog.channel_id.notin_(virtual_ids)),
            )

        # RCS 与短信拆桶：无 RCS 通道时 sms 桶不加任何条件，行为与拆分前一致
        rcs_ids = await ReportsService._fetch_rcs_channel_ids(db)
        if biz == "rcs":
            if not rcs_ids:
                return []
            time_filter = and_(time_filter, SMSLog.channel_id.in_(rcs_ids))
        elif rcs_ids:
            time_filter = and_(
                time_filter,
                or_(SMSLog.channel_id.is_(None), SMSLog.channel_id.notin_(rcs_ids)),
            )

        # 整天对齐的区间（today/this_week/this_month/last_month/纯日期 custom）走按天缓存，
        # 只实时扫「今天」；带时分秒的自定义区间无法按天切，回落到原始整段聚合。
        rollup_days = ReportsService._rollup_days(start_dt, end_dt)

        # === 第一步：按 sms_logs 自带列聚合 ===
        if dimension == "country":
            # 国家维度直接出结果
            if rollup_days is not None:
                rows = await ReportsService._sms_group_rollup(
                    db, "country_code", rollup_days, virtual_ids, rcs_ids=rcs_ids, biz=biz
                )
            else:
                query = (
                    select(
                        SMSLog.country_code.label("dim_id"),
                        agg_count, agg_delivered, agg_revenue, agg_cost, agg_profit,
                    )
                    .where(time_filter)
                    .group_by(SMSLog.country_code)
                )
                rows = (await db.execute(query)).all()
            return [ReportsService._fmt_sms_row(r.dim_id, r.dim_id or "Unknown", r, biz) for r in rows]

        if dimension in ("customer", "employee"):
            base_col, base_col_name = SMSLog.account_id, "account_id"
        elif dimension in ("channel", "supplier"):
            base_col, base_col_name = SMSLog.channel_id, "channel_id"
        else:
            return []

        if rollup_days is not None:
            rows = await ReportsService._sms_group_rollup(
                db, base_col_name, rollup_days, virtual_ids, rcs_ids=rcs_ids, biz=biz
            )
        else:
            query = (
                select(base_col.label("fk"), agg_count, agg_delivered, agg_revenue, agg_cost, agg_profit)
                .where(time_filter)
                .group_by(base_col)
            )
            if await ReportsService._has_cov_index(db):
                query = query.with_hint(SMSLog, f"FORCE INDEX ({_COV_INDEX})")
            rows = (await db.execute(query)).all()
        if not rows:
            return []

        fk_ids = [r.fk for r in rows if r.fk is not None]

        # === 第二步：根据维度补名称 / 二次聚合 ===
        if dimension == "customer":
            name_map = await ReportsService._fetch_account_names(db, fk_ids)
            # 退补充值只挂在 sms 行：balance_logs 没有通道/协议归属，无法拆到 RCS，
            # 若两个桶都挂同一笔，业务类型选「全部」时同一笔退款会显示两遍。
            rr_acc = (
                (await ReportsService._fetch_refund_recharge(db, start_dt, end_dt))[0]
                if biz == "sms" else {}
            )
            out = []
            for r in rows:
                if r.fk is None:
                    continue
                d = ReportsService._fmt_sms_row(r.fk, name_map.get(r.fk, f"Account#{r.fk}"), r, biz)
                rr = rr_acc.get(r.fk)
                if rr:
                    d["refunded_count"] = rr["cnt"]
                    d["refund_amount"] = rr["amt"]
                out.append(d)
            return out

        if dimension == "channel":
            name_map = await ReportsService._fetch_channel_names(db, fk_ids)
            return [
                ReportsService._fmt_sms_row(r.fk, name_map.get(r.fk, f"Channel#{r.fk}"), r, biz)
                for r in rows if r.fk is not None
            ]

        if dimension == "employee":
            # account_id -> sales_id 映射
            sales_map = await ReportsService._fetch_account_sales_map(db, fk_ids)
            # 同 customer 维度：退补只挂 sms 行，避免「全部」口径下一笔退款计两遍
            rr_sales = (
                (await ReportsService._fetch_refund_recharge(db, start_dt, end_dt))[1]
                if biz == "sms" else {}
            )
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
                    "business_type": biz,
                    "dim_id": sid,
                    "dim_name": admin_map.get(sid, f"Admin#{sid}"),
                    "count": b["count"],
                    "delivered": b["delivered"],
                    "revenue": b["revenue"],
                    "cost": b["cost"],
                    "profit": b["profit"],
                    "refunded_count": rr_sales.get(sid, {}).get("cnt", 0),
                    "refund_amount": rr_sales.get(sid, {}).get("amt", 0.0),
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
                    "business_type": biz,
                    "dim_id": sup_id,
                    "dim_name": sup_name_map.get(sup_id, f"Supplier#{sup_id}"),
                    "count": b["count"],
                    "delivered": b["delivered"],
                    "revenue": b["revenue"],
                    "cost": b["cost"],
                    "profit": b["profit"],
                    "refunded_count": 0,  # 供应商维度无法归属退补(balance_logs 无 channel/supplier)
                    "refund_amount": 0.0,
                    "success_rate": round(b["delivered"] / b["count"] * 100, 2) if b["count"] > 0 else 0,
                }
                for sup_id, b in buckets.items()
            ]

        return []

    @staticmethod
    def _fmt_sms_row(dim_id: Any, dim_name: Any, row: Any, biz: str = "sms") -> Dict[str, Any]:
        cnt = int(row.total_count or 0)
        delivered = int(row.delivered_count or 0)
        return {
            "business_type": biz,
            "dim_id": dim_id,
            "dim_name": dim_name,
            "count": cnt,
            "delivered": delivered,
            "revenue": float(row.revenue or 0),
            "cost": float(row.cost or 0),
            "profit": float(row.profit or 0),
            "refunded_count": int(getattr(row, "refunded_count", 0) or 0),
            "refund_amount": float(getattr(row, "refund_amount", 0) or 0),
            "success_rate": round(delivered / cnt * 100, 2) if cnt > 0 else 0,
        }

    @staticmethod
    async def _fetch_refund_recharge(db: AsyncSession, start_dt: datetime, end_dt: datetime):
        """退补充值(balance_logs.change_type=refund_recharge)按账户/员工归属。
        仅列示，不计入成本/收入/利润。返回 (rr_by_account, rr_by_sales)，值={'cnt','amt'}。"""
        rows = (await db.execute(
            select(
                BalanceLog.account_id.label("acc"),
                Account.sales_id.label("sid"),
                func.count(BalanceLog.id).label("cnt"),
                func.coalesce(func.sum(BalanceLog.amount), 0).label("amt"),
            )
            .join(Account, BalanceLog.account_id == Account.id)
            .where(and_(
                BalanceLog.change_type == "refund_recharge",
                BalanceLog.created_at >= start_dt,
                BalanceLog.created_at < end_dt,
            ))
            .group_by(BalanceLog.account_id, Account.sales_id)
        )).all()
        rr_acc: Dict[Any, Dict[str, float]] = {}
        rr_sales: Dict[Any, Dict[str, float]] = {}
        for r in rows:
            c = int(r.cnt or 0)
            a = float(r.amt or 0)
            rr_acc[r.acc] = {"cnt": c, "amt": a}
            if r.sid is not None:
                b = rr_sales.setdefault(r.sid, {"cnt": 0, "amt": 0.0})
                b["cnt"] += c
                b["amt"] += a
        return rr_acc, rr_sales

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
    async def _fetch_virtual_channel_ids(db: AsyncSession) -> List[int]:
        """虚拟通道(protocol=VIRTUAL)的ID，用于从业务报表中剔除注水/演示流量。"""
        rows = (await db.execute(select(Channel.id).where(Channel.protocol == "VIRTUAL"))).all()
        return [r[0] for r in rows]

    @staticmethod
    async def _fetch_rcs_channel_ids(db: AsyncSession) -> List[int]:
        """RCS 通道(protocol=RCS)的ID，用于把 RCS 流量从短信桶里拆出来。

        不过滤 is_deleted：通道删了，历史 sms_logs 里那些记录仍然属于 RCS 业务，
        排除掉会让它们悄悄回流到短信桶。
        """
        rows = (await db.execute(select(Channel.id).where(Channel.protocol == "RCS"))).all()
        return [r[0] for r in rows]

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
