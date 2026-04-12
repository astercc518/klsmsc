"""
注水 Celery 队列（web_automation）深度查询与清空
"""
from typing import Tuple

from kombu import Connection

from app.config import settings


def get_web_automation_queue_stats() -> Tuple[int, int, bool]:
    """
    返回 (队列中待消费消息数, 消费者数, 队列是否存在)。
    """
    try:
        with Connection(settings.RABBITMQ_URL) as conn:
            ch = conn.channel()
            ok = ch.queue_declare(queue="web_automation", passive=True)
            return int(ok.message_count), int(ok.consumer_count), True
    except Exception:
        return 0, 0, False


def purge_web_automation_queue() -> int:
    """
    清空 RabbitMQ 中 web_automation 队列内尚未投递给 worker 的消息。
    已在 worker 中执行的任务无法通过此方式中断。
    返回被丢弃的消息条数。
    """
    with Connection(settings.RABBITMQ_URL) as conn:
        ch = conn.channel()
        n = ch.queue_purge("web_automation")
        return int(n) if n is not None else 0
