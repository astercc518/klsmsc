"""管理员 - 定价模板管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from decimal import Decimal

from app.database import get_db
from app.modules.data.models import (
    DataPricingTemplate, DATA_SOURCES, DATA_PURPOSES, FRESHNESS_TIERS,
    SOURCE_LABELS, PURPOSE_LABELS, FRESHNESS_LABELS,
)
from app.core.auth import get_current_admin
from app.schemas.data import PricingTemplateCreate, PricingTemplateUpdate, PricingTemplateBatchCreate
from app.api.v1.data.helpers import serialize_pricing_template

router = APIRouter()

_ISO_TO_CN = {
    'CN': '中国', 'VN': '越南', 'PH': '菲律宾', 'BR': '巴西',
    'CO': '哥伦比亚', 'MX': '墨西哥', 'ID': '印尼', 'TH': '泰国',
    'IN': '印度', 'MY': '马来西亚', 'SG': '新加坡', 'JP': '日本',
    'KR': '韩国', 'US': '美国', 'GB': '英国', 'DE': '德国',
    'FR': '法国', 'AU': '澳大利亚', 'CA': '加拿大', 'RU': '俄罗斯',
    'SA': '沙特', 'AE': '阿联酋', 'TR': '土耳其', 'NG': '尼日利亚',
    'EG': '埃及', 'ZA': '南非', 'PE': '秘鲁', 'CL': '智利',
    'AR': '阿根廷', 'PK': '巴基斯坦', 'BD': '孟加拉',
    'MM': '缅甸', 'KH': '柬埔寨', 'LA': '老挝', 'NP': '尼泊尔',
    'TW': '台湾', 'HK': '香港', 'MO': '澳门',
}


def _country_name(code: str) -> str:
    """ISO 码 → 中文国名，兼容旧的拨号码"""
    if not code or code == '*':
        return '全部'
    name = _ISO_TO_CN.get(code.upper())
    if name:
        return name
    if code.isdigit():
        import phonenumbers
        regions = phonenumbers.region_codes_for_country_code(int(code))
        if regions:
            return _ISO_TO_CN.get(regions[0], code)
    return code


@router.get("/pricing-templates")
async def list_pricing_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    country_code: Optional[str] = None,
    source: Optional[str] = None,
    purpose: Optional[str] = None,
    freshness: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取定价模板列表"""
    query = select(DataPricingTemplate)
    if country_code:
        query = query.where(DataPricingTemplate.country_code == country_code)
    if source:
        query = query.where(DataPricingTemplate.source == source)
    if purpose:
        query = query.where(DataPricingTemplate.purpose == purpose)
    if freshness:
        query = query.where(DataPricingTemplate.freshness == freshness)
    if status:
        query = query.where(DataPricingTemplate.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(DataPricingTemplate.country_code, DataPricingTemplate.source, DataPricingTemplate.purpose, DataPricingTemplate.freshness)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    templates = result.scalars().all()

    return {
        "success": True,
        "items": [serialize_pricing_template(t) for t in templates],
        "total": total,
        "page": page,
        "page_size": page_size,
        "enums": {
            "sources": [{"value": k, "label": v} for k, v in SOURCE_LABELS.items()],
            "purposes": [{"value": k, "label": v} for k, v in PURPOSE_LABELS.items()],
            "freshness": [{"value": k, "label": v} for k, v in FRESHNESS_LABELS.items()],
        },
    }


@router.post("/pricing-templates")
async def create_pricing_template(
    data: PricingTemplateCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """创建定价模板"""
    if data.source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail=f"无效来源: {data.source}")
    if data.purpose not in DATA_PURPOSES:
        raise HTTPException(status_code=400, detail=f"无效用途: {data.purpose}")
    if data.freshness not in FRESHNESS_TIERS:
        raise HTTPException(status_code=400, detail=f"无效时效: {data.freshness}")

    existing = await db.execute(
        select(DataPricingTemplate).where(
            DataPricingTemplate.source == data.source,
            DataPricingTemplate.purpose == data.purpose,
            DataPricingTemplate.freshness == data.freshness,
            DataPricingTemplate.country_code == data.country_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该组合的定价模板已存在，请使用编辑功能修改")

    price = Decimal(data.price_per_number)
    cost = Decimal(data.cost_per_number) if data.cost_per_number else (price * Decimal('0.3')).quantize(Decimal('0.0001'))
    cn = _country_name(data.country_code)
    auto_name = f"{cn}-{SOURCE_LABELS[data.source]}-{PURPOSE_LABELS[data.purpose]}-{FRESHNESS_LABELS[data.freshness]}-{price}"

    tpl = DataPricingTemplate(
        name=data.name or auto_name,
        country_code=data.country_code,
        source=data.source,
        purpose=data.purpose,
        freshness=data.freshness,
        price_per_number=price,
        cost_per_number=cost,
        currency=data.currency,
        remarks=data.remarks,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)

    return {"success": True, "id": tpl.id, "name": tpl.name}


@router.post("/pricing-templates/batch")
async def batch_create_pricing_templates(
    data: PricingTemplateBatchCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """批量创建/更新定价模板"""
    created = 0
    updated = 0
    for item in data.items:
        if item.source not in DATA_SOURCES or item.purpose not in DATA_PURPOSES or item.freshness not in FRESHNESS_TIERS:
            continue

        existing = await db.execute(
            select(DataPricingTemplate).where(
                DataPricingTemplate.source == item.source,
                DataPricingTemplate.purpose == item.purpose,
                DataPricingTemplate.freshness == item.freshness,
                DataPricingTemplate.country_code == item.country_code,
            )
        )
        tpl = existing.scalar_one_or_none()
        price = Decimal(item.price_per_number)
        cost = Decimal(item.cost_per_number) if item.cost_per_number else (price * Decimal('0.3')).quantize(Decimal('0.0001'))
        cn = _country_name(item.country_code)
        auto_name = f"{cn}-{SOURCE_LABELS[item.source]}-{PURPOSE_LABELS[item.purpose]}-{FRESHNESS_LABELS[item.freshness]}-{price}"

        if tpl:
            tpl.price_per_number = price
            tpl.cost_per_number = cost
            tpl.currency = item.currency
            tpl.name = item.name or auto_name
            tpl.remarks = item.remarks
            tpl.status = 'active'
            updated += 1
        else:
            tpl = DataPricingTemplate(
                name=item.name or auto_name,
                country_code=item.country_code,
                source=item.source,
                purpose=item.purpose,
                freshness=item.freshness,
                price_per_number=price,
                cost_per_number=cost,
                currency=item.currency,
                remarks=item.remarks,
            )
            db.add(tpl)
            created += 1

    await db.commit()
    return {"success": True, "created": created, "updated": updated}


@router.put("/pricing-templates/{template_id}")
async def update_pricing_template(
    template_id: int,
    data: PricingTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """更新定价模板"""
    result = await db.execute(select(DataPricingTemplate).where(DataPricingTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")

    if data.price_per_number is not None:
        tpl.price_per_number = Decimal(data.price_per_number)
    if data.cost_per_number is not None:
        tpl.cost_per_number = Decimal(data.cost_per_number)
    if data.currency is not None:
        tpl.currency = data.currency
    if data.status is not None:
        tpl.status = data.status
    if data.name is not None:
        tpl.name = data.name
    if data.remarks is not None:
        tpl.remarks = data.remarks

    cn = _country_name(tpl.country_code)
    auto_name = f"{cn}-{SOURCE_LABELS.get(tpl.source, tpl.source)}-{PURPOSE_LABELS.get(tpl.purpose, tpl.purpose)}-{FRESHNESS_LABELS.get(tpl.freshness, tpl.freshness)}-{tpl.price_per_number}"
    if data.name is None:
        tpl.name = auto_name

    await db.commit()
    return {"success": True, "name": tpl.name}


@router.delete("/pricing-templates/{template_id}")
async def delete_pricing_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """删除定价模板"""
    result = await db.execute(select(DataPricingTemplate).where(DataPricingTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")

    await db.delete(tpl)
    await db.commit()
    return {"success": True}


@router.get("/pricing-templates/match")
async def match_pricing_template(
    country_code: str = Query(...),
    source: str = Query(...),
    purpose: str = Query(...),
    freshness: str = Query(...),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """根据条件匹配最佳定价模板（优先精确国家 > 通配符*）"""
    result = await db.execute(
        select(DataPricingTemplate).where(
            DataPricingTemplate.source == source,
            DataPricingTemplate.purpose == purpose,
            DataPricingTemplate.freshness == freshness,
            DataPricingTemplate.country_code == country_code,
            DataPricingTemplate.status == 'active',
        )
    )
    tpl = result.scalar_one_or_none()

    if not tpl and country_code != '*':
        result = await db.execute(
            select(DataPricingTemplate).where(
                DataPricingTemplate.source == source,
                DataPricingTemplate.purpose == purpose,
                DataPricingTemplate.freshness == freshness,
                DataPricingTemplate.country_code == '*',
                DataPricingTemplate.status == 'active',
            )
        )
        tpl = result.scalar_one_or_none()

    if tpl:
        return {"success": True, "matched": True, "template": serialize_pricing_template(tpl)}
    return {"success": True, "matched": False, "template": None}


@router.get("/pricing-matrix")
async def get_pricing_matrix(
    country_code: str = Query("*"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """获取完整价格矩阵视图"""
    result = await db.execute(
        select(DataPricingTemplate).where(
            DataPricingTemplate.country_code == country_code,
            DataPricingTemplate.status == 'active',
        )
    )
    templates = result.scalars().all()

    matrix = {}
    for t in templates:
        key = f"{t.source}_{t.purpose}"
        if key not in matrix:
            matrix[key] = {
                "source": t.source,
                "source_label": SOURCE_LABELS.get(t.source, t.source),
                "purpose": t.purpose,
                "purpose_label": PURPOSE_LABELS.get(t.purpose, t.purpose),
                "prices": {},
                "costs": {},
            }
        matrix[key]["prices"][t.freshness] = str(t.price_per_number)
        matrix[key]["costs"][t.freshness] = str(t.cost_per_number) if t.cost_per_number else "0"

    return {
        "success": True,
        "country_code": country_code,
        "matrix": list(matrix.values()),
        "freshness_columns": [{"value": k, "label": v} for k, v in FRESHNESS_LABELS.items()],
    }
