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
celery_app.conf.task_routes = {
    'send_sms_task': {'queue': 'sms_send'},
    'process_dlr_task': {'queue': 'sms_dlr'},
    'process_smpp_dlr_task': {'queue': 'sms_dlr'},
    'fetch_dlr_reports_task': {'queue': 'sms_dlr'},
    'dlr_timeout_check_task': {'queue': 'sms_dlr'},
}

# 任务队列
celery_app.conf.task_queues = {
    'sms_send': {
        'exchange': 'sms_send',
        'routing_key': 'sms_send',
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
    'send_webhook': {'queue': 'celery'},
    'okcc_sync_balances_task': {'queue': 'celery'},
    'virtual_dlr_generate': {'queue': 'celery'},
    'virtual_dlr_batch_generate': {'queue': 'celery'},
    'virtual_submit_simulate': {'queue': 'celery'},
    'data_buy_send_async': {'queue': 'data_tasks'},
    'web_click_task': {'queue': 'web_automation'},
    'web_register_task': {'queue': 'web_automation'},
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
    # 每5分钟巡检一次卡死的批次
    'inspect-stuck-batches-5min': {
        'task': 'inspect_batches_task',
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

