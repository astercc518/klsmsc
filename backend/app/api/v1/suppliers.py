"""供应商管理API"""
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, case
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal

from app.database import get_db
from app.modules.sms.supplier import Supplier, SupplierChannel, SupplierRate, SellRate, RateDeck, AccountRateDeck
from app.modules.sms.channel import Channel
from app.api.v1.admin import get_current_admin
from app.modules.common.admin_user import AdminUser
from app.utils.country_code import normalize_country_code
from app.core.audit_dep import audited

router = APIRouter(prefix="/admin/suppliers", tags=["供应商管理"])


# ============ Pydantic 模型 ============

class SupplierCreate(BaseModel):
    supplier_code: str = Field(..., max_length=50, description="供应商编码")
    supplier_name: str = Field(..., max_length=100, description="供应商名称")
    supplier_group: Optional[str] = Field(None, max_length=100, description="供应商群组名称")
    telegram_group_id: Optional[str] = Field(None, max_length=50, description="Telegram群组ID，用于短信审核转发")
    supplier_type: str = Field(default="direct", description="供应商类型")
    business_type: str = Field(default="sms", description="业务类型")
    country: Optional[str] = Field(None, max_length=100, description="国家")
    resource_type: Optional[str] = Field(None, max_length=50, description="资源类型")
    cost_price: Decimal = Field(default=0, description="成本价")
    cost_currency: str = Field(default="USD", description="成本币种")
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    protocol: str = Field(default="HTTP")
    status: str = Field(default="active")
    priority: int = Field(default=0)
    settlement_currency: str = Field(default="USD")
    settlement_period: str = Field(default="monthly")
    settlement_day: int = Field(default=1)
    payment_method: str = Field(default="postpaid")
    credit_limit: Decimal = Field(default=0)
    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None
    notes: Optional[str] = None


class SupplierUpdate(BaseModel):
    supplier_name: Optional[str] = None
    supplier_group: Optional[str] = None
    telegram_group_id: Optional[str] = None
    supplier_type: Optional[str] = None
    business_type: Optional[str] = None
    country: Optional[str] = None
    resource_type: Optional[str] = None
    cost_price: Optional[Decimal] = None
    cost_currency: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    protocol: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    settlement_currency: Optional[str] = None
    settlement_period: Optional[str] = None
    settlement_day: Optional[int] = None
    payment_method: Optional[str] = None
    credit_limit: Optional[Decimal] = None
    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None
    notes: Optional[str] = None


class SupplierRateCreate(BaseModel):
    business_type: str = Field(default="sms", description="业务类型：sms/voice/data")
    country_code: str = Field(..., description="国家代码")
    resource_type: str = Field(default="card", description="资源类型/发送方式")
    business_scope: str = Field(default="otp", description="业务范围")
    billing_model: Optional[str] = Field(None, max_length=20, description="语音计费模式：1+1/6+6/30+6/60+1/60+60")
    line_desc: Optional[str] = Field(None, max_length=100, description="语音线路描述")
    mcc: Optional[str] = None
    mnc: Optional[str] = None
    operator_name: Optional[str] = None
    cost_price: Decimal = Field(..., description="成本价")
    sell_price: Decimal = Field(default=0, description="售价")
    remark: Optional[str] = Field(None, max_length=255, description="备注")
    currency: str = Field(default="USD")
    effective_date: Optional[datetime] = None
    expire_date: Optional[datetime] = None


class SupplierRateBatchImport(BaseModel):
    rates: List[SupplierRateCreate]


class RateDeckCreate(BaseModel):
    deck_name: str = Field(..., max_length=100)
    deck_code: str = Field(..., max_length=50)
    description: Optional[str] = None
    deck_type: str = Field(default="standard")
    markup_type: str = Field(default="percentage")
    markup_value: Decimal = Field(default=0)
    is_default: bool = Field(default=False)


class SellRateCreate(BaseModel):
    rate_deck_id: Optional[int] = None
    account_id: Optional[int] = None
    country_code: str = Field(..., description="国家代码")
    mcc: Optional[str] = None
    mnc: Optional[str] = None
    operator_name: Optional[str] = None
    sell_price: Decimal = Field(..., description="销售价")
    currency: str = Field(default="USD")
    effective_date: Optional[datetime] = None
    expire_date: Optional[datetime] = None


# ============ 供应商 CRUD ============

@router.get("")
async def get_suppliers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    status: Optional[str] = None,
    business_type: Optional[str] = None,
    resource_type: Optional[str] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取供应商列表"""
    query = select(Supplier).where(Supplier.is_deleted == False)
    
    if status:
        query = query.where(Supplier.status == status)
    
    if business_type:
        query = query.where(Supplier.business_type == business_type)
    
    if resource_type:
        query = query.where(Supplier.resource_type == resource_type)
    
    if keyword:
        query = query.where(
            or_(
                Supplier.supplier_code.ilike(f"%{keyword}%"),
                Supplier.supplier_name.ilike(f"%{keyword}%"),
                Supplier.supplier_group.ilike(f"%{keyword}%")
            )
        )
    
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # 分页
    query = query.order_by(Supplier.priority.desc(), Supplier.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    suppliers = result.scalars().all()
    
    # 获取每个供应商的报价统计
    supplier_ids = [s.id for s in suppliers]
    rate_stats = {}
    if supplier_ids:
        # 查询报价数量和覆盖国家数
        stats_query = select(
            SupplierRate.supplier_id,
            func.count(SupplierRate.id).label('rate_count'),
            func.count(func.distinct(SupplierRate.country_code)).label('country_count')
        ).where(
            SupplierRate.supplier_id.in_(supplier_ids),
            SupplierRate.status == 'active'
        ).group_by(SupplierRate.supplier_id)
        
        stats_result = await db.execute(stats_query)
        for row in stats_result:
            rate_stats[row.supplier_id] = {
                'rate_count': row.rate_count,
                'country_count': row.country_count
            }
    
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "suppliers": [
            {
                "id": s.id,
                "supplier_code": s.supplier_code,
                "supplier_name": s.supplier_name,
                "supplier_group": s.supplier_group,
                "telegram_group_id": getattr(s, 'telegram_group_id', None),
                "supplier_type": s.supplier_type,
                "business_type": s.business_type,
                "rate_count": rate_stats.get(s.id, {}).get('rate_count', 0),
                "country_count": rate_stats.get(s.id, {}).get('country_count', 0),
                "contact_person": s.contact_person,
                "contact_email": s.contact_email,
                "contact_phone": s.contact_phone,
                "protocol": s.protocol,
                "status": s.status,
                "priority": s.priority,
                "settlement_currency": s.settlement_currency,
                "settlement_period": s.settlement_period,
                "payment_method": s.payment_method,
                "credit_limit": float(s.credit_limit) if s.credit_limit else 0,
                "current_balance": float(s.current_balance) if s.current_balance else 0,
                "notes": s.notes,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in suppliers
        ]
    }


@router.get("/by-business-type")
async def get_suppliers_by_business_type(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """
    按业务类型分组返回供应商及报价统计
    供应商对应业务，业务对应资源报价
    """
    base_supplier = select(Supplier).where(Supplier.is_deleted == False)
    if status:
        base_supplier = base_supplier.where(Supplier.status == status)
    if keyword:
        base_supplier = base_supplier.where(
            or_(
                Supplier.supplier_code.ilike(f"%{keyword}%"),
                Supplier.supplier_name.ilike(f"%{keyword}%"),
                Supplier.supplier_group.ilike(f"%{keyword}%")
            )
        )

    result = {}
    for biz in ["sms", "voice", "data"]:
        # 1. 该业务类型下有报价的供应商
        subq = (
            select(SupplierRate.supplier_id)
            .where(
                SupplierRate.business_type == biz,
                SupplierRate.status == 'active'
            )
            .distinct()
        )
        q = (
            select(
                Supplier,
                func.count(SupplierRate.id).label('rate_count'),
                func.count(func.distinct(SupplierRate.country_code)).label('country_count')
            )
            .join(SupplierRate, Supplier.id == SupplierRate.supplier_id)
            .where(
                Supplier.id.in_(subq),
                SupplierRate.business_type == biz,
                SupplierRate.status == 'active',
                Supplier.is_deleted == False
            )
        )
        if status:
            q = q.where(Supplier.status == status)
        if keyword:
            q = q.where(
                or_(
                    Supplier.supplier_code.ilike(f"%{keyword}%"),
                    Supplier.supplier_name.ilike(f"%{keyword}%"),
                    Supplier.supplier_group.ilike(f"%{keyword}%")
                )
            )
        q = q.group_by(Supplier.id).order_by(Supplier.priority.desc(), Supplier.created_at.desc())
        rows = (await db.execute(q)).all()
        seen_ids = {s.id for s, _, _ in rows}

        suppliers_list = []
        for s, rc, cc in rows:
            suppliers_list.append({
                "id": s.id,
                "supplier_code": s.supplier_code,
                "supplier_name": s.supplier_name,
                "supplier_group": s.supplier_group,
                "telegram_group_id": getattr(s, 'telegram_group_id', None),
                "status": s.status,
                "business_type": getattr(s, 'business_type', 'sms'),
                "rate_count": int(rc or 0),
                "country_count": int(cc or 0),
                "notes": s.notes,
            })

        # 2. 主业务类型为该类型、但尚无报价的供应商（新建后未添加报价的，如 KL数据）
        q2 = (
            select(Supplier)
            .where(
                Supplier.business_type == biz,
                Supplier.is_deleted == False
            )
        )
        if seen_ids:
            q2 = q2.where(Supplier.id.not_in(seen_ids))
        if status:
            q2 = q2.where(Supplier.status == status)
        if keyword:
            q2 = q2.where(
                or_(
                    Supplier.supplier_code.ilike(f"%{keyword}%"),
                    Supplier.supplier_name.ilike(f"%{keyword}%"),
                    Supplier.supplier_group.ilike(f"%{keyword}%")
                )
            )
        q2 = q2.order_by(Supplier.priority.desc(), Supplier.created_at.desc())
        rows2 = (await db.execute(q2)).scalars().all()
        for s in rows2:
            suppliers_list.append({
                "id": s.id,
                "supplier_code": s.supplier_code,
                "supplier_name": s.supplier_name,
                "supplier_group": s.supplier_group,
                "telegram_group_id": getattr(s, 'telegram_group_id', None),
                "status": s.status,
                "business_type": getattr(s, 'business_type', 'sms'),
                "rate_count": 0,
                "country_count": 0,
                "notes": s.notes,
            })

        result[biz] = {"suppliers": suppliers_list, "total": len(suppliers_list)}

    return {"success": True, "by_business": result}


@router.post("/{supplier_id}/remove-from-business")
async def remove_supplier_from_business(
    supplier_id: int,
    business_type: str = Query(..., description="业务类型：sms/voice/data"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """
    将供应商从指定业务中移除（停用该供应商在此业务下的所有报价）。
    用于纠正误归类的供应商，如一正通信本属短信业务但误有数据业务报价。
    """
    if business_type not in ("sms", "voice", "data"):
        raise HTTPException(status_code=400, detail="business_type 必须为 sms/voice/data 之一")
    # 校验供应商存在
    r = await db.execute(select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted == False))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="供应商不存在")
    stmt = (
        update(SupplierRate)
        .where(
            SupplierRate.supplier_id == supplier_id,
            SupplierRate.business_type == business_type,
            SupplierRate.status == 'active'
        )
        .values(status='inactive')
    )
    result = await db.execute(stmt)
    await db.commit()
    n = result.rowcount
    label_map = {"sms": "短信", "voice": "语音", "data": "数据"}
    return {"success": True, "message": f"已从{label_map.get(business_type, business_type)}业务移除，停用 {n} 条报价", "deactivated": n}


@router.post("/{supplier_id}/sync-from-data-pricing")
async def sync_supplier_rates_from_data_pricing(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """
    将指定供应商（数据业务）的报价表同步自「数据业务定价模板」。
    仅支持 business_type='data' 的供应商（如 KL数据）。
    按模板的 country_code、source、purpose、freshness 生成 supplier_rates，成本/售价取自模板。
    """
    from app.modules.data.models import DataPricingTemplate
    r = await db.execute(select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted == False))
    supplier = r.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")
    biz = getattr(supplier, 'business_type', None) or 'sms'
    if biz != 'data':
        raise HTTPException(status_code=400, detail="仅支持数据业务供应商，当前供应商业务类型为 " + biz)

    tpls = (await db.execute(
        select(DataPricingTemplate).where(
            DataPricingTemplate.status == 'active',
            DataPricingTemplate.country_code != '*'
        )
    )).scalars().all()
    created, updated = 0, 0
    for t in tpls:
        resource_type = f"{t.source}_{t.purpose}_{t.freshness}"[:50]
        remark = f"同步自定价模板 {t.name or t.id}"
        exist = (await db.execute(
            select(SupplierRate).where(
                SupplierRate.supplier_id == supplier_id,
                SupplierRate.business_type == 'data',
                SupplierRate.country_code == t.country_code,
                SupplierRate.resource_type == resource_type
            ).limit(1)
        )).scalar_one_or_none()
        cost = Decimal(str(t.cost_per_number or 0))
        price = Decimal(str(t.price_per_number or 0))
        if exist:
            exist.cost_price = cost
            exist.sell_price = price
            exist.currency = t.currency or 'USD'
            exist.remark = remark
            exist.status = 'active'
            updated += 1
        else:
            rate = SupplierRate(
                supplier_id=supplier_id,
                business_type='data',
                country_code=t.country_code,
                resource_type=resource_type,
                business_scope='otp',
                cost_price=cost,
                sell_price=price,
                currency=t.currency or 'USD',
                remark=remark,
                status='active',
            )
            db.add(rate)
            created += 1
    await db.commit()
    return {
        "success": True,
        "message": f"同步完成：新增 {created} 条，更新 {updated} 条报价",
        "created": created,
        "updated": updated,
    }


@router.post("/import-from-resource-pricing")
async def import_from_resource_pricing(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """
    从 data/resource_pricing.json 导入供应商报价到 supplier_rates 表
    自动创建不存在的供应商，批量导入各供应商的国家报价
    """
    data_path = Path("/app/data/resource_pricing.json")
    if not data_path.exists():
        raise HTTPException(status_code=404, detail="资源报价文件不存在，请先运行 scripts/generate_resource_pricing.py 生成")

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    by_supplier = data.get("by_supplier", {})
    if not by_supplier:
        raise HTTPException(status_code=400, detail="资源报价文件为空或格式不正确")

    created_suppliers = 0
    imported_rates = 0
    skipped_rates = 0

    for supplier_name, info in by_supplier.items():
        supplier_name = (supplier_name or "").strip()
        countries = info.get("countries", {})
        if not countries:
            continue

        # 查找或创建供应商（名称精确匹配，去除首尾空格）
        result = await db.execute(
            select(Supplier).where(
                Supplier.supplier_name == supplier_name,
                Supplier.is_deleted == False
            )
        )
        supplier = result.scalar_one_or_none()

        if not supplier:
            safe = supplier_name.replace(" ", "_").replace("通信", "").replace("短信", "")[:10] or "SUP"
            code = f"SP_{safe}_{int(time.time() % 100000)}"
            supplier = Supplier(
                supplier_code=code,
                supplier_name=supplier_name,
                business_type="sms",
                status="active",
                cost_currency="USD",
            )
            db.add(supplier)
            await db.flush()
            created_suppliers += 1

        supplier_id = supplier.id

        for country_code, item in countries.items():
            cost = item.get("cost_usd") or item.get("price_usd")
            sale = item.get("sale_usd") or item.get("price_usd")
            if cost is None or float(cost) <= 0:
                continue

            typ = (item.get("type") or "SMS").lower()
            business_type = "data" if typ == "data" else "sms"
            resource_type = (item.get("resource_type") or "card")[:50]

            # 避免重复：若该供应商+国家+业务类型+资源类型已存在则跳过
            exist_result = await db.execute(
                select(SupplierRate.id).where(
                    SupplierRate.supplier_id == supplier_id,
                    SupplierRate.country_code == country_code,
                    SupplierRate.business_type == business_type,
                    SupplierRate.resource_type == resource_type,
                ).limit(1)
            )
            if exist_result.scalar_one_or_none():
                skipped_rates += 1
                continue

            rate = SupplierRate(
                supplier_id=supplier_id,
                business_type=business_type,
                country_code=country_code,
                resource_type=resource_type,
                business_scope="otp",
                cost_price=Decimal(str(cost)),
                sell_price=Decimal(str(sale)) if sale else Decimal("0"),
                remark=item.get("description"),
                currency="USD",
            )
            db.add(rate)
            imported_rates += 1

    await db.commit()

    msg = f"导入完成：新增 {created_suppliers} 个供应商，导入 {imported_rates} 条报价"
    if skipped_rates > 0:
        msg += f"，跳过已存在 {skipped_rates} 条"
    return {
        "success": True,
        "message": msg,
    }


@router.post("/import-from-voice-pricing")
async def import_from_voice_pricing(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """
    从 data/resource_voice_pricing.json 导入语音供应商及报价
    自动创建不存在的语音供应商，批量导入各供应商的语音网关报价
    """
    data_path = Path("/app/data/resource_voice_pricing.json")
    if not data_path.exists():
        raise HTTPException(status_code=404, detail="语音报价文件不存在，请先运行 scripts/parse_voice_pricing.py 生成")

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    by_supplier = data.get("by_supplier", {})
    if not by_supplier:
        raise HTTPException(status_code=400, detail="语音报价文件为空或格式不正确")

    created_suppliers = 0
    imported_rates = 0
    skipped_rates = 0

    for supplier_name, info in by_supplier.items():
        supplier_name = (supplier_name or "").strip()
        items = info.get("items", [])
        if not items:
            continue

        channel_code = info.get("channel_code", "")

        result = await db.execute(
            select(Supplier).where(
                Supplier.supplier_name == supplier_name,
                Supplier.is_deleted == False
            )
        )
        supplier = result.scalar_one_or_none()

        if not supplier:
            safe = supplier_name.replace(" ", "_")[:10] or "VOICE"
            code = channel_code or f"VOICE_{safe}_{int(time.time() % 100000)}"
            supplier = Supplier(
                supplier_code=code,
                supplier_name=supplier_name,
                business_type="voice",
                status="active",
                cost_currency="USD",
            )
            db.add(supplier)
            await db.flush()
            created_suppliers += 1

        supplier_id = supplier.id

        for item in items:
            country_code = item.get("country_code") or ""
            cost = item.get("cost_usd") or item.get("price_usd")
            sale = item.get("sale_usd") or item.get("price_usd")
            gateway_name = (item.get("gateway_name") or "")[:255]
            billing_model_val = (item.get("billing_model") or "60+60")[:20]
            full_desc = (item.get("full_desc") or "")[:255]
            description = (item.get("description") or "")[:100]

            if not country_code or cost is None or float(cost) <= 0:
                continue

            remark = gateway_name or full_desc

            # 去重：同供应商 + 同国家 + 同计费模式 + 同线路描述 = 同一条报价
            dedup_where = [
                SupplierRate.supplier_id == supplier_id,
                SupplierRate.country_code == country_code,
                SupplierRate.business_type == "voice",
                SupplierRate.billing_model == billing_model_val,
            ]
            if description:
                dedup_where.append(SupplierRate.line_desc == description)
            else:
                dedup_where.append(
                    or_(SupplierRate.line_desc == None, SupplierRate.line_desc == "")  # noqa: E711
                )

            exist_result = await db.execute(
                select(SupplierRate.id).where(*dedup_where).limit(1)
            )
            if exist_result.scalar_one_or_none():
                skipped_rates += 1
                continue

            rate = SupplierRate(
                supplier_id=supplier_id,
                business_type="voice",
                country_code=country_code,
                resource_type="voice",
                business_scope="otp",
                billing_model=billing_model_val,
                line_desc=description or None,
                cost_price=Decimal(str(cost)),
                sell_price=Decimal(str(sale)) if sale else Decimal("0"),
                remark=remark or None,
                currency="USD",
            )
            db.add(rate)
            imported_rates += 1

    await db.commit()

    msg = f"导入完成：新增 {created_suppliers} 个语音供应商，导入 {imported_rates} 条报价"
    if skipped_rates > 0:
        msg += f"，跳过已存在 {skipped_rates} 条"
    return {
        "success": True,
        "message": msg,
    }


@router.get("/voice-pricing-reference")
async def get_voice_pricing_reference(
    admin: AdminUser = Depends(get_current_admin)
):
    """
    获取语音业务报价参考数据（来自 data/resource_voice_pricing.json）
    用于资源报价页面的语音 tab 展示
    """
    data_path = Path("/app/data/resource_voice_pricing.json")
    if not data_path.exists():
        return {
            "success": True,
            "flat_list": [],
            "total_records": 0,
            "supplier_count": 0,
            "country_count": 0,
        }
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "success": True,
        "flat_list": data.get("flat_list", []),
        "total_records": data.get("total_records", 0),
        "supplier_count": data.get("supplier_count", 0),
        "country_count": data.get("country_count", 0),
    }


@router.post("")
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "create")),
):
    """创建供应商"""
    admin, audit = auth
    # 检查编码是否已存在
    existing = await db.execute(
        select(Supplier).where(Supplier.supplier_code == data.supplier_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="供应商编码已存在")

    supplier = Supplier(**data.dict())
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    await audit(target_id=supplier.id, target_type="supplier",
                title=f"创建供应商 {supplier.supplier_code}",
                detail={"supplier_code": supplier.supplier_code,
                        "supplier_name": supplier.supplier_name})
    await db.commit()
    return {"success": True, "message": "供应商创建成功", "supplier_id": supplier.id}


@router.get("/{supplier_id}")
async def get_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取供应商详情"""
    result = await db.execute(
        select(Supplier)
        .options(selectinload(Supplier.channels))
        .where(Supplier.id == supplier_id, Supplier.is_deleted == False)
    )
    supplier = result.scalar_one_or_none()
    
    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    return {
        "success": True,
        "supplier": {
            "id": supplier.id,
            "supplier_code": supplier.supplier_code,
            "supplier_name": supplier.supplier_name,
            "supplier_group": supplier.supplier_group,
            "telegram_group_id": supplier.telegram_group_id,
            "supplier_type": supplier.supplier_type,
            "contact_person": supplier.contact_person,
            "contact_email": supplier.contact_email,
            "contact_phone": supplier.contact_phone,
            "contact_address": supplier.contact_address,
            "api_endpoint": supplier.api_endpoint,
            "api_key": supplier.api_key,
            "protocol": supplier.protocol,
            "status": supplier.status,
            "priority": supplier.priority,
            "settlement_currency": supplier.settlement_currency,
            "settlement_period": supplier.settlement_period,
            "settlement_day": supplier.settlement_day,
            "payment_method": supplier.payment_method,
            "credit_limit": float(supplier.credit_limit) if supplier.credit_limit else 0,
            "current_balance": float(supplier.current_balance) if supplier.current_balance else 0,
            "contract_start_date": supplier.contract_start_date.isoformat() if supplier.contract_start_date else None,
            "contract_end_date": supplier.contract_end_date.isoformat() if supplier.contract_end_date else None,
            "notes": supplier.notes,
            "created_at": supplier.created_at.isoformat() if supplier.created_at else None,
            "channel_count": len(supplier.channels) if supplier.channels else 0
        }
    }


@router.put("/{supplier_id}")
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "update")),
):
    """更新供应商"""
    admin, audit = auth
    result = await db.execute(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted == False)
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(supplier, key, value)

    await db.commit()
    await audit(target_id=supplier_id, target_type="supplier",
                title=f"更新供应商 {supplier.supplier_code}",
                detail={"changed_fields": list(update_data.keys())})
    await db.commit()
    return {"success": True, "message": "供应商更新成功"}


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "delete")),
):
    """删除供应商(软删除)"""
    admin, audit = auth
    result = await db.execute(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted == False)
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")

    supplier.is_deleted = True
    await db.commit()
    await audit(target_id=supplier_id, target_type="supplier",
                title=f"删除供应商 {supplier.supplier_code}",
                detail={"supplier_name": supplier.supplier_name})
    await db.commit()
    return {"success": True, "message": "供应商删除成功"}


# ============ 供应商费率管理 ============

@router.get("/{supplier_id}/rates")
async def get_supplier_rates(
    supplier_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    business_type: Optional[str] = None,
    country_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取供应商费率列表"""
    query = select(SupplierRate).where(
        SupplierRate.supplier_id == supplier_id,
        SupplierRate.status == 'active'
    )
    
    if business_type:
        query = query.where(SupplierRate.business_type == business_type)
    
    if country_code:
        query = query.where(SupplierRate.country_code == country_code)
    
    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # 分页 - 按业务类型和国家排序
    query = query.order_by(SupplierRate.business_type, SupplierRate.country_code)
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    rates = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "rates": [
            {
                "id": r.id,
                "business_type": r.business_type or 'sms',
                "country_code": r.country_code,
                "resource_type": r.resource_type or 'card',
                "business_scope": r.business_scope or 'otp',
                "billing_model": getattr(r, 'billing_model', None) or '',
                "line_desc": getattr(r, 'line_desc', None) or '',
                "mcc": r.mcc,
                "mnc": r.mnc,
                "operator_name": r.operator_name,
                "cost_price": float(r.cost_price) if r.cost_price else 0,
                "sell_price": float(r.sell_price) if r.sell_price else 0,
                "remark": r.remark,
                "currency": r.currency,
                "effective_date": r.effective_date.isoformat() if r.effective_date else None,
                "expire_date": r.expire_date.isoformat() if r.expire_date else None,
                "status": r.status or 'active'
            }
            for r in rates
        ]
    }


@router.post("/{supplier_id}/rates")
async def create_supplier_rate(
    supplier_id: int,
    data: SupplierRateCreate,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "create_rate")),
):
    """创建供应商费率"""
    admin, audit = auth
    # 验证供应商存在
    supplier = await db.get(Supplier, supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="供应商不存在")

    rate_data = data.dict()
    rate_data["country_code"] = normalize_country_code(rate_data.get("country_code")) or rate_data.get("country_code")
    rate = SupplierRate(supplier_id=supplier_id, **rate_data)
    db.add(rate)
    await db.commit()
    await audit(target_id=rate.id, target_type="supplier_rate",
                title=f"新增供应商费率 supplier={supplier.supplier_code} country={rate.country_code}",
                detail={"supplier_id": supplier_id,
                        "country_code": rate.country_code,
                        "cost_price": float(rate.cost_price or 0),
                        "sell_price": float(rate.sell_price or 0)})
    await db.commit()
    return {"success": True, "message": "费率创建成功", "rate_id": rate.id}


@router.post("/{supplier_id}/rates/batch")
async def batch_import_supplier_rates(
    supplier_id: int,
    data: SupplierRateBatchImport,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "batch_import_rates")),
):
    """批量导入供应商费率"""
    admin, audit = auth
    supplier = await db.get(Supplier, supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="供应商不存在")

    created_count = 0
    for rate_item in data.rates:
        rd = rate_item.dict()
        rd["country_code"] = normalize_country_code(rd.get("country_code")) or rd.get("country_code")
        rate = SupplierRate(supplier_id=supplier_id, **rd)
        db.add(rate)
        created_count += 1

    await db.commit()
    await audit(target_id=supplier_id, target_type="supplier",
                title=f"批量导入供应商费率 {created_count} 条",
                detail={"supplier_code": supplier.supplier_code, "count": created_count})
    await db.commit()
    return {"success": True, "message": f"成功导入 {created_count} 条费率"}


class SupplierRateUpdate(BaseModel):
    business_type: Optional[str] = None
    country_code: Optional[str] = None
    resource_type: Optional[str] = None
    business_scope: Optional[str] = None
    billing_model: Optional[str] = None
    line_desc: Optional[str] = None
    cost_price: Optional[Decimal] = None
    sell_price: Optional[Decimal] = None
    remark: Optional[str] = None
    status: Optional[str] = None


@router.put("/{supplier_id}/rates/{rate_id}")
async def update_supplier_rate(
    supplier_id: int,
    rate_id: int,
    data: SupplierRateUpdate,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "update_rate")),
):
    """更新供应商报价"""
    admin, audit = auth
    result = await db.execute(
        select(SupplierRate).where(
            SupplierRate.id == rate_id,
            SupplierRate.supplier_id == supplier_id
        )
    )
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(status_code=404, detail="报价不存在")

    update_data = data.dict(exclude_unset=True)
    if "country_code" in update_data:
        update_data["country_code"] = normalize_country_code(update_data["country_code"]) or update_data["country_code"]
    for key, value in update_data.items():
        setattr(rate, key, value)

    await db.commit()
    await audit(target_id=rate_id, target_type="supplier_rate",
                title=f"更新供应商报价 supplier_id={supplier_id} rate_id={rate_id}",
                detail={"changed_fields": list(update_data.keys())})
    await db.commit()
    return {"success": True, "message": "报价更新成功"}


@router.delete("/{supplier_id}/rates/{rate_id}")
async def delete_supplier_rate(
    supplier_id: int,
    rate_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "delete_rate")),
):
    """删除供应商报价"""
    admin, audit = auth
    result = await db.execute(
        select(SupplierRate).where(
            SupplierRate.id == rate_id,
            SupplierRate.supplier_id == supplier_id
        )
    )
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(status_code=404, detail="报价不存在")

    snap = {"country_code": rate.country_code, "business_type": rate.business_type,
            "cost_price": float(rate.cost_price or 0), "sell_price": float(rate.sell_price or 0)}
    await db.delete(rate)
    await db.commit()
    await audit(target_id=rate_id, target_type="supplier_rate",
                title=f"删除供应商报价 supplier_id={supplier_id}",
                detail=snap)
    await db.commit()
    return {"success": True, "message": "报价删除成功"}


# ============ 销售费率表管理 ============

@router.get("/rate-decks", name="get_rate_decks")
async def get_rate_decks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取费率表列表"""
    query = select(RateDeck).where(RateDeck.is_deleted == False)
    
    if status:
        query = query.where(RateDeck.status == status)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.order_by(RateDeck.is_default.desc(), RateDeck.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    decks = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "rate_decks": [
            {
                "id": d.id,
                "deck_code": d.deck_code,
                "deck_name": d.deck_name,
                "deck_type": d.deck_type,
                "markup_type": d.markup_type,
                "markup_value": float(d.markup_value) if d.markup_value else 0,
                "is_default": d.is_default,
                "status": d.status,
                "description": d.description,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in decks
        ]
    }


@router.post("/rate-decks", name="create_rate_deck")
async def create_rate_deck(
    data: RateDeckCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """创建费率表"""
    # 检查编码是否存在
    existing = await db.execute(
        select(RateDeck).where(RateDeck.deck_code == data.deck_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="费率表编码已存在")
    
    # 如果设置为默认，取消其他默认
    if data.is_default:
        await db.execute(
            select(RateDeck).where(RateDeck.is_default == True)
        )
        # 这里应该更新其他记录
    
    deck = RateDeck(**data.dict())
    db.add(deck)
    await db.commit()
    
    return {"success": True, "message": "费率表创建成功", "deck_id": deck.id}


@router.get("/rate-decks/{deck_id}/rates", name="get_deck_rates")
async def get_rate_deck_rates(
    deck_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    country_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取费率表的销售费率列表"""
    query = select(SellRate).where(
        SellRate.rate_deck_id == deck_id,
        SellRate.status == 'active'
    )
    
    if country_code:
        query = query.where(SellRate.country_code == country_code)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.order_by(SellRate.country_code)
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    rates = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "rates": [
            {
                "id": r.id,
                "country_code": r.country_code,
                "mcc": r.mcc,
                "mnc": r.mnc,
                "operator_name": r.operator_name,
                "sell_price": float(r.sell_price),
                "currency": r.currency,
                "effective_date": r.effective_date.isoformat() if r.effective_date else None,
                "status": r.status
            }
            for r in rates
        ]
    }


@router.post("/rate-decks/{deck_id}/rates", name="create_deck_rate")
async def create_rate_deck_rate(
    deck_id: int,
    data: SellRateCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """创建销售费率"""
    deck = await db.get(RateDeck, deck_id)
    if not deck or deck.is_deleted:
        raise HTTPException(status_code=404, detail="费率表不存在")
    
    rate = SellRate(rate_deck_id=deck_id, **data.dict(exclude={'rate_deck_id'}))
    db.add(rate)
    await db.commit()
    
    return {"success": True, "message": "销售费率创建成功", "rate_id": rate.id}


# ============ 供应商通道关联 ============

@router.get("/{supplier_id}/channels")
async def get_supplier_channels(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取供应商关联的通道"""
    result = await db.execute(
        select(SupplierChannel)
        .options(selectinload(SupplierChannel.channel))
        .where(SupplierChannel.supplier_id == supplier_id)
    )
    channels = result.scalars().all()
    
    return {
        "success": True,
        "channels": [
            {
                "id": c.id,
                "channel_id": c.channel_id,
                "channel_code": c.channel.channel_code if c.channel else None,
                "channel_name": c.channel.channel_name if c.channel else None,
                "supplier_channel_code": c.supplier_channel_code,
                "status": c.status
            }
            for c in channels
        ]
    }


@router.post("/{supplier_id}/channels")
async def link_supplier_channel(
    supplier_id: int,
    channel_id: int,
    supplier_channel_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "link_channel")),
):
    """关联供应商与通道"""
    admin, audit = auth
    # 验证供应商
    supplier = await db.get(Supplier, supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="供应商不存在")

    # 验证通道
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    # 检查是否已关联
    existing = await db.execute(
        select(SupplierChannel).where(
            SupplierChannel.supplier_id == supplier_id,
            SupplierChannel.channel_id == channel_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="通道已关联")

    link = SupplierChannel(
        supplier_id=supplier_id,
        channel_id=channel_id,
        supplier_channel_code=supplier_channel_code
    )
    db.add(link)
    await db.commit()
    await audit(target_id=supplier_id, target_type="supplier_channel",
                title=f"关联通道 supplier={supplier.supplier_code} channel={channel.channel_code}",
                detail={"channel_id": channel_id, "supplier_channel_code": supplier_channel_code})
    await db.commit()
    return {"success": True, "message": "通道关联成功"}


@router.delete("/{supplier_id}/channels/{channel_id}")
async def unlink_supplier_channel(
    supplier_id: int,
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("supplier", "unlink_channel")),
):
    """解绑供应商与通道"""
    admin, audit = auth
    result = await db.execute(
        select(SupplierChannel).where(
            SupplierChannel.supplier_id == supplier_id,
            SupplierChannel.channel_id == channel_id
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="通道关联不存在")

    await db.delete(link)
    await db.commit()
    await audit(target_id=supplier_id, target_type="supplier_channel",
                title=f"解绑通道 supplier_id={supplier_id} channel_id={channel_id}",
                detail={"channel_id": channel_id})
    await db.commit()
    return {"success": True, "message": "通道解绑成功"}


# ============ 统计接口 ============

@router.get("/{supplier_id}/statistics")
async def get_supplier_statistics(
    supplier_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """获取供应商统计数据"""
    from app.modules.sms.sms_log import SMSLog
    
    # 获取供应商关联的通道
    channels_result = await db.execute(
        select(SupplierChannel.channel_id).where(SupplierChannel.supplier_id == supplier_id)
    )
    channel_ids = [c for c in channels_result.scalars().all()]
    
    if not channel_ids:
        return {
            "success": True,
            "statistics": {
                "total_sms": 0,
                "success_count": 0,
                "failed_count": 0,
                "total_cost": 0,
                "success_rate": 0
            }
        }
    
    # 构建查询
    query = select(
        func.count(SMSLog.id).label('total'),
        func.sum(case((SMSLog.status == 'delivered', 1), else_=0)).label('success'),
        func.sum(case((SMSLog.status == 'failed', 1), else_=0)).label('failed'),
        func.sum(SMSLog.cost_price).label('cost')
    ).where(SMSLog.channel_id.in_(channel_ids))
    
    if start_date:
        query = query.where(SMSLog.submit_time >= start_date)
    if end_date:
        query = query.where(SMSLog.submit_time <= end_date)
    
    result = await db.execute(query)
    stats = result.one()
    
    total = stats.total or 0
    success = stats.success or 0
    
    return {
        "success": True,
        "statistics": {
            "total_sms": total,
            "success_count": success,
            "failed_count": stats.failed or 0,
            "total_cost": float(stats.cost) if stats.cost else 0,
            "success_rate": round(success / total * 100, 2) if total > 0 else 0
        }
    }


