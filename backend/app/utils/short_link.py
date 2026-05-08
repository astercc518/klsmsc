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
_REDIS_TTL = 90 * 86400         # 90 天


def _gen_token(length: int = 7) -> str:
    return "".join(secrets.choice(_BASE62) for _ in range(length))


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
        if "|" in embedded:
            t, b = embedded.split("|", 1)
            target_url = (t.strip() or default_url)
            base_url = (b.strip() or default_base_url)
        else:
            target_url = embedded
    if not target_url:
        return None
    return target_url, (base_url or default_base_url)


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


async def generate_short_link(
    db: AsyncSession,
    sms_log_id: int,
    original_url: str,
    base_url: str,
    *,
    max_retries: int = 5,
) -> Tuple[str, str]:
    """
    为指定 sms_log_id 生成唯一短链。

    碰撞处理：使用 INSERT IGNORE（而非 ORM flush+rollback），不会意外回滚
    同一会话里其他待提交字段（如 sms_log.channel_id）。

    Returns:
        (token, short_url)
    """
    from app.modules.sms.short_link_log import ShortLinkLog

    # 幂等：同一条 sms_log 已有 token 时直接复用（Redis 优先）
    cached_token = await _redis_get(f"{_REDIS_SMSLOG_PREFIX}{sms_log_id}")
    if cached_token:
        return cached_token, f"{base_url.rstrip('/')}/{cached_token}"

    # worker 重试时 Redis 可能已过期，回库确认
    existing = (
        await db.execute(
            select(ShortLinkLog.token).where(ShortLinkLog.sms_log_id == sms_log_id)
        )
    ).scalar_one_or_none()
    if existing:
        await _redis_set(f"{_REDIS_SMSLOG_PREFIX}{sms_log_id}", existing)
        await _redis_set(f"{_REDIS_TOKEN_PREFIX}{existing}", original_url)
        return existing, f"{base_url.rstrip('/')}/{existing}"

    # 生成前先查一次 domain_id（每条 sms_log 一次反查 + Redis 缓存）
    domain_id = await _resolve_domain_id_by_base_url(db, base_url)

    # 生成新 token；使用 INSERT IGNORE 避免碰撞时回滚整个会话
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
            {
                "token": token,
                "sms_log_id": sms_log_id,
                "domain_id": domain_id,
                "original_url": original_url,
            },
        )
        if result.rowcount == 0:
            # DB UNIQUE 碰撞（Redis 可能误判），释放 Redis 占位并重试
            await r.delete(redis_key)
            logger.debug(f"short_link DB INSERT IGNORE collision: token={token} attempt={attempt}")
            continue

        # 成功写入 DB（INSERT IGNORE rowcount=1）；缓存 sms_log_id → token 映射
        await _redis_set(f"{_REDIS_SMSLOG_PREFIX}{sms_log_id}", token)
        short_url = f"{base_url.rstrip('/')}/{token}"
        logger.info(f"short_link generated: token={token} sms_log_id={sms_log_id}")
        return token, short_url

    raise RuntimeError(f"Failed to generate unique short_link token after {max_retries} attempts")


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

    _, short_url = await generate_short_link(db, sms_log_id, target_url, effective_base)
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
