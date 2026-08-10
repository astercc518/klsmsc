"""
节点(nodesms) RCS 群发任务的轮询与结果回写

节点没有回执推送，只能轮询：beat 定时拉起 poll_rcs_node_tasks_task，
对在途任务调 getTask，落终态后 getFile 下载结果文件并回写 sms_logs。

Celery 里必须自建 engine（NullPool），不能复用 API 的 async engine —— 与本仓其它
worker 同一约束（Celery 会 fork）。
"""
import asyncio
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.modules.sms.channel import Channel
from app.modules.sms.rcs_task import RCSSendTask
from app.utils.logger import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _make_session():
    """与其它 worker 同一约束：必须 NullPool。

    Celery ForkPool 每次任务新建事件循环，持久连接池会把连接 bound 在首个 loop 上，
    换 loop 后触发「Task got Future attached to a different loop」。
    读超时放宽到 60s：轮询本身是外部 HTTP，DB 侧只有小查询，但结果回写会做批量 UPDATE。
    """
    eng = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        pool_pre_ping=True,
        pool_recycle=600,
        connect_args={
            "connect_timeout": int(os.getenv("WORKER_DB_CONNECT_TIMEOUT_SEC", "10")),
            "read_timeout": int(os.getenv("RCS_NODE_DB_READ_TIMEOUT_SEC", "60")),
        },
    )
    return eng, async_sessionmaker(
        eng, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
    )


def _run(coro, timeout: float = 300.0):
    async def _with_timeout():
        return await asyncio.wait_for(coro, timeout=timeout)

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_with_timeout())
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)


@celery_app.task(name='poll_rcs_node_tasks_task')
def poll_rcs_node_tasks_task(limit: int = 50):
    """轮询在途的节点 RCS 群发任务；落终态的顺带取结果回写。"""
    return _run(_do_poll(limit), timeout=float(os.getenv("RCS_NODE_POLL_TIMEOUT_SEC", "600")))


async def _do_poll(limit: int) -> dict:
    from app.services.rcs_node_service import apply_result, pending_tasks, poll_task

    eng, Session = _make_session()
    polled = finalized = applied = 0
    try:
        async with Session() as db:
            tasks = await pending_tasks(db, limit=limit)
            if not tasks:
                return {"polled": 0, "finalized": 0, "applied": 0}

            ch_ids = {t.channel_id for t in tasks}
            ch_rows = (
                await db.execute(select(Channel).where(Channel.id.in_(list(ch_ids))))
            ).scalars().all()
            channels = {c.id: c for c in ch_rows}

            for task in tasks:
                channel: Optional[Channel] = channels.get(task.channel_id)
                if channel is None:
                    logger.warning(f"节点 RCS 任务的通道已不存在: task={task.id} channel={task.channel_id}")
                    continue
                try:
                    if task.state != RCSSendTask.STATE_FINAL:
                        polled += 1
                        if not await poll_task(db, task, channel):
                            continue
                        finalized += 1
                    # 终态：取结果回写（未识别出状态列时内部只存档告警，不改状态）
                    applied += await apply_result(db, task, channel)
                except Exception as e:
                    logger.error(
                        f"节点 RCS 任务处理异常: task={task.id} sn={task.sn}, {e}", exc_info=e
                    )
                    try:
                        await db.rollback()
                    except Exception:
                        pass

        logger.info(
            f"节点 RCS 轮询完成: 轮询={polled} 落终态={finalized} 回写={applied} 条"
        )
        return {"polled": polled, "finalized": finalized, "applied": applied}
    finally:
        await eng.dispose()


@celery_app.task(name='purge_rcs_number_files_task')
def purge_rcs_number_files_task(limit: int = 500):
    """兜底清理：过期但仍留有正文的号码文件（正常路径在任务终态时就清了）。"""
    return _run(_do_purge(limit), timeout=120.0)


async def _do_purge(limit: int) -> dict:
    from app.services.rcs_number_file import purge_expired

    eng, Session = _make_session()
    try:
        async with Session() as db:
            n = await purge_expired(db, limit=limit)
            await db.commit()
            if n:
                logger.info(f"节点 RCS 号码文件兜底清理: {n} 份")
            return {"purged": n}
    finally:
        await eng.dispose()
