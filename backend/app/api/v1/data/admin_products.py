"""管理员 - 数据商品管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime, timedelta
import uuid

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

    query = query.order_by(DataProduct.created_at.desc())
    # 多取以应对去重（重复上传的只显示一个）
    fetch_limit = max(500, page * page_size * 4)
    result = await db.execute(query.limit(fetch_limit))
    all_fetched = result.scalars().all()

    # 同 (country, source, purpose, freshness) 保留一个：优先在售 > 库存高 > 新
    def _filter_key(p):
        fc = p.filter_criteria or {}
        return (fc.get("country") or "", fc.get("source") or "", fc.get("purpose") or "", fc.get("freshness") or "")

    seen, order_list = {}, []
    for p in all_fetched:
        k = _filter_key(p)
        if k == ("", "", "", ""):
            key = f"_no_filter_{p.id}"
            seen[key] = p
            order_list.append(key)
            continue
        if k not in seen:
            seen[k] = p
            order_list.append(k)
        else:
            cur = seen[k]
            cur_score = (1 if cur.status in ("active", "inactive") else 0, cur.stock_count or 0, cur.id)
            new_score = (1 if p.status in ("active", "inactive") else 0, p.stock_count or 0, p.id)
            if new_score > cur_score:
                seen[k] = p

    products = [seen[k] for k in order_list]
    total = len(products)
    products = products[(page - 1) * page_size : page * page_size]

    # 批量获取评分统计
    product_ids = [p.id for p in products]
    rating_map = {}
    if product_ids:
        recent_30d = datetime.now() - timedelta(days=30)
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
    """删除数据商品(软删除)，同时删除关联的号码数据（已售出号码保留）"""
    try:
        from sqlalchemy import delete, and_, select
        from app.modules.data.models import DataNumber, DataOrderNumber
        from app.api.v1.data.helpers import freshness_to_date_range

        result = await db.execute(select(DataProduct).where(DataProduct.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在")

        # 按商品筛选条件删除关联号码
        fc = product.filter_criteria or {}
        conditions = []
        if fc.get("batch_id"):
            conditions.append(DataNumber.batch_id == fc["batch_id"])
        else:
            if fc.get("country"):
                conditions.append(DataNumber.country_code == fc["country"])
            if fc.get("source"):
                conditions.append(DataNumber.source == fc["source"])
            if fc.get("purpose"):
                conditions.append(DataNumber.purpose == fc["purpose"])
            if fc.get("freshness"):
                start_date, end_date = freshness_to_date_range(fc["freshness"])
                if start_date and end_date:
                    conditions.append(DataNumber.data_date.between(start_date, end_date))
                elif end_date:
                    from sqlalchemy import or_
                    conditions.append(or_(DataNumber.data_date.is_(None), DataNumber.data_date < end_date))

        deleted_numbers = 0
        if conditions:  # 仅当有明确筛选条件时才删除，避免误删；排除已售出号码避免外键约束
            used_subq = select(DataOrderNumber.number_id).distinct()
            conditions.append(DataNumber.id.not_in(used_subq))
            stmt = delete(DataNumber).where(and_(*conditions))
            r = await db.execute(stmt)
            deleted_numbers = r.rowcount
            logger.info(f"删除商品 {product_id} 同时删除关联号码 {deleted_numbers} 条")

        product.is_deleted = True
        await db.commit()
        return {"success": True, "deleted_numbers": deleted_numbers, "message": f"商品已删除，同时删除 {deleted_numbers} 条关联号码"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除商品 {product_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e) or "删除失败，请稍后重试")


@router.post("/products/sync-from-pool")
async def sync_products_from_pool(
    country_code: Optional[str] = Query(None, description="仅处理指定国家，不传则处理全部"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """从号码池补充缺失的商品：对有数据但无对应商品的国家+来源+用途组合创建商品"""
    from app.modules.data.models import DataNumber, DataPricingTemplate, DataProduct
    from app.modules.data.models import SOURCE_LABELS, PURPOSE_LABELS, FRESHNESS_LABELS

    # 查询号码池中 (country_code, source, purpose) 的组合及数量
    q = (
        select(DataNumber.country_code, DataNumber.source, DataNumber.purpose, func.count().label("cnt"))
        .where(DataNumber.status == "active", DataNumber.source.isnot(None), DataNumber.purpose.isnot(None))
        .group_by(DataNumber.country_code, DataNumber.source, DataNumber.purpose)
    )
    if country_code:
        q = q.where(DataNumber.country_code == country_code.upper())
    pool_rows = (await db.execute(q)).fetchall()

    created = []
    for row in pool_rows:
        cc, src, pur = row.country_code, row.source, row.purpose
        if not cc or not src or not pur:
            continue
        cnt = row.cnt or 0
        if cnt <= 0:
            continue

        # 查找匹配的定价模板（优先国家专属，再通配符）
        for fresh in ("30day", "7day", "3day", "history"):
            tpl_q = select(DataPricingTemplate).where(
                DataPricingTemplate.source == src,
                DataPricingTemplate.purpose == pur,
                DataPricingTemplate.freshness == fresh,
                DataPricingTemplate.status == "active",
            )
            tpl_result = (await db.execute(tpl_q)).scalars().all()
            tpl = next((t for t in tpl_result if t.country_code == cc), None)
            if not tpl:
                tpl = next((t for t in tpl_result if t.country_code == "*"), None)
            if tpl:
                break
        else:
            continue

        filter_criteria = {"source": src, "purpose": pur, "freshness": tpl.freshness, "country": cc}
        stock = await calculate_stock(db, filter_criteria)

        # 检查是否已有对应商品（排除已售罄：有上架中的则不创建；仅有售罄的则刷新其库存，避免重复）
        exist_q = select(DataProduct).where(
            DataProduct.is_deleted == False,
            DataProduct.filter_criteria.isnot(None),
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.country")) == cc,
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.source")) == src,
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.purpose")) == pur,
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.freshness")) == tpl.freshness,
        )
        existings = (await db.execute(exist_q)).scalars().all()
        active_one = next((e for e in existings if e.status in ("active", "inactive")), None)
        sold_out_one = next((e for e in existings if e.status == "sold_out"), None)

        if active_one:
            continue  # 已有在售商品，不再创建

        if sold_out_one and stock > 0:
            # 仅有售罄的，刷新其库存并上架，不新建
            sold_out_one.stock_count = stock
            sold_out_one.status = "active"
            sold_out_one.max_purchase = max(stock, 100000)
            await db.commit()
            created.append({"product_code": sold_out_one.product_code, "product_name": sold_out_one.product_name, "stock_count": stock, "action": "revived"})
            logger.info(f"复售商品: {sold_out_one.product_code} 库存={stock}")
            continue

        if existings:
            continue  # 有其他状态且无库存，跳过

        # 无任何现有商品，新建
        suffix = uuid.uuid4().hex[:6].upper()
        code = f"AUTO-{cc}-{src}-{pur}-{tpl.freshness}-{suffix}"
        reg_map = {
            "IT": "意大利", "VN": "越南", "PH": "菲律宾", "CN": "中国", "US": "美国",
            "CO": "哥伦比亚", "MX": "墨西哥", "IN": "印度", "TH": "泰国", "DE": "德国", "FR": "法国",
        }
        cname = reg_map.get(cc, cc)
        name = f"{cname}-{SOURCE_LABELS.get(src, src)}-{PURPOSE_LABELS.get(pur, pur)}-{FRESHNESS_LABELS.get(tpl.freshness, tpl.freshness)}"
        product = DataProduct(
            product_code=code,
            product_name=name,
            description=f"从号码池同步: {cc} {src} {pur}",
            filter_criteria=filter_criteria,
            price_per_number=tpl.price_per_number,
            stock_count=stock,
            min_purchase=10,
            max_purchase=max(stock, 100000),
            product_type="data_only",
            status="active" if stock > 0 else "sold_out",
        )
        db.add(product)
        await db.commit()
        created.append({"product_code": code, "product_name": name, "stock_count": stock})
        logger.info(f"补充商品: {code} 库存={stock}")

    return {"success": True, "created": created, "message": f"已创建 {len(created)} 个商品"}


@router.post("/products/{product_id}/assign-pool-numbers")
async def assign_pool_numbers_to_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """将池中同国家+用途但不同来源的号码划入本商品（更新来源），适用于售罄商品"""
    from sqlalchemy import update, and_
    from app.modules.data.models import DataNumber

    result = await db.execute(select(DataProduct).where(DataProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    fc = product.filter_criteria or {}
    country = fc.get("country")
    target_source = fc.get("source")
    purpose = fc.get("purpose")
    if not country or not target_source:
        raise HTTPException(status_code=400, detail="商品筛选条件不足")

    # 将池中 (country, purpose) 匹配但 source 不同的号码改为 target_source
    stmt = update(DataNumber).where(
        and_(
            DataNumber.country_code == country,
            DataNumber.purpose == purpose,
            DataNumber.source != target_source,
            DataNumber.source.isnot(None),
            DataNumber.status == "active",
        )
    ).values(source=target_source)
    r = await db.execute(stmt)
    await db.commit()
    updated = r.rowcount

    # 刷新商品库存
    stock = await calculate_stock(db, fc, public_only=True)

    # 若划入成功但库存仍为 0（时效不匹配），尝试放宽时效：30day -> history
    old_fresh = fc.get("freshness", "")
    if updated > 0 and stock == 0:
        from app.modules.data.models import FRESHNESS_LABELS
        for try_fresh in ("30day", "history"):
            fc_try = {**fc, "freshness": try_fresh}
            stock_try = await calculate_stock(db, fc_try, public_only=True)
            if stock_try > 0:
                fc["freshness"] = try_fresh
                product.filter_criteria = fc
                old_label = FRESHNESS_LABELS.get(old_fresh, old_fresh)
                new_label = FRESHNESS_LABELS.get(try_fresh, try_fresh)
                if old_label and new_label and old_label != new_label:
                    product.product_name = (product.product_name or "").replace(old_label, new_label)
                stock = stock_try
                break

    product.stock_count = stock
    if stock > 0:
        product.status = "active"
    product.max_purchase = max(stock, 100000)
    await db.commit()

    msg = f"已划入 {updated} 条号码，当前库存 {stock}"
    if updated > 0 and stock == 0:
        msg += "（划入的号码时效均不满足 3/7/30日 或历史，未计入）"
    return {"success": True, "updated": updated, "stock_count": stock, "message": msg}


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

    recent_30d = datetime.now() - timedelta(days=30)
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
