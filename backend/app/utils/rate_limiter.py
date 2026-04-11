"""
按通道 Redis 滑动窗口限速器
使用 Redis 固定窗口计数器实现，每秒为一个窗口
"""
import time
import redis
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_sync_redis: redis.Redis = None


def _get_sync_redis() -> redis.Redis:
    """获取同步 Redis 客户端（worker 进程级单例）"""
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _sync_redis


# Lua 脚本：原子性检查+递增，返回 [当前计数, TTL剩余毫秒]
_RATE_CHECK_SCRIPT = """
local key = KEYS[1]
local max_tps = tonumber(ARGV[1])
local current = tonumber(redis.call('GET', key) or '0')
if current >= max_tps then
    local ttl_ms = redis.call('PTTL', key)
    if ttl_ms < 0 then ttl_ms = 1000 end
    return {current, ttl_ms}
end
local new_val = redis.call('INCR', key)
if new_val == 1 then
    redis.call('PEXPIRE', key, 1100)
end
return {new_val, 0}
"""

_lua_sha = None


def acquire_send_slot(channel_id: int, max_tps: int) -> tuple:
    """
    尝试获取发送槽位

    Returns:
        (allowed: bool, wait_ms: int)
        allowed=True 表示可以发送
        allowed=False 表示需等待 wait_ms 毫秒后重试
    """
    if max_tps <= 0:
        return True, 0

    global _lua_sha
    r = _get_sync_redis()
    current_second = int(time.time())
    key = f"rate:ch:{channel_id}:{current_second}"

    try:
        if _lua_sha is None:
            _lua_sha = r.script_load(_RATE_CHECK_SCRIPT)

        result = r.evalsha(_lua_sha, 1, key, max_tps)
        count, wait_ms = int(result[0]), int(result[1])

        if wait_ms > 0:
            return False, max(50, min(wait_ms, 1100))
        return True, 0

    except redis.exceptions.NoScriptError:
        _lua_sha = r.script_load(_RATE_CHECK_SCRIPT)
        return acquire_send_slot(channel_id, max_tps)
    except Exception as e:
        logger.warning(f"限速器异常（放行）: channel={channel_id}, {e}")
        return True, 0
