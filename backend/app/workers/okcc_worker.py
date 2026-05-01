"""
OKCC 余额全量同步 — 由 Celery Beat 定时触发
"""
import asyncio
import os
from typing import Optional

from app.database import AsyncSessionLocal
from app.services.okcc_sync import sync_okcc_to_accounts
from app.utils.logger import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# OKCC 全量同步可能慢（网络拉取 + 大量账户）；本任务自身就有 soft_time_limit=3600，
# 这里的协程级超时取相同量级避免误杀。
_RUN_ASYNC_DEFAULT_TIMEOUT = float(os.getenv("WORKER_OKCC_RUN_ASYNC_TIMEOUT_SEC", "3300"))


def _run_async(coro, *, timeout: Optional[float] = None):
    """在 Celery 同步 worker 中执行异步协程，带协程级超时保护。"""
    eff_timeout = timeout if timeout is not None else _RUN_ASYNC_DEFAULT_TIMEOUT
    loop = asyncio.new_event_loop()
    try:
        if eff_timeout and eff_timeout > 0:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=eff_timeout))
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _sync_okcc_job():
    async with AsyncSessionLocal() as db:
        return await sync_okcc_to_accounts(db)


@celery_app.task(
    name="okcc_sync_balances_task",
    soft_time_limit=3600,
    time_limit=3660,
)
def okcc_sync_balances_task():
    """定时从两台 OKCC 拉取客户列表并更新本地语音账户余额与资费"""
    logger.info("开始定时 OKCC 余额全量同步")
    try:
        stats = _run_async(_sync_okcc_job())
        logger.info("OKCC 定时同步完成: synced=%s created=%s errors=%s", stats.get("synced"), stats.get("created"), stats.get("errors"))
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.exception("OKCC 定时同步失败: %s", e)
        return {"success": False, "error": str(e)}
