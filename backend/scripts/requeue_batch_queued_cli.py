#!/usr/bin/env python3
"""
运维 CLI：将指定批次中仍为 queued / pending 的短信重新投递到 sms_send（不重复扣费）。

用法（在 API 容器内，须设置 PYTHONPATH）:
  docker compose exec api sh -c 'cd /app && PYTHONPATH=/app python scripts/requeue_batch_queued_cli.py <batch_id>'
"""
from __future__ import annotations

import asyncio
import sys


async def _run(batch_id: int) -> None:
    from sqlalchemy import or_, select

    from app.database import AsyncSessionLocal
    # 预加载全部 ORM 模型，避免 Account→AdminUser 等跨模块 relationship 未注册导致 mapper 初始化失败
    from app.modules.common.admin_user import AdminUser  # noqa: F401
    from app.modules.common.account import Account  # noqa: F401
    from app.modules.sms.batch_utils import update_batch_progress
    from app.modules.sms.sms_batch import SmsBatch
    from app.modules.sms.sms_log import SMSLog
    from app.utils.queue import QueueManager

    async with AsyncSessionLocal() as db:
        batch = (
            await db.execute(
                select(SmsBatch).where(SmsBatch.id == batch_id, SmsBatch.is_deleted == False)
            )
        ).scalar_one_or_none()
        if not batch:
            print(f"批次不存在: batch_id={batch_id}", file=sys.stderr)
            sys.exit(1)
        if str(batch.status).lower() == "cancelled":
            print("批次已取消，拒绝操作", file=sys.stderr)
            sys.exit(1)

        q = (
            select(SMSLog)
            .where(
                SMSLog.batch_id == batch_id,
                or_(SMSLog.status == "queued", SMSLog.status == "pending"),
            )
            .order_by(SMSLog.id)
        )
        rows = list((await db.execute(q)).scalars().all())
        if not rows:
            print(f"批次 {batch_id} 无 queued/pending 记录，无需入队")
            return

        retried = 0
        skipped = 0
        for sms_log in rows:
            mid = sms_log.message_id
            if not mid:
                skipped += 1
                continue
            if QueueManager.queue_sms(mid):
                retried += 1
            else:
                skipped += 1

        try:
            await update_batch_progress(db, batch_id)
            await db.commit()
        except Exception as e:
            # 入队已成功；进度汇总依赖 ORM 元数据，部分环境缺表会失败，不阻断运维
            print(f"提示: 更新批次进度时出现异常（可忽略或检查库表）: {e}", file=sys.stderr)

        print(
            f"批次 {batch_id}: 共 {len(rows)} 条 queued/pending，"
            f"重新入队成功 {retried}，失败/跳过 {skipped}"
        )


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python scripts/requeue_batch_queued_cli.py <batch_id>", file=sys.stderr)
        sys.exit(2)
    batch_id = int(sys.argv[1])
    asyncio.run(_run(batch_id))


if __name__ == "__main__":
    main()
