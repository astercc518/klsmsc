"""语音扩展：主叫号码池、外呼任务、挂机短信规则、DNC、导出"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, delete
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
from app.utils.voice_contact_import import (
    MAX_VOICE_CONTACTS_PER_IMPORT,
    normalize_e164_phone,
    parse_phones_from_csv_bytes,
)
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
    ai_prompt: Optional[str] = None


class CampaignUpdate(BaseModel):
    """更新外呼任务（不含状态，状态走 /campaigns/{id}/status）。"""

    name: Optional[str] = Field(None, max_length=200)
    timezone: Optional[str] = Field(None, max_length=64)
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    max_concurrent: Optional[int] = Field(None, ge=1, le=9999)
    caller_id_mode: Optional[str] = Field(None, pattern="^(fixed|round_robin|random)$")
    fixed_caller_id_id: Optional[int] = None
    ai_mode: Optional[str] = Field(None, pattern="^(ivr|ai)$")
    ai_prompt: Optional[str] = None


async def _ensure_fixed_caller_for_account(
    db: AsyncSession, account_id: int, caller_id: Optional[int]
) -> None:
    if caller_id is None:
        return
    r = await db.execute(
        select(VoiceCallerId).where(
            VoiceCallerId.id == caller_id,
            VoiceCallerId.account_id == account_id,
        )
    )
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="fixed_caller_id_id 不属于该业务账户")


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
                "ai_prompt": getattr(x, "ai_prompt", None),
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
        ai_prompt=data.ai_prompt,
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


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    r = await db.execute(
        select(VoiceOutboundCampaign).where(VoiceOutboundCampaign.id == campaign_id)
    )
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    upd = data.dict(exclude_unset=True)
    if "name" in upd and upd["name"] is not None:
        row.name = (upd["name"] or "").strip() or row.name
    if "timezone" in upd and upd["timezone"] is not None:
        row.timezone = upd["timezone"].strip() or "Asia/Shanghai"
    if "window_start" in upd:
        row.window_start = upd.get("window_start")
    if "window_end" in upd:
        row.window_end = upd.get("window_end")
    if "max_concurrent" in upd and upd["max_concurrent"] is not None:
        row.max_concurrent = upd["max_concurrent"]
    if "caller_id_mode" in upd and upd["caller_id_mode"] is not None:
        row.caller_id_mode = upd["caller_id_mode"]
    if "fixed_caller_id_id" in upd:
        fid = upd.get("fixed_caller_id_id")
        if fid is not None:
            await _ensure_fixed_caller_for_account(db, row.account_id, fid)
        row.fixed_caller_id_id = fid
    if "ai_mode" in upd and upd["ai_mode"] is not None:
        row.ai_mode = upd["ai_mode"][:16]
    if "ai_prompt" in upd:
        row.ai_prompt = upd["ai_prompt"]
    mode = row.caller_id_mode
    if mode == "fixed" and not row.fixed_caller_id_id:
        raise HTTPException(status_code=422, detail="固定主叫模式下须指定 fixed_caller_id_id")
    await db.flush()
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="update",
        title="更新外呼任务",
        target_type="VoiceOutboundCampaign",
        target_id=str(campaign_id),
        detail=upd,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return {"success": True}


@router.get("/campaigns/{campaign_id}/contacts")
async def list_campaign_contacts(
    campaign_id: int,
    status: Optional[str] = Query(
        None,
        description="pending|dialing|completed|failed|skipped",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    r = await db.execute(
        select(VoiceOutboundCampaign.id).where(VoiceOutboundCampaign.id == campaign_id)
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    valid = {"pending", "dialing", "completed", "failed", "skipped"}
    if status is not None and status not in valid:
        raise HTTPException(status_code=400, detail="无效的 status 参数")
    cnt_filters = [VoiceOutboundContact.campaign_id == campaign_id]
    if status:
        cnt_filters.append(VoiceOutboundContact.status == status)
    total = (
        await db.execute(
            select(func.count()).select_from(VoiceOutboundContact).where(*cnt_filters)
        )
    ).scalar() or 0
    list_q = select(VoiceOutboundContact).where(*cnt_filters)
    res = await db.execute(
        list_q.order_by(VoiceOutboundContact.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = res.scalars().all()
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": x.id,
                "phone_e164": x.phone_e164,
                "status": x.status,
                "attempt_count": x.attempt_count,
                "last_error": (x.last_error or "")[:500] if x.last_error else None,
                "created_at": x.created_at.isoformat() if x.created_at else None,
                "updated_at": x.updated_at.isoformat() if x.updated_at else None,
            }
            for x in rows
        ],
    }


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
    if len(body.phones) > MAX_VOICE_CONTACTS_PER_IMPORT:
        raise HTTPException(
            status_code=400,
            detail=f"单次导入不得超过 {MAX_VOICE_CONTACTS_PER_IMPORT} 条",
        )
    n = 0
    for p in body.phones:
        phone = normalize_e164_phone(p)
        if not phone:
            continue
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


@router.post("/campaigns/{campaign_id}/contacts/csv")
async def import_contacts_csv(
    campaign_id: int,
    request: Request,
    file: UploadFile = File(..., description="CSV，首列为号码"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """从 CSV 导入外呼名单（首列号码，可选表头行）。"""
    r = await db.execute(
        select(VoiceOutboundCampaign).where(VoiceOutboundCampaign.id == campaign_id)
    )
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大")
    try:
        raw_phones = parse_phones_from_csv_bytes(raw)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV 须为 UTF-8 编码")
    n = 0
    for p in raw_phones:
        phone = normalize_e164_phone(p)
        if not phone:
            continue
        db.add(
            VoiceOutboundContact(
                campaign_id=campaign_id,
                phone_e164=phone,
                status="pending",
            )
        )
        n += 1
    await log_operation(
        db,
        admin_id=admin.id,
        admin_name=admin.username,
        module="voice",
        action="create",
        title="CSV 导入外呼名单",
        target_type="VoiceOutboundCampaign",
        target_id=str(campaign_id),
        detail={"imported": n, "filename": file.filename},
        ip_address=request.client.host if request.client else None,
    )
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
