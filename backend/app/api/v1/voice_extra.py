"""语音扩展：主叫号码池、外呼任务、挂机短信规则、DNC、导出"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import get_current_admin
from app.database import get_db
from app.modules.common.admin_user import AdminUser
from app.modules.voice.campaign_models import (
    VoiceCallerId,
    VoiceDncNumber,
    VoiceHangupSmsRule,
    VoiceOutboundCampaign,
    VoiceOutboundContact,
)
from app.modules.voice.models import VoiceCall, VoiceRoute
from app.modules.voice.voice_account import VoiceAccount
from app.services.operation_log import log_operation
from app.utils.voice_call_query import apply_voice_call_date_filter, voice_call_order_column
from app.utils.voice_campaign_names import batch_outbound_campaign_names_by_ids
from app.workers.voice_worker import voice_campaign_tick_task

router = APIRouter(prefix="/admin/voice", tags=["Voice"])


# ---------- 主叫号码 ----------
class CallerIdCreate(BaseModel):
    account_id: int
    number_e164: str = Field(..., max_length=32)
    label: Optional[str] = None
    trunk_ref: Optional[str] = None
    voice_route_id: Optional[int] = None


class CallerIdUpdate(BaseModel):
    label: Optional[str] = None
    trunk_ref: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, pattern="^(active|disabled)$")
    voice_route_id: Optional[int] = None


async def _ensure_voice_route_exists(db: AsyncSession, route_id: Optional[int]) -> None:
    if route_id is None:
        return
    r = await db.execute(select(VoiceRoute).where(VoiceRoute.id == route_id))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="voice_route_id 不存在")


@router.get("/caller-ids")
async def list_caller_ids(
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    q = select(VoiceCallerId)
    if account_id:
        q = q.where(VoiceCallerId.account_id == account_id)
    r = await db.execute(q.order_by(VoiceCallerId.id.desc()))
    rows = r.scalars().all()
    return {
        "success": True,
        "items": [
            {
                "id": x.id,
                "account_id": x.account_id,
                "number_e164": x.number_e164,
                "label": x.label,
                "trunk_ref": x.trunk_ref,
                "voice_route_id": getattr(x, "voice_route_id", None),
                "status": x.status,
            }
            for x in rows
        ],
    }


@router.post("/caller-ids")
async def create_caller_id(
    data: CallerIdCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    await _ensure_voice_route_exists(db, data.voice_route_id)
    row = VoiceCallerId(
        account_id=data.account_id,
        number_e164=data.number_e164,
        label=data.label,
        trunk_ref=data.trunk_ref,
        voice_route_id=data.voice_route_id,
        status="active",
    )
    db.add(row)
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="create",
        title="新增主叫号码",
        target_type="VoiceCallerId",
        target_id=str(row.id),
        detail={
            "number_e164": data.number_e164,
            "account_id": data.account_id,
            "voice_route_id": data.voice_route_id,
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return {"success": True, "id": row.id}


@router.put("/caller-ids/{caller_id}")
async def update_caller_id(
    caller_id: int,
    data: CallerIdUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """更新主叫号码（标签、Trunk、状态、绑定路由）。"""
    r = await db.execute(select(VoiceCallerId).where(VoiceCallerId.id == caller_id))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="主叫号码不存在")
    upd = data.dict(exclude_unset=True)
    if "voice_route_id" in upd:
        await _ensure_voice_route_exists(db, upd.get("voice_route_id"))
    before = {}
    for k in ("label", "trunk_ref", "status", "voice_route_id"):
        if k in upd:
            before[k] = getattr(row, k, None)
            setattr(row, k, upd[k])
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="update",
        title="更新主叫号码",
        target_type="VoiceCallerId",
        target_id=str(caller_id),
        detail={"before": before, "after": upd},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"success": True}


@router.delete("/caller-ids/{caller_id}")
async def delete_caller_id(
    caller_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """删除主叫号码（若仍为默认主叫或外呼任务引用则拒绝）。"""
    r = await db.execute(select(VoiceCallerId).where(VoiceCallerId.id == caller_id))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="主叫号码不存在")
    r1 = await db.execute(
        select(VoiceAccount).where(VoiceAccount.default_caller_id_id == caller_id)
    )
    if r1.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="该号码仍为某语音账户默认主叫，请先更换默认主叫",
        )
    r2 = await db.execute(
        select(VoiceOutboundCampaign).where(
            VoiceOutboundCampaign.fixed_caller_id_id == caller_id
        )
    )
    if r2.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="外呼任务仍固定使用该主叫，请先修改任务配置",
        )
    await db.delete(row)
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="delete",
        title="删除主叫号码",
        target_type="VoiceCallerId",
        target_id=str(caller_id),
        detail={"number_e164": row.number_e164},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"success": True}


# ---------- 外呼任务 ----------
class CampaignCreate(BaseModel):
    account_id: int
    name: str
    timezone: str = "Asia/Shanghai"
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    max_concurrent: int = 1
    caller_id_mode: str = "fixed"
    fixed_caller_id_id: Optional[int] = None
    ai_mode: Optional[str] = "ivr"  # ivr | ai


@router.get("/campaigns")
async def list_campaigns(
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    q = select(VoiceOutboundCampaign)
    if account_id:
        q = q.where(VoiceOutboundCampaign.account_id == account_id)
    r = await db.execute(q.order_by(VoiceOutboundCampaign.id.desc()))
    rows = r.scalars().all()
    return {
        "success": True,
        "items": [
            {
                "id": x.id,
                "account_id": x.account_id,
                "name": x.name,
                "status": x.status,
                "timezone": x.timezone,
                "window_start": x.window_start,
                "window_end": x.window_end,
                "max_concurrent": x.max_concurrent,
                "caller_id_mode": getattr(x, "caller_id_mode", None),
                "fixed_caller_id_id": x.fixed_caller_id_id,
                "ai_mode": getattr(x, "ai_mode", None) or "ivr",
            }
            for x in rows
        ],
    }


@router.post("/campaigns")
async def create_campaign(
    data: CampaignCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    row = VoiceOutboundCampaign(
        account_id=data.account_id,
        name=data.name,
        timezone=data.timezone,
        window_start=data.window_start,
        window_end=data.window_end,
        max_concurrent=data.max_concurrent,
        caller_id_mode=data.caller_id_mode,
        fixed_caller_id_id=data.fixed_caller_id_id,
        ai_mode=(data.ai_mode or "ivr")[:16],
        status="draft",
    )
    db.add(row)
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="create",
        title="新建外呼任务",
        target_type="VoiceOutboundCampaign",
        target_id=str(row.id),
        detail={"name": data.name, "ai_mode": data.ai_mode},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return {"success": True, "id": row.id}


class DefaultCallerBody(BaseModel):
    caller_id: int = Field(..., description="voice_caller_ids.id")


@router.put("/voice-accounts/{va_id}/default-caller")
async def set_default_caller(
    va_id: int,
    body: DefaultCallerBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """设置语音子账户默认外显主叫（须属于同一业务账户）。"""
    r = await db.execute(select(VoiceAccount).where(VoiceAccount.id == va_id))
    va = r.scalar_one_or_none()
    if not va:
        raise HTTPException(status_code=404, detail="语音账户不存在")
    r2 = await db.execute(select(VoiceCallerId).where(VoiceCallerId.id == body.caller_id))
    cid = r2.scalar_one_or_none()
    if not cid or cid.account_id != va.account_id:
        raise HTTPException(status_code=400, detail="主叫号码不属于该客户")
    va.default_caller_id_id = body.caller_id
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="update",
        title="设置默认主叫号码",
        target_type="VoiceAccount",
        target_id=str(va_id),
        detail={"caller_id": body.caller_id},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"success": True}


class CampaignStatusBody(BaseModel):
    status: str = Field(pattern="^(running|paused|completed|cancelled|draft)$")


@router.post("/campaigns/{campaign_id}/status")
async def campaign_status(
    campaign_id: int,
    body: CampaignStatusBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    r = await db.execute(
        select(VoiceOutboundCampaign).where(VoiceOutboundCampaign.id == campaign_id)
    )
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="任务不存在")
    c.status = body.status
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="update",
        title=f"外呼任务状态={body.status}",
        target_type="VoiceOutboundCampaign",
        target_id=str(campaign_id),
        detail={"status": body.status},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    if body.status == "running":
        voice_campaign_tick_task.delay(campaign_id)
    return {"success": True}


class ContactsImport(BaseModel):
    phones: List[str] = Field(default_factory=list)


@router.post("/campaigns/{campaign_id}/contacts")
async def import_contacts(
    campaign_id: int,
    body: ContactsImport,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    r = await db.execute(
        select(VoiceOutboundCampaign).where(VoiceOutboundCampaign.id == campaign_id)
    )
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")
    n = 0
    for p in body.phones:
        phone = (p or "").strip()
        if not phone:
            continue
        if not phone.startswith("+"):
            phone = "+" + phone.lstrip("+")
        db.add(
            VoiceOutboundContact(
                campaign_id=campaign_id,
                phone_e164=phone,
                status="pending",
            )
        )
        n += 1
    await db.commit()
    return {"success": True, "imported": n}


# ---------- 挂机短信规则 ----------
class HangupRuleCreate(BaseModel):
    account_id: Optional[int] = None
    campaign_id: Optional[int] = None
    name: str
    template_body: str
    match_answered_only: bool = True
    enabled: bool = True
    priority: int = 0


@router.get("/hangup-sms-rules")
async def list_hangup_rules(
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    q = select(VoiceHangupSmsRule)
    if account_id:
        q = q.where(VoiceHangupSmsRule.account_id == account_id)
    r = await db.execute(q.order_by(VoiceHangupSmsRule.priority.desc()))
    rows = r.scalars().all()
    return {
        "success": True,
        "items": [
            {
                "id": x.id,
                "account_id": x.account_id,
                "campaign_id": x.campaign_id,
                "name": x.name,
                "enabled": x.enabled,
                "match_answered_only": x.match_answered_only,
                "template_body": x.template_body,
                "priority": x.priority,
            }
            for x in rows
        ],
    }


@router.post("/hangup-sms-rules")
async def create_hangup_rule(
    data: HangupRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    row = VoiceHangupSmsRule(
        account_id=data.account_id,
        campaign_id=data.campaign_id,
        name=data.name,
        template_body=data.template_body,
        match_answered_only=data.match_answered_only,
        enabled=data.enabled,
        priority=data.priority,
    )
    db.add(row)
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="create",
        title="新增挂机短信规则",
        target_type="VoiceHangupSmsRule",
        target_id=str(row.id),
        detail={"name": data.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return {"success": True, "id": row.id}


# ---------- DNC ----------
class DncCreate(BaseModel):
    account_id: int
    phone_e164: str
    source: Optional[str] = None


@router.get("/dnc")
async def list_dnc(
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    q = select(VoiceDncNumber)
    if account_id:
        q = q.where(VoiceDncNumber.account_id == account_id)
    r = await db.execute(q.order_by(VoiceDncNumber.id.desc()).limit(500))
    rows = r.scalars().all()
    return {
        "success": True,
        "items": [
            {"id": x.id, "account_id": x.account_id, "phone_e164": x.phone_e164, "source": x.source}
            for x in rows
        ],
    }


@router.post("/dnc")
async def create_dnc(
    data: DncCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    phone = data.phone_e164.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    row = VoiceDncNumber(account_id=data.account_id, phone_e164=phone, source=data.source)
    db.add(row)
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="create",
        title="新增语音禁呼号码",
        target_type="VoiceDncNumber",
        target_id=str(row.id),
        detail={"phone_e164": phone},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"success": True}


@router.delete("/dnc/{dnc_id}")
async def delete_dnc(
    dnc_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    await db.execute(delete(VoiceDncNumber).where(VoiceDncNumber.id == dnc_id))
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="delete",
        title="删除语音禁呼号码",
        target_type="VoiceDncNumber",
        target_id=str(dnc_id),
        detail={},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"success": True}


# ---------- 导出话单 ----------
@router.get("/calls/export")
async def export_calls_csv(
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    outbound_campaign_id: Optional[int] = None,
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD，含当日"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD，含当日"),
    date_basis: str = Query(
        "created_at",
        description="created_at 或 start_time",
    ),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    q = select(VoiceCall)
    if account_id:
        q = q.where(VoiceCall.account_id == account_id)
    if status:
        q = q.where(VoiceCall.status == status)
    if outbound_campaign_id is not None:
        q = q.where(VoiceCall.outbound_campaign_id == outbound_campaign_id)
    q = apply_voice_call_date_filter(q, VoiceCall, start_date, end_date, date_basis)
    order_col = voice_call_order_column(VoiceCall, date_basis)
    r = await db.execute(q.order_by(order_col.desc()).limit(10000))
    rows = r.scalars().all()
    camp_ids: Set[int] = {
        int(x)
        for x in (getattr(c, "outbound_campaign_id", None) for c in rows)
        if x is not None
    }
    camp_names = await batch_outbound_campaign_names_by_ids(db, camp_ids)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "call_id",
            "account_id",
            "caller",
            "callee",
            "outbound_campaign_id",
            "outbound_campaign_name",
            "billsec",
            "cost",
            "voice_route_id",
            "recording_url",
            "status",
            "start_time",
            "end_time",
        ]
    )
    for c in rows:
        _ocid = getattr(c, "outbound_campaign_id", None)
        _ocname = camp_names.get(int(_ocid), "") if _ocid is not None else ""
        w.writerow(
            [
                c.call_id,
                c.account_id,
                c.caller,
                c.callee,
                _ocid or "",
                _ocname,
                c.billsec or c.duration,
                c.cost,
                getattr(c, "voice_route_id", "") or "",
                getattr(c, "recording_url", "") or "",
                c.status,
                c.start_time.isoformat() if c.start_time else "",
                c.end_time.isoformat() if c.end_time else "",
            ]
        )
    buf.seek(0)
    fn = f"voice_calls_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )
