"""
Celery应用配置
"""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# 创建Celery应用
_redis_auth = f":{settings.REDIS_PASSWORD}@" if settings.REDIS_PASSWORD else ""
_celery_result_backend = f"redis://{_redis_auth}{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"

celery_app = Celery(
    'sms_gateway',
    broker=settings.RABBITMQ_URL,
    backend=_celery_result_backend,
    include=[
        'app.workers.sms_worker',
        'app.workers.data_worker',
        'app.workers.batch_worker',
        'app.workers.webhook_worker',
        'app.workers.okcc_worker',
        'app.workers.web_worker',
        'app.workers.batch_inspector',
    ]
)

# Celery配置
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=False,
    task_track_started=True,
    task_time_limit=60 * 60,  # 默认60分钟硬超时
    task_soft_time_limit=55 * 60,  # 默认55分钟软超时
    worker_prefetch_multiplier=1,  # 每个worker一次只取一个任务
    worker_max_tasks_per_child=1000,  # 每个worker处理1000个任务后重启
)

# ============ 全局兜底：统一定时 eta 时区 ============
# 时间统一：容器/MySQL/datetime.now() 全是北京时间(UTC+8)，唯独 Celery 序列化 eta 时
# 会把 naive datetime 一律当 UTC（无视上面 timezone='Asia/Shanghai' / enable_utc=False），
# 使定时任务被推迟 8 小时（线上事故：batch 712 选 17:30 实排次日 01:30）。
# apply_async 与 send_task 最终都汇入 celery_app.send_task —— 在此统一把任何 naive 的
# eta 标成应用时区，杜绝该类 bug 在未来任何调用点复发（无需每处手动 localize）。
from datetime import datetime as _dt  # noqa: E402
from zoneinfo import ZoneInfo as _ZoneInfo  # noqa: E402

_APP_TZ = _ZoneInfo(celery_app.conf.timezone or "Asia/Shanghai")
_orig_send_task = celery_app.send_task


def _send_task_tz_safe(name, args=None, kwargs=None, **options):
    _eta = options.get("eta")
    if isinstance(_eta, _dt) and _eta.tzinfo is None:
        options["eta"] = _eta.replace(tzinfo=_APP_TZ)
    return _orig_send_task(name, args, kwargs, **options)


celery_app.send_task = _send_task_tz_safe

# 任务路由
# 发送（sms_send / sms_send_smpp）与回执（sms_dlr）队列隔离：大批量 send 不会占满消费 DLR 的 worker。
celery_app.conf.task_routes = {
    'send_sms_task': {'queue': 'sms_send'},
    'process_sms_result_task': {'queue': 'sms_result_queue'},
    'process_dlr_task': {'queue': 'sms_dlr'},
    'process_smpp_dlr_task': {'queue': 'sms_dlr'},
    'fetch_dlr_reports_task': {'queue': 'sms_dlr'},
    'dlr_timeout_check_task': {'queue': 'sms_dlr'},
    'flush_dlr_retry_buffer_task': {'queue': 'sms_dlr'},
    # DLR 后注水：与 sms_dlr 分离，避免 HTTP 回调与注水 DB 拖慢回执落库
    'dlr_water_followup_task': {'queue': 'data_tasks'},
}

# 任务队列
celery_app.conf.task_queues = {
    'sms_send': {
        'exchange': 'sms_send',
        'routing_key': 'sms_send',
    },
    'sms_send_smpp': {
        'exchange': 'sms_send_smpp',
        'routing_key': 'sms_send_smpp',
    },
    'sms_dlr': {
        'exchange': 'sms_dlr',
        'routing_key': 'sms_dlr',
    },
    'data_tasks': {
        'exchange': 'data_tasks',
        'routing_key': 'data_tasks',
    },
    'web_automation': {
        'exchange': 'web_automation',
        'routing_key': 'web_automation',
    },
    # 与通用 celery 队列隔离：Webhook 洪峰不拖慢批量 chunk
    'webhook_tasks': {
        'exchange': 'webhook_tasks',
        'routing_key': 'webhook_tasks',
    },
    # 外部集成（OKCC 等）单独队列，便于限流与扩容
    'integrations': {
        'exchange': 'integrations',
        'routing_key': 'integrations',
    },
    # Go smpp-gateway SubmitSM 结果异步回写 sms_logs（批量合并 UPDATE）
    'sms_result_queue': {
        'exchange': 'sms_result_queue',
        'routing_key': 'sms_result_queue',
    },
    # SMPP 入站服务器：DLR 回推给在线客户的 RECEIVER 会话
    # Python 在 _process_smpp_dlr_async 完成 sms_logs 更新后投递；Go inbound_dlr_consumer 消费
    # 24h 消息 TTL，避免网关长时间停摆累积无限增长
    'sms_inbound_dlr': {
        'exchange': 'sms_inbound_dlr',
        'routing_key': 'sms_inbound_dlr',
        'queue_arguments': {'x-message-ttl': 86_400_000},
    },
}

# ---------------------------------------------------------------------------
# Webhook 重试 DLX 拓扑（替代 Celery self.retry(countdown=...) 这个把消息挂 worker 内存、
# 重启即丢、占 prefetch 的反模式）。下列队列【无消费者】，纯"延迟暂存"：消息躺到 x-message-ttl
# 到期后被死信(dead-letter)回 webhook_tasks 交换机，重新投递给 worker-webhook。
# 声明机制与上方 sms_inbound_dlr 完全一致（task_queues 的 queue_arguments 在首次 publish 时声明）。
# ---------------------------------------------------------------------------
_webhook_dlx_queues = {}
# 失败重试阶梯：1m → 5m → 30m → 2h → 6h
for _label, _ttl in [('1m', 60_000), ('5m', 300_000), ('30m', 1_800_000),
                     ('2h', 7_200_000), ('6h', 21_600_000)]:
    _webhook_dlx_queues[f'webhook.retry.{_label}'] = {
        'exchange': f'webhook.retry.{_label}',
        'routing_key': f'webhook.retry.{_label}',
        'queue_arguments': {
            'x-message-ttl': _ttl,
            'x-dead-letter-exchange': 'webhook_tasks',
            'x-dead-letter-routing-key': 'webhook_tasks',
        },
    }
# 限流暂存：被令牌桶限流的消息在此停留 10s 再回投，不计入失败重试次数。
_webhook_dlx_queues['webhook.throttle'] = {
    'exchange': 'webhook.throttle',
    'routing_key': 'webhook.throttle',
    'queue_arguments': {
        'x-message-ttl': 10_000,
        'x-dead-letter-exchange': 'webhook_tasks',
        'x-dead-letter-routing-key': 'webhook_tasks',
    },
}
# 死信队列：穷尽重试仍失败的回执落此，保留 7 天供审计/手动重放（无消费者、无 DLX）。
_webhook_dlx_queues['webhook.dlq'] = {
    'exchange': 'webhook.dlq',
    'routing_key': 'webhook.dlq',
    'queue_arguments': {'x-message-ttl': 604_800_000},
}
celery_app.conf.task_queues.update(_webhook_dlx_queues)

# 任务路由 - 数据业务
celery_app.conf.task_routes.update({
    'data_refresh_all_product_stock': {'queue': 'data_tasks'},
    'data_refresh_carriers_cache': {'queue': 'data_tasks'},
    'data_recycle_expired_numbers': {'queue': 'data_tasks'},
    'data_expire_pending_orders': {'queue': 'data_tasks'},
    'data_import_numbers': {'queue': 'data_tasks'},
    'private_library_upload': {'queue': 'data_tasks'},
    'private_library_sync_used': {'queue': 'data_tasks'},
})
# 任务路由 - 批量发送 & Webhook 回调
celery_app.conf.task_routes.update({
    'process_batch': {'queue': 'celery'},
    'process_batch_chunk': {'queue': 'celery'},
    'retry_batch_as_new': {'queue': 'celery'},
    'inspect_batches_task': {'queue': 'celery'},
    'sync_processing_batch_progress_task': {'queue': 'celery'},
    'send_webhook': {'queue': 'webhook_tasks'},
    'record_link_click_task': {'queue': 'webhook_tasks'},
    'okcc_sync_balances_task': {'queue': 'integrations'},
    # 与 send_sms_task 同队列：仅起 worker-sms 时也能消费模拟回执，避免 DataSend 万级任务积压在无人消费的 celery 队列
    'virtual_dlr_generate': {'queue': 'sms_send'},
    'virtual_dlr_batch_generate': {'queue': 'sms_send'},
    'virtual_submit_simulate': {'queue': 'sms_send'},
    'repair_virtual_batch_dlr': {'queue': 'sms_send'},
    'data_buy_send_async': {'queue': 'data_tasks'},
    'web_click_task': {'queue': 'web_automation'},
    'web_register_task': {'queue': 'web_automation'},
    'cleanup_stuck_water_logs_task': {'queue': 'web_automation'},
    # SMPP 入站待发 DLR 清理（与其他 sms_dlr 任务同队列；任务体本身只跑短 SQL）
    'smpp_pending_dlr_cleanup': {'queue': 'sms_dlr'},
})

# 定时任务配置（Celery Beat）
celery_app.conf.beat_schedule = {
    # 每30秒拉取一次 DLR 报告
    'fetch-dlr-reports-every-30s': {
        'task': 'fetch_dlr_reports_task',
        'schedule': 30.0,
    },
    # 每10分钟刷新所有活跃商品库存（含时效过期自动下架）
    'data-refresh-stock-10min': {
        'task': 'data_refresh_all_product_stock',
        'schedule': 600.0,
    },
    # 每10分钟预热客户端 /data/carriers 接口的聚合缓存。data_numbers 现 1500w+ 行，
    # 按 country_code GROUP BY 在 TH/BD 等大国可达 130s+，必须由 beat 离线刷新避免请求超时。
    'data-refresh-carriers-cache-10min': {
        'task': 'data_refresh_carriers_cache',
        'schedule': 600.0,
    },
    # 每天 03:00 回收过期私库号码
    'data-recycle-expired-daily': {
        'task': 'data_recycle_expired_numbers',
        'schedule': crontab(hour=3, minute=0),
    },
    # 每30分钟清理过期 pending 订单
    'data-expire-pending-orders': {
        'task': 'data_expire_pending_orders',
        'schedule': 1800.0,
    },
    # 每10分钟检查 DLR 超时记录
    'dlr-timeout-check-every-10min': {
        'task': 'dlr_timeout_check_task',
        'schedule': 600.0,
    },
    # 每30秒同步 processing 批次进度（SMPP sent 实时反映到前端）
    'sync-processing-batch-progress-30s': {
        'task': 'sync_processing_batch_progress_task',
        'schedule': 30.0,
    },
    # 每5分钟巡检一次卡死的批次
    'inspect-stuck-batches-5min': {
        'task': 'inspect_batches_task',
        'schedule': 300.0,
    },
    # 每5秒重试一次「DLR先于SubmitSMResp到达」导致未匹配的回执（防止 DLR 永久丢失）
    'flush-dlr-retry-buffer-5s': {
        'task': 'flush_dlr_retry_buffer_task',
        'schedule': 5.0,
    },
    # 每25分钟预热员工月度业绩缓存（员工管理页避免全表扫描 sms_logs）
    'refresh-staff-commission-cache-25min': {
        'task': 'refresh_staff_commission_cache_task',
        'schedule': 1500.0,
    },
    # 每小时预热业务报表缓存（last_month/this_month × 5维度，避免首次打开等 ~17s）
    'refresh-business-report-cache-1h': {
        'task': 'refresh_business_report_cache_task',
        'schedule': 3600.0,
    },
    # 每天 00:30 清理过期 SMPP 待发 DLR
    'smpp-pending-dlr-cleanup-daily': {
        'task': 'smpp_pending_dlr_cleanup',
        'schedule': crontab(hour=0, minute=30),
    },
    # 每 5 分钟巡检卡死的注水任务（Playwright/硬超时 SIGTERM 后行永停 processing）
    'cleanup-stuck-water-logs-5min': {
        'task': 'cleanup_stuck_water_logs_task',
        'schedule': 300.0,
    },
}

# OKCC 余额定时全量同步（可通过 OKCC_BEAT_SYNC_ENABLED=false 关闭）
if settings.OKCC_BEAT_SYNC_ENABLED:
    celery_app.conf.beat_schedule['okcc-sync-balances-periodic'] = {
        'task': 'okcc_sync_balances_task',
        'schedule': float(settings.OKCC_BEAT_SYNC_INTERVAL_SECONDS),
    }

# Schema 变更已统一由 Alembic 管理，部署前运行 alembic upgrade head 即可。
# Worker 启动时不再执行 ALTER TABLE。

# sms_send_smpp 整包投递：注册 Kombu orjson，降低大批量 Celery 消息序列化 CPU（Go 网关仅解析 JSON 体）
SMPP_BULK_PUBLISH_SERIALIZER = "json"
try:
    import orjson
    from kombu.serialization import register

    def _orjson_enc(o):
        return orjson.dumps(o, default=str).decode("utf-8")

    def _orjson_dec(s):
        if isinstance(s, memoryview):
            s = s.tobytes()
        if isinstance(s, bytes):
            return orjson.loads(s)
        return orjson.loads(s)

    register(
        "orjson",
        _orjson_enc,
        _orjson_dec,
        content_type="application/json",
        content_encoding="utf-8",
    )
    SMPP_BULK_PUBLISH_SERIALIZER = "orjson"
    _ac = list(celery_app.conf.get("accept_content") or ["json"])
    if "orjson" not in _ac:
        _ac.append("orjson")
    celery_app.conf.accept_content = _ac
except Exception:
    pass

