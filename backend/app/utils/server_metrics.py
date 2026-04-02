"""
采集运行 API 进程所在主机的性能指标（用于管理仪表盘）。
依赖 psutil；采集在线程中执行以免阻塞事件循环。
"""
from __future__ import annotations

import os
import platform
from typing import Any, Dict, List, Optional


def collect_host_metrics_sync() -> Dict[str, Any]:
    """同步采集 CPU、内存、磁盘、负载等信息。"""
    import psutil

    cpu_percent = psutil.cpu_percent(interval=0.15)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    load_avg: Optional[List[float]] = None
    if hasattr(os, "getloadavg"):
        try:
            load_avg = list(os.getloadavg())
        except OSError:
            load_avg = None

    return {
        "hostname": platform.node() or "",
        "cpu_percent": round(float(cpu_percent or 0), 1),
        "memory_percent": round(vm.percent, 1),
        "memory_used_gb": round(vm.used / (1024**3), 2),
        "memory_total_gb": round(vm.total / (1024**3), 2),
        "disk_percent": round(disk.percent, 1),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "load_avg": load_avg,
    }


def check_rabbitmq_sync() -> bool:
    """检测 RabbitMQ（Celery broker）是否可达。"""
    from kombu import Connection
    from app.config import settings

    with Connection(settings.RABBITMQ_URL, connect_timeout=2) as conn:
        conn.connect()
    return True
