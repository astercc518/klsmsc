"""销售佣金结算 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models.settlement import SalesCommissionSettlement, SalesCommissionDetail
from app.modules.common.account import Account
from app.api.v1.admin import get_current_admin
from app.modules.common.admin_user import AdminUser
from app.core.commission import (
    calculate_sales_commission,
    create_commission_settlement,
)

router = APIRouter(prefix="/admin/sales-commission", tags=["销售佣金"])


class CommissionPay(BaseModel):
    payment_method: str = Field(..., description="支付方式")
    payment_reference: Optional[str] = Field(None, description="支付凭证/流水号")
    notes: Optional[str] = None


# ============ 列表与汇总 ============

@router.get("/summary")
async def get_commission_summary(
    sales_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """获取销售佣金结算汇总"""
    query = select(
        func.count(SalesCommissionSettlement.id).label("total_count"),
        func.coalesce(func.sum(SalesCommissionSettlement.commission_amount), 0).label("total_amount"),
        func.sum(case((SalesCommissionSettlement.status == 'draft', 1), else_=0)).label("draft_count"),
        func.sum(case((SalesCommissionSettlement.status == 'confirmed', 1), else_=0)).label("confirmed_count"),
        func.sum(case((SalesCommissionSettlement.status == 'paid', 1), else_=0)).label("paid_count"),
    ).select_from(SalesCommissionSettlement)

    if sales_id:
        query = query.where(SalesCommissionSettlement.sales_id == sales_id)
    if status:
        query = query.where(SalesCommissionSettlement.status == status)
    if start_date:
        query = query.where(SalesCommissionSettlement.period_start >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        end_dt = datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)
        query = query.where(SalesCommissionSettlement.period_start < end_dt)

    row = (await db.execute(query)).first()
    return {
        "success": True,
        "summary": {
            "total_count": row.total_count or 0,
            "total_amount": float(row.total_amount or 0),
            "draft_count": row.draft_count or 0,
            "confirmed_count": row.confirmed_count or 0,
            "paid_count": row.paid_count or 0,
        }
    }


@router.get("")
async def get_commission_settlements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sales_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """获取销售佣金结算单列表"""
    query = select(SalesCommissionSettlement).options(
        selectinload(SalesCommissionSettlement.sales)
    )

    if sales_id:
        query = query.where(SalesCommissionSettlement.sales_id == sales_id)
    if status:
        query = query.where(SalesCommissionSettlement.status == status)
    if start_date:
        query = query.where(SalesCommissionSettlement.period_start >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        end_dt = datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)
        query = query.where(SalesCommissionSettlement.period_start < end_dt)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(SalesCommissionSettlement.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "settlements": [
            {
                "id": s.id,
                "settlement_no": s.settlement_no,
                "sales_id": s.sales_id,
                "sales_name": s.sales.real_name or s.sales.username if s.sales else None,
                "period_start": s.period_start.isoformat() if s.period_start else None,
                "period_end": s.period_end.isoformat() if s.period_end else None,
                "total_sms_count": s.total_sms_count,
                "total_revenue": float(s.total_revenue or 0),
                "commission_rate": float(s.commission_rate or 0),
                "commission_amount": float(s.commission_amount or 0),
                "currency": s.currency,
                "status": s.status,
                "paid_at": s.paid_at.isoformat() if s.paid_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in items
        ]
    }


# ============ 生成结算单 ============

@router.post("/generate")
async def generate_commission_settlement(
    sales_id: int = Query(..., description="销售ID"),
    year: int = Query(..., description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """手动生成指定销售、指定月份的佣金结算单"""
    period_start = datetime(year, month, 1, 0, 0, 0)
    if month == 12:
        from datetime import timedelta
        period_end = datetime(year + 1, 1, 1, 0, 0, 0) - timedelta(seconds=1)
    else:
        from datetime import timedelta
        period_end = datetime(year, month + 1, 1, 0, 0, 0) - timedelta(seconds=1)

    settlement = await create_commission_settlement(db, period_start, period_end, sales_id)
    if not settlement:
        raise HTTPException(status_code=400, detail="该周期已有结算单或无需结算（无佣金）")

    return {
        "success": True,
        "message": "佣金结算单生成成功",
        "settlement_id": settlement.id,
        "settlement_no": settlement.settlement_no,
        "commission_amount": float(settlement.commission_amount),
    }


# ============ 详情 ============

@router.get("/{settlement_id}")
async def get_commission_settlement_detail(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """获取销售佣金结算单详情"""
    result = await db.execute(
        select(SalesCommissionSettlement)
        .options(
            selectinload(SalesCommissionSettlement.sales),
            selectinload(SalesCommissionSettlement.details).selectinload(SalesCommissionDetail.account),
        )
        .where(SalesCommissionSettlement.id == settlement_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="结算单不存在")

    details = []
    for d in s.details:
        details.append({
            "account_id": d.account_id,
            "account_name": d.account.account_name if d.account else None,
            "total_sms_count": d.total_sms_count,
            "total_revenue": float(d.total_revenue or 0),
            "commission_rate": float(d.commission_rate or 0),
            "commission_amount": float(d.commission_amount or 0),
        })

    return {
        "success": True,
        "settlement": {
            "id": s.id,
            "settlement_no": s.settlement_no,
            "sales_id": s.sales_id,
            "sales_name": s.sales.real_name or s.sales.username if s.sales else None,
            "period_start": s.period_start.isoformat() if s.period_start else None,
            "period_end": s.period_end.isoformat() if s.period_end else None,
            "total_sms_count": s.total_sms_count,
            "total_revenue": float(s.total_revenue or 0),
            "commission_rate": float(s.commission_rate or 0),
            "commission_amount": float(s.commission_amount or 0),
            "currency": s.currency,
            "status": s.status,
            "payment_method": s.payment_method,
            "payment_reference": s.payment_reference,
            "paid_at": s.paid_at.isoformat() if s.paid_at else None,
            "notes": s.notes,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "details": details,
        }
    }


# ============ 确认 ============

@router.post("/{settlement_id}/confirm")
async def confirm_commission_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """确认佣金结算单"""
    s = await db.get(SalesCommissionSettlement, settlement_id)
    if not s:
        raise HTTPException(status_code=404, detail="结算单不存在")
    if s.status != 'draft':
        raise HTTPException(status_code=400, detail="只有草稿状态可确认")

    s.status = 'confirmed'
    await db.commit()
    return {"success": True, "message": "已确认"}


# ============ 支付 ============

@router.post("/{settlement_id}/pay")
async def pay_commission_settlement(
    settlement_id: int,
    data: CommissionPay,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """支付佣金结算单"""
    s = await db.get(SalesCommissionSettlement, settlement_id)
    if not s:
        raise HTTPException(status_code=404, detail="结算单不存在")
    if s.status != 'confirmed':
        raise HTTPException(status_code=400, detail="只有已确认状态可支付")

    s.status = 'paid'
    s.payment_method = data.payment_method
    s.payment_reference = data.payment_reference
    s.paid_by = admin.id
    s.paid_at = datetime.now()
    if data.notes:
        s.notes = (s.notes or '') + '\n' + data.notes

    await db.commit()
    return {"success": True, "message": "已支付"}


# ============ 取消 ============

@router.post("/{settlement_id}/cancel")
async def cancel_commission_settlement(
    settlement_id: int,
    reason: str = Query(..., description="取消原因"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """取消佣金结算单"""
    s = await db.get(SalesCommissionSettlement, settlement_id)
    if not s:
        raise HTTPException(status_code=404, detail="结算单不存在")
    if s.status == 'paid':
        raise HTTPException(status_code=400, detail="已支付不可取消")

    s.status = 'cancelled'
    if reason:
        s.notes = (s.notes or '') + f'\n取消原因: {reason}'
    await db.commit()
    return {"success": True, "message": "已取消"}
