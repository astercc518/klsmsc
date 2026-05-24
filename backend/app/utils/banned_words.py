"""
违禁词检测

数据来源（按优先级合并，命中任一即拦截）：
  1. SystemConfig.global_banned_words —— admin 在 /admin/system/config 维护的全局词表
  2. Channel.banned_words            —— 通道级（命中即拦本通道全部国家）
  3. RoutingRule.banned_words        —— 通道 × 国家级（命中只拦该国家）

调用方在内容校验阶段（已知 channel_id + country_code）触发；命中第一个词即返回。

Redis 缓存 60s，避免每条短信都查 DB 三次。Cache miss 不致命：抢热不上时按 miss 路径走一次。
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.common.system_config import SystemConfig
from app.modules.sms.channel import Channel
from app.modules.sms.routing_rule import RoutingRule
from app.utils.logger import get_logger

logger = get_logger(__name__)

_CACHE_TTL = 60  # 秒。词表更新 1 分钟内全网生效
_SPLIT_RE = re.compile(r"[,\n\r、，；;|]+")
_REDIS_KEY_GLOBAL = b"bw:global"
_REDIS_KEY_CHANNEL = "bw:channel:{cid}"
_REDIS_KEY_ROUTING = "bw:routing:{cid}:{cc}"


def _split_words(raw: Optional[str]) -> List[str]:
    """逗号/换行/中文标点 多分隔符容错 → 去空 → 去重保序"""
    if not raw:
        return []
    seen: Set[str] = set()
    out: List[str] = []
    for w in _SPLIT_RE.split(raw):
        w = w.strip()
        if not w or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


async def _redis_get_str(key: bytes) -> Optional[str]:
    try:
        from app.utils.cache import get_redis_client
        r = await get_redis_client()
        val = await r.get(key)
        return val.decode() if val else None
    except Exception:
        return None


async def _redis_set_str(key: bytes, value: str, ttl: int = _CACHE_TTL) -> None:
    try:
        from app.utils.cache import get_redis_client
        r = await get_redis_client()
        await r.setex(key, ttl, value.encode())
    except Exception:
        pass


async def _load_global_words(db: AsyncSession) -> List[str]:
    cached = await _redis_get_str(_REDIS_KEY_GLOBAL)
    if cached is not None:
        return _split_words(cached)
    raw = (
        await db.execute(
            select(SystemConfig.config_value).where(SystemConfig.config_key == "global_banned_words")
        )
    ).scalar_one_or_none() or ""
    await _redis_set_str(_REDIS_KEY_GLOBAL, raw)
    return _split_words(raw)


async def _load_channel_words(db: AsyncSession, channel_id: int) -> List[str]:
    key = _REDIS_KEY_CHANNEL.format(cid=int(channel_id)).encode()
    cached = await _redis_get_str(key)
    if cached is not None:
        return _split_words(cached)
    raw = (
        await db.execute(
            select(Channel.banned_words).where(Channel.id == int(channel_id))
        )
    ).scalar_one_or_none() or ""
    await _redis_set_str(key, raw)
    return _split_words(raw)


async def _load_routing_words(db: AsyncSession, channel_id: int, country_code: str) -> List[str]:
    cc = (country_code or "").strip().upper()
    if not cc:
        return []
    key = _REDIS_KEY_ROUTING.format(cid=int(channel_id), cc=cc).encode()
    cached = await _redis_get_str(key)
    if cached is not None:
        return _split_words(cached)
    raw = (
        await db.execute(
            select(RoutingRule.banned_words).where(
                RoutingRule.channel_id == int(channel_id),
                RoutingRule.country_code == cc,
            )
        )
    ).scalar_one_or_none() or ""
    await _redis_set_str(key, raw)
    return _split_words(raw)


async def check_banned_words(
    db: AsyncSession,
    content: str,
    channel_id: Optional[int] = None,
    country_code: Optional[str] = None,
) -> Optional[str]:
    """
    在 content 中检查是否含违禁词，命中返回首个匹配词；否则 None。

    channel_id / country_code 缺失时跳过对应词表（如发送前路由还没决定通道）。
    全局词表始终检查。
    """
    if not content:
        return None

    words: List[str] = []
    words.extend(await _load_global_words(db))
    if channel_id is not None:
        try:
            words.extend(await _load_channel_words(db, int(channel_id)))
        except (TypeError, ValueError):
            pass
        if country_code:
            try:
                words.extend(await _load_routing_words(db, int(channel_id), country_code))
            except (TypeError, ValueError):
                pass

    if not words:
        return None

    # 大小写不敏感匹配；词典里如果包含混合大小写需求，admin 可写多版本
    lower_content = content.lower()
    for w in words:
        if w and w.lower() in lower_content:
            return w
    return None


async def invalidate_banned_words_cache(
    *,
    global_words: bool = False,
    channel_ids: Optional[Iterable[int]] = None,
    routing_keys: Optional[Iterable[tuple]] = None,  # [(channel_id, country_code), ...]
) -> None:
    """配置/通道/路由规则变更后调用，清掉 Redis 缓存。"""
    try:
        from app.utils.cache import get_redis_client
        r = await get_redis_client()
        keys: List[bytes] = []
        if global_words:
            keys.append(_REDIS_KEY_GLOBAL)
        if channel_ids:
            for cid in channel_ids:
                keys.append(_REDIS_KEY_CHANNEL.format(cid=int(cid)).encode())
        if routing_keys:
            for cid, cc in routing_keys:
                keys.append(_REDIS_KEY_ROUTING.format(cid=int(cid), cc=(cc or "").upper()).encode())
        if keys:
            await r.delete(*keys)
    except Exception as e:
        logger.warning(f"banned_words 缓存失效失败（不影响功能，TTL 后自然过期）: {e}")
