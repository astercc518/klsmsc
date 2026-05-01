"""
DLR Redis 缓冲：两个场景使用：
1. 高频 deliver_sm 批量写入缓冲：将状态更新先写 Redis，flush 任务每 5s 批量写 DB
2. DLR 先于 SubmitSMResp 到达时的重试缓冲：upstream_message_id 尚未落库时暂存，
   flush 任务延迟重试，防止 DLR 永久丢失（当前系统直接 warn 丢弃）

key 设计（per-field TTL，避免整 hash key TTL 到期清空全部积压）：
  dlr_pending_retry         Hash, field="{channel_id}:{upstream_id}", value=json
                             正常存放数据；不再在 Hash 自身上设 EXPIRE。
  dlr_pending_retry:expire  ZSet, member="{channel_id}:{upstream_id}",
                             score=过期 unix 时间戳；扫描后清掉过期项。

历史问题：早期实现给整个 Hash 设 1 小时 TTL，期间一旦 worker hang，
新 DLR 不进来 → 整 key 过期 → 已积压上万条 DLR 全部丢失。
新实现：每条 DLR 各自的 expire-at 写入 ZSet，flush 时主动按 score 清理过期项；
worker 卡死也只丢真正超时的旧条目，未过期的随时可被 flush 接力恢复。
"""
import json
from datetime import datetime
from typing import List, Dict

from app.utils.cache import get_redis_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

_RETRY_KEY = "dlr_pending_retry"            # DLR 未匹配到 sms_log，等待重试
_RETRY_EXPIRE_ZSET = "dlr_pending_retry:expire"  # 每条记录的 expire-at（unix ts）
_RETRY_TTL = 3600                           # 单条 DLR 最多重试 1 小时


def _now_ts() -> float:
    return datetime.now().timestamp()


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
        added = await redis.hsetnx(_RETRY_KEY, field, payload)
        if added:
            # 仅首次入缓冲时写入 expire-at；ZADD NX 避免覆盖 retry 时的旧值
            await redis.zadd(_RETRY_EXPIRE_ZSET, {field: _now_ts() + _RETRY_TTL}, nx=True)
        logger.info(f"DLR 重试缓冲: channel={channel_id}, upstream_id={upstream_id}, status={new_status}")
        return True
    except Exception as e:
        logger.warning(f"DLR 重试缓冲写入失败: {e}")
        return False


async def pop_retry_buffer(limit: int = 100) -> List[Dict]:
    """取出最多 limit 条待重试 DLR（不删除，由调用方按结果决定删除还是更新重试计数）"""
    try:
        redis = await get_redis_client()
        # 优先取最早 expire 的 N 条；若 ZSet 为空（兼容旧数据）回退扫 hash
        fields_b = await redis.zrange(_RETRY_EXPIRE_ZSET, 0, limit - 1)
        if fields_b:
            fields = [f.decode("utf-8") if isinstance(f, bytes) else f for f in fields_b]
            raws = await redis.hmget(_RETRY_KEY, fields)
            result = []
            for fld, v in zip(fields, raws):
                if v is None:
                    # ZSet 残留但 Hash 已被清掉，顺手清 ZSet
                    await redis.zrem(_RETRY_EXPIRE_ZSET, fld)
                    continue
                try:
                    item = json.loads(v.decode("utf-8") if isinstance(v, bytes) else v)
                    item["_field"] = fld
                    result.append(item)
                except Exception:
                    pass
            return result

        # 兼容回退：旧版本只用 Hash，没有 ZSet 索引
        raw: dict = await redis.hgetall(_RETRY_KEY)
        if not raw:
            return []
        result = []
        for field, v in list(raw.items())[:limit]:
            try:
                item = json.loads(v.decode("utf-8") if isinstance(v, bytes) else v)
                item["_field"] = field.decode("utf-8") if isinstance(field, bytes) else field
                # 顺手补齐 ZSet（默认从现在起 _RETRY_TTL）
                await redis.zadd(_RETRY_EXPIRE_ZSET, {item["_field"]: _now_ts() + _RETRY_TTL}, nx=True)
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
        await redis.zrem(_RETRY_EXPIRE_ZSET, field)
    except Exception as e:
        logger.warning(f"DLR 重试缓冲删除失败: {e}")


async def increment_retry_count(field: str, item: dict):
    """重试失败，增加计数；超过阈值则删除（放弃）"""
    try:
        redis = await get_redis_client()
        item["retry_count"] = item.get("retry_count", 0) + 1
        if item["retry_count"] >= 20:  # 最多重试 20 次（约 100s）
            await redis.hdel(_RETRY_KEY, field)
            await redis.zrem(_RETRY_EXPIRE_ZSET, field)
            logger.warning(
                f"DLR 重试放弃: channel={item.get('channel_id')}, "
                f"upstream_id={item.get('upstream_id')}, 已重试 {item['retry_count']} 次"
            )
            return
        await redis.hset(_RETRY_KEY, field, json.dumps(item, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"DLR 重试计数更新失败: {e}")


async def cleanup_expired() -> int:
    """清理 expire-at 已过期的条目，返回清理数量；建议在 flush 任务中调用一次。"""
    try:
        redis = await get_redis_client()
        now = _now_ts()
        # 取出所有过期 field（一次最多 500 条，避免长尾阻塞）
        expired_b = await redis.zrangebyscore(_RETRY_EXPIRE_ZSET, "-inf", now, start=0, num=500)
        if not expired_b:
            return 0
        expired = [f.decode("utf-8") if isinstance(f, bytes) else f for f in expired_b]
        # pipeline 删除
        pipe = redis.pipeline()
        if expired:
            pipe.hdel(_RETRY_KEY, *expired)
            pipe.zrem(_RETRY_EXPIRE_ZSET, *expired)
        await pipe.execute()
        logger.warning(f"DLR 重试缓冲: 清理过期条目 {len(expired)} 条（超过 {_RETRY_TTL}s 未匹配，放弃）")
        return len(expired)
    except Exception as e:
        logger.warning(f"DLR 重试缓冲过期清理失败: {e}")
        return 0


async def retry_buffer_size() -> int:
    """返回待重试 DLR 数量（监控用）"""
    try:
        redis = await get_redis_client()
        return await redis.hlen(_RETRY_KEY)
    except Exception:
        return -1
