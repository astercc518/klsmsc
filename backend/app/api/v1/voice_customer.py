"""客户侧语音 API（API Key）"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
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
from app.modules.voice.campaign_models import VoiceCallerId, VoiceOutboundCampaign
from app.modules.voice.models import VoiceCall
from app.modules.voice.voice_account import VoiceAccount
from app.utils.voice_campaign_names import batch_outbound_campaign_names_for_account

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


class SipConfigResponse(BaseModel):
    sip_domain: str
    sip_port: int
    sip_transport: str
    sip_username: Optional[str] = None


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
