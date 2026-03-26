"""挂机短信：CDR 完成后按规则触发短信发送。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pricing import PricingEngine
from app.core.router import RoutingEngine
from app.modules.sms.sms_log import SMSLog
from app.modules.voice.campaign_models import VoiceHangupSmsRule, VoiceOutboundCampaign
from app.modules.voice.models import VoiceCall
from app.utils.logger import get_logger
from app.utils.queue import QueueManager
from app.utils.validator import Validator

logger = get_logger(__name__)


def _render_template(body: str, *, callee: str, duration_sec: int, campaign_name: str) -> str:
    out = body
    out = out.replace("{callee}", callee or "")
    out = out.replace("{duration}", str(duration_sec or 0))
    out = out.replace("{campaign_name}", campaign_name or "")
    return out


async def send_hangup_sms_if_needed(db: AsyncSession, call: VoiceCall) -> Optional[str]:
    """
    根据规则发送挂机短信，返回 message_id。
    幂等：若 hangup_sms_message_id 已存在则跳过。
    """
    if call.hangup_sms_message_id:
        return call.hangup_sms_message_id

    q = (
        select(VoiceHangupSmsRule)
        .where(VoiceHangupSmsRule.enabled == True)  # noqa: E712
        .where(
            (VoiceHangupSmsRule.account_id == call.account_id)
            | (VoiceHangupSmsRule.account_id.is_(None))
        )
        .order_by(VoiceHangupSmsRule.priority.desc(), VoiceHangupSmsRule.id.desc())
    )
    rules = (await db.execute(q)).scalars().all()

    campaign_name = ""
    if call.outbound_campaign_id:
        cq = await db.execute(
            select(VoiceOutboundCampaign).where(
                VoiceOutboundCampaign.id == call.outbound_campaign_id
            )
        )
        camp = cq.scalar_one_or_none()
        if camp:
            campaign_name = camp.name or ""

    billsec = int(call.billsec or call.duration or 0)
    for rule in rules:
        if rule.account_id and rule.account_id != call.account_id:
            continue
        if rule.campaign_id and rule.campaign_id != call.outbound_campaign_id:
            continue
        if rule.match_answered_only and billsec <= 0:
            continue

        body = _render_template(
            rule.template_body,
            callee=call.callee or "",
            duration_sec=billsec,
            campaign_name=campaign_name,
        )
        if not body.strip():
            continue

        target = call.callee or call.caller
        if not target:
            continue

        ok, err, phone_info = Validator.validate_phone_number(target)
        if not ok:
            logger.warning(f"挂机短信号码无效: {target} {err}")
            continue

        country_code = phone_info["country_code"]
        phone_e164 = phone_info["e164_format"]

        # 频控：同一账户对同一被叫每日挂机短信条数上限
        try:
            from datetime import date

            from app.config import settings
            from app.utils.cache import get_redis_client

            r = await get_redis_client()
            day = date.today().isoformat()
            key = f"voice:hangup:{call.account_id}:{phone_e164}:{day}"
            cnt = await r.incr(key)
            if cnt == 1:
                await r.expire(key, 172800)
            if cnt > settings.VOICE_HANGUP_SMS_MAX_PER_CALLEE_PER_DAY:
                logger.warning(f"挂机短信超频控跳过: {phone_e164} count={cnt}")
                continue
        except Exception as ex:
            logger.debug(f"挂机短信频控 Redis 不可用，继续发送: {ex}")

        routing = RoutingEngine(db)
        channel = await routing.select_channel(
            country_code=country_code, account_id=call.account_id
        )
        if not channel:
            logger.warning("挂机短信无可用通道")
            continue

        pricing = PricingEngine(db)
        charge = await pricing.calculate_and_charge(
            account_id=call.account_id,
            channel_id=channel.id,
            country_code=country_code,
            message=body,
        )
        if not charge.get("success"):
            logger.warning(f"挂机短信计费失败: {charge.get('error')}")
            continue

        message_id = f"msg_{uuid.uuid4().hex}"
        sms = SMSLog(
            message_id=message_id,
            account_id=call.account_id,
            channel_id=channel.id,
            phone_number=phone_e164,
            country_code=country_code,
            message=body,
            message_count=charge["message_count"],
            status="queued",
            cost_price=charge["total_base_cost"],
            selling_price=charge["total_cost"],
            currency=charge["currency"],
            submit_time=datetime.now(),
        )
        db.add(sms)
        await db.flush()

        okq = QueueManager.queue_sms(message_id)
        if not okq:
            logger.error(f"挂机短信入队失败 {message_id}")
            return None

        call.hangup_sms_message_id = message_id
        await db.flush()
        return message_id

    return None
