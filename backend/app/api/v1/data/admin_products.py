"""管理员 - 数据商品管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.database import get_db
from app.modules.data.models import DataProduct
from app.core.auth import get_current_admin
from app.utils.logger import get_logger
from app.schemas.data import ProductCreate, ProductUpdate
from app.api.v1.data.helpers import calculate_stock, serialize_product

logger = get_logger(__name__)
router = APIRouter()


@router.get("/products")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    product_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取数据商品列表"""
    query = select(DataProduct).where(DataProduct.is_deleted == False)

    if status:
        query = query.where(DataProduct.status == status)
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


@router.post("/products")
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """创建数据商品（支持纯数据/组合套餐/买即发）"""
    existing = await db.execute(
        select(DataProduct).where(DataProduct.product_code == data.product_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="商品编码已存在")

    stock_count = await calculate_stock(db, data.filter_criteria)

    product = DataProduct(
        product_code=data.product_code,
        product_name=data.product_name,
        description=data.description,
        filter_criteria=data.filter_criteria,
        price_per_number=data.price_per_number,
        currency=data.currency,
        stock_count=stock_count,
        min_purchase=data.min_purchase,
        max_purchase=data.max_purchase,
        product_type=data.product_type,
        sms_quota=data.sms_quota,
        sms_unit_price=data.sms_unit_price,
        bundle_price=data.bundle_price,
        bundle_discount=data.bundle_discount,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    return {
        "success": True,
        "id": product.id,
        "product_code": product.product_code,
        "stock_count": stock_count,
    }


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """更新数据商品"""
    result = await db.execute(select(DataProduct).where(DataProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)

    if data.filter_criteria:
        product.stock_count = await calculate_stock(db, data.filter_criteria)

    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """删除数据商品(软删除)"""
    result = await db.execute(select(DataProduct).where(DataProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    product.is_deleted = True
    await db.commit()
    return {"success": True, "message": "删除成功"}


@router.post("/products/{product_id}/refresh-stock")
async def refresh_product_stock(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """刷新商品库存"""
    result = await db.execute(select(DataProduct).where(DataProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    stock_count = await calculate_stock(db, product.filter_criteria)
    product.stock_count = stock_count
    if stock_count > 0 and product.status == 'sold_out':
        product.status = 'active'
    elif stock_count == 0 and product.status == 'active':
        product.status = 'sold_out'
    await db.commit()

    return {"success": True, "stock_count": stock_count, "status": product.status}
