"""通道关系管理API - 管理通道与国家、SID的关系绑定"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from app.database import get_db
from app.modules.sms.channel_relations import ChannelCountry, ChannelCountrySenderId
from app.modules.sms.channel import Channel
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.api.v1.admin import get_current_admin
from app.core.audit_dep import audited

router = APIRouter(prefix="/admin/channel-relations", tags=["通道关系管理"])


# ============ Pydantic 模型 ============

class ChannelCountryCreate(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    country_code: str = Field(..., max_length=10, description="国家代码")
    country_name: Optional[str] = Field(None, max_length=100, description="国家名称")
    status: str = Field(default="active", description="状态")
    priority: int = Field(default=0, description="优先级")


class ChannelCountryUpdate(BaseModel):
    country_name: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None


class ChannelCountrySenderIdCreate(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    country_code: str = Field(..., max_length=10, description="国家代码")
    sender_id: str = Field(..., max_length=50, description="发送方ID")
    sid_type: str = Field(default="alpha", description="SID类型")
    status: str = Field(default="active", description="状态")
    is_default: bool = Field(default=False, description="是否默认SID")


class ChannelCountrySenderIdUpdate(BaseModel):
    sender_id: Optional[str] = None
    sid_type: Optional[str] = None
    status: Optional[str] = None
    is_default: Optional[bool] = None
    reject_reason: Optional[str] = None


# ============ 通道-国家关系管理 ============

@router.get("/channels/{channel_id}/countries")
async def list_channel_countries(
    channel_id: int,
    status: Optional[str] = Query(None, description="状态筛选"),
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取通道支持的国家列表"""
    query = select(ChannelCountry).where(ChannelCountry.channel_id == channel_id)
    
    if status:
        query = query.where(ChannelCountry.status == status)
    
    query = query.order_by(ChannelCountry.priority.desc(), ChannelCountry.country_code)
    result = await db.execute(query)
    countries = result.scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": c.id,
            "channel_id": c.channel_id,
            "country_code": c.country_code,
            "country_name": c.country_name,
            "status": c.status,
            "priority": c.priority,
            "created_at": c.created_at.isoformat() if c.created_at else None
        } for c in countries],
        "total": len(countries)
    }


@router.post("/channels/{channel_id}/countries")
async def add_channel_country(
    channel_id: int,
    data: ChannelCountryCreate,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("channel", "add_country")),
):
    """为通道添加支持的国家"""
    admin, audit = auth
    # 验证通道存在
    channel_result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = channel_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    # 检查是否已存在
    existing = await db.execute(
        select(ChannelCountry).where(
            ChannelCountry.channel_id == channel_id,
            ChannelCountry.country_code == data.country_code
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该国家已关联到此通道")

    country = ChannelCountry(
        channel_id=channel_id,
        country_code=data.country_code,
        country_name=data.country_name,
        status=data.status,
        priority=data.priority
    )
    db.add(country)
    await db.commit()
    await db.refresh(country)

    await audit(target_id=channel_id, target_type="channel_country",
                title=f"通道{channel.channel_code}添加国家 {data.country_code}",
                detail={"country_code": data.country_code, "priority": data.priority,
                        "status": data.status})
    await db.commit()
    return {"success": True, "message": "添加成功", "id": country.id}


@router.put("/channels/{channel_id}/countries/{country_id}")
async def update_channel_country(
    channel_id: int,
    country_id: int,
    data: ChannelCountryUpdate,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("channel", "update_country")),
):
    """更新通道-国家关系"""
    admin, audit = auth
    result = await db.execute(
        select(ChannelCountry).where(
            ChannelCountry.id == country_id,
            ChannelCountry.channel_id == channel_id
        )
    )
    country = result.scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail="关系不存在")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(country, key, value)

    await db.commit()
    await audit(target_id=country_id, target_type="channel_country",
                title=f"更新通道国家关系 channel={channel_id} country={country.country_code}",
                detail={"changed_fields": list(update_data.keys())})
    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.delete("/channels/{channel_id}/countries/{country_id}")
async def remove_channel_country(
    channel_id: int,
    country_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("channel", "delete_country")),
):
    """移除通道-国家关系"""
    admin, audit = auth
    result = await db.execute(
        select(ChannelCountry).where(
            ChannelCountry.id == country_id,
            ChannelCountry.channel_id == channel_id
        )
    )
    country = result.scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail="关系不存在")

    snap = {"channel_id": channel_id, "country_code": country.country_code,
            "priority": country.priority}
    await db.delete(country)
    await db.commit()
    await audit(target_id=country_id, target_type="channel_country",
                title=f"删除通道国家关系 channel={channel_id} country={snap['country_code']}",
                detail=snap)
    await db.commit()
    return {"success": True, "message": "删除成功"}


# ============ 通道-国家-SID关系管理 ============

@router.get("/channels/{channel_id}/countries/{country_code}/sids")
async def list_channel_country_sids(
    channel_id: int,
    country_code: str,
    status: Optional[str] = Query(None, description="状态筛选"),
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取通道在指定国家的可用SID列表"""
    query = select(ChannelCountrySenderId).where(
        ChannelCountrySenderId.channel_id == channel_id,
        ChannelCountrySenderId.country_code == country_code
    )
    
    if status:
        query = query.where(ChannelCountrySenderId.status == status)
    
    query = query.order_by(
        ChannelCountrySenderId.is_default.desc(),
        ChannelCountrySenderId.sender_id
    )
    result = await db.execute(query)
    sids = result.scalars().all()
    
    return {
        "success": True,
        "items": [{
            "id": s.id,
            "channel_id": s.channel_id,
            "country_code": s.country_code,
            "sender_id": s.sender_id,
            "sid_type": s.sid_type,
            "status": s.status,
            "is_default": s.is_default,
            "approved_at": s.approved_at.isoformat() if s.approved_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None
        } for s in sids],
        "total": len(sids)
    }


@router.post("/channels/{channel_id}/countries/{country_code}/sids")
async def add_channel_country_sid(
    channel_id: int,
    country_code: str,
    data: ChannelCountrySenderIdCreate,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """为通道在指定国家添加SID"""
    # 验证通道-国家关系存在
    country_result = await db.execute(
        select(ChannelCountry).where(
            ChannelCountry.channel_id == channel_id,
            ChannelCountry.country_code == country_code,
            ChannelCountry.status == 'active'
        )
    )
    if not country_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="通道未支持该国家，请先添加国家支持")
    
    # 检查SID是否已存在
    existing = await db.execute(
        select(ChannelCountrySenderId).where(
            ChannelCountrySenderId.channel_id == channel_id,
            ChannelCountrySenderId.country_code == country_code,
            ChannelCountrySenderId.sender_id == data.sender_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该SID已存在")
    
    # 如果设置为默认，取消其他默认SID
    if data.is_default:
        from sqlalchemy import update
        await db.execute(
            update(ChannelCountrySenderId)
            .where(
                ChannelCountrySenderId.channel_id == channel_id,
                ChannelCountrySenderId.country_code == country_code,
                ChannelCountrySenderId.is_default == True
            )
            .values(is_default=False)
        )
    
    sid = ChannelCountrySenderId(
        channel_id=channel_id,
        country_code=country_code,
        sender_id=data.sender_id,
        sid_type=data.sid_type,
        status=data.status,
        is_default=data.is_default,
        approved_at=datetime.now() if data.status == 'active' else None,
        approved_by=admin.id if data.status == 'active' else None
    )
    db.add(sid)
    await db.commit()
    await db.refresh(sid)
    
    return {
        "success": True,
        "message": "添加成功",
        "id": sid.id
    }


@router.put("/channels/{channel_id}/countries/{country_code}/sids/{sid_id}")
async def update_channel_country_sid(
    channel_id: int,
    country_code: str,
    sid_id: int,
    data: ChannelCountrySenderIdUpdate,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """更新通道-国家-SID关系"""
    result = await db.execute(
        select(ChannelCountrySenderId).where(
            ChannelCountrySenderId.id == sid_id,
            ChannelCountrySenderId.channel_id == channel_id,
            ChannelCountrySenderId.country_code == country_code
        )
    )
    sid = result.scalar_one_or_none()
    if not sid:
        raise HTTPException(status_code=404, detail="SID不存在")
    
    update_data = data.dict(exclude_unset=True)
    
    # 如果设置为默认，取消其他默认SID
    if update_data.get('is_default') is True:
        from sqlalchemy import update
        await db.execute(
            update(ChannelCountrySenderId)
            .where(
                ChannelCountrySenderId.channel_id == channel_id,
                ChannelCountrySenderId.country_code == country_code,
                ChannelCountrySenderId.id != sid_id,
                ChannelCountrySenderId.is_default == True
            )
            .values(is_default=False)
        )
        await db.commit()
    
    # 如果状态变为active，记录审核信息
    if update_data.get('status') == 'active' and sid.status != 'active':
        update_data['approved_at'] = datetime.now()
        update_data['approved_by'] = admin.id
    
    for key, value in update_data.items():
        setattr(sid, key, value)
    
    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.delete("/channels/{channel_id}/countries/{country_code}/sids/{sid_id}")
async def remove_channel_country_sid(
    channel_id: int,
    country_code: str,
    sid_id: int,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """删除通道-国家-SID关系"""
    result = await db.execute(
        select(ChannelCountrySenderId).where(
            ChannelCountrySenderId.id == sid_id,
            ChannelCountrySenderId.channel_id == channel_id,
            ChannelCountrySenderId.country_code == country_code
        )
    )
    sid = result.scalar_one_or_none()
    if not sid:
        raise HTTPException(status_code=404, detail="SID不存在")
    
    await db.delete(sid)
    await db.commit()
    return {"success": True, "message": "删除成功"}


# ============ 客户-销售关系管理 ============

@router.get("/accounts/{account_id}/sales")
async def get_account_sales(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    admin = Depends(get_current_admin)
):
    """获取账户的销售信息"""
    result = await db.execute(
        select(Account).options(selectinload(Account.sales)).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    return {
        "success": True,
        "account_id": account.id,
        "account_name": account.account_name,
        "sales": {
            "id": account.sales.id if account.sales else None,
            "username": account.sales.username if account.sales else None,
            "real_name": account.sales.real_name if account.sales else None,
            "email": account.sales.email if account.sales else None
        } if account.sales else None
    }


@router.put("/accounts/{account_id}/sales/{sales_id}")
async def bind_account_sales(
    account_id: int,
    sales_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("account", "bind_sales")),
):
    """绑定账户与销售"""
    admin, audit = auth
    # 验证账户存在
    account_result = await db.execute(
        select(Account).where(Account.id == account_id)
    )
    account = account_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    sales_result = await db.execute(
        select(AdminUser).where(
            AdminUser.id == sales_id,
            AdminUser.role == 'sales',
            AdminUser.status == 'active'
        )
    )
    sales = sales_result.scalar_one_or_none()
    if not sales:
        raise HTTPException(status_code=404, detail="销售不存在或状态异常")

    old_sales_id = account.sales_id
    account.sales_id = sales_id
    await db.commit()
    await audit(target_id=account_id, target_type="account",
                title=f"绑定销售 account={account.account_name} → {sales.username}",
                detail={"old_sales_id": old_sales_id, "new_sales_id": sales_id,
                        "sales_username": sales.username})
    await db.commit()
    return {
        "success": True,
        "message": "绑定成功",
        "sales": {
            "id": sales.id,
            "username": sales.username,
            "real_name": sales.real_name
        }
    }


@router.delete("/accounts/{account_id}/sales")
async def unbind_account_sales(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    auth = Depends(audited("account", "unbind_sales")),
):
    """解绑账户与销售"""
    admin, audit = auth
    result = await db.execute(
        select(Account).where(Account.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    old_sales_id = account.sales_id
    account.sales_id = None
    await db.commit()
    await audit(target_id=account_id, target_type="account",
                title=f"解绑销售 account={account.account_name}",
                detail={"old_sales_id": old_sales_id})
    await db.commit()
    return {"success": True, "message": "解绑成功"}
