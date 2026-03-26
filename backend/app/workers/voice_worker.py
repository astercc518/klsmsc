"""语音外呼 Celery 任务"""
from __future__ import annotations

import asyncio
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.modules.voice.campaign_models import (
    VoiceCallerId,
    VoiceCdrWebhookLog,
    VoiceOutboundCampaign,
    VoiceOutboundContact,
    VoiceDncNumber,
)
from app.modules.voice.voice_account import VoiceAccount
from app.utils.logger import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _in_window(now_local: datetime, tz_name: str, start_s: Optional[str], end_s: Optional[str]) -> bool:
    if not start_s or not end_s:
        return True
    try:
        sh, sm = [int(x) for x in start_s.split(":")]
        eh, em = [int(x) for x in end_s.split(":")]
        tnow = now_local.time()
        a = dt_time(sh, sm)
        b = dt_time(eh, em)
        return a <= tnow <= b
    except Exception:
        return True


async def _pick_caller_id(
    db: AsyncSession, camp: VoiceOutboundCampaign, contact: VoiceOutboundContact
) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """返回 (E.164 主叫, trunk_ref, voice_route_id)。"""
    if camp.caller_id_mode == "fixed" and camp.fixed_caller_id_id:
        r = await db.execute(
            select(VoiceCallerId).where(VoiceCallerId.id == camp.fixed_caller_id_id)
        )
        cid = r.scalar_one_or_none()
        if cid:
            return (
                cid.number_e164,
                cid.trunk_ref,
                getattr(cid, "voice_route_id", None),
            )
        return (None, None, None)
    q = await db.execute(
        select(VoiceCallerId).where(
            VoiceCallerId.account_id == camp.account_id,
            VoiceCallerId.status == "active",
        )
    )
    rows: List[VoiceCallerId] = list(q.scalars().all())
    if not rows:
        return (None, None, None)
    if camp.caller_id_mode == "random":
        import random

        x = random.choice(rows)
        return (x.number_e164, x.trunk_ref, getattr(x, "voice_route_id", None))
    # round_robin：按名单 id 轮转，避免永远打同一条主叫
    rows.sort(key=lambda x: x.id)
    idx = (contact.id or 0) % len(rows)
    x = rows[idx]
    return (x.number_e164, x.trunk_ref, getattr(x, "voice_route_id", None))


async def _count_account_dialing(db: AsyncSession, account_id: int) -> int:
    q = select(func.count()).select_from(VoiceOutboundContact).join(
        VoiceOutboundCampaign,
        VoiceOutboundContact.campaign_id == VoiceOutboundCampaign.id,
    ).where(
        VoiceOutboundCampaign.account_id == account_id,
        VoiceOutboundContact.status == "dialing",
    )
    return (await db.execute(q)).scalar() or 0


async def _count_today_outbound_attempts(db: AsyncSession, account_id: int) -> int:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = select(func.count()).select_from(VoiceOutboundContact).join(
        VoiceOutboundCampaign,
        VoiceOutboundContact.campaign_id == VoiceOutboundCampaign.id,
    ).where(
        VoiceOutboundCampaign.account_id == account_id,
        VoiceOutboundContact.updated_at >= start,
        VoiceOutboundContact.status.in_(("dialing", "completed", "failed")),
    )
    return (await db.execute(q)).scalar() or 0


async def _originate(
    *,
    account_id: int,
    phone: str,
    campaign_id: int,
    caller_id: Optional[str],
    trunk_ref: Optional[str] = None,
    voice_route_id: Optional[int] = None,
    ai_mode: Optional[str] = None,
) -> Dict[str, Any]:
    base = settings.VOICE_GATEWAY_BASE_URL
    if not base:
        logger.warning("未配置 VOICE_GATEWAY_BASE_URL，跳过真实外呼")
        return {"success": False, "message": "gateway not configured"}

    url = base.rstrip("/") + "/originate"
    headers = {}
    if settings.VOICE_ORIGINATE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.VOICE_ORIGINATE_TOKEN}"
    payload = {
        "account_id": account_id,
        "callee": phone,
        "campaign_id": campaign_id,
        "caller_id": caller_id,
        "trunk_ref": trunk_ref,
        "voice_route_id": voice_route_id,
        "ai_mode": (ai_mode or "ivr")[:16],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        try:
            return {"success": r.status_code < 400, "status_code": r.status_code, "body": r.text[:500]}
        except Exception as e:
            return {"success": False, "message": str(e)}


async def _process_campaign_batch_async(campaign_id: int, limit: int = 20) -> Dict[str, Any]:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(VoiceOutboundCampaign).where(VoiceOutboundCampaign.id == campaign_id)
        )
        camp = r.scalar_one_or_none()
        if not camp or camp.status != "running":
            return {"skipped": True}

        rva = await db.execute(
            select(VoiceAccount).where(VoiceAccount.account_id == camp.account_id).limit(1)
        )
        va = rva.scalar_one_or_none()
        if settings.VOICE_MIN_BALANCE_FOR_ORIGINATE > 0:
            if va and float(va.balance or 0) < settings.VOICE_MIN_BALANCE_FOR_ORIGINATE:
                return {"skipped": True, "reason": "low_balance"}

        if va:
            lim = getattr(va, "daily_outbound_limit", None) or 0
            if lim > 0:
                n = await _count_today_outbound_attempts(db, camp.account_id)
                if n >= lim:
                    return {"skipped": True, "reason": "daily_outbound_limit"}
            mc = getattr(va, "max_concurrent_calls", None) or 0
            if mc > 0:
                d = await _count_account_dialing(db, camp.account_id)
                if d >= mc:
                    return {"skipped": True, "reason": "max_concurrent_calls"}

        now = datetime.now()
        if not _in_window(now, camp.timezone or "Asia/Shanghai", camp.window_start, camp.window_end):
            return {"skipped": True, "reason": "outside window"}

        dialing_c = (
            await db.execute(
                select(func.count()).where(
                    VoiceOutboundContact.campaign_id == campaign_id,
                    VoiceOutboundContact.status == "dialing",
                )
            )
        ).scalar() or 0
        max_c = camp.max_concurrent or 1
        slots = max(0, max_c - int(dialing_c))
        if slots <= 0:
            return {"skipped": True, "reason": "campaign_max_concurrent"}

        q = await db.execute(
            select(VoiceOutboundContact)
            .where(
                VoiceOutboundContact.campaign_id == campaign_id,
                VoiceOutboundContact.status == "pending",
            )
            .limit(min(limit, slots))
        )
        contacts = list(q.scalars().all())
        dialed = 0
        for c in contacts:
            dnc = await db.execute(
                select(VoiceDncNumber).where(
                    VoiceDncNumber.account_id == camp.account_id,
                    VoiceDncNumber.phone_e164 == c.phone_e164,
                )
            )
            if dnc.scalar_one_or_none():
                c.status = "skipped"
                c.last_error = "DNC"
                continue

            c.status = "dialing"
            c.attempt_count = (c.attempt_count or 0) + 1
            await db.flush()

            caller, trunk_ref, vrid = await _pick_caller_id(db, camp, c)
            res = await _originate(
                account_id=camp.account_id,
                phone=c.phone_e164,
                campaign_id=campaign_id,
                caller_id=caller,
                trunk_ref=trunk_ref,
                voice_route_id=vrid,
                ai_mode=getattr(camp, "ai_mode", None),
            )
            if res.get("success"):
                c.status = "completed"
                dialed += 1
            else:
                c.status = "failed"
                c.last_error = str(res.get("message") or res.get("body"))[:500]
        await db.commit()
        return {"campaign_id": campaign_id, "dialed": dialed, "batch": len(contacts)}


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="voice_campaign_tick_task", bind=True, max_retries=2)
def voice_campaign_tick_task(self, campaign_id: int):
    """处理单个外呼任务的一批名单。"""
    try:
        return _run_async(_process_campaign_batch_async(campaign_id))
    except Exception as e:
        logger.exception(f"voice_campaign_tick_task 失败: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task(name="voice_campaign_scan_task")
def voice_campaign_scan_task():
    """扫描所有 running 任务并投递 tick（简化：由 beat 或管理端触发）。"""
    async def _scan():
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(VoiceOutboundCampaign.id).where(
                    VoiceOutboundCampaign.status == "running"
                )
            )
            ids = [row[0] for row in r.all()]
            return ids

    ids = _run_async(_scan())
    for cid in ids:
        voice_campaign_tick_task.delay(cid)
    return {"campaigns": len(ids)}


@celery_app.task(name="voice_cdr_retry_failed_task")
def voice_cdr_retry_failed_task():
    """重试处理失败的 CDR Webhook（依赖 raw_payload）。"""

    async def _retry():
        import json
        from datetime import datetime

        from app.services.voice_cdr import process_cdr_pipeline

        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(VoiceCdrWebhookLog)
                .where(
                    and_(
                        VoiceCdrWebhookLog.status == "failed",
                        or_(
                            VoiceCdrWebhookLog.retry_count.is_(None),
                            VoiceCdrWebhookLog.retry_count < settings.VOICE_CDR_MAX_RETRIES,
                        ),
                    )
                )
                .limit(100)
            )
            rows = list(r.scalars().all())
            ok = 0
            for log in rows:
                rc = getattr(log, "retry_count", None) or 0
                if not log.raw_payload:
                    continue
                try:
                    payload = json.loads(log.raw_payload)
                    await process_cdr_pipeline(db, payload)
                    log.status = "processed"
                    log.error_message = None
                    log.processed_at = datetime.utcnow()
                    ok += 1
                except Exception as e:
                    log.retry_count = rc + 1
                    log.error_message = str(e)[:2000]
                    logger.warning(f"CDR 重试仍失败 {log.call_id}: {e}")
            await db.commit()
            return {"candidates": len(rows), "recovered": ok}

    return _run_async(_retry())
