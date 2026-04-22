#!/usr/bin/env python3
"""
一键清空 RabbitMQ 队列 sms_send_smpp 中的积压消息。

用途：部署新版 Go 网关前清理「仅 message_id」等旧格式 Celery 消息，避免新网关解析失败。
依赖：与后端相同的 RabbitMQ 配置（环境变量或 .env），使用 kombu（项目已依赖）。

用法（在 backend 目录或设置 PYTHONPATH=/app 的容器内）:
  cd /var/smsc/backend && python3 scripts/purge_old_smpp_queue.py
  docker compose exec worker python /app/scripts/purge_old_smpp_queue.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证可导入 app.*
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge RabbitMQ 队列 sms_send_smpp")
    parser.add_argument(
        "--queue",
        default="sms_send_smpp",
        help="要清空的队列名（默认 sms_send_smpp）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印当前积压条数，不执行 purge",
    )
    args = parser.parse_args()

    from kombu import Connection

    from app.config import settings

    url = settings.RABBITMQ_URL
    qname = args.queue.strip() or "sms_send_smpp"

    with Connection(url, connect_timeout=10) as conn:
        conn.ensure_connection(max_retries=3)
        ch = conn.channel()
        try:
            # passive：只查询，不创建队列
            _, message_count, consumer_count = ch.queue_declare(queue=qname, passive=True)
        except Exception as e:
            print(f"[错误] 无法声明/查询队列 {qname!r}: {e}", file=sys.stderr)
            return 2

        print(
            f"队列 {qname!r}: 就绪+未确认消息约 {message_count} 条, 消费者数 {consumer_count}"
        )

        if args.dry_run:
            print("[dry-run] 未执行 purge。")
            return 0

        ch.queue_purge(qname)
        print(f"[完成] 已对队列 {qname!r} 执行 queue_purge；purge 前积压约 {message_count} 条。")
        ch.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
