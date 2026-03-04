"""供应商管理API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
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

router = APIRouter(prefix="/admin/suppliers", tags=["供应商管理"])


# ============ Pydantic 模型 ============

class SupplierCreate(BaseModel):
    supplier_code: str = Field(..., max_length=50, description="供应商编码")
    supplier_name: str = Field(..., max_length=100, description="供应商名称")
    supplier_group: Optional[str] = Field(None, max_length=100, description="供应商群组")
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
    page_size: int = Query(20, ge=1, le=100),
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


@router.post("")
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """创建供应商"""
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
    admin: AdminUser = Depends(get_current_admin)
):
    """更新供应商"""
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
    
    return {"success": True, "message": "供应商更新成功"}


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """删除供应商(软删除)"""
    result = await db.execute(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted == False)
    )
    supplier = result.scalar_one_or_none()
    
    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    supplier.is_deleted = True
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
    admin: AdminUser = Depends(get_current_admin)
):
    """创建供应商费率"""
    # 验证供应商存在
    supplier = await db.get(Supplier, supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    rate = SupplierRate(supplier_id=supplier_id, **data.dict())
    db.add(rate)
    await db.commit()
    
    return {"success": True, "message": "费率创建成功", "rate_id": rate.id}


@router.post("/{supplier_id}/rates/batch")
async def batch_import_supplier_rates(
    supplier_id: int,
    data: SupplierRateBatchImport,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """批量导入供应商费率"""
    supplier = await db.get(Supplier, supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="供应商不存在")
    
    created_count = 0
    for rate_data in data.rates:
        rate = SupplierRate(supplier_id=supplier_id, **rate_data.dict())
        db.add(rate)
        created_count += 1
    
    await db.commit()
    
    return {"success": True, "message": f"成功导入 {created_count} 条费率"}


class SupplierRateUpdate(BaseModel):
    business_type: Optional[str] = None
    country_code: Optional[str] = None
    resource_type: Optional[str] = None
    business_scope: Optional[str] = None
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
    admin: AdminUser = Depends(get_current_admin)
):
    """更新供应商报价"""
    result = await db.execute(
        select(SupplierRate).where(
            SupplierRate.id == rate_id,
            SupplierRate.supplier_id == supplier_id
        )
    )
    rate = result.scalar_one_or_none()
    
    if not rate:
        raise HTTPException(status_code=404, detail="报价不存在")
    
    if data.business_type is not None:
        rate.business_type = data.business_type
    if data.country_code is not None:
        rate.country_code = data.country_code
    if data.resource_type is not None:
        rate.resource_type = data.resource_type
    if data.business_scope is not None:
        rate.business_scope = data.business_scope
    if data.cost_price is not None:
        rate.cost_price = data.cost_price
    if data.sell_price is not None:
        rate.sell_price = data.sell_price
    if data.remark is not None:
        rate.remark = data.remark
    if data.status is not None:
        rate.status = data.status
    
    await db.commit()
    
    return {"success": True, "message": "报价更新成功"}


@router.delete("/{supplier_id}/rates/{rate_id}")
async def delete_supplier_rate(
    supplier_id: int,
    rate_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """删除供应商报价"""
    result = await db.execute(
        select(SupplierRate).where(
            SupplierRate.id == rate_id,
            SupplierRate.supplier_id == supplier_id
        )
    )
    rate = result.scalar_one_or_none()
    
    if not rate:
        raise HTTPException(status_code=404, detail="报价不存在")
    
    await db.delete(rate)
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
    admin: AdminUser = Depends(get_current_admin)
):
    """关联供应商与通道"""
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
    
    return {"success": True, "message": "通道关联成功"}


@router.delete("/{supplier_id}/channels/{channel_id}")
async def unlink_supplier_channel(
    supplier_id: int,
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """解绑供应商与通道"""
    # 查找关联记录
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
        func.sum(func.case((SMSLog.status == 'delivered', 1), else_=0)).label('success'),
        func.sum(func.case((SMSLog.status == 'failed', 1), else_=0)).label('failed'),
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


