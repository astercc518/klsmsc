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
    include=['app.workers.sms_worker', 'app.workers.data_worker']
)

# Celery配置
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 默认30分钟硬超时
    task_soft_time_limit=25 * 60,  # 默认25分钟软超时
    worker_prefetch_multiplier=1,  # 每个worker一次只取一个任务
    worker_max_tasks_per_child=1000,  # 每个worker处理1000个任务后重启
)

# 任务路由
celery_app.conf.task_routes = {
    'send_sms_task': {'queue': 'sms_send'},
    'process_dlr_task': {'queue': 'sms_dlr'},
    'fetch_dlr_reports_task': {'queue': 'sms_dlr'},
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
}

# 任务路由 - 数据业务
celery_app.conf.task_routes.update({
    'data_refresh_all_product_stock': {'queue': 'data_tasks'},
    'data_recycle_expired_numbers': {'queue': 'data_tasks'},
    'data_expire_pending_orders': {'queue': 'data_tasks'},
    'data_import_numbers': {'queue': 'data_tasks'},
})

# 定时任务配置（Celery Beat）
celery_app.conf.beat_schedule = {
    # 每30秒拉取一次 DLR 报告
    'fetch-dlr-reports-every-30s': {
        'task': 'fetch_dlr_reports_task',
        'schedule': 30.0,
    },
    # 每小时刷新所有活跃商品库存
    'data-refresh-stock-hourly': {
        'task': 'data_refresh_all_product_stock',
        'schedule': 3600.0,
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
}

