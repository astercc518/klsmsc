"""结算系统API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, delete
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from calendar import monthrange
from decimal import Decimal
import uuid

from app.database import get_db
from app.models.settlement import Settlement, SettlementDetail, SettlementLog, CustomerBill, CustomerBillDetail, ProfitReport
from app.modules.sms.supplier import Supplier, SupplierChannel, SupplierRate
from app.modules.sms.channel import Channel
from app.modules.sms.sms_log import SMSLog
from app.modules.common.account import Account
from app.api.v1.admin import get_current_admin
from app.modules.common.admin_user import AdminUser
from app.core.commission import create_commission_settlement
from app.core.pricing import PricingEngine

router = APIRouter(prefix="/admin/settlements", tags=["结算管理"])


async def _resolve_settlement_line_cost(
    db: AsyncSession,
    supplier_id: int,
    channel_id: int,
    country_code: Optional[str],
    total_cost_from_logs: float,
    total_parts: int,
) -> float:
    """
    单行（通道+国家）结算成本：优先 sum(sms_logs.cost_price)；若为 0 则用供应商国家费率 × 短信条数，
    再不行用通道 cost_rate × 条数（与计费引擎、历史零成本日志补救一致）。
    """
    tc = float(total_cost_from_logs or 0)
    if tc > 0:
        return tc
    parts = int(total_parts or 0)
    if parts <= 0:
        return 0.0

    link = await db.scalar(
        select(SupplierChannel.id).where(
            SupplierChannel.supplier_id == supplier_id,
            SupplierChannel.channel_id == channel_id,
            SupplierChannel.status == 'active',
        ).limit(1)
    )
    if not link:
        return 0.0

    codes = PricingEngine._supplier_rate_country_variants(country_code or '')
    if codes:
        rate_row = await db.execute(
            select(SupplierRate.cost_price)
            .where(
                SupplierRate.supplier_id == supplier_id,
                SupplierRate.business_type == 'sms',
                SupplierRate.status == 'active',
                SupplierRate.country_code.in_(codes),
            )
            .order_by(SupplierRate.id.desc())
            .limit(1)
        )
        cp = rate_row.scalar_one_or_none()
        if cp is not None and float(cp) > 0:
            return float(cp) * parts

    ch = await db.get(Channel, channel_id)
    if ch and ch.cost_rate is not None and float(ch.cost_rate) > 0:
        return float(ch.cost_rate) * parts

    return 0.0


def _month_datetime_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """与前端生成结算单一致：当月首 00:00:00 至 当日 23:59:59"""
    last_day = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0)
    end = datetime(year, month, last_day, 23, 59, 59)
    return start, end


def _commission_month_period(year: int, month: int) -> tuple[datetime, datetime]:
    """与 /sales-commission/generate 一致，供 create_commission_settlement 周期与去重"""
    period_start = datetime(year, month, 1, 0, 0, 0)
    if month == 12:
        period_end = datetime(year + 1, 1, 1, 0, 0, 0) - timedelta(seconds=1)
    else:
        period_end = datetime(year, month + 1, 1, 0, 0, 0) - timedelta(seconds=1)
    return period_start, period_end


# ============ Pydantic 模型 ============

class SettlementCreate(BaseModel):
    supplier_id: int = Field(..., description="供应商ID")
    period_start: datetime = Field(..., description="结算周期开始")
    period_end: datetime = Field(..., description="结算周期结束")
    notes: Optional[str] = None


class SettlementAdjust(BaseModel):
    adjustment_amount: Decimal = Field(..., description="调整金额(正为增加,负为减少)")
    reason: str = Field(..., description="调整原因")


class SettlementPay(BaseModel):
    payment_method: str = Field(..., description="支付方式")
    payment_reference: Optional[str] = Field(None, description="支付凭证/流水号")
    payment_proof: Optional[str] = Field(None, description="支付凭证图片")
    notes: Optional[str] = None


class CustomerBillCreate(BaseModel):
    account_id: int = Field(..., description="账户ID")
    period_start: datetime = Field(..., description="账单周期开始")
    period_end: datetime = Field(..., description="账单周期结束")
    due_days: Optional[int] = Field(7, description="到期天数(从周期结束起)")


class CustomerBillPay(BaseModel):
    amount: float = Field(..., gt=0, description="收款金额")
    payment_method: Optional[str] = Field(None, description="支付方式")
    payment_reference: Optional[str] = Field(None, description="流水号")
    notes: Optional[str] = None


def generate_settlement_no() -> str:
    """生成结算单号"""
    now = datetime.now()
    return f"ST{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"


def generate_bill_no() -> str:
    """生成账单号"""
    now = datetime.now()
    return f"BL{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"


# ============ 供应商结算 ============

def _settlement_month_bounds(ym: str) -> tuple[datetime, datetime]:
    """YYYY-MM -> 该月首尾（本地日历日 00:00 ~ 当日 23:59:59）"""
    parts = ym.strip().split("-")
    y, m = int(parts[0]), int(parts[1])
    last_day = monthrange(y, m)[1]
    first = datetime(y, m, 1, 0, 0, 0)
    last = datetime(y, m, last_day, 23, 59, 59)
    return first, last


def _settlement_list_filters(
    supplier_id: Optional[int],
    status: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    settlement_month: Optional[str],
    supplier_keyword: Optional[str],
):
    """供应商结算列表/汇总共用筛选（与 Supplier 内连接）"""
    conditions = []
    if supplier_id:
        conditions.append(Settlement.supplier_id == supplier_id)
    if status:
        conditions.append(Settlement.status == status)
    if settlement_month and settlement_month.strip():
        first, last = _settlement_month_bounds(settlement_month.strip())
        conditions.append(Settlement.period_start >= first)
        conditions.append(Settlement.period_start <= last)
    else:
        if start_date:
            conditions.append(Settlement.period_start >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            conditions.append(Settlement.period_end <= datetime.combine(end_date, datetime.max.time()))
    if supplier_keyword and supplier_keyword.strip():
        kw = supplier_keyword.strip()
        conditions.append(Supplier.supplier_name.like(f"%{kw}%"))
    return conditions


@router.get("/summary")
async def get_settlements_summary(
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    settlement_month: Optional[str] = None,
    supplier_keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取结算单汇总统计"""
    conditions = _settlement_list_filters(
        supplier_id, status, start_date, end_date, settlement_month, supplier_keyword
    )
    query = select(
        func.count(Settlement.id).label("total_count"),
        func.coalesce(func.sum(Settlement.final_amount), 0).label("total_amount"),
        func.sum(case((Settlement.status == 'draft', 1), else_=0)).label("draft_count"),
        func.sum(case((Settlement.status == 'pending', 1), else_=0)).label("pending_count"),
        func.sum(case((Settlement.status == 'confirmed', 1), else_=0)).label("confirmed_count"),
        func.sum(case((Settlement.status == 'paid', 1), else_=0)).label("paid_count"),
    ).select_from(Settlement).join(Supplier, Settlement.supplier_id == Supplier.id)
    if conditions:
        query = query.where(and_(*conditions))
    row = (await db.execute(query)).first()
    return {
        "success": True,
        "summary": {
            "total_count": row.total_count or 0,
            "total_amount": float(row.total_amount or 0),
            "draft_count": row.draft_count or 0,
            "pending_count": row.pending_count or 0,
            "confirmed_count": row.confirmed_count or 0,
            "paid_count": row.paid_count or 0,
        }
    }


@router.get("")
async def get_settlements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    settlement_month: Optional[str] = Query(None, description="结算月 YYYY-MM，优先于 start/end 日期范围"),
    supplier_keyword: Optional[str] = Query(None, description="供应商名称模糊搜索"),
    sort_by: str = Query("created_at", description="created_at|total_sms_count|final_amount"),
    sort_order: str = Query("desc", description="asc|desc"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取结算单列表（通道数为供应商关联活跃通道数、备注；支持结算月与供应商名称筛选）"""
    conditions = _settlement_list_filters(
        supplier_id, status, start_date, end_date, settlement_month, supplier_keyword
    )
    base_join = Settlement.supplier_id == Supplier.id
    count_stmt = select(func.count(Settlement.id)).select_from(Settlement).join(Supplier, base_join)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = await db.scalar(count_stmt) or 0

    order_col = Settlement.created_at
    if sort_by == "total_sms_count":
        order_col = Settlement.total_sms_count
    elif sort_by == "final_amount":
        order_col = Settlement.final_amount
    asc = sort_order.lower() == "asc"

    stmt = (
        select(Settlement)
        .join(Supplier, base_join)
        .options(
            selectinload(Settlement.supplier).selectinload(Supplier.channels),
            selectinload(Settlement.details),
        )
    )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(order_col.asc() if asc else order_col.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    settlements = result.scalars().all()

    def _channel_count(s: Settlement) -> int:
        """供应商当前关联的活跃通道数（与当月明细是否只覆盖部分通道无关）。"""
        sup = s.supplier
        if not sup:
            return 0
        chs = getattr(sup, "channels", None) or []
        return len(
            {c.channel_id for c in chs if getattr(c, "status", None) == "active"}
        )

    rows = []
    for s in settlements:
        ps = s.period_start
        settlement_month_str = f"{ps.year}-{ps.month:02d}" if ps else ""
        rows.append(
            {
                "id": s.id,
                "settlement_no": s.settlement_no,
                "supplier_id": s.supplier_id,
                "supplier_name": s.supplier.supplier_name if s.supplier else None,
                "settlement_month": settlement_month_str,
                "period_start": s.period_start.isoformat() if s.period_start else None,
                "period_end": s.period_end.isoformat() if s.period_end else None,
                "channel_count": _channel_count(s),
                "total_sms_count": s.total_sms_count,
                "total_cost": float(s.total_cost) if s.total_cost else 0,
                "adjustment_amount": float(s.adjustment_amount) if s.adjustment_amount else 0,
                "final_amount": float(s.final_amount) if s.final_amount else 0,
                "currency": s.currency,
                "status": s.status,
                "notes": s.notes,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
        )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "settlements": rows,
    }


async def _execute_supplier_settlement(
    db: AsyncSession,
    data: SettlementCreate,
    admin: AdminUser,
) -> dict:
    """生成供应商结算单（单条提交，内部 commit）"""
    supplier = await db.get(Supplier, data.supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="供应商不存在")

    channels_result = await db.execute(
        select(SupplierChannel.channel_id).where(
            SupplierChannel.supplier_id == data.supplier_id,
            SupplierChannel.status == 'active',
        )
    )
    channel_ids = [c for c in channels_result.scalars().all()]

    if not channel_ids:
        raise HTTPException(status_code=400, detail="供应商没有关联的通道")

    stats_query = (
        select(
            SMSLog.channel_id,
            SMSLog.country_code,
            func.count(SMSLog.id).label('total_count'),
            func.sum(func.coalesce(SMSLog.message_count, 1)).label('total_parts'),
            func.sum(case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
            func.sum(case((SMSLog.status == 'failed', 1), else_=0)).label('failed_count'),
            func.sum(SMSLog.cost_price).label('total_cost'),
        )
        .where(
            SMSLog.channel_id.in_(channel_ids),
            SMSLog.submit_time >= data.period_start,
            SMSLog.submit_time < data.period_end,
        )
        .group_by(SMSLog.channel_id, SMSLog.country_code)
    )

    stats_result = await db.execute(stats_query)
    stats_rows = stats_result.all()

    line_costs: list[float] = []
    for row in stats_rows:
        raw_tc = float(row.total_cost or 0)
        parts = int(row.total_parts or 0)
        line_costs.append(
            await _resolve_settlement_line_cost(
                db,
                data.supplier_id,
                row.channel_id,
                row.country_code,
                raw_tc,
                parts,
            )
        )

    total_sms = sum(row.total_count for row in stats_rows)
    total_success = sum(row.success_count or 0 for row in stats_rows)
    total_failed = sum(row.failed_count or 0 for row in stats_rows)
    total_cost = sum(line_costs)

    settlement = Settlement(
        settlement_no=generate_settlement_no(),
        supplier_id=data.supplier_id,
        period_start=data.period_start,
        period_end=data.period_end,
        total_sms_count=total_sms,
        total_success_count=total_success,
        total_failed_count=total_failed,
        total_cost=total_cost,
        final_amount=total_cost,
        currency=supplier.settlement_currency,
        settlement_type='manual',
        status='draft',
        notes=data.notes,
    )
    db.add(settlement)
    await db.flush()

    for idx, row in enumerate(stats_rows):
        await db.get(Channel, row.channel_id)
        line_tc = line_costs[idx]
        detail = SettlementDetail(
            settlement_id=settlement.id,
            channel_id=row.channel_id,
            country_code=row.country_code,
            sms_count=row.total_count,
            success_count=row.success_count or 0,
            failed_count=row.failed_count or 0,
            unit_cost=float(line_tc) / row.total_count if row.total_count > 0 else 0,
            total_cost=line_tc,
        )
        db.add(detail)

    log = SettlementLog(
        settlement_id=settlement.id,
        action='create',
        new_status='draft',
        operator_id=admin.id,
        operator_name=admin.username,
        description='创建结算单',
    )
    db.add(log)

    await db.commit()
    await db.refresh(settlement)

    return {
        "success": True,
        "message": "结算单生成成功",
        "settlement_id": settlement.id,
        "settlement_no": settlement.settlement_no,
        "total_sms_count": total_sms,
        "total_cost": total_cost,
    }


@router.post("/generate")
async def generate_settlement(
    data: SettlementCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """生成结算单"""
    return await _execute_supplier_settlement(db, data, admin)


async def _supplier_settlement_month_exists(
    db: AsyncSession,
    supplier_id: int,
    month_first: datetime,
    month_last: datetime,
) -> bool:
    q = (
        select(Settlement.id)
        .where(
            Settlement.supplier_id == supplier_id,
            Settlement.period_start >= month_first,
            Settlement.period_start <= month_last,
        )
        .limit(1)
    )
    return (await db.scalar(q)) is not None


async def _customer_bill_month_exists(
    db: AsyncSession,
    account_id: int,
    month_first: datetime,
    month_last: datetime,
) -> bool:
    q = (
        select(CustomerBill.id)
        .where(
            CustomerBill.account_id == account_id,
            CustomerBill.period_start >= month_first,
            CustomerBill.period_start <= month_last,
        )
        .limit(1)
    )
    return (await db.scalar(q)) is not None


async def _execute_customer_bill_generate(
    db: AsyncSession,
    data: CustomerBillCreate,
) -> dict:
    """生成客户账单（单条提交，内部 commit）"""
    account_id = data.account_id
    period_start = data.period_start
    period_end = data.period_end
    due_days = data.due_days or 7

    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    stats_query = (
        select(
            SMSLog.country_code,
            func.count(SMSLog.id).label('total_count'),
            func.sum(case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
            func.sum(SMSLog.selling_price).label('total_amount'),
        )
        .where(
            SMSLog.account_id == account_id,
            SMSLog.submit_time >= period_start,
            SMSLog.submit_time < period_end,
        )
        .group_by(SMSLog.country_code)
    )

    stats_result = await db.execute(stats_query)
    stats_rows = stats_result.all()

    total_sms = sum(row.total_count for row in stats_rows)
    total_success = sum(row.success_count or 0 for row in stats_rows)
    total_amount = sum(float(row.total_amount or 0) for row in stats_rows)

    due_date = period_end + timedelta(days=due_days) if due_days else None
    bill = CustomerBill(
        bill_no=generate_bill_no(),
        account_id=account_id,
        period_start=period_start,
        period_end=period_end,
        total_sms_count=total_sms,
        total_success_count=total_success,
        total_amount=total_amount,
        outstanding_amount=total_amount,
        currency=account.currency or 'USD',
        status='draft',
        due_date=due_date,
    )
    db.add(bill)
    await db.flush()

    for row in stats_rows:
        detail = CustomerBillDetail(
            bill_id=bill.id,
            country_code=row.country_code,
            sms_count=row.total_count,
            success_count=row.success_count or 0,
            unit_price=float(row.total_amount or 0) / row.total_count if row.total_count > 0 else 0,
            total_amount=row.total_amount or 0,
        )
        db.add(detail)

    await db.commit()
    await db.refresh(bill)

    return {
        "success": True,
        "message": "客户账单生成成功",
        "bill_id": bill.id,
        "bill_no": bill.bill_no,
        "total_amount": total_amount,
    }


@router.post("/auto-generate-month")
async def auto_generate_month_settlements(
    year: Optional[int] = Query(None, ge=2000, le=2100, description="年，默认当前年"),
    month: Optional[int] = Query(None, ge=1, le=12, description="月，默认当前月"),
    include_suppliers: bool = Query(True, description="是否生成全部供应商结算单"),
    include_employees: bool = Query(True, description="是否生成全部员工佣金结算单"),
    include_customers: bool = Query(True, description="是否生成全部客户账单"),
    due_days: int = Query(7, ge=0, le=90, description="客户账单到期天数（从周期结束起）"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    按指定月份批量生成：供应商结算、员工佣金结算、客户账单。
    已存在当月记录的则跳过；客户无短信则跳过；员工无佣金或已有单则跳过。
    """
    now = datetime.now()
    y = year if year is not None else now.year
    m = month if month is not None else now.month

    month_first, month_last = _month_datetime_bounds(y, m)
    comm_start, comm_end = _commission_month_period(y, m)

    out: dict = {
        "success": True,
        "period": {
            "year": y,
            "month": m,
            "supplier_period_start": month_first.isoformat(),
            "supplier_period_end": month_last.isoformat(),
        },
        "suppliers": {"created": 0, "skipped": 0, "failed": 0, "items": []},
        "employees": {"created": 0, "skipped": 0, "failed": 0, "items": []},
        "customers": {"created": 0, "skipped": 0, "failed": 0, "items": []},
    }

    # 1) 供应商
    if include_suppliers:
        sup_res = await db.execute(select(Supplier).where(Supplier.is_deleted == False))
        suppliers = sup_res.scalars().all()
        for s in suppliers:
            item = {"supplier_id": s.id, "supplier_name": s.supplier_name, "status": ""}
            try:
                if await _supplier_settlement_month_exists(db, s.id, month_first, month_last):
                    item["status"] = "skipped"
                    item["reason"] = "当月已有结算单"
                    out["suppliers"]["skipped"] += 1
                    out["suppliers"]["items"].append(item)
                    continue
                ch = await db.execute(
                    select(SupplierChannel.channel_id).where(
                        SupplierChannel.supplier_id == s.id,
                        SupplierChannel.status == 'active',
                    )
                )
                if not list(ch.scalars().all()):
                    item["status"] = "skipped"
                    item["reason"] = "无有效通道"
                    out["suppliers"]["skipped"] += 1
                    out["suppliers"]["items"].append(item)
                    continue
                data = SettlementCreate(
                    supplier_id=s.id,
                    period_start=month_first,
                    period_end=month_last,
                    notes="批量自动生成",
                )
                r = await _execute_supplier_settlement(db, data, admin)
                item["status"] = "created"
                item["settlement_no"] = r.get("settlement_no")
                out["suppliers"]["created"] += 1
            except HTTPException as e:
                item["status"] = "failed"
                item["error"] = e.detail if isinstance(e.detail, str) else str(e.detail)
                out["suppliers"]["failed"] += 1
            except Exception as e:
                item["status"] = "failed"
                item["error"] = str(e)
                out["suppliers"]["failed"] += 1
            out["suppliers"]["items"].append(item)

    # 2) 员工佣金（销售）
    if include_employees:
        sales_q = await db.execute(
            select(AdminUser.id, AdminUser.username).where(
                AdminUser.role == 'sales',
                AdminUser.status == 'active',
                AdminUser.commission_rate > 0,
            )
        )
        for row in sales_q.all():
            sid, uname = row[0], row[1]
            item = {"sales_id": sid, "username": uname, "status": ""}
            try:
                settlement = await create_commission_settlement(db, comm_start, comm_end, sid)
                if settlement:
                    item["status"] = "created"
                    item["settlement_no"] = settlement.settlement_no
                    out["employees"]["created"] += 1
                else:
                    item["status"] = "skipped"
                    item["reason"] = "已有结算单或无佣金数据"
                    out["employees"]["skipped"] += 1
            except Exception as e:
                item["status"] = "failed"
                item["error"] = str(e)
                out["employees"]["failed"] += 1
            out["employees"]["items"].append(item)

    # 3) 客户账单
    if include_customers:
        acc_q = await db.execute(
            select(Account.id, Account.account_name).where(
                Account.is_deleted == False,
                Account.status == 'active',
            )
        )
        for row in acc_q.all():
            aid, aname = row[0], row[1]
            item = {"account_id": aid, "account_name": aname, "status": ""}
            try:
                if await _customer_bill_month_exists(db, aid, month_first, month_last):
                    item["status"] = "skipped"
                    item["reason"] = "当月已有账单"
                    out["customers"]["skipped"] += 1
                    out["customers"]["items"].append(item)
                    continue
                sms_n = await db.scalar(
                    select(func.count(SMSLog.id)).where(
                        SMSLog.account_id == aid,
                        SMSLog.submit_time >= month_first,
                        SMSLog.submit_time < month_last,
                    )
                )
                if not sms_n:
                    item["status"] = "skipped"
                    item["reason"] = "无短信数据"
                    out["customers"]["skipped"] += 1
                    out["customers"]["items"].append(item)
                    continue
                cdata = CustomerBillCreate(
                    account_id=aid,
                    period_start=month_first,
                    period_end=month_last,
                    due_days=due_days,
                )
                r = await _execute_customer_bill_generate(db, cdata)
                item["status"] = "created"
                item["bill_no"] = r.get("bill_no")
                out["customers"]["created"] += 1
            except HTTPException as e:
                item["status"] = "failed"
                item["error"] = e.detail if isinstance(e.detail, str) else str(e.detail)
                out["customers"]["failed"] += 1
            except Exception as e:
                item["status"] = "failed"
                item["error"] = str(e)
                out["customers"]["failed"] += 1
            out["customers"]["items"].append(item)

    return out


@router.get("/{settlement_id}")
async def get_settlement_detail(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取结算单详情"""
    result = await db.execute(
        select(Settlement)
        .options(
            selectinload(Settlement.supplier),
            selectinload(Settlement.details),
            selectinload(Settlement.logs)
        )
        .where(Settlement.id == settlement_id)
    )
    settlement = result.scalar_one_or_none()
    
    if not settlement:
        raise HTTPException(status_code=404, detail="结算单不存在")
    
    return {
        "success": True,
        "settlement": {
            "id": settlement.id,
            "settlement_no": settlement.settlement_no,
            "supplier_id": settlement.supplier_id,
            "supplier_name": settlement.supplier.supplier_name if settlement.supplier else None,
            "period_start": settlement.period_start.isoformat() if settlement.period_start else None,
            "period_end": settlement.period_end.isoformat() if settlement.period_end else None,
            "total_sms_count": settlement.total_sms_count,
            "total_success_count": settlement.total_success_count,
            "total_failed_count": settlement.total_failed_count,
            "total_cost": float(settlement.total_cost) if settlement.total_cost else 0,
            "adjustment_amount": float(settlement.adjustment_amount) if settlement.adjustment_amount else 0,
            "final_amount": float(settlement.final_amount) if settlement.final_amount else 0,
            "currency": settlement.currency,
            "status": settlement.status,
            "payment_method": settlement.payment_method,
            "payment_reference": settlement.payment_reference,
            "payment_proof": settlement.payment_proof,
            "paid_at": settlement.paid_at.isoformat() if settlement.paid_at else None,
            "notes": settlement.notes,
            "created_at": settlement.created_at.isoformat() if settlement.created_at else None,
            "details": [
                {
                    "id": d.id,
                    "channel_id": d.channel_id,
                    "country_code": d.country_code,
                    "country_name": d.country_name,
                    "sms_count": d.sms_count,
                    "success_count": d.success_count,
                    "failed_count": d.failed_count,
                    "unit_cost": float(d.unit_cost) if d.unit_cost else 0,
                    "total_cost": float(d.total_cost) if d.total_cost else 0
                }
                for d in settlement.details
            ],
            "logs": [
                {
                    "id": l.id,
                    "action": l.action,
                    "old_status": l.old_status,
                    "new_status": l.new_status,
                    "operator_name": l.operator_name,
                    "description": l.description,
                    "created_at": l.created_at.isoformat() if l.created_at else None
                }
                for l in settlement.logs
            ]
        }
    }


@router.post("/{settlement_id}/confirm")
async def confirm_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """确认结算单"""
    settlement = await db.get(Settlement, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="结算单不存在")
    
    if settlement.status not in ['draft', 'pending']:
        raise HTTPException(status_code=400, detail="当前状态无法确认")
    
    old_status = settlement.status
    settlement.status = 'confirmed'
    settlement.confirmed_by = admin.id
    settlement.confirmed_at = datetime.now()
    
    # 记录日志
    log = SettlementLog(
        settlement_id=settlement_id,
        action='confirm',
        old_status=old_status,
        new_status='confirmed',
        operator_id=admin.id,
        operator_name=admin.username,
        description='确认结算单'
    )
    db.add(log)
    
    await db.commit()
    
    return {"success": True, "message": "结算单已确认"}


@router.post("/{settlement_id}/adjust")
async def adjust_settlement(
    settlement_id: int,
    data: SettlementAdjust,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """调整结算金额"""
    settlement = await db.get(Settlement, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="结算单不存在")
    
    if settlement.status == 'paid':
        raise HTTPException(status_code=400, detail="已支付的结算单无法调整")
    
    old_amount = settlement.final_amount
    settlement.adjustment_amount = (settlement.adjustment_amount or 0) + data.adjustment_amount
    settlement.final_amount = (settlement.total_cost or 0) + settlement.adjustment_amount
    
    # 记录日志
    log = SettlementLog(
        settlement_id=settlement_id,
        action='adjust',
        old_status=settlement.status,
        new_status=settlement.status,
        operator_id=admin.id,
        operator_name=admin.username,
        description=f"调整金额: {data.adjustment_amount}, 原因: {data.reason}",
        extra_data={
            "old_final_amount": float(old_amount) if old_amount else 0,
            "new_final_amount": float(settlement.final_amount),
            "adjustment": float(data.adjustment_amount),
            "reason": data.reason
        }
    )
    db.add(log)
    
    await db.commit()
    
    return {"success": True, "message": "金额调整成功", "final_amount": float(settlement.final_amount)}


@router.post("/{settlement_id}/pay")
async def pay_settlement(
    settlement_id: int,
    data: SettlementPay,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """支付结算单"""
    settlement = await db.get(Settlement, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="结算单不存在")
    
    if settlement.status != 'confirmed':
        raise HTTPException(status_code=400, detail="只有已确认的结算单才能支付")
    
    old_status = settlement.status
    settlement.status = 'paid'
    settlement.payment_method = data.payment_method
    settlement.payment_reference = data.payment_reference
    settlement.payment_proof = data.payment_proof
    settlement.paid_by = admin.id
    settlement.paid_at = datetime.now()
    if data.notes:
        settlement.notes = (settlement.notes or '') + '\n' + data.notes
    
    # 更新供应商余额
    supplier = await db.get(Supplier, settlement.supplier_id)
    if supplier:
        supplier.current_balance = (supplier.current_balance or 0) - settlement.final_amount
    
    # 记录日志
    log = SettlementLog(
        settlement_id=settlement_id,
        action='pay',
        old_status=old_status,
        new_status='paid',
        operator_id=admin.id,
        operator_name=admin.username,
        description=f"支付结算单，支付方式: {data.payment_method}"
    )
    db.add(log)
    
    await db.commit()
    
    return {"success": True, "message": "结算单已支付"}


@router.post("/{settlement_id}/cancel")
async def cancel_settlement(
    settlement_id: int,
    reason: str = Query(..., description="取消原因"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """取消结算单"""
    settlement = await db.get(Settlement, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="结算单不存在")
    
    if settlement.status == 'paid':
        raise HTTPException(status_code=400, detail="已支付的结算单无法取消")
    
    old_status = settlement.status
    settlement.status = 'cancelled'
    
    # 记录日志
    log = SettlementLog(
        settlement_id=settlement_id,
        action='cancel',
        old_status=old_status,
        new_status='cancelled',
        operator_id=admin.id,
        operator_name=admin.username,
        description=f"取消结算单，原因: {reason}"
    )
    db.add(log)
    
    await db.commit()
    
    return {"success": True, "message": "结算单已取消"}


@router.delete("/{settlement_id}")
async def delete_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """物理删除结算单（仅草稿/待确认/已取消，已确认或已支付不可删）"""
    settlement = await db.get(Settlement, settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="结算单不存在")
    if settlement.status in ("confirmed", "paid"):
        raise HTTPException(status_code=400, detail="已确认或已支付的结算单不可删除")

    await db.execute(delete(SettlementDetail).where(SettlementDetail.settlement_id == settlement_id))
    await db.execute(delete(SettlementLog).where(SettlementLog.settlement_id == settlement_id))
    await db.execute(delete(Settlement).where(Settlement.id == settlement_id))
    await db.commit()

    return {"success": True, "message": "结算单已删除"}


# ============ 利润报表 ============

@router.get("/reports/profit")
async def get_profit_report(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    group_by: str = Query("day", description="分组方式: day/supplier/country/channel"),
    supplier_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取利润报表"""
    # 构建查询
    if group_by == "day":
        query = select(
            func.date(SMSLog.submit_time).label('date'),
            func.count(SMSLog.id).label('total_count'),
            func.sum(case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
            func.sum(SMSLog.cost_price).label('total_cost'),
            func.sum(SMSLog.selling_price).label('total_revenue')
        ).where(
            SMSLog.submit_time >= start_date,
            SMSLog.submit_time < end_date + timedelta(days=1)
        ).group_by(func.date(SMSLog.submit_time))
        
    elif group_by == "country":
        query = select(
            SMSLog.country_code.label('country_code'),
            func.count(SMSLog.id).label('total_count'),
            func.sum(case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
            func.sum(SMSLog.cost_price).label('total_cost'),
            func.sum(SMSLog.selling_price).label('total_revenue')
        ).where(
            SMSLog.submit_time >= start_date,
            SMSLog.submit_time < end_date + timedelta(days=1)
        ).group_by(SMSLog.country_code)
        
    elif group_by == "channel":
        query = select(
            SMSLog.channel_id.label('channel_id'),
            Channel.channel_name.label('channel_name'),
            func.count(SMSLog.id).label('total_count'),
            func.sum(case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
            func.sum(SMSLog.cost_price).label('total_cost'),
            func.sum(SMSLog.selling_price).label('total_revenue')
        ).join(Channel, SMSLog.channel_id == Channel.id).where(
            SMSLog.submit_time >= start_date,
            SMSLog.submit_time < end_date + timedelta(days=1)
        ).group_by(SMSLog.channel_id, Channel.channel_name)
        
    else:  # supplier
        query = select(
            Supplier.id.label('supplier_id'),
            Supplier.supplier_name.label('supplier_name'),
            func.count(SMSLog.id).label('total_count'),
            func.sum(case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
            func.sum(SMSLog.cost_price).label('total_cost'),
            func.sum(SMSLog.selling_price).label('total_revenue')
        ).join(Channel, SMSLog.channel_id == Channel.id
        ).join(SupplierChannel, Channel.id == SupplierChannel.channel_id
        ).join(Supplier, SupplierChannel.supplier_id == Supplier.id
        ).where(
            SMSLog.submit_time >= start_date,
            SMSLog.submit_time < end_date + timedelta(days=1)
        ).group_by(Supplier.id, Supplier.supplier_name)
    
    if supplier_id:
        # 筛选供应商
        channel_ids_query = select(SupplierChannel.channel_id).where(SupplierChannel.supplier_id == supplier_id)
        channel_ids_result = await db.execute(channel_ids_query)
        channel_ids = [c for c in channel_ids_result.scalars().all()]
        if channel_ids:
            query = query.where(SMSLog.channel_id.in_(channel_ids))
    
    result = await db.execute(query)
    rows = result.all()
    
    # 处理结果
    report_data = []
    total_cost = 0
    total_revenue = 0
    total_profit = 0
    
    for row in rows:
        cost = float(row.total_cost or 0)
        revenue = float(row.total_revenue or 0)
        profit = revenue - cost
        margin = (profit / revenue * 100) if revenue > 0 else 0
        
        total_cost += cost
        total_revenue += revenue
        total_profit += profit
        
        item = {
            "total_count": row.total_count,
            "success_count": row.success_count or 0,
            "total_cost": cost,
            "total_revenue": revenue,
            "profit": profit,
            "profit_margin": round(margin, 2)
        }
        
        if group_by == "day":
            item["date"] = row.date.isoformat() if row.date else None
        elif group_by == "country":
            item["country_code"] = row.country_code
        elif group_by == "channel":
            item["channel_id"] = row.channel_id
            item["channel_name"] = row.channel_name
        else:
            item["supplier_id"] = row.supplier_id
            item["supplier_name"] = row.supplier_name
        
        report_data.append(item)
    
    return {
        "success": True,
        "summary": {
            "total_cost": total_cost,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "overall_margin": round((total_profit / total_revenue * 100) if total_revenue > 0 else 0, 2)
        },
        "data": report_data
    }


# ============ 客户账单 ============

customer_bill_router = APIRouter(prefix="/admin/bills", tags=["客户账单"])


def _customer_bill_list_conditions(
    account_id: Optional[int],
    status: Optional[str],
    settlement_month: Optional[str],
    account_keyword: Optional[str],
):
    """客户账单筛选（需与 Account 内连接）"""
    conditions = []
    if account_id:
        conditions.append(CustomerBill.account_id == account_id)
    if status:
        conditions.append(CustomerBill.status == status)
    if settlement_month and settlement_month.strip():
        first, last = _settlement_month_bounds(settlement_month.strip())
        conditions.append(CustomerBill.period_start >= first)
        conditions.append(CustomerBill.period_start <= last)
    if account_keyword and account_keyword.strip():
        kw = account_keyword.strip()
        conditions.append(Account.account_name.like(f"%{kw}%"))
    return conditions


@customer_bill_router.get("")
async def get_customer_bills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    settlement_month: Optional[str] = Query(None, description="账期月 YYYY-MM"),
    account_keyword: Optional[str] = Query(None, description="客户名称模糊"),
    sort_by: str = Query("created_at", description="created_at|total_sms_count|total_amount"),
    sort_order: str = Query("desc", description="asc|desc"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取客户账单列表（客户结算）"""
    conditions = _customer_bill_list_conditions(
        account_id, status, settlement_month, account_keyword
    )
    join_on = CustomerBill.account_id == Account.id
    count_stmt = (
        select(func.count(CustomerBill.id))
        .select_from(CustomerBill)
        .join(Account, join_on)
    )
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = await db.scalar(count_stmt) or 0

    order_col = CustomerBill.created_at
    if sort_by == "total_sms_count":
        order_col = CustomerBill.total_sms_count
    elif sort_by == "total_amount":
        order_col = CustomerBill.total_amount
    asc = sort_order.lower() == "asc"

    stmt = (
        select(CustomerBill)
        .join(Account, join_on)
        .options(selectinload(CustomerBill.account), selectinload(CustomerBill.details))
    )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(order_col.asc() if asc else order_col.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    bills = result.scalars().all()

    out_bills = []
    for b in bills:
        ps = b.period_start
        settlement_month_str = f"{ps.year}-{ps.month:02d}" if ps else ""
        details = b.details or []
        country_count = len({d.country_code for d in details if d.country_code})
        out_bills.append(
            {
                "id": b.id,
                "bill_no": b.bill_no,
                "account_id": b.account_id,
                "account_name": b.account.account_name if b.account else None,
                "settlement_month": settlement_month_str,
                "period_start": b.period_start.isoformat() if b.period_start else None,
                "period_end": b.period_end.isoformat() if b.period_end else None,
                "country_count": country_count,
                "total_sms_count": b.total_sms_count,
                "total_amount": float(b.total_amount) if b.total_amount else 0,
                "paid_amount": float(b.paid_amount) if b.paid_amount else 0,
                "outstanding_amount": float(b.outstanding_amount) if b.outstanding_amount else 0,
                "status": b.status,
                "notes": b.notes,
                "due_date": b.due_date.isoformat() if b.due_date else None,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
        )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "bills": out_bills,
    }


@customer_bill_router.post("/generate")
async def generate_customer_bill(
    data: CustomerBillCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """生成客户账单"""
    return await _execute_customer_bill_generate(db, data)


@customer_bill_router.get("/{bill_id}")
async def get_customer_bill_detail(
    bill_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取客户账单详情"""
    result = await db.execute(
        select(CustomerBill)
        .options(selectinload(CustomerBill.account), selectinload(CustomerBill.details))
        .where(CustomerBill.id == bill_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="账单不存在")
    details = [
        {"country_code": d.country_code, "country_name": d.country_name, "sms_count": d.sms_count,
         "success_count": d.success_count, "unit_price": float(d.unit_price or 0),
         "total_amount": float(d.total_amount or 0)}
        for d in bill.details
    ]
    return {
        "success": True,
        "bill": {
            "id": bill.id, "bill_no": bill.bill_no, "account_id": bill.account_id,
            "account_name": bill.account.account_name if bill.account else None,
            "period_start": bill.period_start.isoformat() if bill.period_start else None,
            "period_end": bill.period_end.isoformat() if bill.period_end else None,
            "total_sms_count": bill.total_sms_count, "total_success_count": bill.total_success_count,
            "total_amount": float(bill.total_amount or 0), "paid_amount": float(bill.paid_amount or 0),
            "outstanding_amount": float(bill.outstanding_amount or 0), "status": bill.status,
            "due_date": bill.due_date.isoformat() if bill.due_date else None,
            "currency": bill.currency, "notes": bill.notes,
            "created_at": bill.created_at.isoformat() if bill.created_at else None,
            "details": details
        }
    }


@customer_bill_router.post("/{bill_id}/pay")
async def pay_customer_bill(
    bill_id: int,
    data: CustomerBillPay,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """客户账单收款（支持部分收款）"""
    bill = await db.get(CustomerBill, bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="账单不存在")
    outstanding = float(bill.outstanding_amount or 0)
    if data.amount > outstanding:
        raise HTTPException(status_code=400, detail=f"收款金额不能超过待付金额 {outstanding:.2f}")
    bill.paid_amount = (bill.paid_amount or 0) + Decimal(str(data.amount))
    bill.outstanding_amount = Decimal(str(outstanding - data.amount))
    bill.status = 'paid' if bill.outstanding_amount <= 0 else 'partial'
    if data.notes:
        bill.notes = (bill.notes or '') + f"\n收款: {data.amount}, {data.notes}"
    await db.commit()
    return {"success": True, "message": "收款成功", "outstanding_amount": float(bill.outstanding_amount)}


# customer_bill_router 已在 main.py 中直接注册到 /api/v1/admin/bills
