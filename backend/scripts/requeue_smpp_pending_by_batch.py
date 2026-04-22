#!/usr/bin/env python3
"""
将指定批次中仍为 pending（可选含 queued）且通道为 SMPP 的短信，按全量负载重新投递到 sms_send_smpp。

适用场景：Go 网关曾无法解析 Celery JSON 信封导致消息被丢弃、或 purge 后需按库补投；
与 scripts/requeue_batch_queued_cli.py 不同：本脚本直投 sms_send_smpp，不经过 sms_send。

用法:
  cd /var/smsc/backend && python3 scripts/requeue_smpp_pending_by_batch.py 302 303
  docker compose exec api sh -c 'cd /app && PYTHONPATH=/app python scripts/requeue_smpp_pending_by_batch.py 302 --dry-run'
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


async def _requeue_one_batch(
    db,
    batch_id: int,
    *,
    include_queued: bool,
    dry_run: bool,
) -> tuple[int, int, int]:
    """返回 (待补投条数, 成功入队, 失败/跳过)"""
    from sqlalchemy import or_, select

    from app.modules.sms.batch_utils import update_batch_progress
    from app.modules.sms.channel import Channel
    from app.modules.sms.sms_batch import SmsBatch
    from app.modules.sms.sms_log import SMSLog
    from app.utils.queue import QueueManager
    from app.utils.smpp_payload import smpp_payload_public_dict

    batch = (
        await db.execute(
            select(SmsBatch).where(SmsBatch.id == batch_id, SmsBatch.is_deleted == False)
        )
    ).scalar_one_or_none()
    if not batch:
        print(f"[跳过] batch_id={batch_id} 不存在或已删除", file=sys.stderr)
        return 0, 0, 0
    if str(batch.status).lower() == "cancelled":
        print(f"[跳过] batch_id={batch_id} 已取消", file=sys.stderr)
        return 0, 0, 0

    status_filter = (
        or_(SMSLog.status == "queued", SMSLog.status == "pending")
        if include_queued
        else SMSLog.status == "pending"
    )

    q = (
        select(SMSLog)
        .join(Channel, SMSLog.channel_id == Channel.id)
        .where(
            SMSLog.batch_id == batch_id,
            status_filter,
            Channel.protocol == "SMPP",
        )
        .order_by(SMSLog.id)
    )
    rows = list((await db.execute(q)).scalars().all())
    if not rows:
        print(f"[批次 {batch_id}] 无符合条件的 SMPP pending 记录（已过滤非 SMPP 通道）")
        return 0, 0, 0

    batch_status_val = getattr(batch.status, "value", batch.status) or ""
    payloads = [smpp_payload_public_dict(r, batch_status_val) for r in rows]

    if dry_run:
        print(
            f"[dry-run] batch_id={batch_id}: 将补投 {len(payloads)} 条至 sms_send_smpp（未实际发布）"
        )
        return len(payloads), len(payloads), 0

    ok = QueueManager.queue_sms_batch_smpp(payloads, http_credentials=None)
    if ok:
        print(f"[批次 {batch_id}] 已投递 sms_send_smpp: {len(payloads)} 条")
    else:
        print(f"[批次 {batch_id}] 批量入队失败（部分可能未发出），请查日志", file=sys.stderr)

    try:
        await update_batch_progress(db, batch_id)
        await db.commit()
    except Exception as e:
        print(f"[提示] batch_id={batch_id} 更新批次进度异常（可忽略）: {e}", file=sys.stderr)

    return len(payloads), len(payloads) if ok else 0, 0 if ok else len(payloads)


async def _run(batch_ids: list[int], *, include_queued: bool, dry_run: bool) -> int:
    from app.database import AsyncSessionLocal
    from app.modules.common.account import Account  # noqa: F401
    from app.modules.common.admin_user import AdminUser  # noqa: F401

    total_rows = 0
    exit_code = 0
    async with AsyncSessionLocal() as db:
        for bid in batch_ids:
            n, okc, bad = await _requeue_one_batch(
                db,
                bid,
                include_queued=include_queued,
                dry_run=dry_run,
            )
            total_rows += n
            if bad:
                exit_code = 1
    if dry_run:
        print(f"[dry-run] 合计将处理约 {total_rows} 条（未发布）")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按 batch_id 将 SMPP 的 pending 记录重新投递到 sms_send_smpp"
    )
    parser.add_argument(
        "batch_ids",
        type=int,
        nargs="+",
        help="一个或多个 sms_batches.id",
    )
    parser.add_argument(
        "--include-queued",
        action="store_true",
        help="同时包含状态为 queued 的记录（默认仅 pending）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅统计将要补投的条数，不向 RabbitMQ 发布",
    )
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.batch_ids,
            include_queued=args.include_queued,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
