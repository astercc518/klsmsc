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
        'app.workers.settlement_worker',
        'app.workers.voice_worker',
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
    'voice_tasks': {
        'exchange': 'voice_tasks',
        'routing_key': 'voice_tasks',
    },
    'settlement_tasks': {
        'exchange': 'settlement_tasks',
        'routing_key': 'settlement_tasks',
    },
}

# 任务路由 - 结算业务
celery_app.conf.task_routes.update({
    'settlement_commission_monthly_task': {'queue': 'settlement_tasks'},
    'settlement_refresh_monthly_commission_task': {'queue': 'settlement_tasks'},
})
# 任务路由 - 数据业务
celery_app.conf.task_routes.update({
    'voice_campaign_tick_task': {'queue': 'voice_tasks'},
    'voice_campaign_scan_task': {'queue': 'voice_tasks'},
    'voice_cdr_retry_failed_task': {'queue': 'voice_tasks'},
})
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
    # 每10分钟检查 DLR 超时记录
    'dlr-timeout-check-every-10min': {
        'task': 'dlr_timeout_check_task',
        'schedule': 600.0,
    },
    # 每 2 分钟重试失败的 CDR Webhook
    'voice-cdr-retry-every-2min': {
        'task': 'voice_cdr_retry_failed_task',
        'schedule': 120.0,
    },
    # 每 30 秒扫描 running 外呼任务并投递 tick（与网关配合时启用）
    'voice-campaign-scan-every-30s': {
        'task': 'voice_campaign_scan_task',
        'schedule': 30.0,
    },
    # 每月 1 日 02:00 生成上月销售佣金结算单
    'settlement-commission-monthly': {
        'task': 'settlement_commission_monthly_task',
        'schedule': crontab(day_of_month=1, hour=2, minute=0),
    },
    # 每天 01:00 刷新销售本月累计佣金
    'settlement-refresh-monthly-commission': {
        'task': 'settlement_refresh_monthly_commission_task',
        'schedule': crontab(hour=1, minute=0),
    },
}

# 各 Worker 子进程启动时补齐 ORM 所需列（与 API 一致，避免任务内加载 Channel 失败）
from celery.signals import worker_process_init

from app.utils.logger import get_logger as _schema_get_logger

_schema_logger = _schema_get_logger(__name__)


@worker_process_init.connect
def _ensure_channel_dlr_columns_on_worker(**_kwargs):
    import asyncio

    try:
        from app.database import (
            ensure_channel_dlr_preference_columns,
            ensure_sales_commission_total_cost_columns,
        )

        async def _ensure_schema():
            await ensure_channel_dlr_preference_columns()
            await ensure_sales_commission_total_cost_columns()

        asyncio.run(_ensure_schema())
    except Exception as e:
        _schema_logger.warning(
            "Celery Worker 启动时补齐 channels DLR 列失败（可手动执行 scripts/add_channel_dlr_columns.sql）: %s",
            e,
        )

