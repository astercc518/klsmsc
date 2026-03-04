"""结算系统API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
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

router = APIRouter(prefix="/admin/settlements", tags=["结算管理"])


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


def generate_settlement_no() -> str:
    """生成结算单号"""
    now = datetime.now()
    return f"ST{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"


def generate_bill_no() -> str:
    """生成账单号"""
    now = datetime.now()
    return f"BL{now.strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4().hex)[:6].upper()}"


# ============ 供应商结算 ============

@router.get("")
async def get_settlements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取结算单列表"""
    query = select(Settlement).options(selectinload(Settlement.supplier))
    
    if supplier_id:
        query = query.where(Settlement.supplier_id == supplier_id)
    if status:
        query = query.where(Settlement.status == status)
    if start_date:
        query = query.where(Settlement.period_start >= start_date)
    if end_date:
        query = query.where(Settlement.period_end <= end_date)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.order_by(Settlement.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    settlements = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "settlements": [
            {
                "id": s.id,
                "settlement_no": s.settlement_no,
                "supplier_id": s.supplier_id,
                "supplier_name": s.supplier.supplier_name if s.supplier else None,
                "period_start": s.period_start.isoformat() if s.period_start else None,
                "period_end": s.period_end.isoformat() if s.period_end else None,
                "total_sms_count": s.total_sms_count,
                "total_cost": float(s.total_cost) if s.total_cost else 0,
                "adjustment_amount": float(s.adjustment_amount) if s.adjustment_amount else 0,
                "final_amount": float(s.final_amount) if s.final_amount else 0,
                "currency": s.currency,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in settlements
        ]
    }


@router.post("/generate")
async def generate_settlement(
    data: SettlementCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """生成结算单"""
    # 验证供应商
    supplier = await db.get(Supplier, data.supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    # 获取供应商关联的通道
    channels_result = await db.execute(
        select(SupplierChannel.channel_id).where(
            SupplierChannel.supplier_id == data.supplier_id,
            SupplierChannel.status == 'active'
        )
    )
    channel_ids = [c for c in channels_result.scalars().all()]
    
    if not channel_ids:
        raise HTTPException(status_code=400, detail="供应商没有关联的通道")
    
    # 统计短信数据
    stats_query = select(
        SMSLog.channel_id,
        SMSLog.country_code,
        func.count(SMSLog.id).label('total_count'),
        func.sum(func.case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
        func.sum(func.case((SMSLog.status == 'failed', 1), else_=0)).label('failed_count'),
        func.sum(SMSLog.cost_price).label('total_cost')
    ).where(
        SMSLog.channel_id.in_(channel_ids),
        SMSLog.submit_time >= data.period_start,
        SMSLog.submit_time < data.period_end
    ).group_by(SMSLog.channel_id, SMSLog.country_code)
    
    stats_result = await db.execute(stats_query)
    stats_rows = stats_result.all()
    
    # 创建结算单
    total_sms = sum(row.total_count for row in stats_rows)
    total_success = sum(row.success_count or 0 for row in stats_rows)
    total_failed = sum(row.failed_count or 0 for row in stats_rows)
    total_cost = sum(float(row.total_cost or 0) for row in stats_rows)
    
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
        notes=data.notes
    )
    db.add(settlement)
    await db.flush()
    
    # 创建明细
    for row in stats_rows:
        # 获取通道信息
        channel = await db.get(Channel, row.channel_id)
        
        detail = SettlementDetail(
            settlement_id=settlement.id,
            channel_id=row.channel_id,
            country_code=row.country_code,
            sms_count=row.total_count,
            success_count=row.success_count or 0,
            failed_count=row.failed_count or 0,
            unit_cost=float(row.total_cost or 0) / row.total_count if row.total_count > 0 else 0,
            total_cost=row.total_cost or 0
        )
        db.add(detail)
    
    # 记录日志
    log = SettlementLog(
        settlement_id=settlement.id,
        action='create',
        new_status='draft',
        operator_id=admin.id,
        operator_name=admin.username,
        description='创建结算单'
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
        "total_cost": total_cost
    }


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
            func.sum(func.case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
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
            func.sum(func.case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
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
            func.sum(func.case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
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
            func.sum(func.case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
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


@customer_bill_router.get("")
async def get_customer_bills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取客户账单列表"""
    query = select(CustomerBill).options(selectinload(CustomerBill.account))
    
    if account_id:
        query = query.where(CustomerBill.account_id == account_id)
    if status:
        query = query.where(CustomerBill.status == status)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.order_by(CustomerBill.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    bills = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "bills": [
            {
                "id": b.id,
                "bill_no": b.bill_no,
                "account_id": b.account_id,
                "account_name": b.account.account_name if b.account else None,
                "period_start": b.period_start.isoformat() if b.period_start else None,
                "period_end": b.period_end.isoformat() if b.period_end else None,
                "total_sms_count": b.total_sms_count,
                "total_amount": float(b.total_amount) if b.total_amount else 0,
                "paid_amount": float(b.paid_amount) if b.paid_amount else 0,
                "outstanding_amount": float(b.outstanding_amount) if b.outstanding_amount else 0,
                "status": b.status,
                "due_date": b.due_date.isoformat() if b.due_date else None,
                "created_at": b.created_at.isoformat() if b.created_at else None
            }
            for b in bills
        ]
    }


@customer_bill_router.post("/generate")
async def generate_customer_bill(
    account_id: int,
    period_start: datetime,
    period_end: datetime,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """生成客户账单"""
    # 验证账户
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    # 统计短信数据
    stats_query = select(
        SMSLog.country_code,
        func.count(SMSLog.id).label('total_count'),
        func.sum(func.case((SMSLog.status == 'delivered', 1), else_=0)).label('success_count'),
        func.sum(SMSLog.selling_price).label('total_amount')
    ).where(
        SMSLog.account_id == account_id,
        SMSLog.submit_time >= period_start,
        SMSLog.submit_time < period_end
    ).group_by(SMSLog.country_code)
    
    stats_result = await db.execute(stats_query)
    stats_rows = stats_result.all()
    
    # 创建账单
    total_sms = sum(row.total_count for row in stats_rows)
    total_success = sum(row.success_count or 0 for row in stats_rows)
    total_amount = sum(float(row.total_amount or 0) for row in stats_rows)
    
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
        status='draft'
    )
    db.add(bill)
    await db.flush()
    
    # 创建明细
    for row in stats_rows:
        detail = CustomerBillDetail(
            bill_id=bill.id,
            country_code=row.country_code,
            sms_count=row.total_count,
            success_count=row.success_count or 0,
            unit_price=float(row.total_amount or 0) / row.total_count if row.total_count > 0 else 0,
            total_amount=row.total_amount or 0
        )
        db.add(detail)
    
    await db.commit()
    await db.refresh(bill)
    
    return {
        "success": True,
        "message": "客户账单生成成功",
        "bill_id": bill.id,
        "bill_no": bill.bill_no,
        "total_amount": total_amount
    }


router.include_router(customer_bill_router)
