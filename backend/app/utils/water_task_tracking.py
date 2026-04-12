"""
注水 Celery 任务追踪：按客户账户记录待执行的 task_id，支持仅撤销某一账户的排队任务。

说明：RabbitMQ 无法按业务字段筛选清空队列；派发时把 task_id 写入 Redis，
撤销时对每个 id 调用 control.revoke，worker 取到消息后会跳过执行。
本功能上线后新派发的任务才会被追踪；历史已入队且未记录的任务无法用此方式撤销。
"""
from typing import Optional

import redis

from app.config import settings

_KEY = "water:pending_tasks:{account_id}"
_TTL_SECONDS = 86400 * 14  # 集合存活时间，每次写入会刷新

_redis: Optional[redis.Redis] = None


def _r() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _redis


def track_water_task(account_id: int, task_id: str) -> None:
    """派发任务成功后写入 Redis，供按账户撤销。"""
    if not account_id or not task_id:
        return
    key = _KEY.format(account_id=account_id)
    r = _r()
    r.sadd(key, task_id)
    r.expire(key, _TTL_SECONDS)


def untrack_water_task(account_id: int, task_id: str) -> None:
    """worker 开始执行时移除（已进入执行则不再参与 revoke 列表）。"""
    if not account_id or not task_id:
        return
    r = _r()
    r.srem(_KEY.format(account_id=account_id), task_id)


def count_tracked_pending(account_id: int) -> int:
    """当前 Redis 中记录的该账户待撤销任务数（近似：未开始执行的已派发任务）。"""
    if not account_id:
        return 0
    return int(_r().scard(_KEY.format(account_id=account_id)))


def revoke_tracked_tasks_for_account(account_id: int) -> int:
    """
    对该账户已记录的全部 task_id 执行 revoke，并清空 Redis 集合。
    返回 revoke 调用次数（与集合大小一致）。
    """
    if not account_id:
        return 0
    from app.workers.celery_app import celery_app

    r = _r()
    key = _KEY.format(account_id=account_id)
    members = list(r.smembers(key))
    for tid in members:
        celery_app.control.revoke(tid, terminate=False)
    if members:
        r.delete(key)
    return len(members)
