"""数据业务公共辅助函数"""
from datetime import datetime, timedelta, date
from typing import Optional
from decimal import Decimal
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.data.models import (
    DataNumber, DataPricingTemplate,
    SOURCE_LABELS, PURPOSE_LABELS, FRESHNESS_LABELS,
)


def freshness_to_date_range(freshness: str) -> tuple:
    """将时效标签转为日期范围 (start_date, end_date)"""
    today = date.today()
    if freshness == '3day':
        return today - timedelta(days=3), today
    elif freshness == '7day':
        return today - timedelta(days=7), today
    elif freshness == '30day':
        return today - timedelta(days=30), today
    else:  # history
        return None, today - timedelta(days=30)


def compute_freshness(data_date: Optional[date]) -> str:
    """根据数据日期计算时效标签"""
    if not data_date:
        return 'history'
    days = (date.today() - data_date).days
    if days <= 3:
        return '3day'
    elif days <= 7:
        return '7day'
    elif days <= 30:
        return '30day'
    return 'history'


def build_filter_query(filter_criteria: dict, public_only: bool = False):
    """根据筛选条件构建查询"""
    query = select(DataNumber).where(DataNumber.status == 'active')

    if public_only:
        query = query.where(DataNumber.account_id.is_(None))

    if filter_criteria.get('country'):
        country_val = filter_criteria['country']
        if country_val.isdigit():
            import phonenumbers as _pn
            regions = _pn.region_codes_for_country_code(int(country_val))
            country_val = regions[0] if regions else country_val
        query = query.where(DataNumber.country_code == country_val)
    if filter_criteria.get('carrier'):
        query = query.where(DataNumber.carrier == filter_criteria['carrier'])
    if filter_criteria.get('source'):
        query = query.where(DataNumber.source == filter_criteria['source'])
    if filter_criteria.get('purpose'):
        query = query.where(DataNumber.purpose == filter_criteria['purpose'])

    if filter_criteria.get('freshness'):
        start_date, end_date = freshness_to_date_range(filter_criteria['freshness'])
        if start_date and end_date:
            query = query.where(DataNumber.data_date.between(start_date, end_date))
        elif end_date:
            query = query.where(
                or_(DataNumber.data_date.is_(None), DataNumber.data_date < end_date)
            )

    if filter_criteria.get('tags'):
        tags = filter_criteria['tags']
        tag_conditions = [DataNumber.tags.contains([tag]) for tag in tags]
        query = query.where(or_(*tag_conditions))

    if filter_criteria.get('exclude_used_days'):
        days = filter_criteria['exclude_used_days']
        cutoff = datetime.now() - timedelta(days=days)
        query = query.where(
            or_(DataNumber.last_used_at.is_(None), DataNumber.last_used_at < cutoff)
        )

    query = query.where(
        or_(DataNumber.cooldown_until.is_(None), DataNumber.cooldown_until < datetime.now())
    )

    return query


async def calculate_stock(db: AsyncSession, filter_criteria: dict, public_only: bool = False) -> int:
    """计算符合条件的号码数量"""
    query = build_filter_query(filter_criteria, public_only=public_only)
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    return result.scalar() or 0


async def calculate_stock_with_carriers(
    db: AsyncSession, filter_criteria: dict, public_only: bool = True
) -> tuple:
    """计算精确库存（含时效过滤）并返回运营商分布。
    返回 (total_stock, carrier_list) 其中 carrier_list = [{"name": str, "count": int}, ...]
    """
    query = build_filter_query(filter_criteria, public_only=public_only)
    carrier_q = query.with_only_columns(
        DataNumber.carrier, func.count().label("cnt")
    ).group_by(DataNumber.carrier)
    result = await db.execute(carrier_q)
    carriers = []
    total = 0
    for row in result.fetchall():
        name = row[0] or "Unknown"
        cnt = int(row[1])
        carriers.append({"name": name, "count": cnt})
        total += cnt
    return total, carriers


async def lookup_price(db: AsyncSession, source: str, purpose: str, freshness: str, country_code: str = '*') -> Optional[Decimal]:
    """从定价模板查找单价，优先匹配具体国家，回退到通配符"""
    result = await db.execute(
        select(DataPricingTemplate.price_per_number).where(
            DataPricingTemplate.source == source,
            DataPricingTemplate.purpose == purpose,
            DataPricingTemplate.freshness == freshness,
            DataPricingTemplate.country_code == country_code,
            DataPricingTemplate.status == 'active',
        )
    )
    price = result.scalar_one_or_none()
    if price is not None:
        return price

    if country_code != '*':
        result = await db.execute(
            select(DataPricingTemplate.price_per_number).where(
                DataPricingTemplate.source == source,
                DataPricingTemplate.purpose == purpose,
                DataPricingTemplate.freshness == freshness,
                DataPricingTemplate.country_code == '*',
                DataPricingTemplate.status == 'active',
            )
        )
        return result.scalar_one_or_none()
    return None


def serialize_number(n: DataNumber) -> dict:
    return {
        "id": n.id,
        "phone_number": n.phone_number,
        "country_code": n.country_code,
        "tags": n.tags or [],
        "carrier": n.carrier,
        "status": n.status,
        "source": n.source,
        "source_label": SOURCE_LABELS.get(n.source, n.source or ''),
        "purpose": n.purpose,
        "purpose_label": PURPOSE_LABELS.get(n.purpose, n.purpose or ''),
        "data_date": n.data_date.isoformat() if n.data_date else None,
        "freshness": compute_freshness(n.data_date),
        "freshness_label": FRESHNESS_LABELS.get(compute_freshness(n.data_date), ''),
        "batch_id": n.batch_id,
        "pricing_template_id": n.pricing_template_id,
        "use_count": n.use_count,
        "account_id": n.account_id,
        "last_used_at": n.last_used_at.isoformat() if n.last_used_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def serialize_product(p) -> dict:
    from app.modules.data.models import SOURCE_LABELS, PURPOSE_LABELS, FRESHNESS_LABELS

    fc = p.filter_criteria or {}
    source = fc.get("source", "")
    purpose = fc.get("purpose", "")
    freshness = fc.get("freshness", "")
    country = fc.get("country", "")
    if country and country.isdigit():
        import phonenumbers as _pn
        regions = _pn.region_codes_for_country_code(int(country))
        country = regions[0] if regions else country

    total_sold = p.total_sold or 0
    stock = p.stock_count or 0

    return {
        "id": p.id,
        "product_code": p.product_code,
        "product_name": p.product_name,
        "description": p.description,
        "filter_criteria": fc,
        "country_code": country,
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "purpose": purpose,
        "purpose_label": PURPOSE_LABELS.get(purpose, purpose),
        "freshness": freshness,
        "freshness_label": FRESHNESS_LABELS.get(freshness, freshness),
        "price_per_number": p.price_per_number,
        "currency": p.currency,
        "stock_count": stock,
        "total_sold": total_sold,
        "unsold_count": stock,
        "total_quantity": stock + total_sold,
        "min_purchase": p.min_purchase,
        "max_purchase": p.max_purchase,
        "product_type": p.product_type or "data_only",
        "sms_quota": p.sms_quota,
        "sms_unit_price": p.sms_unit_price,
        "bundle_price": p.bundle_price,
        "bundle_discount": p.bundle_discount,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def serialize_order(o, include_account: bool = False) -> dict:
    result = {
        "id": o.id,
        "order_no": o.order_no,
        "account_id": o.account_id,
        "product_id": o.product_id,
        "product_name": o.product.product_name if o.product else "自定义筛选",
        "filter_criteria": o.filter_criteria,
        "quantity": o.quantity,
        "unit_price": o.unit_price,
        "total_price": o.total_price,
        "order_type": o.order_type or "data_only",
        "status": o.status,
        "executed_count": o.executed_count,
        "cancel_reason": o.cancel_reason,
        "refund_amount": o.refund_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "executed_at": o.executed_at.isoformat() if o.executed_at else None,
        "refunded_at": o.refunded_at.isoformat() if o.refunded_at else None,
    }
    if include_account and o.account:
        result["account_name"] = getattr(o.account, 'username', None) or getattr(o.account, 'account_name', None)
    return result


def serialize_pricing_template(t: DataPricingTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "country_code": t.country_code,
        "source": t.source,
        "source_label": SOURCE_LABELS.get(t.source, t.source),
        "purpose": t.purpose,
        "purpose_label": PURPOSE_LABELS.get(t.purpose, t.purpose),
        "freshness": t.freshness,
        "freshness_label": FRESHNESS_LABELS.get(t.freshness, t.freshness),
        "price_per_number": str(t.price_per_number),
        "cost_per_number": str(t.cost_per_number) if t.cost_per_number else "0",
        "currency": t.currency,
        "remarks": t.remarks,
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
