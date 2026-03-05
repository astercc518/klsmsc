"""管理员 - 数据商品管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.modules.data.models import DataProduct, DataProductRating
from app.modules.common.account import Account
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

    # 批量获取评分统计
    product_ids = [p.id for p in products]
    rating_map = {}
    if product_ids:
        recent_30d = datetime.utcnow() - timedelta(days=30)
        all_stats = (await db.execute(
            select(
                DataProductRating.product_id,
                func.count().label("total"),
                func.avg(DataProductRating.rating).label("avg"),
                func.max(DataProductRating.rating).label("max"),
            ).where(DataProductRating.product_id.in_(product_ids))
            .group_by(DataProductRating.product_id)
        )).fetchall()
        for s in all_stats:
            rating_map[s.product_id] = {
                "total": s.total, "avg": round(float(s.avg or 0), 1), "max": s.max or 0,
                "recent_avg": 0, "recent_count": 0,
            }

        recent_agg = (await db.execute(
            select(
                DataProductRating.product_id,
                func.avg(DataProductRating.rating).label("avg"),
                func.count().label("cnt"),
            ).where(
                DataProductRating.product_id.in_(product_ids),
                DataProductRating.created_at >= recent_30d,
            ).group_by(DataProductRating.product_id)
        )).fetchall()
        for r in recent_agg:
            if r.product_id in rating_map:
                rating_map[r.product_id]["recent_avg"] = round(float(r.avg or 0), 1)
                rating_map[r.product_id]["recent_count"] = r.cnt

    items = []
    for p in products:
        item = serialize_product(p)
        item["rating"] = rating_map.get(p.id, {"total": 0, "avg": 0, "max": 0, "recent_avg": 0, "recent_count": 0})
        items.append(item)

    return {
        "success": True,
        "items": items,
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


# ============ 评分管理 ============

@router.get("/products/{product_id}/ratings")
async def admin_get_product_ratings(
    product_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """管理员查看商品全部评分"""
    from app.modules.data.models import DataOrder

    stats = (await db.execute(
        select(
            func.count().label("total"),
            func.avg(DataProductRating.rating).label("avg"),
            func.max(DataProductRating.rating).label("max"),
        ).where(DataProductRating.product_id == product_id)
    )).first()

    recent_30d = datetime.utcnow() - timedelta(days=30)
    recent_stats = (await db.execute(
        select(
            func.avg(DataProductRating.rating).label("avg"),
            func.max(DataProductRating.rating).label("max"),
            func.count().label("cnt"),
        ).where(
            DataProductRating.product_id == product_id,
            DataProductRating.created_at >= recent_30d,
        )
    )).first()

    count_q = select(func.count()).select_from(
        select(DataProductRating).where(DataProductRating.product_id == product_id).subquery()
    )
    total = (await db.execute(count_q)).scalar()

    rows = (await db.execute(
        select(DataProductRating, Account.account_name, DataOrder.order_no)
        .outerjoin(Account, DataProductRating.account_id == Account.id)
        .outerjoin(DataOrder, DataProductRating.order_id == DataOrder.id)
        .where(DataProductRating.product_id == product_id)
        .order_by(DataProductRating.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()

    items = []
    for r, account_name, order_no in rows:
        items.append({
            "id": r.id,
            "account_id": r.account_id,
            "account_name": account_name or f"用户#{r.account_id}",
            "order_id": r.order_id,
            "order_no": order_no,
            "rating": r.rating,
            "comment": r.comment,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "success": True,
        "product_id": product_id,
        "stats": {
            "total": stats.total or 0,
            "avg": round(float(stats.avg or 0), 1),
            "max": stats.max or 0,
            "recent_avg": round(float(recent_stats.avg or 0), 1),
            "recent_count": recent_stats.cnt or 0,
        },
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/products/ratings/{rating_id}")
async def admin_update_rating(
    rating_id: int,
    rating: int = Query(..., ge=1, le=5),
    comment: Optional[str] = Query(None, max_length=500),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """管理员修改评分"""
    r = (await db.execute(
        select(DataProductRating).where(DataProductRating.id == rating_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "评分记录不存在")
    r.rating = rating
    if comment is not None:
        r.comment = comment
    await db.commit()
    return {"success": True, "message": "评分已更新"}


@router.delete("/products/ratings/{rating_id}")
async def admin_delete_rating(
    rating_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """管理员删除评分"""
    r = (await db.execute(
        select(DataProductRating).where(DataProductRating.id == rating_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "评分记录不存在")
    await db.delete(r)
    await db.commit()
    return {"success": True, "message": "评分已删除"}
