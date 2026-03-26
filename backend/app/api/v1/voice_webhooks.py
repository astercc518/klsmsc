"""语音 CDR Webhook（自建 FreeSWITCH / 网关回调）"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.utils.cache import get_redis_client
from app.modules.voice.campaign_models import VoiceCdrWebhookLog
from app.services.voice_cdr import process_cdr_pipeline, verify_cdr_signature
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/voice/webhooks", tags=["Voice Webhooks"])

_RAW_MAX = 65535


async def _cdr_ip_rate_limit(ip: str) -> None:
    """CDR 回调按 IP 滑动窗口限流，防刷与误循环。"""
    lim = settings.VOICE_CDR_WEBHOOK_IP_RATE_PER_MINUTE
    if lim <= 0 or not ip:
        return
    try:
        r = await get_redis_client()
        minute = datetime.utcnow().strftime("%Y%m%d%H%M")
        key = f"voice:cdr:rl:{ip}:{minute}"
        n = await r.incr(key.encode())
        if n == 1:
            await r.expire(key.encode(), 70)
        if n > lim:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except HTTPException:
        raise
    except Exception as ex:
        logger.debug(f"CDR 限流 Redis 不可用，跳过: {ex}")


def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host or ""
    return ""


@router.post("/cdr")
async def receive_cdr(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw = await request.body()
    raw_str = raw.decode("utf-8", errors="replace")[:_RAW_MAX]
    sig = request.headers.get("X-Voice-Signature") or request.headers.get("x-voice-signature")

    allow_ips = settings.voice_cdr_webhook_ip_list
    client_ip = _client_ip(request)
    if allow_ips:
        if client_ip not in allow_ips:
            raise HTTPException(status_code=403, detail="IP not allowed")

    await _cdr_ip_rate_limit(client_ip)

    if not verify_cdr_signature(raw, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload: Dict[str, Any] = json.loads(raw_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    call_id = str(payload.get("call_id") or "").strip()
    if not call_id:
        raise HTTPException(status_code=400, detail="call_id required")

    ph = hashlib.sha256(raw).hexdigest()
    existing = await db.execute(
        select(VoiceCdrWebhookLog).where(VoiceCdrWebhookLog.call_id == call_id)
    )
    log_row = existing.scalar_one_or_none()
    if log_row and log_row.status == "processed":
        return {"success": True, "duplicate": True, "call_id": call_id}

    if not log_row:
        db.add(
            VoiceCdrWebhookLog(
                call_id=call_id,
                payload_hash=ph,
                raw_payload=raw_str,
                status="received",
                retry_count=0,
            )
        )
        await db.flush()
        q2 = await db.execute(
            select(VoiceCdrWebhookLog).where(VoiceCdrWebhookLog.call_id == call_id)
        )
        log_row = q2.scalar_one_or_none()
    else:
        log_row.raw_payload = log_row.raw_payload or raw_str
        log_row.payload_hash = ph

    try:
        await process_cdr_pipeline(db, payload)
        log_row.status = "processed"
        log_row.error_message = None
        log_row.processed_at = datetime.utcnow()
        if hasattr(log_row, "retry_count") and log_row.retry_count is None:
            log_row.retry_count = 0
        await db.flush()
        logger.info(f"CDR 已处理 call_id={call_id}")
        return {"success": True, "call_id": call_id}
    except Exception as e:
        logger.exception("CDR 处理失败")
        log_row.status = "failed"
        log_row.error_message = str(e)[:2000]
        log_row.raw_payload = raw_str
        rc = getattr(log_row, "retry_count", None) or 0
        if hasattr(log_row, "retry_count"):
            log_row.retry_count = rc
        await db.flush()
        # 显式提交失败状态，避免请求异常回滚导致无法重试与对账
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))
