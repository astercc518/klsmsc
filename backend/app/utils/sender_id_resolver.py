"""发送方ID(SID)选择与白名单校验。

数据源：channel_country_sender_ids（通道-国家-SID，含 status/is_default）。
业务：客户网页发送可从"该通道+目的国家已审批(active)"的 SID 中自选一个；
未指定则用该国家默认SID；无国家级配置则留空，由 worker 回退 channel.default_sender_id。
"""
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sms.channel_relations import ChannelCountrySenderId
from app.utils.country_code import get_country_variants


async def list_active_sender_ids(
    db: AsyncSession, channel_id: int, country_code: str
) -> List[dict]:
    """返回该通道+国家下 active 的 SID 列表（默认SID优先、再按字母序），供前端下拉。

    country_code 可能是 ISO2(发送侧,如 BR) 或区号(routing/SID存储侧,如 55)，两表格式不一，
    故用 get_country_variants 取等价写法做 IN 匹配，跨格式命中。
    """
    if not channel_id or not country_code:
        return []
    variants = get_country_variants(country_code) or [country_code]
    rows = (
        await db.execute(
            select(
                ChannelCountrySenderId.sender_id,
                ChannelCountrySenderId.sid_type,
                ChannelCountrySenderId.is_default,
            )
            .where(
                ChannelCountrySenderId.channel_id == channel_id,
                ChannelCountrySenderId.country_code.in_(variants),
                ChannelCountrySenderId.status == "active",
            )
            .order_by(
                ChannelCountrySenderId.is_default.desc(),
                ChannelCountrySenderId.sender_id.asc(),
            )
        )
    ).all()
    return [
        {"sender_id": r[0], "sid_type": r[1], "is_default": bool(r[2])}
        for r in rows
    ]


async def resolve_sender_id(
    db: AsyncSession, channel_id: int, country_code: str, requested: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """解析本次发送实际使用的 SID。

    Returns: (sid, error)
    - error 非空：requested 不在白名单（该通道+国家 active 的 SID），调用方应拒绝发送
    - requested 非空且合法：返回该 SID
    - requested 为空：返回该国家 is_default 的 active SID；若无国家级配置返回 (None, None)，
      由调用方落库 None、worker 回退 channel.default_sender_id
    """
    req = (requested or "").strip()
    active = await list_active_sender_ids(db, channel_id, country_code)
    if req:
        if any(a["sender_id"] == req for a in active):
            return req, None
        avail = "、".join(a["sender_id"] for a in active) or "（该国家未配置SID）"
        return None, f"发送者ID「{req}」不在该通道 {country_code} 的可用SID中。可用：{avail}"
    for a in active:
        if a["is_default"]:
            return a["sender_id"], None
    return None, None
