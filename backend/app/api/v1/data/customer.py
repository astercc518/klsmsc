"""客户 - 数据业务 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text as sa_text, update as sa_update
from sqlalchemy.orm import joinedload
from typing import Optional
from datetime import datetime, date, timedelta
import uuid
import csv
import io
import random

from app.database import get_db
from app.modules.data.models import DataNumber, DataProduct, DataOrder, DataOrderNumber
from app.modules.data.data_account import DataAccount
from app.modules.common.account import Account
from app.modules.common.package import AccountPackage
from app.core.auth import get_current_account
from app.utils.logger import get_logger
from app.schemas.data import (
    DataOrderCreate, DataBuyAndSend, ComboBuyRequest,
    FilterCriteria, OrderCancelRequest,
)
from app.api.v1.data.helpers import (
    build_filter_query, calculate_stock, serialize_product, serialize_order, serialize_number,
)

logger = get_logger(__name__)
router = APIRouter()


def _gen_order_no():
    return f"DO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


# ============ 商品浏览 ============

@router.get("/products")
async def customer_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_type: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    freshness: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户获取可购买的数据商品列表（自动按关联国家过滤）"""
    query = select(DataProduct).where(
        DataProduct.is_deleted == False, DataProduct.status == "active"
    )

    # 按客户数据账户的国家自动过滤
    da_result = await db.execute(
        select(DataAccount).where(DataAccount.account_id == account.id)
    )
    da = da_result.scalar_one_or_none()
    if da and da.country_code:
        from sqlalchemy import cast, String
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.country")) == da.country_code
        )

    if product_type:
        query = query.where(DataProduct.product_type == product_type)
    if source:
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.source")) == source
        )
    if purpose:
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.purpose")) == purpose
        )
    if freshness:
        query = query.where(
            func.json_unquote(func.json_extract(DataProduct.filter_criteria, "$.freshness")) == freshness
        )

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
        "country_code": da.country_code if da else None,
    }


@router.post("/preview")
async def preview_data_selection(
    data: FilterCriteria,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """预览筛选结果(不消费数据)"""
    filter_dict = data.dict(exclude_unset=True)
    count = await calculate_stock(db, filter_dict, public_only=True)

    query = build_filter_query(filter_dict, public_only=True).limit(10)
    result = await db.execute(query)
    samples = result.scalars().all()

    return {
        "success": True,
        "total_count": count,
        "samples": [
            {"country_code": s.country_code, "carrier": s.carrier, "tags": s.tags or [], "status": s.status}
            for s in samples
        ],
    }


# ============ 购买模式一：单独购买数据 ============

@router.post("/buy-to-stock")
async def buy_to_stock(
    data: DataOrderCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """购买数据到私有库(不立即发送) — 使用 SQL 批量操作"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db)

    total_price = float(unit_price) * data.quantity
    if float(account.balance or 0) < total_price:
        raise HTTPException(400, "余额不足")

    # 构建筛选子查询获取待锁定号码 ID
    id_query = build_filter_query(filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]

    if not number_ids:
        raise HTTPException(400, "库存不足，无可用号码")
    if len(number_ids) < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {len(number_ids)}")

    actual_price = float(unit_price) * len(number_ids)

    # 创建订单
    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=data.product_id,
        filter_criteria=filter_criteria,
        quantity=len(number_ids),
        unit_price=str(unit_price),
        total_price=str(actual_price),
        order_type="data_only",
        status="completed",
        executed_count=len(number_ids),
        executed_at=datetime.now(),
    )
    db.add(order)
    await db.flush()

    # 批量锁定号码（一条 UPDATE）
    await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids))
        .values(account_id=account.id)
    )

    # 批量插入订单号码关联
    await db.execute(
        sa_text("INSERT INTO data_order_numbers (order_id, number_id) VALUES " +
                ",".join([f"({order.id},{nid})" for nid in number_ids]))
    )

    account.balance = float(account.balance) - actual_price

    if product:
        product.total_sold = (product.total_sold or 0) + len(number_ids)

    await db.commit()
    return {"success": True, "message": f"已购买 {len(number_ids)} 条数据到私库", "order_no": order.order_no}


# ============ 购买模式二：组合套餐 ============

@router.post("/buy-combo")
async def buy_combo(
    data: ComboBuyRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """购买数据+短信组合套餐"""
    result = await db.execute(
        select(DataProduct).where(
            DataProduct.id == data.product_id,
            DataProduct.product_type == "combo",
            DataProduct.status == "active",
            DataProduct.is_deleted == False,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "组合套餐不存在或不可用")

    if data.quantity < product.min_purchase:
        raise HTTPException(400, f"最小购买量: {product.min_purchase}")
    if data.quantity > product.max_purchase:
        raise HTTPException(400, f"最大购买量: {product.max_purchase}")

    available = await calculate_stock(db, product.filter_criteria, public_only=True)
    if available < data.quantity:
        raise HTTPException(400, f"数据库存不足，当前可用: {available}")

    # 计价：使用打包价，若无打包价则按单价
    if product.bundle_price:
        total_price = float(product.bundle_price) * data.quantity
    else:
        total_price = float(product.price_per_number) * data.quantity

    if float(account.balance or 0) < total_price:
        raise HTTPException(400, "余额不足")

    # 创建订单
    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=product.id,
        filter_criteria=product.filter_criteria,
        quantity=data.quantity,
        unit_price=product.bundle_price or product.price_per_number,
        total_price=str(total_price),
        order_type="combo",
        status="completed",
        executed_count=data.quantity,
        executed_at=datetime.now(),
    )
    db.add(order)
    account.balance = float(account.balance) - total_price

    # 锁定号码
    query = build_filter_query(product.filter_criteria, public_only=True).limit(data.quantity)
    num_result = await db.execute(query)
    numbers = num_result.scalars().all()

    for num in numbers:
        num.account_id = account.id

    product.total_sold = (product.total_sold or 0) + len(numbers)

    # 写入短信额度到 AccountPackage
    if product.sms_quota:
        sms_total = product.sms_quota * data.quantity
        pkg = AccountPackage(
            account_id=account.id,
            package_id=0,
            sms_remaining=sms_total,
            data_used=0,
            data_remaining=data.quantity,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=365),
            is_active=True,
            purchase_price=total_price,
            order_id=order.order_no,
        )
        db.add(pkg)

    await db.commit()

    return {
        "success": True,
        "message": f"已购买组合套餐: {len(numbers)} 条数据" + (f" + {product.sms_quota * data.quantity} 条短信额度" if product.sms_quota else ""),
        "order_no": order.order_no,
    }


# ============ 变量模板替换 ============

def _render_sms_template(template: str, index: int, phone: str, country: str) -> str:
    """将短信模板中的变量占位符替换为实际值"""
    today_str = date.today().strftime("%Y-%m-%d")
    rand_code = str(random.randint(100000, 999999))

    msg = template
    msg = msg.replace("{序号}", str(index))
    msg = msg.replace("{国家}", country or "")
    msg = msg.replace("{日期}", today_str)
    msg = msg.replace("{随机码}", rand_code)
    msg = msg.replace("{号码}", phone.lstrip("+") if phone else "")
    # 英文别名
    msg = msg.replace("{index}", str(index))
    msg = msg.replace("{country}", country or "")
    msg = msg.replace("{date}", today_str)
    msg = msg.replace("{code}", rand_code)
    msg = msg.replace("{phone}", phone.lstrip("+") if phone else "")
    return msg


# ============ 购买模式三：买即发 ============

@router.post("/buy-and-send")
async def buy_and_send(
    data: DataBuyAndSend,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """购买数据并立即发送短信（支持变量模板）"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db)

    available = await calculate_stock(db, filter_criteria, public_only=True)
    if available < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {available}")

    data_cost = float(unit_price) * data.quantity
    if float(account.balance or 0) < data_cost:
        raise HTTPException(400, "余额不足")

    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=getattr(data, "product_id", None),
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=str(unit_price),
        total_price=str(data_cost),
        order_type="data_and_send",
        status="completed",
        executed_count=data.quantity,
        executed_at=datetime.now(),
    )
    db.add(order)
    account.balance = float(account.balance) - data_cost

    query = build_filter_query(filter_criteria, public_only=True).limit(data.quantity)
    result = await db.execute(query)
    numbers = result.scalars().all()

    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.sms_log import SMSLog

    batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    sms_batch = SmsBatch(
        batch_id=batch_id,
        account_id=account.id,
        batch_name=f"DataSend-{product.product_name if product else 'Custom'}-{datetime.now().strftime('%m%d')}",
        total_count=len(numbers),
        status=BatchStatus.processing,
    )
    db.add(sms_batch)

    # 多文案模式：均匀分配不同文案给不同号码
    msg_list = data.messages if data.messages and len(data.messages) > 1 else [data.message]
    msg_count = len(msg_list)

    # 预检测各文案是否含变量
    var_tags = ("{序号}", "{国家}", "{日期}", "{随机码}", "{号码}", "{index}", "{country}", "{date}", "{code}", "{phone}")
    msg_has_vars = [any(v in m for v in var_tags) for m in msg_list]

    for idx, num in enumerate(numbers, start=1):
        num.account_id = account.id
        num.last_used_at = datetime.now()
        num.use_count = (num.use_count or 0) + 1

        # 轮询分配文案
        template = msg_list[(idx - 1) % msg_count]
        msg = _render_sms_template(template, idx, num.phone_number, num.country_code) if msg_has_vars[(idx - 1) % msg_count] else template

        sms = SMSLog(
            account_id=account.id,
            batch_id=batch_id,
            phone_number=num.phone_number,
            message=msg,
            status="pending",
            submit_time=datetime.now(),
        )
        db.add(sms)
        db.add(DataOrderNumber(order_id=0, number_id=num.id))

    if product:
        product.total_sold = (product.total_sold or 0) + len(numbers)

    await db.commit()

    return {
        "success": True,
        "message": f"已购买 {len(numbers)} 条数据并创建发送任务",
        "order_no": order.order_no,
        "batch_id": batch_id,
    }


# ============ 订单管理 ============

@router.post("/orders")
async def create_data_order(
    data: DataOrderCreate,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """创建数据订单(预下单)"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db)

    available = await calculate_stock(db, filter_criteria)
    if available < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {available}")

    total_price = str(float(unit_price) * data.quantity)
    if float(account.balance or 0) < float(total_price):
        raise HTTPException(400, "余额不足")

    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=getattr(data, "product_id", None),
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=unit_price,
        total_price=total_price,
        order_type="data_only",
        status="pending",
        expires_at=datetime.now() + timedelta(hours=24),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "success": True,
        "order_no": order.order_no,
        "quantity": data.quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "status": "pending",
        "expires_at": order.expires_at.isoformat(),
    }


@router.get("/orders")
async def customer_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户获取自己的数据订单"""
    query = select(DataOrder).options(joinedload(DataOrder.product)).where(
        DataOrder.account_id == account.id
    )
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
        "items": [serialize_order(o) for o in orders],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/orders/{order_id}")
async def customer_order_detail(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """获取订单详情"""
    result = await db.execute(
        select(DataOrder)
        .options(joinedload(DataOrder.product))
        .where(DataOrder.id == order_id, DataOrder.account_id == account.id)
    )
    order = result.unique().scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")

    return {"success": True, "data": serialize_order(order)}


@router.post("/orders/{order_id}/cancel")
async def customer_cancel_order(
    order_id: int,
    data: OrderCancelRequest,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户取消 pending 订单"""
    result = await db.execute(
        select(DataOrder).where(
            DataOrder.id == order_id, DataOrder.account_id == account.id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "pending":
        raise HTTPException(400, "只能取消待处理的订单")

    order.status = "cancelled"
    order.cancel_reason = data.reason or "客户主动取消"
    await db.commit()
    return {"success": True, "message": "订单已取消"}


# ============ 私库管理 ============

@router.get("/my-numbers/summary")
async def get_my_numbers_summary(
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """私库号码按来源+用途+国家聚合统计（卡片展示用）"""
    from app.modules.data.models import SOURCE_LABELS, PURPOSE_LABELS
    result = await db.execute(
        select(
            DataNumber.country_code,
            DataNumber.source,
            DataNumber.purpose,
            func.count().label("count"),
            func.min(DataNumber.created_at).label("first_at"),
            func.max(DataNumber.created_at).label("last_at"),
        )
        .where(DataNumber.account_id == account.id)
        .group_by(DataNumber.country_code, DataNumber.source, DataNumber.purpose)
        .order_by(func.count().desc())
    )
    rows = result.fetchall()

    total = sum(r.count for r in rows)
    items = []
    for r in rows:
        items.append({
            "country_code": r.country_code or "",
            "source": r.source or "",
            "source_label": SOURCE_LABELS.get(r.source, r.source or ""),
            "purpose": r.purpose or "",
            "purpose_label": PURPOSE_LABELS.get(r.purpose, r.purpose or ""),
            "count": r.count,
            "first_at": r.first_at.isoformat() if r.first_at else None,
            "last_at": r.last_at.isoformat() if r.last_at else None,
        })

    return {"success": True, "items": items, "total": total}


@router.get("/my-numbers")
async def get_my_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country: Optional[str] = None,
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
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
        "items": [serialize_number(n) for n in numbers],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/my-numbers/export")
async def export_my_numbers(
    fmt: str = Query("csv", regex="^(csv|txt)$"),
    country: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """导出私库号码 CSV 或 TXT"""
    query = select(DataNumber).where(DataNumber.account_id == account.id)
    if country:
        query = query.where(DataNumber.country_code == country)
    if source:
        query = query.where(DataNumber.source == source)
    if purpose:
        query = query.where(DataNumber.purpose == purpose)

    result = await db.execute(query.order_by(DataNumber.id))
    numbers = result.scalars().all()

    ts = datetime.now().strftime('%Y%m%d%H%M%S')

    def _strip_plus(phone: str) -> str:
        return phone.lstrip('+') if phone else phone

    if fmt == "txt":
        output = "\n".join(_strip_plus(n.phone_number) for n in numbers)
        filename = f"my_numbers_{ts}.txt"
        return StreamingResponse(
            iter([output]),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["phone_number", "country_code", "carrier", "tags", "source"])
    for n in numbers:
        writer.writerow([_strip_plus(n.phone_number), n.country_code, n.carrier or "", "|".join(n.tags) if n.tags else "", n.source or ""])

    output.seek(0)
    filename = f"my_numbers_{ts}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ 辅助 ============

async def _validate_purchase(data, db: AsyncSession):
    """验证购买请求，返回 (product, filter_criteria, unit_price)"""
    if getattr(data, "product_id", None):
        result = await db.execute(
            select(DataProduct).where(
                DataProduct.id == data.product_id,
                DataProduct.status == "active",
                DataProduct.is_deleted == False,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(404, "商品不存在或已下架")
        if data.quantity < product.min_purchase:
            raise HTTPException(400, f"最小购买量: {product.min_purchase}")
        if data.quantity > product.max_purchase:
            raise HTTPException(400, f"最大购买量: {product.max_purchase}")
        return product, product.filter_criteria, product.price_per_number

    if getattr(data, "filter_criteria", None):
        return None, data.filter_criteria, "0.001"

    raise HTTPException(400, "请选择商品或指定筛选条件")
