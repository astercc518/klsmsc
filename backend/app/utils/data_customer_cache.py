"""客户私库汇总相关 Redis 缓存失效（供 API 与异步上传任务共用）"""
from app.utils.cache import get_cache_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _my_numbers_count_cache_key(account_id: int) -> str:
    return f"data:my_numbers:count:{account_id}"


async def invalidate_my_numbers_summary_cache(account_id: int) -> None:
    """
    上传/删除后删除汇总缓存全部变体，避免返回过期卡片数据。
    """
    try:
        cm = await get_cache_manager()
        stale_key = f"data:my_numbers:stale:{account_id}"
        redis_client = await cm.redis
        await cm.delete_pattern(f"data:my_numbers:summary:{account_id}:*")
        await redis_client.delete(stale_key)
        await cm.delete(_my_numbers_count_cache_key(account_id))
    except Exception as e:
        # Worker 与 API 必须能连同一 Redis；静默失败会导致「上传已完成但私库页仍是旧缓存」
        logger.warning("私库汇总缓存失效失败 account_id=%s: %s", account_id, e, exc_info=True)
