"""语音业务API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.v1.admin import get_current_admin
from app.modules.voice.models import VoiceRoute, VoiceCall
from app.modules.voice.voice_account import VoiceAccount, VoiceRechargeLog
from app.modules.common.admin_user import AdminUser
from app.modules.common.account import Account
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/admin/voice", tags=["Voice"])


class VoiceRouteCreate(BaseModel):
    country_code: str = Field(..., max_length=10)
    provider_id: Optional[int] = None
    priority: int = 0
    cost_per_minute: float = 0.0


class VoiceRouteUpdate(BaseModel):
    country_code: Optional[str] = None
    provider_id: Optional[int] = None
    priority: Optional[int] = None
    cost_per_minute: Optional[float] = None


@router.get("/routes")
async def list_voice_routes(
    country_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    query = select(VoiceRoute)
    if country_code:
        query = query.where(VoiceRoute.country_code == country_code)
    result = await db.execute(query.order_by(VoiceRoute.priority.desc(), VoiceRoute.id.desc()))
    routes = result.scalars().all()
    return {
        "success": True,
        "items": [
            {
                "id": r.id,
                "country_code": r.country_code,
                "provider_id": r.provider_id,
                "priority": r.priority,
                "cost_per_minute": r.cost_per_minute,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in routes
        ],
        "total": len(routes),
    }


@router.post("/routes")
async def create_voice_route(
    data: VoiceRouteCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    route = VoiceRoute(
        country_code=data.country_code,
        provider_id=data.provider_id,
        priority=data.priority,
        cost_per_minute=data.cost_per_minute,
    )
    db.add(route)
    await db.commit()
    await db.refresh(route)
    return {"success": True, "id": route.id}


@router.put("/routes/{route_id}")
async def update_voice_route(
    route_id: int,
    data: VoiceRouteUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    result = await db.execute(select(VoiceRoute).where(VoiceRoute.id == route_id))
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(route, key, value)

    await db.commit()
    return {"success": True}


@router.delete("/routes/{route_id}")
async def delete_voice_route(
    route_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    result = await db.execute(select(VoiceRoute).where(VoiceRoute.id == route_id))
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    await db.delete(route)
    await db.commit()
    return {"success": True}


@router.get("/calls")
async def list_voice_calls(
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    query = select(VoiceCall)
    if account_id:
        query = query.where(VoiceCall.account_id == account_id)
    if status:
        query = query.where(VoiceCall.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(VoiceCall.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    calls = result.scalars().all()

    return {
        "success": True,
        "items": [
            {
                "id": c.id,
                "call_id": c.call_id,
                "account_id": c.account_id,
                "caller": c.caller,
                "callee": c.callee,
                "start_time": c.start_time.isoformat() if c.start_time else None,
                "end_time": c.end_time.isoformat() if c.end_time else None,
                "duration": c.duration,
                "status": c.status,
                "cost": c.cost,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in calls
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ========== 语音账户管理 ==========
@router.get("/accounts")
async def list_voice_accounts(
    country_code: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """获取语音账户列表"""
    query = select(VoiceAccount).options(selectinload(VoiceAccount.account))
    
    if country_code:
        query = query.where(VoiceAccount.country_code == country_code)
    if status:
        query = query.where(VoiceAccount.status == status)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    result = await db.execute(
        query.order_by(VoiceAccount.created_at.desc())
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
                "okcc_account": a.okcc_account,
                "country_code": a.country_code,
                "balance": float(a.balance) if a.balance else 0,
                "total_calls": a.total_calls or 0,
                "total_minutes": a.total_minutes or 0,
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


class VoiceAccountUpdate(BaseModel):
    status: Optional[str] = None


@router.put("/accounts/{account_id}")
async def update_voice_account(
    account_id: int,
    data: VoiceAccountUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """更新语音账户"""
    result = await db.execute(select(VoiceAccount).where(VoiceAccount.id == account_id))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    if data.status:
        account.status = data.status
    
    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.post("/accounts/{account_id}/sync")
async def sync_voice_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """同步语音账户状态"""
    from datetime import datetime
    from app.services.okcc_client import get_okcc_client
    
    result = await db.execute(select(VoiceAccount).where(VoiceAccount.id == account_id))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    try:
        client = get_okcc_client()
        sync_result = await client.sync_status(account.external_id)
        
        if sync_result.get('success'):
            data = sync_result.get('data', {})
            account.balance = data.get('balance', account.balance)
            account.total_calls = data.get('total_calls', account.total_calls)
            account.total_minutes = data.get('total_minutes', account.total_minutes)
            account.status = data.get('status', account.status)
            account.last_sync_at = datetime.now()
            account.sync_error = None
            await db.commit()
            return {"success": True, "message": "同步成功"}
        else:
            account.sync_error = sync_result.get('message')
            account.last_sync_at = datetime.now()
            await db.commit()
            return {"success": False, "message": sync_result.get('message')}
            
    except Exception as e:
        account.sync_error = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))
