"""管理员 - 数据订单管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.modules.data.models import DataOrder, DataNumber, DataOrderNumber
from app.modules.common.account import Account
from app.core.auth import get_current_admin
from app.utils.logger import get_logger
from app.schemas.data import OrderCancelRequest, OrderRefundRequest
from app.api.v1.data.helpers import serialize_order, serialize_number

logger = get_logger(__name__)
router = APIRouter()


@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    order_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取数据订单列表"""
    query = select(DataOrder).options(
        joinedload(DataOrder.account), joinedload(DataOrder.product)
    )

    if status:
        query = query.where(DataOrder.status == status)
    if account_id:
        query = query.where(DataOrder.account_id == account_id)
    if order_type:
        query = query.where(DataOrder.order_type == order_type)

    count_query = select(func.count()).select_from(select(DataOrder).subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(DataOrder.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.unique().scalars().all()

    return {
        "success": True,
        "items": [serialize_order(o, include_account=True) for o in orders],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/orders/stats")
async def order_stats(
    period: str = Query("month", description="day/week/month"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """订单统计"""
    now = datetime.now()
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_orders = (
        await db.execute(
            select(func.count()).select_from(DataOrder).where(DataOrder.created_at >= start)
        )
    ).scalar() or 0

    completed_orders = (
        await db.execute(
            select(func.count())
            .select_from(DataOrder)
            .where(DataOrder.created_at >= start, DataOrder.status == "completed")
        )
    ).scalar() or 0

    total_quantity = (
        await db.execute(
            select(func.coalesce(func.sum(DataOrder.executed_count), 0))
            .where(DataOrder.created_at >= start, DataOrder.status == "completed")
        )
    ).scalar() or 0

    return {
        "success": True,
        "period": period,
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "total_quantity": total_quantity,
    }


@router.get("/orders/{order_id}")
async def get_order_detail(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取订单详情（含关联号码）"""
    result = await db.execute(
        select(DataOrder)
        .options(joinedload(DataOrder.account), joinedload(DataOrder.product))
        .where(DataOrder.id == order_id)
    )
    order = result.unique().scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 获取关联号码
    number_result = await db.execute(
        select(DataOrderNumber)
        .options(joinedload(DataOrderNumber.number))
        .where(DataOrderNumber.order_id == order_id)
        .limit(100)
    )
    order_numbers = number_result.unique().scalars().all()

    detail = serialize_order(order, include_account=True)
    detail["numbers"] = [
        serialize_number(on.number) for on in order_numbers if on.number
    ]

    return {"success": True, "data": detail}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    data: OrderCancelRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """取消订单（释放号码回公海）"""
    result = await db.execute(select(DataOrder).where(DataOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status not in ("pending", "completed"):
        raise HTTPException(status_code=400, detail=f"当前状态 {order.status} 不允许取消")

    # 释放关联号码回公海
    on_result = await db.execute(
        select(DataOrderNumber).where(DataOrderNumber.order_id == order_id)
    )
    order_nums = on_result.scalars().all()
    for on in order_nums:
        num_result = await db.execute(select(DataNumber).where(DataNumber.id == on.number_id))
        num = num_result.scalar_one_or_none()
        if num:
            num.account_id = None

    order.status = "cancelled"
    order.cancel_reason = data.reason
    await db.commit()

    return {"success": True, "message": "订单已取消", "released_numbers": len(order_nums)}


@router.post("/orders/{order_id}/refund")
async def refund_order(
    order_id: int,
    data: OrderRefundRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """退款（释放号码 + 返还余额）"""
    result = await db.execute(
        select(DataOrder).options(joinedload(DataOrder.account)).where(DataOrder.id == order_id)
    )
    order = result.unique().scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="订单已取消")
    if order.refunded_at:
        raise HTTPException(status_code=400, detail="订单已退款")

    refund = float(data.refund_amount or order.total_price or 0)

    # 返还余额
    if order.account and refund > 0:
        order.account.balance = float(order.account.balance or 0) + refund

    # 释放号码
    on_result = await db.execute(
        select(DataOrderNumber).where(DataOrderNumber.order_id == order_id)
    )
    order_nums = on_result.scalars().all()
    for on in order_nums:
        num_result = await db.execute(select(DataNumber).where(DataNumber.id == on.number_id))
        num = num_result.scalar_one_or_none()
        if num:
            num.account_id = None

    order.status = "cancelled"
    order.cancel_reason = data.reason or "管理员退款"
    order.refund_amount = str(refund)
    order.refunded_at = datetime.now()
    await db.commit()

    return {
        "success": True,
        "message": "退款成功",
        "refund_amount": refund,
        "released_numbers": len(order_nums),
    }
