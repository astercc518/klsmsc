"""数据业务模块API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import joinedload
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel
import uuid
import csv
import io
import phonenumbers

from app.database import get_db
from app.modules.data.models import DataNumber, DataProduct, DataOrder, DataImportBatch
from app.modules.common.account import Account
from app.utils.logger import get_logger
from app.core.auth import get_current_admin, get_current_account

logger = get_logger(__name__)

# ============ 路由定义 ============
admin_router = APIRouter(prefix="/admin/data", tags=["数据管理-管理员"])
customer_router = APIRouter(prefix="/data", tags=["数据业务-客户"])


# ============ Pydantic模型 ============
class ProductCreate(BaseModel):
    product_code: str
    product_name: str
    description: Optional[str] = None
    filter_criteria: dict
    price_per_number: str = "0.001"
    currency: str = "USD"
    min_purchase: int = 100
    max_purchase: int = 100000


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    description: Optional[str] = None
    filter_criteria: Optional[dict] = None
    price_per_number: Optional[str] = None
    min_purchase: Optional[int] = None
    max_purchase: Optional[int] = None
    status: Optional[str] = None



class DataOrderCreate(BaseModel):
    product_id: Optional[int] = None
    filter_criteria: Optional[dict] = None
    quantity: int


class DataBuyAndSend(BaseModel):
    product_id: Optional[int] = None
    filter_criteria: Optional[dict] = None
    quantity: int
    message: str


class FilterCriteria(BaseModel):
    country: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = "active"
    exclude_used_days: Optional[int] = None  # 排除N天内使用过的号码


# ============ 管理员API ============

@admin_router.get("/numbers")
async def list_data_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    batch_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取号码资源池列表"""
    query = select(DataNumber)
    
    if country:
        query = query.where(DataNumber.country_code == country)
    if status:
        query = query.where(DataNumber.status == status)
    if tag:
        query = query.where(DataNumber.tags.contains([tag]))
    if batch_id:
        query = query.where(DataNumber.batch_id == batch_id)
    
    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    numbers = result.scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": n.id,
            "phone_number": n.phone_number,
            "country_code": n.country_code,
            "tags": n.tags or [],
            "status": n.status,
            "source": n.source,
            "batch_id": n.batch_id,
            "use_count": n.use_count,
            "last_used_at": n.last_used_at.isoformat() if n.last_used_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None
        } for n in numbers],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@admin_router.get("/numbers/stats")
async def get_number_stats(
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取号码资源统计"""
    # 按国家统计
    country_stats = await db.execute(
        select(DataNumber.country_code, func.count(DataNumber.id))
        .group_by(DataNumber.country_code)
    )
    country_data = {row[0]: row[1] for row in country_stats.fetchall()}
    
    # 按状态统计
    status_stats = await db.execute(
        select(DataNumber.status, func.count(DataNumber.id))
        .group_by(DataNumber.status)
    )
    status_data = {row[0]: row[1] for row in status_stats.fetchall()}
    
    # 总数
    total = await db.execute(select(func.count(DataNumber.id)))
    
    return {
        "success": True,
        "total": total.scalar() or 0,
        "by_country": country_data,
        "by_status": status_data
    }


@admin_router.post("/numbers/import")
async def import_numbers(
    file: UploadFile = File(...),
    source: Optional[str] = Query(None),
    default_tags: Optional[str] = Query(None, description="默认标签，逗号分隔"),
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """批量导入号码数据"""
    batch_id = f"IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    
    # 创建导入批次记录
    import_batch = DataImportBatch(
        batch_id=batch_id,
        file_name=file.filename,
        source=source or "manual_upload",
        status="processing",
        created_by=admin.id
    )
    db.add(import_batch)
    
    tags = [t.strip() for t in default_tags.split(",")] if default_tags else []
    
    try:
        content = await file.read()
        text = content.decode('utf-8')
        reader = csv.reader(io.StringIO(text))
        
        total_count = 0
        valid_count = 0
        duplicate_count = 0
        invalid_count = 0
        
        for row in reader:
            total_count += 1
            if not row or not row[0].strip():
                invalid_count += 1
                continue
            
            phone = row[0].strip()
            row_tags = tags.copy()
            row_country = None
            row_carrier = None
            
            # 解析CSV列: 手机号, [国家], [标签], [运营商]
            if len(row) > 1 and row[1].strip():
                row_country = row[1].strip()
            if len(row) > 2 and row[2].strip():
                row_tags.extend([t.strip() for t in row[2].split("|")])
            if len(row) > 3 and row[3].strip():
                 row_carrier = row[3].strip()
            
            # 解析手机号
            try:
                if not phone.startswith('+'):
                    phone = '+' + phone
                parsed = phonenumbers.parse(phone, None)
                if not phonenumbers.is_valid_number(parsed):
                    invalid_count += 1
                    continue
                
                phone_e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                country_code = row_country or phonenumbers.region_code_for_number(parsed)
            except:
                invalid_count += 1
                continue
            
            # 检查重复
            existing = await db.execute(
                select(DataNumber).where(DataNumber.phone_number == phone_e164)
            )
            if existing.scalar_one_or_none():
                duplicate_count += 1
                continue
            
            # 创建记录
            number = DataNumber(
                phone_number=phone_e164,
                country_code=country_code,
                tags=row_tags if row_tags else None,
                carrier=row_carrier,
                status="active",
                source=source or "manual_upload",
                batch_id=batch_id
            )
            db.add(number)
            valid_count += 1
        
        # 更新批次统计
        import_batch.total_count = total_count
        import_batch.valid_count = valid_count
        import_batch.duplicate_count = duplicate_count
        import_batch.invalid_count = invalid_count
        import_batch.status = "completed"
        import_batch.completed_at = datetime.now()
        
        await db.commit()
        
        return {
            "success": True,
            "batch_id": batch_id,
            "total_count": total_count,
            "valid_count": valid_count
        }
    except Exception as e:
        import_batch.status = "failed"
        import_batch.error_message = str(e)
        await db.commit()
        logger.error(f"导入号码失败: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")

# ... (Previous code)

@customer_router.get("/my-numbers")
async def get_my_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country: Optional[str] = None,
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """获取我的私有库号码"""
    query = select(DataNumber).where(DataNumber.account_id == account.id)
    
    if country:
        query = query.where(DataNumber.country_code == country)
    if tag:
        query = query.where(DataNumber.tags.contains([tag]))
        
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    query = query.order_by(DataNumber.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    numbers = result.scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": n.id,
            "phone_number": n.phone_number,
            "country_code": n.country_code,
            "carrier": n.carrier,
            "tags": n.tags,
            "source": n.source,
            "last_used_at": n.last_used_at
        } for n in numbers],
        "total": total,
        "page": page,
        "page_size": page_size
    }

@customer_router.post("/buy-to-stock")
async def buy_to_stock(
    data: DataOrderCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """购买数据到私有库(不立即发送)"""
    # 逻辑同create_data_order，但需要执行所有权转移
    # ... (Create order logic similar to create_order, but we must EXECUTE it too)
    
    # 1. 验证和计算 (简略，复用逻辑)
    if data.product_id:
        product_result = await db.execute(
            select(DataProduct).where(
                DataProduct.id == data.product_id,
                DataProduct.status == 'active',
                DataProduct.is_deleted == False
            )
        )
        product = product_result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在或已下架")
        if data.quantity < product.min_purchase:
            raise HTTPException(status_code=400, detail=f"最小购买量: {product.min_purchase}")
        if data.quantity > product.max_purchase:
            raise HTTPException(status_code=400, detail=f"最大购买量: {product.max_purchase}")
        filter_criteria = product.filter_criteria
        unit_price = product.price_per_number
    elif data.filter_criteria:
        filter_criteria = data.filter_criteria
        unit_price = "0.001" # Default
    else:
        raise HTTPException(400, "Missing criteria")
        
    # 2. Check Public Stock
    available_count = await calculate_stock(db, filter_criteria, public_only=True)
    if available_count < data.quantity:
        raise HTTPException(400, f"Public stock insufficient: {available_count}")
        
    # 3. Cost
    total_price = float(unit_price) * data.quantity
    if float(account.balance or 0) < total_price:
        raise HTTPException(400, "Insufficient balance")
        
    # 4. Create Order
    order_no = f"DO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    order = DataOrder(
        order_no=order_no,
        account_id=account.id,
        product_id=data.product_id,
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=str(unit_price),
        total_price=str(total_price),
        status="completed",
        executed_count=data.quantity,
        executed_at=datetime.now()
    )
    db.add(order)
    
    # 5. Deduct Balance
    account.balance = float(account.balance) - total_price
    
    # 6. Transfer Ownership (Public -> Private)
    query = build_filter_query(filter_criteria, public_only=True).limit(data.quantity)
    result = await db.execute(query)
    numbers = result.scalars().all()
    
    for num in numbers:
        num.account_id = account.id # Claim ownership
        # Don't update last_used_at yet since it's just stocking
        
    await db.commit()
    return {"success": True, "message": f"Purchased {len(numbers)} numbers to Private Pool"}
    

@customer_router.post("/buy-and-send")
async def buy_and_send(
    data: DataBuyAndSend,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """购买数据并立即发送短信"""
    # 1. 验证商品或筛选条件
    if data.product_id:
        product_result = await db.execute(
            select(DataProduct).where(
                DataProduct.id == data.product_id,
                DataProduct.status == 'active',
                DataProduct.is_deleted == False
            )
        )
        product = product_result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在或已下架")
        if data.quantity < product.min_purchase:
            raise HTTPException(status_code=400, detail=f"最小购买量: {product.min_purchase}")
        if data.quantity > product.max_purchase:
            raise HTTPException(status_code=400, detail=f"最大购买量: {product.max_purchase}")
        filter_criteria = product.filter_criteria
        unit_price = product.price_per_number
    elif data.filter_criteria:
        product = None
        filter_criteria = data.filter_criteria
        unit_price = "0.001"
    else:
        raise HTTPException(status_code=400, detail="缺少商品或筛选条件")

    # 2. Check Public Stock
    available_count = await calculate_stock(db, filter_criteria, public_only=True)
    if available_count < data.quantity:
        raise HTTPException(status_code=400, detail=f"库存不足，当前可用: {available_count}")
    
    # 3. Cost
    data_cost = float(unit_price) * data.quantity
    if float(account.balance or 0) < data_cost:
        raise HTTPException(status_code=400, detail="余额不足")
    
    # 4. Order
    order_no = f"DO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    order = DataOrder(
        order_no=order_no,
        account_id=account.id,
        product_id=data.product_id,
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=str(unit_price),
        total_price=str(data_cost),
        status="completed",
        executed_count=data.quantity,
        executed_at=datetime.now()
    )
    db.add(order)
    
    # 5. Deduct Balance
    account.balance = float(account.balance) - data_cost
    
    # 6. Lock Numbers (Claim Ownership)
    query = build_filter_query(filter_criteria, public_only=True).limit(data.quantity)
    result = await db.execute(query)
    numbers = result.scalars().all()
    
    # 7. SMS Batch
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.sms_log import SMSLog
    
    batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    sms_batch = SmsBatch(
        batch_id=batch_id,
        account_id=account.id,
        batch_name=f"DataSend-{product.product_name if product else 'Custom'}-{datetime.now().strftime('%m%d')}",
        total_count=len(numbers),
        status=BatchStatus.processing
    )
    db.add(sms_batch)
    
    # 8. SMS Logs & Number Updates
    for num in numbers:
        num.account_id = account.id  # Claim ownership (Private Pool)
        num.last_used_at = datetime.now()
        num.use_count = (num.use_count or 0) + 1
        
        sms = SMSLog(
            account_id=account.id,
            batch_id=batch_id,
            phone_number=num.phone_number,
            message=data.message,
            status='pending',
            submit_time=datetime.now()
        )
        db.add(sms)
        
    await db.commit()
    
    return {
        "success": True,
        "message": f"成功购买 {len(numbers)} 条数据并创建发送任务",
        "batch_id": batch_id
    }

# ============ 辅助函数 ============

def build_filter_query(filter_criteria: dict, public_only: bool = False):
    """根据筛选条件构建查询"""
    query = select(DataNumber).where(DataNumber.status == 'active')
    
    if public_only:
        # 只查询公海(无主)数据
        query = query.where(DataNumber.account_id.is_(None))
    
    # 基础筛选
    if filter_criteria.get('country'):
        query = query.where(DataNumber.country_code == filter_criteria['country'])
    
    if filter_criteria.get('carrier'):
        query = query.where(DataNumber.carrier == filter_criteria['carrier'])
        
    if filter_criteria.get('source'):
        query = query.where(DataNumber.source == filter_criteria['source'])
    
    if filter_criteria.get('tags'):
        tags = filter_criteria['tags']
        tag_conditions = [DataNumber.tags.contains([tag]) for tag in tags]
        query = query.where(or_(*tag_conditions))
    
    if filter_criteria.get('exclude_used_days'):
        days = filter_criteria['exclude_used_days']
        cutoff = datetime.now() - timedelta(days=days)
        query = query.where(
            or_(
                DataNumber.last_used_at.is_(None),
                DataNumber.last_used_at < cutoff
            )
        )
    
    # 排除冷却中的号码 (Global Cooldown)
    query = query.where(
        or_(
            DataNumber.cooldown_until.is_(None),
            DataNumber.cooldown_until < datetime.now()
        )
    )
    
    return query


async def calculate_stock(db: AsyncSession, filter_criteria: dict, public_only: bool = False) -> int:
    """计算符合条件的号码数量"""
    query = build_filter_query(filter_criteria, public_only=public_only)
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    return result.scalar() or 0


@admin_router.get("/import-batches")
async def list_import_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取导入批次列表"""
    query = select(DataImportBatch).order_by(DataImportBatch.created_at.desc())
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    batches = result.scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": b.id,
            "batch_id": b.batch_id,
            "file_name": b.file_name,
            "source": b.source,
            "total_count": b.total_count,
            "valid_count": b.valid_count,
            "duplicate_count": b.duplicate_count,
            "invalid_count": b.invalid_count,
            "status": b.status,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "completed_at": b.completed_at.isoformat() if b.completed_at else None
        } for b in batches],
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ============ 数据商品管理 ============

@admin_router.get("/products")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取数据商品列表"""
    query = select(DataProduct).where(DataProduct.is_deleted == False)
    
    if status:
        query = query.where(DataProduct.status == status)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    query = query.order_by(DataProduct.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": p.id,
            "product_code": p.product_code,
            "product_name": p.product_name,
            "description": p.description,
            "filter_criteria": p.filter_criteria,
            "price_per_number": p.price_per_number,
            "currency": p.currency,
            "stock_count": p.stock_count,
            "min_purchase": p.min_purchase,
            "max_purchase": p.max_purchase,
            "status": p.status,
            "total_sold": p.total_sold,
            "created_at": p.created_at.isoformat() if p.created_at else None
        } for p in products],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@admin_router.post("/products")
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """创建数据商品"""
    # 检查编码唯一性
    existing = await db.execute(
        select(DataProduct).where(DataProduct.product_code == data.product_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="商品编码已存在")
    
    # 计算库存
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
        max_purchase=data.max_purchase
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    
    return {
        "success": True,
        "id": product.id,
        "product_code": product.product_code,
        "stock_count": stock_count
    }


@admin_router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """更新数据商品"""
    result = await db.execute(
        select(DataProduct).where(DataProduct.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)
    
    # 如果筛选条件变化，重新计算库存
    if data.filter_criteria:
        product.stock_count = await calculate_stock(db, data.filter_criteria)
    
    await db.commit()
    return {"success": True, "message": "更新成功"}


@admin_router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """删除数据商品(软删除)"""
    result = await db.execute(
        select(DataProduct).where(DataProduct.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    
    product.is_deleted = True
    await db.commit()
    return {"success": True, "message": "删除成功"}


@admin_router.post("/products/{product_id}/refresh-stock")
async def refresh_product_stock(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """刷新商品库存"""
    result = await db.execute(
        select(DataProduct).where(DataProduct.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    
    stock_count = await calculate_stock(db, product.filter_criteria)
    product.stock_count = stock_count
    await db.commit()
    
    return {"success": True, "stock_count": stock_count}


# ============ 数据订单管理 ============

@admin_router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取数据订单列表"""
    query = select(DataOrder).options(
        joinedload(DataOrder.account),
        joinedload(DataOrder.product)
    )
    
    if status:
        query = query.where(DataOrder.status == status)
    if account_id:
        query = query.where(DataOrder.account_id == account_id)
    
    count_query = select(func.count()).select_from(select(DataOrder).subquery())
    total = (await db.execute(count_query)).scalar()
    
    query = query.order_by(DataOrder.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.unique().scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": o.id,
            "order_no": o.order_no,
            "account_id": o.account_id,
            "account_name": o.account.username if o.account else None,
            "product_id": o.product_id,
            "product_name": o.product.product_name if o.product else "自定义筛选",
            "filter_criteria": o.filter_criteria,
            "quantity": o.quantity,
            "unit_price": o.unit_price,
            "total_price": o.total_price,
            "status": o.status,
            "executed_count": o.executed_count,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "executed_at": o.executed_at.isoformat() if o.executed_at else None
        } for o in orders],
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ============ 客户API ============

@customer_router.get("/products")
async def customer_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """客户获取可购买的数据商品列表"""
    query = select(DataProduct).where(
        DataProduct.is_deleted == False,
        DataProduct.status == 'active'
    )
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    query = query.order_by(DataProduct.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": p.id,
            "product_code": p.product_code,
            "product_name": p.product_name,
            "description": p.description,
            "filter_criteria": p.filter_criteria,
            "price_per_number": p.price_per_number,
            "currency": p.currency,
            "stock_count": p.stock_count,
            "min_purchase": p.min_purchase,
            "max_purchase": p.max_purchase
        } for p in products],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@customer_router.post("/preview")
async def preview_data_selection(
    data: FilterCriteria,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """预览筛选结果(不消费数据)"""
    filter_dict = data.dict(exclude_unset=True)
    count = await calculate_stock(db, filter_dict)
    
    # 获取样例
    query = build_filter_query(filter_dict)
    query = query.limit(10)
    result = await db.execute(query)
    samples = result.scalars().all()
    
    return {
        "success": True,
        "total_count": count,
        "samples": [{
            "country_code": s.country_code,
            "tags": s.tags or [],
            "status": s.status
        } for s in samples]
    }


@customer_router.post("/orders")
async def create_data_order(
    data: DataOrderCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """创建数据订单"""
    filter_criteria = {}
    unit_price = "0.001"
    
    if data.product_id:
        # 使用商品配置
        product_result = await db.execute(
            select(DataProduct).where(
                DataProduct.id == data.product_id,
                DataProduct.status == 'active',
                DataProduct.is_deleted == False
            )
        )
        product = product_result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在或已下架")
        
        if data.quantity < product.min_purchase:
            raise HTTPException(status_code=400, detail=f"最小购买量: {product.min_purchase}")
        if data.quantity > product.max_purchase:
            raise HTTPException(status_code=400, detail=f"最大购买量: {product.max_purchase}")
        
        filter_criteria = product.filter_criteria
        unit_price = product.price_per_number
    elif data.filter_criteria:
        filter_criteria = data.filter_criteria
    else:
        raise HTTPException(status_code=400, detail="请选择商品或指定筛选条件")
    
    # 检查库存
    available_count = await calculate_stock(db, filter_criteria)
    if available_count < data.quantity:
        raise HTTPException(status_code=400, detail=f"库存不足，当前可用: {available_count}")
    
    # 计算费用
    total_price = str(float(unit_price) * data.quantity)
    
    # 检查余额
    if float(account.balance or 0) < float(total_price):
        raise HTTPException(status_code=400, detail="余额不足")
    
    # 生成订单号
    order_no = f"DO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    
    # 创建订单
    order = DataOrder(
        order_no=order_no,
        account_id=account.id,
        product_id=data.product_id,
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=unit_price,
        total_price=total_price,
        status="pending",
        expires_at=datetime.now() + timedelta(hours=24)
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    return {
        "success": True,
        "order_no": order_no,
        "quantity": data.quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "status": "pending",
        "expires_at": order.expires_at.isoformat()
    }

@customer_router.get("/orders")
async def customer_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account)
):
    """客户获取自己的数据订单"""
    query = select(DataOrder).options(
        joinedload(DataOrder.product)
    ).where(DataOrder.account_id == account.id)
    
    if status:
        query = query.where(DataOrder.status == status)
    
    count_query = select(func.count()).select_from(
        select(DataOrder).where(DataOrder.account_id == account.id).subquery()
    )
    total = (await db.execute(count_query)).scalar()
    
    query = query.order_by(DataOrder.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.unique().scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": o.id,
            "order_no": o.order_no,
            "product_name": o.product.product_name if o.product else "自定义筛选",
            "filter_criteria": o.filter_criteria,
            "quantity": o.quantity,
            "unit_price": o.unit_price,
            "total_price": o.total_price,
            "status": o.status,
            "executed_count": o.executed_count,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "executed_at": o.executed_at.isoformat() if o.executed_at else None
        } for o in orders],
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ============ 辅助函数 ============

def build_filter_query(filter_criteria: dict):
    """根据筛选条件构建查询"""
    query = select(DataNumber).where(DataNumber.status == 'active')
    
    if filter_criteria.get('country'):
        query = query.where(DataNumber.country_code == filter_criteria['country'])
    
    if filter_criteria.get('tags'):
        # 至少包含一个标签
        tags = filter_criteria['tags']
        tag_conditions = [DataNumber.tags.contains([tag]) for tag in tags]
        query = query.where(or_(*tag_conditions))
    
    if filter_criteria.get('exclude_used_days'):
        days = filter_criteria['exclude_used_days']
        cutoff = datetime.now() - timedelta(days=days)
        query = query.where(
            or_(
                DataNumber.last_used_at.is_(None),
                DataNumber.last_used_at < cutoff
            )
        )
    
    # 排除独占号码
    query = query.where(
        or_(
            DataNumber.exclusive_account_id.is_(None),
            DataNumber.exclusive_until < datetime.now()
        )
    )
    
    # 排除冷却中的号码
    query = query.where(
        or_(
            DataNumber.cooldown_until.is_(None),
            DataNumber.cooldown_until < datetime.now()
        )
    )
    
    return query


async def calculate_stock(db: AsyncSession, filter_criteria: dict) -> int:
    """计算符合条件的号码数量"""
    query = build_filter_query(filter_criteria)
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    return result.scalar() or 0


# ============ 数据账户管理API ============
from app.modules.data.data_account import DataAccount, DataExtractionLog
from sqlalchemy.orm import selectinload


@admin_router.get("/accounts")
async def list_data_accounts(
    country_code: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin),
):
    """获取数据账户列表"""
    query = select(DataAccount).options(selectinload(DataAccount.account))
    
    if country_code:
        query = query.where(DataAccount.country_code == country_code)
    if status:
        query = query.where(DataAccount.status == status)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    result = await db.execute(
        query.order_by(DataAccount.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    accounts = result.scalars().all()
    
    return {
        "success": True,
        "items": [
            {
                "id": a.id,
                "account_id": a.account_id,
                "account": {
                    "account_name": a.account.account_name
                } if a.account else None,
                "platform_account": a.platform_account,
                "country_code": a.country_code,
                "balance": float(a.balance) if a.balance else 0,
                "total_extracted": a.total_extracted or 0,
                "total_spent": float(a.total_spent) if a.total_spent else 0,
                "status": a.status,
                "last_sync_at": a.last_sync_at.isoformat() if a.last_sync_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in accounts
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@admin_router.post("/accounts/{account_id}/sync")
async def sync_data_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin),
):
    """同步数据账户状态"""
    from app.services.data_platform_client import get_data_platform_client
    
    result = await db.execute(select(DataAccount).where(DataAccount.id == account_id))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    try:
        client = get_data_platform_client()
        balance = await client.get_balance(account.external_id)
        
        account.balance = balance
        account.last_sync_at = datetime.now()
        account.sync_error = None
        await db.commit()
        
        return {"success": True, "message": "同步成功", "balance": balance}
        
    except Exception as e:
        account.sync_error = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/accounts/{account_id}/logs")
async def list_extraction_logs(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin),
):
    """获取数据提取记录"""
    query = select(DataExtractionLog).where(DataExtractionLog.data_account_id == account_id)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    result = await db.execute(
        query.order_by(DataExtractionLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()
    
    return {
        "success": True,
        "items": [
            {
                "id": log.id,
                "extraction_id": log.extraction_id,
                "count": log.count,
                "unit_price": float(log.unit_price) if log.unit_price else 0,
                "total_cost": float(log.total_cost) if log.total_cost else 0,
                "filters": log.filters,
                "status": log.status,
                "error_message": log.error_message,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
