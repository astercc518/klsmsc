"""客户侧语音 API（API Key）"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.account import get_current_account
from app.utils.voice_call_query import (
    apply_voice_call_date_filter,
    voice_call_order_column,
)
from app.config import settings
from app.database import get_db
from app.modules.common.account import Account
from app.modules.voice.campaign_models import (
    VoiceCallerId,
    VoiceOutboundCampaign,
    VoiceOutboundContact,
)
from app.modules.voice.models import VoiceCall
from app.modules.voice.voice_account import VoiceAccount
from app.utils.voice_campaign_names import batch_outbound_campaign_names_for_account
from app.utils.voice_contact_import import (
    MAX_VOICE_CONTACTS_PER_IMPORT,
    normalize_e164_phone,
    parse_phones_from_csv_bytes,
)
from app.workers.voice_worker import voice_campaign_tick_task

router = APIRouter(prefix="/voice", tags=["Voice Customer"])

# 与 VoiceCall.status 枚举一致
_VOICE_CALL_STATUSES = frozenset(
    {"initiated", "ringing", "answered", "busy", "failed", "completed"}
)
_VOICE_DIRECTIONS = frozenset({"inbound", "outbound"})


async def _assert_outbound_campaign_owned(
    db: AsyncSession, account_id: int, campaign_id: int
) -> None:
    """外呼任务须属于当前业务账户，防止越权按任务 ID 筛话单。"""
    r = await db.execute(
        select(VoiceOutboundCampaign.id).where(
            VoiceOutboundCampaign.id == campaign_id,
            VoiceOutboundCampaign.account_id == account_id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=400,
            detail="outbound_campaign_id 无效或无权访问",
        )


async def _get_owned_campaign(
    db: AsyncSession, account_id: int, campaign_id: int
) -> VoiceOutboundCampaign:
    """获取当前账户下的外呼任务，否则 404。"""
    r = await db.execute(
        select(VoiceOutboundCampaign).where(
            VoiceOutboundCampaign.id == campaign_id,
            VoiceOutboundCampaign.account_id == account_id,
        )
    )
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="外呼任务不存在或无权访问")
    return c


async def _require_active_voice_account(db: AsyncSession, account_id: int) -> VoiceAccount:
    """客户操作外呼前须已开通且为活跃状态的语音子账户。"""
    r = await db.execute(
        select(VoiceAccount).where(VoiceAccount.account_id == account_id).limit(1)
    )
    va = r.scalar_one_or_none()
    if not va:
        raise HTTPException(status_code=404, detail="未开通语音账户")
    if va.status != "active":
        raise HTTPException(
            status_code=403,
            detail="语音账户已暂停或关闭，无法操作外呼任务",
        )
    return va


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
        raise HTTPException(status_code=400, detail="fixed_caller_id_id 不属于当前账户")


class SipConfigResponse(BaseModel):
    sip_domain: str
    sip_port: int
    sip_transport: str
    sip_username: Optional[str] = None


class CustomerVoiceCampaignCreate(BaseModel):
    """客户自建外呼任务（草稿）。"""

    name: str = Field(..., max_length=200)
    timezone: str = "Asia/Shanghai"
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    max_concurrent: int = Field(1, ge=1, le=9999)
    caller_id_mode: str = Field("fixed", pattern="^(fixed|round_robin|random)$")
    fixed_caller_id_id: Optional[int] = None
    ai_mode: str = Field("ivr", pattern="^(ivr|ai)$")
    ai_prompt: Optional[str] = None


class CustomerVoiceCampaignUpdate(BaseModel):
    """客户修改任务：仅草稿或已暂停时可更新。"""

    name: Optional[str] = Field(None, max_length=200)
    timezone: Optional[str] = Field(None, max_length=64)
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    max_concurrent: Optional[int] = Field(None, ge=1, le=9999)
    caller_id_mode: Optional[str] = Field(None, pattern="^(fixed|round_robin|random)$")
    fixed_caller_id_id: Optional[int] = None
    ai_mode: Optional[str] = Field(None, pattern="^(ivr|ai)$")
    ai_prompt: Optional[str] = None


class CustomerVoiceCampaignStatusBody(BaseModel):
    status: str = Field(pattern="^(running|paused|completed|cancelled|draft)$")


class CustomerContactsImport(BaseModel):
    phones: List[str] = Field(default_factory=list)


@router.get("/me")
async def voice_me(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """当前账户的 SIP 注册参数说明。"""
    r = await db.execute(
        select(VoiceAccount)
        .options(selectinload(VoiceAccount.account))
        .where(VoiceAccount.account_id == account.id)
        .order_by(VoiceAccount.id.desc())
        .limit(1)
    )
    va = r.scalar_one_or_none()
    if not va:
        raise HTTPException(status_code=404, detail="未开通语音账户")

    default_caller = None
    if getattr(va, "default_caller_id_id", None):
        rdc = await db.execute(
            select(VoiceCallerId).where(VoiceCallerId.id == va.default_caller_id_id)
        )
        dcid = rdc.scalar_one_or_none()
        if dcid:
            default_caller = {
                "id": dcid.id,
                "number_e164": dcid.number_e164,
                "label": dcid.label,
            }

    return {
        "success": True,
        "voice_account": {
            "id": va.id,
            "sip_username": va.sip_username or va.okcc_account,
            "country_code": va.country_code,
            "balance": float(va.balance or 0),
            "status": va.status,
            "default_caller": default_caller,
        },
        "sip": SipConfigResponse(
            sip_domain=settings.VOICE_SIP_DOMAIN or "",
            sip_port=settings.VOICE_SIP_PORT,
            sip_transport=settings.VOICE_SIP_TRANSPORT,
            sip_username=va.sip_username or va.okcc_account,
        ).model_dump(),
        "policy": {
            "hangup_sms_max_per_callee_per_day": settings.VOICE_HANGUP_SMS_MAX_PER_CALLEE_PER_DAY,
            "min_balance_for_originate": settings.VOICE_MIN_BALANCE_FOR_ORIGINATE,
            "cdr_webhook_max_retries": settings.VOICE_CDR_MAX_RETRIES,
            "max_concurrent_calls": getattr(va, "max_concurrent_calls", None) or 0,
            "daily_outbound_limit": getattr(va, "daily_outbound_limit", None) or 0,
        },
    }


@router.get("/outbound-campaigns")
async def list_my_outbound_campaigns(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """当前业务账户下的外呼任务列表（只读，用于话单筛选等）。"""
    r = await db.execute(
        select(VoiceOutboundCampaign)
        .where(VoiceOutboundCampaign.account_id == account.id)
        .order_by(VoiceOutboundCampaign.id.desc())
    )
    rows = r.scalars().all()
    return {
        "success": True,
        "items": [
            {
                "id": x.id,
                "name": x.name,
                "status": x.status,
                "timezone": x.timezone,
                "window_start": x.window_start,
                "window_end": x.window_end,
                "ai_mode": getattr(x, "ai_mode", None) or "ivr",
                "ai_prompt": getattr(x, "ai_prompt", None),
                "max_concurrent": x.max_concurrent,
                "caller_id_mode": getattr(x, "caller_id_mode", None),
                "fixed_caller_id_id": x.fixed_caller_id_id,
            }
            for x in rows
        ],
    }


@router.get("/outbound-campaigns/{campaign_id}")
async def get_my_outbound_campaign(
    campaign_id: int,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """外呼任务详情（须为本账户任务）。"""
    c = await _get_owned_campaign(db, account.id, campaign_id)
    return {
        "success": True,
        "item": {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "timezone": c.timezone,
            "window_start": c.window_start,
            "window_end": c.window_end,
            "max_concurrent": c.max_concurrent,
            "caller_id_mode": getattr(c, "caller_id_mode", None),
            "fixed_caller_id_id": c.fixed_caller_id_id,
            "ai_mode": getattr(c, "ai_mode", None) or "ivr",
            "ai_prompt": getattr(c, "ai_prompt", None),
        },
    }


@router.post("/outbound-campaigns")
async def create_my_outbound_campaign(
    data: CustomerVoiceCampaignCreate,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    await _require_active_voice_account(db, account.id)
    mode = data.caller_id_mode
    if mode == "fixed":
        await _ensure_fixed_caller_for_account(db, account.id, data.fixed_caller_id_id)
        if not data.fixed_caller_id_id:
            raise HTTPException(status_code=422, detail="固定主叫模式下须指定 fixed_caller_id_id")
    row = VoiceOutboundCampaign(
        account_id=account.id,
        name=data.name.strip(),
        timezone=(data.timezone or "Asia/Shanghai").strip() or "Asia/Shanghai",
        window_start=data.window_start,
        window_end=data.window_end,
        max_concurrent=data.max_concurrent,
        caller_id_mode=data.caller_id_mode,
        fixed_caller_id_id=data.fixed_caller_id_id if mode == "fixed" else None,
        ai_mode=(data.ai_mode or "ivr")[:16],
        ai_prompt=data.ai_prompt,
        status="draft",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"success": True, "id": row.id}


@router.put("/outbound-campaigns/{campaign_id}")
async def update_my_outbound_campaign(
    campaign_id: int,
    data: CustomerVoiceCampaignUpdate,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_owned_campaign(db, account.id, campaign_id)
    if c.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=400,
            detail="仅草稿或已暂停状态的任务可修改配置",
        )
    await _require_active_voice_account(db, account.id)
    upd = data.dict(exclude_unset=True)
    if "name" in upd and upd["name"] is not None:
        c.name = (upd["name"] or "").strip() or c.name
    if "timezone" in upd and upd["timezone"] is not None:
        c.timezone = upd["timezone"].strip() or "Asia/Shanghai"
    if "window_start" in upd:
        c.window_start = upd.get("window_start")
    if "window_end" in upd:
        c.window_end = upd.get("window_end")
    if "max_concurrent" in upd and upd["max_concurrent"] is not None:
        c.max_concurrent = upd["max_concurrent"]
    if "caller_id_mode" in upd and upd["caller_id_mode"] is not None:
        c.caller_id_mode = upd["caller_id_mode"]
    if "fixed_caller_id_id" in upd:
        fid = upd.get("fixed_caller_id_id")
        if fid is not None:
            await _ensure_fixed_caller_for_account(db, account.id, fid)
        c.fixed_caller_id_id = fid
    if "ai_mode" in upd and upd["ai_mode"] is not None:
        c.ai_mode = upd["ai_mode"][:16]
    if "ai_prompt" in upd:
        c.ai_prompt = upd["ai_prompt"]
    mode = c.caller_id_mode
    if mode == "fixed" and not c.fixed_caller_id_id:
        raise HTTPException(status_code=422, detail="固定主叫模式下须指定 fixed_caller_id_id")
    await db.commit()
    await db.refresh(c)
    return {"success": True}


@router.post("/outbound-campaigns/{campaign_id}/status")
async def set_my_outbound_campaign_status(
    campaign_id: int,
    body: CustomerVoiceCampaignStatusBody,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    await _require_active_voice_account(db, account.id)
    c = await _get_owned_campaign(db, account.id, campaign_id)
    c.status = body.status
    await db.commit()
    if body.status == "running":
        voice_campaign_tick_task.delay(campaign_id)
    return {"success": True}


@router.post("/outbound-campaigns/{campaign_id}/contacts")
async def import_my_campaign_contacts(
    campaign_id: int,
    body: CustomerContactsImport,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    await _require_active_voice_account(db, account.id)
    await _get_owned_campaign(db, account.id, campaign_id)
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


@router.post("/outbound-campaigns/{campaign_id}/contacts/csv")
async def import_my_campaign_contacts_csv(
    campaign_id: int,
    file: UploadFile = File(..., description="CSV，首列为号码"),
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    await _require_active_voice_account(db, account.id)
    await _get_owned_campaign(db, account.id, campaign_id)
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
    await db.commit()
    return {"success": True, "imported": n}


@router.get("/outbound-campaigns/{campaign_id}/contacts")
async def list_my_campaign_contacts(
    campaign_id: int,
    status: Optional[str] = Query(
        None,
        description="pending|dialing|completed|failed|skipped",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_campaign(db, account.id, campaign_id)
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


@router.get("/caller-ids")
async def voice_caller_ids_for_account(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """当前业务账户下的主叫号码池（只读，配置变更走管理端）。"""
    r = await db.execute(
        select(VoiceCallerId)
        .where(VoiceCallerId.account_id == account.id)
        .order_by(VoiceCallerId.id.desc())
    )
    rows = r.scalars().all()
    return {
        "success": True,
        "items": [
            {
                "id": x.id,
                "number_e164": x.number_e164,
                "label": x.label,
                "trunk_ref": x.trunk_ref,
                "voice_route_id": getattr(x, "voice_route_id", None),
                "status": x.status,
            }
            for x in rows
        ],
    }


@router.get("/calls")
async def voice_calls_me(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD，含当日"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD，含当日"),
    date_basis: str = Query(
        "created_at",
        description="created_at 入库时间；start_time 通话开始时间",
    ),
    status: Optional[str] = Query(
        None,
        description="通话状态：initiated/ringing/answered/busy/failed/completed",
    ),
    direction: Optional[str] = Query(
        None,
        description="呼向：inbound / outbound",
    ),
    outbound_campaign_id: Optional[int] = Query(
        None,
        ge=1,
        description="外呼任务 ID（须为本账户任务）",
    ),
):
    if status is not None and status not in _VOICE_CALL_STATUSES:
        raise HTTPException(status_code=400, detail="无效的 status 参数")
    if direction is not None and direction not in _VOICE_DIRECTIONS:
        raise HTTPException(status_code=400, detail="无效的 direction 参数")

    q = select(VoiceCall).where(VoiceCall.account_id == account.id)
    if status:
        q = q.where(VoiceCall.status == status)
    if direction:
        q = q.where(VoiceCall.direction == direction)
    if outbound_campaign_id is not None:
        await _assert_outbound_campaign_owned(db, account.id, outbound_campaign_id)
        q = q.where(VoiceCall.outbound_campaign_id == outbound_campaign_id)
    q = apply_voice_call_date_filter(q, VoiceCall, start_date, end_date, date_basis)
    order_col = voice_call_order_column(VoiceCall, date_basis)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    res = await db.execute(
        q.order_by(order_col.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = res.scalars().all()
    camp_ids = {
        int(x)
        for x in (getattr(c, "outbound_campaign_id", None) for c in rows)
        if x is not None
    }
    camp_names = await batch_outbound_campaign_names_for_account(db, account.id, camp_ids)
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "call_id": c.call_id,
                "caller": c.caller,
                "callee": c.callee,
                "direction": getattr(c, "direction", None),
                "outbound_campaign_id": getattr(c, "outbound_campaign_id", None),
                "outbound_campaign_name": (
                    camp_names.get(int(getattr(c, "outbound_campaign_id")))
                    if getattr(c, "outbound_campaign_id", None)
                    else None
                ),
                "voice_route_id": getattr(c, "voice_route_id", None),
                "duration": c.duration,
                "billsec": c.billsec,
                "cost": c.cost,
                "status": c.status,
                "hangup_cause": getattr(c, "hangup_cause", None),
                "recording_url": getattr(c, "recording_url", None),
                "start_time": c.start_time.isoformat() if c.start_time else None,
                "end_time": c.end_time.isoformat() if c.end_time else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows
        ],
    }


@router.get("/calls/export")
async def voice_calls_export_csv(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_basis: str = Query("created_at", description="created_at 或 start_time"),
    status: Optional[str] = Query(
        None,
        description="通话状态，与列表接口一致",
    ),
    direction: Optional[str] = Query(None, description="inbound / outbound"),
    outbound_campaign_id: Optional[int] = Query(
        None,
        ge=1,
        description="外呼任务 ID，与列表接口一致",
    ),
):
    """当前账户话单 CSV（最多 10000 条），筛选条件与列表一致。"""
    if status is not None and status not in _VOICE_CALL_STATUSES:
        raise HTTPException(status_code=400, detail="无效的 status 参数")
    if direction is not None and direction not in _VOICE_DIRECTIONS:
        raise HTTPException(status_code=400, detail="无效的 direction 参数")

    q = select(VoiceCall).where(VoiceCall.account_id == account.id)
    if status:
        q = q.where(VoiceCall.status == status)
    if direction:
        q = q.where(VoiceCall.direction == direction)
    if outbound_campaign_id is not None:
        await _assert_outbound_campaign_owned(db, account.id, outbound_campaign_id)
        q = q.where(VoiceCall.outbound_campaign_id == outbound_campaign_id)
    q = apply_voice_call_date_filter(q, VoiceCall, start_date, end_date, date_basis)
    order_col = voice_call_order_column(VoiceCall, date_basis)
    r = await db.execute(q.order_by(order_col.desc()).limit(10000))
    rows = r.scalars().all()
    camp_ids_csv = {
        int(x)
        for x in (getattr(c, "outbound_campaign_id", None) for c in rows)
        if x is not None
    }
    camp_names_csv = await batch_outbound_campaign_names_for_account(
        db, account.id, camp_ids_csv
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "call_id",
            "caller",
            "callee",
            "direction",
            "outbound_campaign_id",
            "outbound_campaign_name",
            "voice_route_id",
            "billsec",
            "cost",
            "status",
            "hangup_cause",
            "recording_url",
            "start_time",
            "end_time",
            "created_at",
        ]
    )
    for c in rows:
        _ocid = getattr(c, "outbound_campaign_id", None)
        _ocname = (
            camp_names_csv.get(int(_ocid), "") if _ocid is not None else ""
        )
        w.writerow(
            [
                c.call_id,
                c.caller,
                c.callee,
                getattr(c, "direction", "") or "",
                getattr(c, "outbound_campaign_id", "") or "",
                _ocname,
                getattr(c, "voice_route_id", "") or "",
                c.billsec or c.duration,
                c.cost,
                c.status,
                getattr(c, "hangup_cause", "") or "",
                getattr(c, "recording_url", "") or "",
                c.start_time.isoformat() if c.start_time else "",
                c.end_time.isoformat() if c.end_time else "",
                c.created_at.isoformat() if c.created_at else "",
            ]
        )
    buf.seek(0)
    fn = f"voice_calls_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )
