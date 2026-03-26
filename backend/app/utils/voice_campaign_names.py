"""外呼任务名称批量解析（话单列表/导出展示用）"""
from __future__ import annotations

from typing import Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.voice.campaign_models import VoiceOutboundCampaign


async def batch_outbound_campaign_names_for_account(
    db: AsyncSession, account_id: int, campaign_ids: Set[int]
) -> dict[int, str]:
    """客户侧：仅返回属于该业务账户的任务名称。"""
    if not campaign_ids:
        return {}
    r = await db.execute(
        select(VoiceOutboundCampaign.id, VoiceOutboundCampaign.name).where(
            VoiceOutboundCampaign.account_id == account_id,
            VoiceOutboundCampaign.id.in_(campaign_ids),
        )
    )
    return {cid: (nm or "") for cid, nm in r.all()}


async def batch_outbound_campaign_names_by_ids(
    db: AsyncSession, campaign_ids: Set[int]
) -> dict[int, str]:
    """管理端：按任务 ID 全局解析名称（不校验账户）。"""
    if not campaign_ids:
        return {}
    r = await db.execute(
        select(VoiceOutboundCampaign.id, VoiceOutboundCampaign.name).where(
            VoiceOutboundCampaign.id.in_(campaign_ids)
        )
    )
    return {cid: (nm or "") for cid, nm in r.all()}
