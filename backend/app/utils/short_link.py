"""
短链服务

设计要点：
- token 用 secrets.choice 从 Base62 字母表采样，7 位 ≈ 3.5 万亿种组合，碰撞概率极低。
- Redis 充当 L1 缓存：重定向时直接命中，无须回库；TTL = 90 天。
- 点击计数使用 MySQL 原子 UPDATE（click_count = click_count + 1），无 SELECT-then-UPDATE，
  不持跨行锁，高并发下不会产生死锁。
- 占位符格式：{{TRACK_URL=https://target.com}}；若省略 URL 则退化到
  settings.SHORT_LINK_DEFAULT_TARGET_URL。
"""
import json
import re
import secrets
import string
from typing import Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logger import get_logger

logger = get_logger(__name__)

_BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase
# 匹配三种形式：
#   {{TRACK_URL}}
#   {{TRACK_URL=https://target}}
#   {{TRACK_URL=https://target|https://go.kaolach.com/s}}
# 第一段 = target；第二段（可选）= 短链对外前缀
_PLACEHOLDER_RE = re.compile(r"\{\{TRACK_URL(?:=([^}]*))?\}\}")

# Redis 键前缀
_REDIS_TOKEN_PREFIX = "sl:t:"   # sl:t:{token} -> original_url
_REDIS_SMSLOG_PREFIX = "sl:s:"  # sl:s:{sms_log_id} -> token
_REDIS_SHARE_PREFIX = "sl:share:"  # sl:share:{group} -> token（一文案一链：同组共用同一 token）
_REDIS_TTL = 90 * 86400         # 90 天

# 一文案一链分组标记：占位符可带 |g=UID，同 UID 的所有消息共用一个短链
_GROUP_RE = re.compile(r"\|g=([^|}]+)")

# ── 短链域故障转移 (2026-07-06 起) ──────────────────────────────────────────
# 短链域可能被注册商暂停/封禁导致整域失效（如 66c.eu 事故：DNS 整域消失，系统仍闷头
# 往死域灌了一整天打不开的链）。为止损：发送建链时若消息内嵌的短链域在
# short_link_domains 里已被 disable（人工或健康巡检 shortlink_health_worker 自动摘除），
# 自动改写到当前 sort_order 最高的 active 域。
# 只改写「库里已知且被停用」的域；健康 active 域、以及库外未登记的域（如默认
# www.kaolach.com/s）一律原样放行，绝不误改。所有发送路径都汇入
# replace_track_url_in_message，故在该函数取到 effective_base 后统一过一次本函数。
_ACTIVE_MAP_KEY = "sl:domainmap"      # {"active":[host..],"disabled":[host..],"best_base":"..."}
_ACTIVE_MAP_TTL_LAZY = 120            # 发送热路径冷启动兜底缓存(秒)
_ACTIVE_MAP_TTL_PROBE = 900           # 健康巡检刷新时的 TTL(> 巡检周期，避免过期空窗)


async def rebuild_active_domain_map(db: AsyncSession, ttl: int = _ACTIVE_MAP_TTL_PROBE) -> dict:
    """查 short_link_domains 生成 {active,disabled,best_base} 并写 Redis。
    健康巡检状态变更后应调用以立即刷新发送侧的故障转移视图。"""
    from app.modules.sms.short_link_domain import ShortLinkDomain
    rows = (await db.execute(
        select(ShortLinkDomain).order_by(
            ShortLinkDomain.sort_order.desc(), ShortLinkDomain.id.desc()
        )
    )).scalars().all()
    active, disabled, best_base = [], [], None
    for d in rows:
        host = (d.domain or "").strip().lower()
        if not host:
            continue
        if d.status == "active":
            active.append(host)
            if best_base is None:
                best_base = d.base_url()   # 最高 sort_order 的 active 域作为兜底
        else:
            disabled.append(host)
    data = {"active": active, "disabled": disabled, "best_base": best_base}
    await _redis_set(_ACTIVE_MAP_KEY, json.dumps(data), ttl=ttl)
    return data


async def _get_active_domain_map(db: AsyncSession) -> dict:
    cached = await _redis_get(_ACTIVE_MAP_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    try:
        return await rebuild_active_domain_map(db, ttl=_ACTIVE_MAP_TTL_LAZY)
    except Exception as e:
        logger.warning(f"short_link: 读取活跃短链域映射失败，故障转移本次跳过: {e}")
        return {"active": [], "disabled": [], "best_base": None}


async def resolve_effective_base(db: AsyncSession, base_url: str) -> str:
    """若 base_url 指向的短链域在库中已被停用，改写到当前最优 active 域；否则原样返回。"""
    if not base_url:
        return base_url
    raw_host = base_url.split("://", 1)[-1].split("/", 1)[0].lower()
    m = await _get_active_domain_map(db)
    disabled = m.get("disabled") or []
    best_base = m.get("best_base")
    if raw_host in disabled and best_base and best_base.split("://", 1)[-1].split("/", 1)[0].lower() != raw_host:
        logger.warning(f"short_link 故障转移: 短链域 {raw_host} 已停用 → 改用 {best_base}")
        return best_base
    return base_url


# 默认 token 长度从 7 升到 8 位（Base62 8 位 ≈ 218 万亿组合，约 47 bits，
# 与 Twitter t.co 同量级；7 位仅 3.5 万亿 ≈ 41 bits，慢速扫库可枚举）。
# 历史 7 位 token 仍可正常访问（DB 已存）。
def _gen_token(length: int = 8) -> str:
    return "".join(secrets.choice(_BASE62) for _ in range(length))


def _normalize_target_url(url: Optional[str]) -> str:
    """
    规范化客户填写的「原始链接」。
    - 去前后空白
    - 不带 scheme 时补 https://（避免重定向时 Location 被浏览器当相对路径）
    - 拦 javascript: / data: / file: 等危险协议（短信扫描器渲染时会被执行）
    - 拦私网/回环/链路本地/云元数据地址（防钓鱼扫库 + 内网穿透）
    返回空串视作无效（调用方应抛错让前端展示）。
    """
    u = (url or "").strip()
    if not u:
        return ""
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    # 调入安全校验；非法则返回空串触发上层错误
    try:
        from app.utils.url_safety import validate_redirect_target_url
        ok, reason = validate_redirect_target_url(u)
        if not ok:
            logger.warning(f"short_link target URL 被安全策略拒绝: {u!r} reason={reason}")
            return ""
    except Exception as e:
        # 校验本身失败（如 DNS 不可达）：保守不放行，避免开后门
        logger.warning(f"short_link target URL 校验异常: {u!r} err={e}")
        return ""
    return u


def has_track_url_placeholder(message: Optional[str]) -> bool:
    return bool(message) and bool(_PLACEHOLDER_RE.search(message))


def extract_placeholder_parts(message: str, default_url: str, default_base_url: str
                              ) -> Optional[tuple]:
    """
    从消息占位符提取 (target_url, base_url)。
    缺省时分别用 default_url / default_base_url 兜底。
    """
    m = _PLACEHOLDER_RE.search(message)
    if not m:
        return None
    embedded = (m.group(1) or "").strip()
    target_url = default_url
    base_url = default_base_url
    if embedded:
        # 过滤掉分组标记 g=xxx（一文案一链用），只保留 target|base 段
        plain = [s.strip() for s in embedded.split("|") if not s.strip().startswith("g=")]
        if len(plain) >= 1 and plain[0]:
            target_url = plain[0]
        if len(plain) >= 2 and plain[1]:
            base_url = plain[1]
    if not target_url:
        return None
    return target_url, (base_url or default_base_url)


def extract_track_group(message: str) -> Optional[str]:
    """从 {{TRACK_URL=...|g=UID}} 提取分组标记（一文案一链）；无则 None。"""
    m = _PLACEHOLDER_RE.search(message or "")
    if not m:
        return None
    gm = _GROUP_RE.search(m.group(1) or "")
    return gm.group(1).strip() if gm else None


# 旧调用兼容
def extract_original_url(message: str, default_url: str) -> Optional[str]:
    parts = extract_placeholder_parts(message, default_url, "")
    return parts[0] if parts else None


async def _get_redis():
    from app.utils.cache import get_redis_client
    return await get_redis_client()


async def _redis_get(key: str) -> Optional[str]:
    try:
        r = await _get_redis()
        val = await r.get(key.encode())
        return val.decode() if val else None
    except Exception as e:
        logger.debug(f"Redis get failed ({key}): {e}")
        return None


async def _redis_set(key: str, value: str, ttl: int = _REDIS_TTL) -> None:
    try:
        r = await _get_redis()
        await r.setex(key.encode(), ttl, value.encode())
    except Exception as e:
        logger.debug(f"Redis set failed ({key}): {e}")


async def get_original_url_by_token(token: str, db: AsyncSession) -> Optional[str]:
    """查找 token 对应的原始 URL（Redis 优先，miss 时回库）。"""
    cached = await _redis_get(f"{_REDIS_TOKEN_PREFIX}{token}")
    if cached:
        return cached

    from app.modules.sms.short_link_log import ShortLinkLog
    row = (
        await db.execute(
            select(ShortLinkLog.original_url).where(ShortLinkLog.token == token)
        )
    ).scalar_one_or_none()

    if row:
        await _redis_set(f"{_REDIS_TOKEN_PREFIX}{token}", row)
    return row


_DOMAIN_LOOKUP_TTL = 600   # base_url -> domain_id 缓存 10 分钟


async def _resolve_domain_id_by_base_url(db: AsyncSession, base_url: str) -> Optional[int]:
    """
    将 base_url（如 https://go.kaolach.com/s）映射回 short_link_domains.id。
    Redis 缓存 10 分钟，miss 时回库匹配 domain + base_path。
    """
    if not base_url:
        return None
    cache_key = f"sl:domid:{base_url}"
    cached = await _redis_get(cache_key)
    if cached:
        try:
            return int(cached)
        except ValueError:
            pass

    # 解析 base_url 拆出 domain + base_path
    # 支持四种形态:
    #   https://klsms.com/s   (传统)   ->  host=klsms.com path=/s
    #   https://klsms.com     ()        ->  host=klsms.com path=""
    #   klsms.com/s           (无scheme)->  host=klsms.com path=/s
    #   klsms.com             (最短)    ->  host=klsms.com path=""
    try:
        from urllib.parse import urlparse
        # 无 scheme 时补一个 placeholder 让 urlparse 正确抓 host
        if "://" not in base_url:
            parsed = urlparse(f"//{base_url}", scheme="https")
        else:
            parsed = urlparse(base_url)
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").rstrip("/")
    except Exception:
        return None
    if not host:
        return None

    from app.modules.sms.short_link_domain import ShortLinkDomain

    row = (
        await db.execute(
            select(ShortLinkDomain.id, ShortLinkDomain.base_path)
            .where(ShortLinkDomain.domain == host)
            .limit(1)
        )
    ).first()
    if not row:
        return None
    db_path = (row.base_path or "/s").rstrip("/") or "/s"
    if not db_path.startswith("/"):
        db_path = "/" + db_path
    if db_path != path:
        # 域名虽配置了，但 base_path 与请求不一致；不强制匹配，仍按域名归属统计
        pass

    await _redis_set(cache_key, str(row.id), ttl=_DOMAIN_LOOKUP_TTL)
    return int(row.id)


async def _mint_token(
    db: AsyncSession,
    sms_log_id: int,
    original_url: str,
    domain_id,
    max_retries: int = 5,
) -> str:
    """铸造一个全新唯一 token 并写入 short_link_logs（纯生成，不做幂等复用）。"""
    for attempt in range(max_retries):
        token = _gen_token()
        # Redis SETNX：抢占 token，防两个 worker 并发生成同一 token 后同时尝试 DB 写入
        r = await _get_redis()
        redis_key = f"{_REDIS_TOKEN_PREFIX}{token}".encode()
        acquired = await r.set(redis_key, original_url.encode(), ex=_REDIS_TTL, nx=True)
        if not acquired:
            logger.debug(f"short_link Redis SETNX miss (collision): token={token} attempt={attempt}")
            continue
        # INSERT IGNORE：若 token UNIQUE 冲突则 rowcount=0，无异常，无回滚，安全重试
        result = await db.execute(
            text(
                "INSERT IGNORE INTO short_link_logs (token, sms_log_id, domain_id, original_url)"
                " VALUES (:token, :sms_log_id, :domain_id, :original_url)"
            ),
            {"token": token, "sms_log_id": sms_log_id, "domain_id": domain_id, "original_url": original_url},
        )
        if result.rowcount == 0:
            await r.delete(redis_key)
            logger.debug(f"short_link DB INSERT IGNORE collision: token={token} attempt={attempt}")
            continue
        return token
    raise RuntimeError(f"Failed to generate unique short_link token after {max_retries} attempts")


async def generate_short_link(
    db: AsyncSession,
    sms_log_id: int,
    original_url: str,
    base_url: str,
    *,
    max_retries: int = 5,
    share_key: Optional[str] = None,
) -> Tuple[str, str]:
    """
    生成短链。默认「一号码一链」（按 sms_log_id 幂等）；
    传 share_key 时走「一文案一链」：同 share_key 的所有消息共用同一 token（点击按该组聚合）。

    Returns:
        (token, short_url)
    """
    from app.modules.sms.short_link_log import ShortLinkLog

    base_pref = base_url.rstrip('/')

    # ===== 一文案一链：按 share_key 复用同一 token =====
    if share_key:
        skey = f"{_REDIS_SHARE_PREFIX}{share_key}"
        cached = await _redis_get(skey)
        if cached:
            return cached, f"{base_pref}/{cached}"
        domain_id = await _resolve_domain_id_by_base_url(db, base_url)
        token = await _mint_token(db, sms_log_id, original_url, domain_id, max_retries)
        # 抢占分组槽位：赢家的 token 成为该组共用短链；输家丢弃自己刚铸的 token（成孤儿行，无害）
        r = await _get_redis()
        claimed = await r.set(skey.encode(), token.encode(), ex=_REDIS_TTL, nx=True)
        if claimed:
            logger.info(f"short_link generated (shared): token={token} group={share_key}")
            return token, f"{base_pref}/{token}"
        winner = await _redis_get(skey)
        if winner:
            return winner, f"{base_pref}/{winner}"
        return token, f"{base_pref}/{token}"

    # ===== 一号码一链（原逻辑，按 sms_log_id 幂等）=====
    cached_token = await _redis_get(f"{_REDIS_SMSLOG_PREFIX}{sms_log_id}")
    if cached_token:
        return cached_token, f"{base_pref}/{cached_token}"

    # worker 重试时 Redis 可能已过期，回库确认
    existing = (
        await db.execute(
            select(ShortLinkLog.token).where(ShortLinkLog.sms_log_id == sms_log_id)
        )
    ).scalar_one_or_none()
    if existing:
        await _redis_set(f"{_REDIS_SMSLOG_PREFIX}{sms_log_id}", existing)
        await _redis_set(f"{_REDIS_TOKEN_PREFIX}{existing}", original_url)
        return existing, f"{base_pref}/{existing}"

    domain_id = await _resolve_domain_id_by_base_url(db, base_url)
    token = await _mint_token(db, sms_log_id, original_url, domain_id, max_retries)
    await _redis_set(f"{_REDIS_SMSLOG_PREFIX}{sms_log_id}", token)
    logger.info(f"short_link generated: token={token} sms_log_id={sms_log_id}")
    return token, f"{base_pref}/{token}"


async def replace_track_urls_bulk(
    db: AsyncSession,
    items,                               # List[Tuple[int, str]]: [(sms_log_id, message)]
    base_url: str,
    default_target_url: str,
    update_sms_logs_message: bool = True,
):
    """
    批量替换 SMS 文案里的 {{TRACK_URL=...}} 占位符。

    任一条目失败仅 warn，不中断循环；不内部 commit，由调用方决定 commit 时机。

    Args:
        items: 形如 [(sms_log_id, message), ...]
        base_url, default_target_url: 占位符内未指定时的 fallback
        update_sms_logs_message: True 时同步 UPDATE sms_logs.message，便于审计/重发一致

    Returns:
        Dict[sms_log_id, new_message]，仅包含**实际替换过**的 id（含占位符且生成成功）。
        无占位符的不在返回里，调用方需用 .get() 回退到原值。
    """
    out = {}
    if not items:
        return out
    from sqlalchemy import update as _u
    from app.modules.sms.sms_log import SMSLog
    for sms_log_id, message in items:
        if not has_track_url_placeholder(message or ""):
            continue
        try:
            new_msg = await replace_track_url_in_message(
                db, int(sms_log_id), message, base_url, default_target_url,
            )
            out[int(sms_log_id)] = new_msg
            if update_sms_logs_message:
                await db.execute(
                    _u(SMSLog).where(SMSLog.id == int(sms_log_id)).values(message=new_msg)
                )
        except Exception as e:
            logger.warning(f"replace_track_urls_bulk: id={sms_log_id} 失败: {e}")
    return out


async def replace_track_url_in_message(
    db: AsyncSession,
    sms_log_id: int,
    message: str,
    base_url: str,
    default_target_url: str,
) -> str:
    """
    将消息中的 {{TRACK_URL=...}} 或 {{TRACK_URL=target|base}} 替换为唯一短链 URL。
    持久化 short_link_logs 记录（调用方负责最终 commit）。

    Args:
        base_url: 占位符未内嵌 base 段时的兜底前缀（settings.SHORT_LINK_BASE_URL）。
    """
    parts = extract_placeholder_parts(message, default_target_url, base_url)
    if not parts:
        logger.warning(f"short_link: no target URL for sms_log_id={sms_log_id}, skipping replacement")
        return message
    target_url, effective_base = parts
    # 故障转移：若内嵌短链域已被停用(人工/健康巡检)，自动改写到最优 active 域
    effective_base = await resolve_effective_base(db, effective_base)
    # 客户在「短链转换」表单里可能漏写 https://，统一补全后再入库；
    # 否则重定向时浏览器会把 "hi805.com" 当作相对路径，跳到当前短链域名下报 404
    target_url = _normalize_target_url(target_url)
    if not target_url:
        logger.warning(f"short_link: empty target URL for sms_log_id={sms_log_id}, skipping replacement")
        return message

    # 一文案一链：占位符带 |g=UID 时，同组共用一个短链（利于报备）
    group = extract_track_group(message)
    _, short_url = await generate_short_link(
        db, sms_log_id, target_url, effective_base, share_key=group
    )
    return _PLACEHOLDER_RE.sub(short_url, message)


# ---------------------------------------------------------------------------
# Celery 点击计数任务（在此处定义以复用 worker 现有引擎模式）
# ---------------------------------------------------------------------------

def record_link_click(token: str, client_ip: str, user_agent: str) -> None:
    """
    异步（Celery）记录点击事件，使用原子 UPDATE 避免高并发死锁。
    caller: short_link 重定向端点（fire-and-forget）。
    """
    from app.workers.celery_app import celery_app
    celery_app.send_task(
        "record_link_click_task",
        args=[token, client_ip, user_agent],
        queue="webhook_tasks",  # 复用已存在的低优先级队列
    )
