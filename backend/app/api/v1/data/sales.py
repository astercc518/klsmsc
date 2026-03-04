"""销售角色 - 数据业务 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from typing import Optional

from app.database import get_db
from app.modules.data.models import DataProduct, DataOrder
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.core.auth import get_current_admin
from app.utils.logger import get_logger
from app.api.v1.data.helpers import serialize_product, serialize_order

logger = get_logger(__name__)
router = APIRouter()

SALES_ROLES = ("sales", "admin", "super_admin")


def _check_sales_role(admin: AdminUser):
    if admin.role not in SALES_ROLES:
        raise HTTPException(status_code=403, detail="需要销售或管理员权限")


@router.get("/products")
async def sales_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """销售查看全部数据商品"""
    _check_sales_role(admin)

    query = select(DataProduct).where(
        DataProduct.is_deleted == False, DataProduct.status == "active"
    )
    if product_type:
        query = query.where(DataProduct.product_type == product_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(DataProduct.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()

    return {
        "success": True,
        "items": [serialize_product(p) for p in products],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/orders")
async def sales_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """销售查看归属客户的订单"""
    _check_sales_role(admin)

    query = select(DataOrder).options(
        joinedload(DataOrder.account), joinedload(DataOrder.product)
    )

    # 普通销售只能看到自己归属客户的订单
    if admin.role == "sales":
        query = query.join(Account, DataOrder.account_id == Account.id).where(
            Account.sales_id == admin.id
        )

    if status:
        query = query.where(DataOrder.status == status)
    if account_id:
        query = query.where(DataOrder.account_id == account_id)

    base_query = select(DataOrder)
    if admin.role == "sales":
        base_query = base_query.join(Account, DataOrder.account_id == Account.id).where(
            Account.sales_id == admin.id
        )
    count_query = select(func.count()).select_from(base_query.subquery())
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


@router.get("/customers")
async def sales_list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """销售查看归属客户的数据购买概况"""
    _check_sales_role(admin)

    # 获取有数据订单的客户列表
    base = select(
        DataOrder.account_id,
        func.count(DataOrder.id).label("order_count"),
        func.coalesce(func.sum(DataOrder.executed_count), 0).label("total_numbers"),
    ).group_by(DataOrder.account_id)

    if admin.role == "sales":
        base = base.join(Account, DataOrder.account_id == Account.id).where(
            Account.sales_id == admin.id
        )

    subq = base.subquery()

    query = (
        select(Account, subq.c.order_count, subq.c.total_numbers)
        .join(subq, Account.id == subq.c.account_id)
        .order_by(subq.c.total_numbers.desc())
    )

    count_sq = select(func.count()).select_from(subq)
    total = (await db.execute(count_sq)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.all()

    return {
        "success": True,
        "items": [
            {
                "account_id": acc.id,
                "account_name": getattr(acc, "account_name", None) or getattr(acc, "username", None),
                "email": acc.email,
                "order_count": order_count,
                "total_numbers": total_numbers,
            }
            for acc, order_count, total_numbers in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
