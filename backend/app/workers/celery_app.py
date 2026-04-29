"""
Celery应用配置
"""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# 创建Celery应用
celery_app = Celery(
    'sms_gateway',
    broker=settings.RABBITMQ_URL,
    backend=f'redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1',
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

# 任务路由 - 数据业务
celery_app.conf.task_routes.update({
    'data_refresh_all_product_stock': {'queue': 'data_tasks'},
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
    'inspect_batches_task': {'queue': 'celery'},
    'sync_processing_batch_progress_task': {'queue': 'celery'},
    'send_webhook': {'queue': 'webhook_tasks'},
    'okcc_sync_balances_task': {'queue': 'integrations'},
    # 与 send_sms_task 同队列：仅起 worker-sms 时也能消费模拟回执，避免 DataSend 万级任务积压在无人消费的 celery 队列
    'virtual_dlr_generate': {'queue': 'sms_send'},
    'virtual_dlr_batch_generate': {'queue': 'sms_send'},
    'virtual_submit_simulate': {'queue': 'sms_send'},
    'repair_virtual_batch_dlr': {'queue': 'sms_send'},
    'data_buy_send_async': {'queue': 'data_tasks'},
    'web_click_task': {'queue': 'web_automation'},
    'web_register_task': {'queue': 'web_automation'},
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
    # 每天 00:30 清理过期 SMPP 待发 DLR
    'smpp-pending-dlr-cleanup-daily': {
        'task': 'smpp_pending_dlr_cleanup',
        'schedule': crontab(hour=0, minute=30),
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

