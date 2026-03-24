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
from decimal import Decimal

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
from app.utils.sms_template import render_sms_variables, sms_template_has_variables

logger = get_logger(__name__)
router = APIRouter()


def _gen_order_no():
    return f"DO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


# ============ 商品浏览 ============

@router.get("/carriers")
async def get_available_carriers(
    country_code: Optional[str] = Query(None, description="按国家筛选运营商"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """获取可用的运营商列表（去重后的 carrier 值）"""
    query = select(DataNumber.carrier, func.count(DataNumber.id).label("cnt")).where(
        DataNumber.status == 'active',
        DataNumber.account_id.is_(None),
        DataNumber.carrier.isnot(None),
        DataNumber.carrier != '',
        DataNumber.carrier != 'Unknown',
    )

    # 如果有国家过滤或客户绑定了国家
    if country_code:
        query = query.where(DataNumber.country_code == country_code)
    else:
        da_result = await db.execute(
            select(DataAccount).where(DataAccount.account_id == account.id)
        )
        da = da_result.scalar_one_or_none()
        if da and da.country_code:
            query = query.where(DataNumber.country_code == da.country_code)

    query = query.group_by(DataNumber.carrier).order_by(func.count(DataNumber.id).desc())
    result = await db.execute(query)
    rows = result.fetchall()

    return {
        "success": True,
        "carriers": [{"name": row[0], "count": row[1]} for row in rows],
    }


@router.get("/products")
async def customer_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_type: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    freshness: Optional[str] = None,
    carrier: Optional[str] = Query(None, description="按运营商筛选"),
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

    # 如果指定了运营商筛选，计算该运营商下每个商品的实际可用库存
    items = []
    product_ids = [p.id for p in products]

    # 批量获取评分统计
    from app.modules.data.models import DataProductRating
    rating_stats = {}
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
            rating_stats[s.product_id] = {
                "total": s.total, "avg": round(float(s.avg or 0), 1), "max": s.max or 0,
            }

        recent_agg = (await db.execute(
            select(
                DataProductRating.product_id,
                func.avg(DataProductRating.rating).label("avg"),
                func.max(DataProductRating.rating).label("max"),
                func.count().label("cnt"),
            ).where(
                DataProductRating.product_id.in_(product_ids),
                DataProductRating.created_at >= recent_30d,
            ).group_by(DataProductRating.product_id)
        )).fetchall()
        for r in recent_agg:
            if r.product_id in rating_stats:
                rating_stats[r.product_id]["recent_avg"] = round(float(r.avg or 0), 1)
                rating_stats[r.product_id]["recent_max"] = r.max or 0
                rating_stats[r.product_id]["recent_count"] = r.cnt

    for p in products:
        item = serialize_product(p)
        if carrier:
            fc = dict(p.filter_criteria or {})
            fc["carrier"] = carrier
            stock = await calculate_stock(db, fc, public_only=True)
            item["stock_count"] = stock
            item["carrier_filter"] = carrier
            if stock <= 0:
                continue
        rs = rating_stats.get(p.id, {})
        item["rating"] = {
            "avg": rs.get("avg", 0),
            "max": rs.get("max", 0),
            "total": rs.get("total", 0),
            "recent_avg": rs.get("recent_avg", 0),
            "recent_max": rs.get("recent_max", 0),
            "recent_count": rs.get("recent_count", 0),
        }
        items.append(item)

    return {
        "success": True,
        "items": items,
        "total": len(items) if carrier else total,
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

    if data.carrier:
        filter_criteria = dict(filter_criteria or {})
        filter_criteria["carrier"] = data.carrier

    total_price = Decimal(str(unit_price)) * data.quantity

    # P0-FIX: 原子扣费，防止并发双扣
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_price)
        .values(balance=Account.balance - total_price)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, "余额不足")

    # P0-FIX: 锁定号码时加 account_id IS NULL 条件，防止超卖
    id_query = build_filter_query(filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]

    if len(number_ids) < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {len(number_ids)}")

    lock_result = await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids), DataNumber.account_id.is_(None))
        .values(account_id=account.id)
    )
    locked = lock_result.rowcount
    if locked < len(number_ids):
        logger.warning(f"库存竞争: 请求{len(number_ids)}条, 实际锁定{locked}条")

    actual_price = Decimal(str(unit_price)) * locked

    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=data.product_id,
        filter_criteria=filter_criteria,
        quantity=locked,
        unit_price=str(unit_price),
        total_price=str(actual_price),
        order_type="data_only",
        status="completed",
        executed_count=locked,
        executed_at=datetime.now(),
    )
    db.add(order)
    await db.flush()

    # P0-FIX: 参数化插入，防止 SQL 注入
    if number_ids:
        from app.modules.data.models import DataOrderNumber as DON
        db.add_all([DON(order_id=order.id, number_id=nid) for nid in number_ids])

    # 多扣的差额退回
    if total_price > actual_price:
        refund = total_price - actual_price
        await db.execute(
            sa_update(Account).where(Account.id == account.id)
            .values(balance=Account.balance + refund)
        )

    if product:
        product.total_sold = (product.total_sold or 0) + locked

    from app.modules.common.balance_log import BalanceLog
    new_bal = await db.execute(select(Account.balance).where(Account.id == account.id))
    db.add(BalanceLog(
        account_id=account.id, change_type='charge', amount=-actual_price,
        balance_after=float(new_bal.scalar()), description=f"BuyStock: {locked} 条数据"
    ))

    await db.commit()
    return {"success": True, "message": f"已购买 {locked} 条数据到私库", "order_no": order.order_no}


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
        total_price = Decimal(str(product.bundle_price)) * data.quantity
    else:
        total_price = Decimal(str(product.price_per_number)) * data.quantity

    # P0-FIX: 原子扣费
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_price)
        .values(balance=Account.balance - total_price)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, "余额不足")

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

    # P0-FIX: 批量锁定号码，防止超卖
    id_query = build_filter_query(product.filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]

    lock_result = await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids), DataNumber.account_id.is_(None))
        .values(account_id=account.id)
    )
    locked = lock_result.rowcount

    product.total_sold = (product.total_sold or 0) + locked

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
        "message": f"已购买组合套餐: {locked} 条数据" + (f" + {product.sms_quota * data.quantity} 条短信额度" if product.sms_quota else ""),
        "order_no": order.order_no,
    }


# ============ 购买模式三：买即发 ============

@router.post("/buy-and-send")
async def buy_and_send(
    data: DataBuyAndSend,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """购买数据并立即发送短信（支持变量模板 + 运营商过滤）"""
    product, filter_criteria, unit_price = await _validate_purchase(data, db)

    if data.carrier:
        filter_criteria = dict(filter_criteria or {})
        filter_criteria["carrier"] = data.carrier

    available = await calculate_stock(db, filter_criteria, public_only=True)
    if available < data.quantity:
        raise HTTPException(400, f"库存不足，当前可用: {available}")

    # ---------- 1. 先锁定号码（防超卖） ----------
    from app.core.router import RoutingEngine
    from app.core.pricing import PricingEngine
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.sms_log import SMSLog
    from app.utils.queue import QueueManager
    from app.utils.phone_utils import country_to_dial_code

    id_query = build_filter_query(filter_criteria, public_only=True).with_only_columns(DataNumber.id).limit(data.quantity)
    id_result = await db.execute(id_query)
    number_ids = [row[0] for row in id_result.fetchall()]
    if len(number_ids) < data.quantity:
        raise HTTPException(400, f"库存不足，仅剩 {len(number_ids)} 条")

    # 原子锁定
    lock_result = await db.execute(
        sa_update(DataNumber)
        .where(DataNumber.id.in_(number_ids), DataNumber.account_id.is_(None))
        .values(account_id=account.id, last_used_at=datetime.now())
    )
    if lock_result.rowcount < data.quantity:
        raise HTTPException(400, "号码已被抢购，请重试")

    num_result = await db.execute(select(DataNumber).where(DataNumber.id.in_(number_ids)))
    numbers = num_result.scalars().all()

    # ---------- 2. 按每个号码的国家单独选通道（与手动发送一致，避免用样本导致通道错误） ----------
    routing_engine = RoutingEngine(db)
    pricing_engine = PricingEngine(db)
    msg_list = data.messages if data.messages and len(data.messages) > 1 else [data.message]
    msg_count = len(msg_list)
    msg_has_vars = [sms_template_has_variables(m) for m in msg_list]

    # 预计算每条短信的通道、价格、成本
    num_plans = []  # [(num, channel, price_info, msg, parts, sell, cost), ...]
    for idx, num in enumerate(numbers, start=1):
        template = msg_list[(idx - 1) % msg_count]
        msg = (
            render_sms_variables(
                template,
                index=idx,
                phone_e164=num.phone_number or "",
                country_code=num.country_code or "",
            )
            if msg_has_vars[(idx - 1) % msg_count]
            else template
        )
        parts = pricing_engine._count_sms_parts(msg)

        phone_country = num.country_code or "PH"
        dial_code = country_to_dial_code(phone_country)

        channel = None
        for cc in [dial_code, phone_country]:
            try:
                ch = await routing_engine.select_channel(
                    country_code=cc,
                    strategy='priority',
                    account_id=account.id
                )
                if ch:
                    # 支持 HTTP 与 SMPP，与手动发送一致
                    if ch.protocol == 'HTTP':
                        if ch.api_url:
                            channel = ch
                            break
                    elif ch.protocol == 'SMPP':
                        if ch.host and ch.port:
                            channel = ch
                            break
            except Exception:
                continue

        if not channel:
            from sqlalchemy import select as sa_select, or_, and_
            from app.modules.sms.channel import Channel
            from app.modules.common.account import AccountChannel
            # 兜底：HTTP 或 SMPP 均可（与手动发送一致）
            base_q = sa_select(Channel).where(
                Channel.status == 'active',
                Channel.is_deleted == False,
                or_(
                    and_(Channel.protocol == 'HTTP', Channel.api_url.isnot(None)),
                    and_(Channel.protocol == 'SMPP', Channel.host.isnot(None), Channel.port.isnot(None)),
                ),
            )
            ac_result = await db.execute(
                select(AccountChannel.channel_id).where(AccountChannel.account_id == account.id)
            )
            bound_ids = [r[0] for r in ac_result.all()]
            if bound_ids:
                base_q = base_q.where(Channel.id.in_(bound_ids))
            ch_result = await db.execute(base_q.order_by(Channel.priority.desc()).limit(1))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            raise HTTPException(
                400,
                f"号码 {num.phone_number}（国家 {phone_country}）无可用发送通道，请检查账户通道绑定与路由规则"
            )

        price_info = await pricing_engine.get_price(channel.id, dial_code, account_id=account.id)
        if not price_info:
            price_info = await pricing_engine.get_price(channel.id, phone_country, account_id=account.id)
        sell = float(price_info['price']) * parts if price_info else 0.0
        cost = float(channel.cost_rate or 0) * parts
        currency = price_info['currency'] if price_info else 'USD'
        num_plans.append((num, channel, price_info, msg, parts, sell, cost, currency))

    # 汇总费用
    data_cost = Decimal(str(unit_price)) * data.quantity
    sms_cost = sum(Decimal(str(p[5])) for p in num_plans)
    total_cost = data_cost + sms_cost
    currency = num_plans[0][7] if num_plans else 'USD'

    # P0-FIX: 原子扣费
    deduct = await db.execute(
        sa_update(Account)
        .where(Account.id == account.id, Account.balance >= total_cost)
        .values(balance=Account.balance - total_cost)
    )
    if deduct.rowcount == 0:
        raise HTTPException(400, f"余额不足，需要 {total_cost:.4f} {currency}（数据 {data_cost:.4f} + 短信 {sms_cost:.4f}）")

    # ---------- 3. 创建订单 ----------
    order = DataOrder(
        order_no=_gen_order_no(),
        account_id=account.id,
        product_id=getattr(data, "product_id", None),
        filter_criteria=filter_criteria,
        quantity=data.quantity,
        unit_price=str(unit_price),
        total_price=str(total_cost),
        order_type="data_and_send",
        status="completed",
        executed_count=data.quantity,
        executed_at=datetime.now(),
    )
    db.add(order)
    await db.flush()

    # ---------- 4. 创建短信记录（每条使用该号码国家对应的通道） ----------
    batch_tag = f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    sms_batch = SmsBatch(
        account_id=account.id,
        batch_name=f"DataSend-{product.product_name if product else 'Custom'}-{batch_tag}",
        total_count=len(numbers),
        status=BatchStatus.PROCESSING,
    )
    db.add(sms_batch)
    await db.flush()

    message_ids = []
    channels_used = set()
    for idx, (num, channel, price_info, msg, parts, sell, cost, _) in enumerate(num_plans, start=1):
        num.use_count = (num.use_count or 0) + 1
        channels_used.add(channel.channel_code)

        mid = f"msg_{uuid.uuid4().hex}"
        sms = SMSLog(
            message_id=mid,
            account_id=account.id,
            channel_id=channel.id,
            batch_id=sms_batch.id,
            phone_number=num.phone_number,
            country_code=num.country_code,
            message=msg,
            message_count=parts,
            status="pending",
            cost_price=cost,
            selling_price=sell,
            currency=currency,
            submit_time=datetime.now(),
        )
        db.add(sms)
        message_ids.append(mid)
        db.add(DataOrderNumber(order_id=order.id, number_id=num.id))

    if product:
        product.total_sold = (product.total_sold or 0) + len(numbers)

    from app.modules.common.balance_log import BalanceLog
    new_bal = await db.execute(select(Account.balance).where(Account.id == account.id))
    db.add(BalanceLog(
        account_id=account.id, change_type='charge', amount=-total_cost,
        balance_after=float(new_bal.scalar()),
        description=f"DataSend: {len(numbers)} 条 via {','.join(sorted(channels_used))}"
    ))

    await db.commit()

    queued = 0
    for mid in message_ids:
        if QueueManager.queue_sms(mid):
            queued += 1

    return {
        "success": True,
        "message": f"已购买 {len(numbers)} 条数据并创建发送任务",
        "order_no": order.order_no,
        "batch_id": batch_tag,
        "queued": queued,
        "channel": ",".join(sorted(channels_used)) if channels_used else "-",
        "cost": {"data": data_cost, "sms": sms_cost, "total": total_cost, "currency": currency},
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

    # 批量查询当前用户对这些订单的评分
    from app.modules.data.models import DataProductRating
    order_ids = [o.id for o in orders]
    my_ratings = {}
    if order_ids:
        rating_rows = (await db.execute(
            select(DataProductRating.order_id, DataProductRating.rating)
            .where(
                DataProductRating.account_id == account.id,
                DataProductRating.order_id.in_(order_ids),
            )
        )).fetchall()
        for r in rating_rows:
            my_ratings[r.order_id] = r.rating

    items = []
    for o in orders:
        item = serialize_order(o)
        item["_my_rating"] = my_ratings.get(o.id, 0)
        items.append(item)

    return {
        "success": True,
        "items": items,
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


# ============ 商品评分 ============

@router.post("/products/{product_id}/rate")
async def rate_product(
    product_id: int,
    rating: int = Query(..., ge=1, le=5, description="评分(1-5)"),
    order_id: Optional[int] = Query(None, description="关联订单ID"),
    comment: Optional[str] = Query(None, max_length=500, description="评价内容"),
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """客户对数据商品评分（需要有该商品的已完成订单）"""
    from app.modules.data.models import DataProductRating

    product = (await db.execute(
        select(DataProduct).where(DataProduct.id == product_id, DataProduct.is_deleted == False)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "商品不存在")

    order_filter = [DataOrder.account_id == account.id, DataOrder.product_id == product_id]
    if order_id:
        order_filter.append(DataOrder.id == order_id)
    order = (await db.execute(
        select(DataOrder).where(*order_filter).order_by(DataOrder.created_at.desc())
    )).scalars().first()
    if not order:
        raise HTTPException(400, "您没有该商品的订单，无法评分")

    actual_order_id = order_id or order.id

    existing = (await db.execute(
        select(DataProductRating).where(
            DataProductRating.account_id == account.id,
            DataProductRating.order_id == actual_order_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.rating = rating
        existing.comment = comment
        await db.commit()
        return {"success": True, "message": "评分已更新", "rating_id": existing.id}

    new_rating = DataProductRating(
        product_id=product_id,
        account_id=account.id,
        order_id=actual_order_id,
        rating=rating,
        comment=comment,
    )
    db.add(new_rating)
    await db.commit()
    await db.refresh(new_rating)
    return {"success": True, "message": "评分成功", "rating_id": new_rating.id}


@router.get("/products/{product_id}/ratings")
async def get_product_ratings(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
):
    """获取某个商品的评分统计和近期评分"""
    from app.modules.data.models import DataProductRating

    stats = (await db.execute(
        select(
            func.count().label("total_ratings"),
            func.avg(DataProductRating.rating).label("avg_rating"),
            func.max(DataProductRating.rating).label("max_rating"),
        ).where(DataProductRating.product_id == product_id)
    )).first()

    recent_30d = datetime.now() - timedelta(days=30)
    recent_stats = (await db.execute(
        select(
            func.count().label("recent_count"),
            func.avg(DataProductRating.rating).label("recent_avg"),
            func.max(DataProductRating.rating).label("recent_max"),
        ).where(
            DataProductRating.product_id == product_id,
            DataProductRating.created_at >= recent_30d,
        )
    )).first()

    recent_list = (await db.execute(
        select(DataProductRating)
        .where(DataProductRating.product_id == product_id)
        .order_by(DataProductRating.created_at.desc())
        .limit(10)
    )).scalars().all()

    my_rating = (await db.execute(
        select(DataProductRating).where(
            DataProductRating.product_id == product_id,
            DataProductRating.account_id == account.id,
        ).order_by(DataProductRating.created_at.desc())
    )).scalars().first()

    return {
        "success": True,
        "product_id": product_id,
        "total_ratings": stats.total_ratings or 0,
        "avg_rating": round(float(stats.avg_rating or 0), 1),
        "max_rating": stats.max_rating or 0,
        "recent_avg": round(float(recent_stats.recent_avg or 0), 1),
        "recent_count": recent_stats.recent_count or 0,
        "recent_max": recent_stats.recent_max or 0,
        "my_rating": {
            "rating": my_rating.rating,
            "comment": my_rating.comment,
            "order_id": my_rating.order_id,
            "created_at": my_rating.created_at.isoformat() if my_rating.created_at else None,
        } if my_rating else None,
        "recent_ratings": [
            {
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_list
        ],
    }
