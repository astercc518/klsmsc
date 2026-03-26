"""CDR 入库、语音批价扣费（简化：按账户国家与 VoiceRoute 首条匹配）"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.voice.models import VoiceCall, VoiceRoute
from app.modules.voice.voice_account import VoiceAccount
from app.utils.logger import get_logger

logger = get_logger(__name__)


def verify_cdr_signature(raw_body: bytes, signature_hex: Optional[str]) -> bool:
    """校验 X-Voice-Signature：hex(hmac_sha256(body, secret))"""
    secret = (settings.VOICE_CDR_WEBHOOK_SECRET or "").encode()
    if not secret:
        return settings.APP_DEBUG
    if not signature_hex:
        return False
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.lower(), signature_hex.lower().strip())


def _parse_dt(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, (int, float)):
        return datetime.utcfromtimestamp(val)
    s = str(val).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


async def apply_voice_billing(
    db: AsyncSession,
    *,
    account_id: int,
    country_code: str,
    billsec: int,
    voice_route_id: Optional[int] = None,
) -> tuple[float, Optional[int]]:
    """
    按分钟单价估算费用（不足一分钟按一分钟）。
    若 CDR 携带 voice_route_id 则优先用该路由批价，否则按国家码匹配，再退回全局优先级最高的一条。
    返回 (费用, 实际使用的路由 ID)。
    """
    logger.debug("批价 account_id=%s country=%s route_hint=%s", account_id, country_code, voice_route_id)
    if billsec <= 0:
        return 0.0, None
    route = None
    if voice_route_id:
        q = await db.execute(select(VoiceRoute).where(VoiceRoute.id == voice_route_id))
        route = q.scalar_one_or_none()
    if not route:
        q = await db.execute(
            select(VoiceRoute)
            .where(VoiceRoute.country_code == country_code)
            .order_by(VoiceRoute.priority.desc(), VoiceRoute.id.desc())
            .limit(1)
        )
        route = q.scalar_one_or_none()
    if not route:
        q2 = await db.execute(
            select(VoiceRoute)
            .order_by(VoiceRoute.priority.desc(), VoiceRoute.id.desc())
            .limit(1)
        )
        route = q2.scalar_one_or_none()
    if not route:
        return 0.0, None
    minutes = max(1, (billsec + 59) // 60)
    return float(route.cost_per_minute or 0) * minutes, route.id


async def upsert_voice_call_from_cdr(
    db: AsyncSession,
    payload: Dict[str, Any],
) -> VoiceCall:
    """幂等 upsert voice_calls。"""
    call_id = str(payload.get("call_id") or "").strip()
    if not call_id:
        raise ValueError("call_id 必填")

    q = await db.execute(select(VoiceCall).where(VoiceCall.call_id == call_id))
    row = q.scalar_one_or_none()

    account_id = int(payload.get("account_id"))
    _va = payload.get("voice_account_id")
    voice_account_id_int: Optional[int] = int(_va) if _va is not None and str(_va).strip() != "" else None
    campaign_id = payload.get("campaign_id")

    billsec = int(payload.get("billsec") or payload.get("duration") or 0)

    vr_raw = payload.get("voice_route_id")
    voice_route_id_hint: Optional[int] = None
    if vr_raw is not None and str(vr_raw).strip() != "":
        try:
            voice_route_id_hint = int(vr_raw)
        except (TypeError, ValueError):
            voice_route_id_hint = None

    country = str(payload.get("country_code") or "").strip()
    if not country and voice_account_id_int:
        qva = await db.execute(
            select(VoiceAccount).where(VoiceAccount.id == voice_account_id_int)
        )
        va = qva.scalar_one_or_none()
        if va and va.country_code:
            country = str(va.country_code)
    if not country:
        country = "PH"

    cost, resolved_route_id = await apply_voice_billing(
        db,
        account_id=account_id,
        country_code=country,
        billsec=billsec,
        voice_route_id=voice_route_id_hint,
    )

    status = "completed"
    if payload.get("hangup_cause") and str(payload.get("hangup_cause")).upper() in (
        "USER_BUSY",
        "BUSY",
    ):
        status = "busy"
    elif billsec <= 0 and payload.get("answered") is False:
        status = "failed"

    vals = dict(
        account_id=account_id,
        provider_call_id=payload.get("provider_call_id"),
        voice_account_id=voice_account_id_int,
        outbound_campaign_id=int(campaign_id) if campaign_id else None,
        caller=payload.get("caller"),
        callee=payload.get("callee"),
        direction=payload.get("direction"),
        sip_extension=payload.get("sip_extension"),
        start_time=_parse_dt(payload.get("start_time")),
        answer_time=_parse_dt(payload.get("answer_time")),
        end_time=_parse_dt(payload.get("end_time")),
        duration=int(payload.get("duration") or billsec),
        billsec=billsec,
        status=status,
        hangup_cause=payload.get("hangup_cause"),
        recording_url=payload.get("recording_url"),
        cost=cost,
        voice_route_id=resolved_route_id,
    )

    if row:
        for k, v in vals.items():
            setattr(row, k, v)
        await db.flush()
        return row

    row = VoiceCall(call_id=call_id, **vals)
    db.add(row)
    await db.flush()
    await deduct_voice_balance(db, voice_account_id_int, cost)
    return row


async def deduct_voice_balance(
    db: AsyncSession, voice_account_id: Optional[int], cost: float
) -> None:
    """从语音子账户扣减余额（若有）。"""
    if cost <= 0 or not voice_account_id:
        return
    q = await db.execute(
        select(VoiceAccount).where(VoiceAccount.id == voice_account_id)
    )
    va = q.scalar_one_or_none()
    if not va or va.balance is None:
        return
    from decimal import Decimal

    va.balance = Decimal(str(float(va.balance) - cost)).quantize(Decimal("0.01"))
    await db.flush()


async def process_cdr_pipeline(db: AsyncSession, payload: Dict[str, Any]):
    """CDR 入库 + 挂机短信（供 Webhook 与重试 Worker 共用）。"""
    from app.services.voice_hangup_sms import send_hangup_sms_if_needed

    call = await upsert_voice_call_from_cdr(db, payload)
    await send_hangup_sms_if_needed(db, call)
    return call
