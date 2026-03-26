"""语音业务API"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from sqlalchemy import select, func
from typing import Optional, Set
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.v1.admin import get_current_admin
from app.services.operation_log import log_operation
from app.modules.voice.models import VoiceRoute, VoiceCall
from app.modules.voice.campaign_models import (
    VoiceCallerId,
    VoiceCdrWebhookLog,
    VoiceOutboundCampaign,
    VoiceOutboundContact,
)
from app.modules.voice.voice_account import VoiceAccount, VoiceRechargeLog
from app.modules.common.admin_user import AdminUser
from app.utils.voice_call_query import (
    apply_voice_call_date_filter,
    voice_call_order_column,
)
from app.utils.voice_campaign_names import batch_outbound_campaign_names_by_ids
from app.modules.common.account import Account
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/admin/voice", tags=["Voice"])


def _escape_like_literal(s: str) -> str:
    """将用户输入中的 LIKE 通配符按字面量匹配（反斜杠、%、_）。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class VoiceRouteCreate(BaseModel):
    country_code: str = Field(..., max_length=10)
    provider_id: Optional[int] = None
    priority: int = 0
    cost_per_minute: float = 0.0
    trunk_profile: Optional[str] = Field(None, max_length=128)
    dial_prefix: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = None


class VoiceRouteUpdate(BaseModel):
    country_code: Optional[str] = None
    provider_id: Optional[int] = None
    priority: Optional[int] = None
    cost_per_minute: Optional[float] = None
    trunk_profile: Optional[str] = Field(None, max_length=128)
    dial_prefix: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = None


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
                "trunk_profile": getattr(r, "trunk_profile", None),
                "dial_prefix": getattr(r, "dial_prefix", None),
                "notes": getattr(r, "notes", None),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in routes
        ],
        "total": len(routes),
    }


@router.post("/routes")
async def create_voice_route(
    data: VoiceRouteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    route = VoiceRoute(
        country_code=data.country_code,
        provider_id=data.provider_id,
        priority=data.priority,
        cost_per_minute=data.cost_per_minute,
        trunk_profile=data.trunk_profile,
        dial_prefix=data.dial_prefix,
        notes=data.notes,
    )
    db.add(route)
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="create",
        title="新增语音路由",
        target_type="VoiceRoute",
        target_id=str(route.id),
        detail=data.dict(),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(route)
    return {"success": True, "id": route.id}


@router.put("/routes/{route_id}")
async def update_voice_route(
    route_id: int,
    data: VoiceRouteUpdate,
    request: Request,
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

    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="update",
        title="更新语音路由",
        target_type="VoiceRoute",
        target_id=str(route_id),
        detail=update_data,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"success": True}


@router.delete("/routes/{route_id}")
async def delete_voice_route(
    route_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    result = await db.execute(select(VoiceRoute).where(VoiceRoute.id == route_id))
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    await db.delete(route)
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="delete",
        title="删除语音路由",
        target_type="VoiceRoute",
        target_id=str(route_id),
        detail={},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"success": True}


@router.get("/calls")
async def list_voice_calls(
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    outbound_campaign_id: Optional[int] = None,
    start_date: Optional[str] = Query(
        None,
        description="开始日期（含当日），YYYY-MM-DD；与 date_basis 联用",
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束日期（含当日），YYYY-MM-DD",
    ),
    date_basis: str = Query(
        "created_at",
        description="日期字段：created_at 入库时间；start_time 通话开始时间",
    ),
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
    if outbound_campaign_id is not None:
        query = query.where(VoiceCall.outbound_campaign_id == outbound_campaign_id)
    query = apply_voice_call_date_filter(
        query, VoiceCall, start_date, end_date, date_basis
    )
    order_col = voice_call_order_column(VoiceCall, date_basis)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(order_col.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    calls = result.scalars().all()
    camp_ids: Set[int] = {
        int(x)
        for x in (getattr(c, "outbound_campaign_id", None) for c in calls)
        if x is not None
    }
    camp_names = await batch_outbound_campaign_names_by_ids(db, camp_ids)

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
                "billsec": c.billsec,
                "direction": c.direction,
                "outbound_campaign_id": c.outbound_campaign_id,
                "outbound_campaign_name": (
                    camp_names.get(int(c.outbound_campaign_id))
                    if c.outbound_campaign_id is not None
                    else None
                ),
                "recording_url": c.recording_url,
                "voice_route_id": getattr(c, "voice_route_id", None),
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
    account_id: Optional[int] = Query(None, description="业务账户 accounts.id"),
    account_name: Optional[str] = Query(None, description="客户账户名模糊匹配"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """获取语音账户列表（支持按业务账户 ID、客户名筛选）。"""
    query = select(VoiceAccount).options(selectinload(VoiceAccount.account))

    if account_name and account_name.strip():
        pat = f"%{_escape_like_literal(account_name.strip())}%"
        query = query.join(Account, VoiceAccount.account_id == Account.id).where(
            Account.account_name.like(pat, escape="\\")
        )
    if account_id is not None:
        query = query.where(VoiceAccount.account_id == account_id)
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

    dc_ids = {a.default_caller_id_id for a in accounts if a.default_caller_id_id}
    dc_numbers: dict[int, str] = {}
    if dc_ids:
        rdc = await db.execute(
            select(VoiceCallerId.id, VoiceCallerId.number_e164).where(
                VoiceCallerId.id.in_(dc_ids)
            )
        )
        dc_numbers = {rid: num for rid, num in rdc.all()}

    def _sync_err(txt: Optional[str]) -> Optional[str]:
        if not txt:
            return None
        t = txt.strip()
        if len(t) <= 500:
            return t
        return t[:500] + "…"

    return {
        "success": True,
        "items": [
            {
                "id": a.id,
                "account_id": a.account_id,
                "account": {
                    "account_name": a.account.account_name
                }
                if a.account
                else None,
                "okcc_account": a.okcc_account,
                "sip_username": a.sip_username,
                "sip_login_hint": a.sip_username or a.okcc_account,
                "external_id": a.external_id,
                "default_caller_id_id": a.default_caller_id_id,
                "default_caller_number": dc_numbers.get(a.default_caller_id_id)
                if a.default_caller_id_id
                else None,
                "country_code": a.country_code,
                "balance": float(a.balance) if a.balance else 0,
                "total_calls": a.total_calls or 0,
                "total_minutes": a.total_minutes or 0,
                "max_concurrent_calls": getattr(a, "max_concurrent_calls", None) or 0,
                "daily_outbound_limit": getattr(a, "daily_outbound_limit", None) or 0,
                "status": a.status,
                "sync_error": _sync_err(getattr(a, "sync_error", None)),
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
    max_concurrent_calls: Optional[int] = Field(None, ge=0)
    daily_outbound_limit: Optional[int] = Field(None, ge=0)
    sip_username: Optional[str] = Field(
        None,
        max_length=100,
        description="SIP 注册用户名；空字符串表示清空，回退为 okcc_account",
    )


@router.put("/accounts/{account_id}")
async def update_voice_account(
    account_id: int,
    data: VoiceAccountUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """更新语音账户"""
    result = await db.execute(select(VoiceAccount).where(VoiceAccount.id == account_id))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    upd = data.dict(exclude_unset=True)
    before = {}
    if "status" in upd and upd["status"]:
        before["status"] = account.status
        account.status = upd["status"]
    if "max_concurrent_calls" in upd:
        before["max_concurrent_calls"] = getattr(account, "max_concurrent_calls", None)
        account.max_concurrent_calls = upd["max_concurrent_calls"]
    if "daily_outbound_limit" in upd:
        before["daily_outbound_limit"] = getattr(account, "daily_outbound_limit", None)
        account.daily_outbound_limit = upd["daily_outbound_limit"]
    if "sip_username" in upd:
        before["sip_username"] = account.sip_username
        raw = upd["sip_username"]
        if raw is None:
            account.sip_username = None
        else:
            stripped = raw.strip()
            account.sip_username = stripped if stripped else None

    await db.flush()
    if before:
        await log_operation(
            db,
            admin_id=admin.id,
            admin_name=admin.username,
            module="voice",
            action="update",
            title="更新语音账户配置",
            target_type="VoiceAccount",
            target_id=str(account_id),
            detail={"before": before, "after": upd},
            ip_address=request.client.host if request.client else None,
        )
    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.post("/accounts/{account_id}/reset-sip-password")
async def reset_voice_account_sip_password(
    account_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """重置 SIP 登录密码：写入数据库并一次性返回明文；需在网关侧同步（如 Kamailio/FS 用户库）。"""
    result = await db.execute(select(VoiceAccount).where(VoiceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    new_pwd = secrets.token_urlsafe(16)
    account.okcc_password = new_pwd
    await db.flush()
    sip_user = (account.sip_username or account.okcc_account) or ""
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="update",
        title="重置语音账户 SIP 密码",
        target_type="VoiceAccount",
        target_id=str(account_id),
        detail={"sip_username": sip_user, "password_rotated": True},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {
        "success": True,
        "sip_username": sip_user,
        "sip_password": new_pwd,
        "message": "新密码仅本次返回，请同步至网关并妥善保管",
    }


@router.get("/ops-metrics")
async def voice_ops_metrics(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """运营可观测：近 24h CDR Webhook 处理量、外呼任务状态分布（供告警规则对接）。"""
    since = datetime.utcnow() - timedelta(hours=24)
    cdr_ok = (
        await db.execute(
            select(func.count()).select_from(VoiceCdrWebhookLog).where(
                VoiceCdrWebhookLog.status == "processed",
                VoiceCdrWebhookLog.processed_at.isnot(None),
                VoiceCdrWebhookLog.processed_at >= since,
            )
        )
    ).scalar() or 0
    cdr_fail = (
        await db.execute(
            select(func.count()).select_from(VoiceCdrWebhookLog).where(
                VoiceCdrWebhookLog.status == "failed",
                VoiceCdrWebhookLog.created_at >= since,
            )
        )
    ).scalar() or 0
    camp_running = (
        await db.execute(
            select(func.count()).select_from(VoiceOutboundCampaign).where(
                VoiceOutboundCampaign.status == "running"
            )
        )
    ).scalar() or 0
    # 近 24h 话单入库量与「已接通」占比（供告警与大盘；接通判定为 answered/completed）
    calls_total_24h = (
        await db.execute(
            select(func.count()).select_from(VoiceCall).where(VoiceCall.created_at >= since)
        )
    ).scalar() or 0
    calls_connected_24h = (
        await db.execute(
            select(func.count()).select_from(VoiceCall).where(
                VoiceCall.created_at >= since,
                VoiceCall.status.in_(["answered", "completed"]),
            )
        )
    ).scalar() or 0
    outbound_contacts_pending = (
        await db.execute(
            select(func.count()).select_from(VoiceOutboundContact).where(
                VoiceOutboundContact.status == "pending"
            )
        )
    ).scalar() or 0
    answer_rate_24h = (
        round(calls_connected_24h / calls_total_24h, 4) if calls_total_24h else None
    )
    return {
        "success": True,
        "window_hours": 24,
        "cdr_webhook_processed": cdr_ok,
        "cdr_webhook_failed": cdr_fail,
        "campaigns_running": camp_running,
        "voice_calls_total_24h": calls_total_24h,
        "voice_calls_connected_24h": calls_connected_24h,
        "voice_answer_rate_24h": answer_rate_24h,
        "outbound_contacts_pending": outbound_contacts_pending,
    }


@router.post("/accounts/{account_id}/sync")
async def sync_voice_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """同步语音账户状态"""
    from datetime import datetime
    from app.services.voice_provider import get_voice_provider

    result = await db.execute(select(VoiceAccount).where(VoiceAccount.id == account_id))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    
    try:
        client = get_voice_provider()
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
