"""
DLR Redis 缓冲：两个场景使用：
1. 高频 deliver_sm 批量写入缓冲：将状态更新先写 Redis，flush 任务每 5s 批量写 DB
2. DLR 先于 SubmitSMResp 到达时的重试缓冲：upstream_message_id 尚未落库时暂存，
   flush 任务延迟重试，防止 DLR 永久丢失（当前系统直接 warn 丢弃）

key 设计：
  dlr_pending_retry:  Hash, field="{channel_id}:{upstream_id}", value=json
                      存放「未找到 sms_log」的 DLR，待重试
"""
import json
from datetime import datetime
from typing import List, Dict

from app.utils.cache import get_redis_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

_RETRY_KEY = "dlr_pending_retry"   # DLR 未匹配到 sms_log，等待重试
_RETRY_TTL = 3600                  # 最多重试 1 小时


async def buffer_unmatched_dlr(
    channel_id: int, upstream_id: str, new_status: str,
    stat: str, err: str, dest_addr: str, source_addr: str, receipted_message_id: str,
) -> bool:
    """
    将未找到 sms_log 的 DLR 写入 Redis 重试缓冲区。
    flush 任务会定期重试这些 DLR，处理「DLR 先于 SubmitSMResp 到达」的竞态场景。
    """
    if not upstream_id:
        return False
    try:
        redis = await get_redis_client()
        field = f"{channel_id}:{upstream_id}"
        payload = json.dumps({
            "channel_id": channel_id,
            "upstream_id": upstream_id,
            "new_status": new_status,
            "stat": stat,
            "err": err,
            "dest_addr": dest_addr,
            "source_addr": source_addr,
            "receipted_message_id": receipted_message_id,
            "first_seen": datetime.now().isoformat(),
            "retry_count": 0,
        }, ensure_ascii=False)
        # NX: 仅首次写入（避免覆盖已有重试计数）
        await redis.hsetnx(_RETRY_KEY, field, payload)
        await redis.expire(_RETRY_KEY, _RETRY_TTL)
        logger.info(f"DLR 重试缓冲: channel={channel_id}, upstream_id={upstream_id}, status={new_status}")
        return True
    except Exception as e:
        logger.warning(f"DLR 重试缓冲写入失败: {e}")
        return False


async def pop_retry_buffer(limit: int = 100) -> List[Dict]:
    """取出最多 limit 条待重试 DLR（不删除，由调用方按结果决定删除还是更新重试计数）"""
    try:
        redis = await get_redis_client()
        raw: dict = await redis.hgetall(_RETRY_KEY)
        if not raw:
            return []
        result = []
        for field, v in list(raw.items())[:limit]:
            try:
                item = json.loads(v.decode("utf-8") if isinstance(v, bytes) else v)
                item["_field"] = field.decode("utf-8") if isinstance(field, bytes) else field
                result.append(item)
            except Exception:
                pass
        return result
    except Exception as e:
        logger.warning(f"DLR 重试缓冲读取失败: {e}")
        return []


async def remove_retry_item(field: str):
    """处理成功后从缓冲区删除"""
    try:
        redis = await get_redis_client()
        await redis.hdel(_RETRY_KEY, field)
    except Exception as e:
        logger.warning(f"DLR 重试缓冲删除失败: {e}")


async def increment_retry_count(field: str, item: dict):
    """重试失败，增加计数；超过阈值则删除（放弃）"""
    try:
        redis = await get_redis_client()
        item["retry_count"] = item.get("retry_count", 0) + 1
        if item["retry_count"] >= 20:  # 最多重试 20 次（约 100s）
            await redis.hdel(_RETRY_KEY, field)
            logger.warning(
                f"DLR 重试放弃: channel={item.get('channel_id')}, "
                f"upstream_id={item.get('upstream_id')}, 已重试 {item['retry_count']} 次"
            )
            return
        await redis.hset(_RETRY_KEY, field, json.dumps(item, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"DLR 重试计数更新失败: {e}")


async def retry_buffer_size() -> int:
    """返回待重试 DLR 数量（监控用）"""
    try:
        redis = await get_redis_client()
        return await redis.hlen(_RETRY_KEY)
    except Exception:
        return -1
