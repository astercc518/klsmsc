"""
管理员系统操作日志 API
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, or_, union_all, literal, case, text
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.modules.common.admin_operation_log import AdminOperationLog
from app.modules.common.config_audit_log import ConfigAuditLog
from app.modules.common.security_log import SecurityLog, LoginAttempt
from app.modules.common.admin_user import AdminUser
from app.core.auth import get_current_admin
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

MODULE_LABELS = {
    "system": "系统管理",
    "account": "账户管理",
    "channel": "通道管理",
    "sms": "短信业务",
    "finance": "财务管理",
    "security": "安全管理",
    "config": "配置变更",
    "login": "登录认证",
}


@router.get("/admin/system/logs", summary="查询系统操作日志")
async def list_system_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    module: Optional[str] = Query(None, description="模块筛选"),
    action: Optional[str] = Query(None, description="操作类型"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    admin_name: Optional[str] = Query(None, description="操作人"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """查询系统操作日志（聚合多源）"""
    try:
        conditions = []
        if module:
            conditions.append(AdminOperationLog.module == module)
        if action:
            conditions.append(AdminOperationLog.action == action)
        if admin_name:
            conditions.append(AdminOperationLog.admin_name.ilike(f"%{admin_name}%"))
        if keyword:
            conditions.append(
                or_(
                    AdminOperationLog.title.ilike(f"%{keyword}%"),
                    AdminOperationLog.detail.ilike(f"%{keyword}%"),
                    AdminOperationLog.target_type.ilike(f"%{keyword}%"),
                )
            )
        if start_date:
            conditions.append(AdminOperationLog.created_at >= start_date)
        if end_date:
            conditions.append(AdminOperationLog.created_at <= end_date)

        where_clause = and_(*conditions) if conditions else True

        count_q = select(func.count()).select_from(AdminOperationLog).where(where_clause)
        total = (await db.execute(count_q)).scalar() or 0

        offset = (page - 1) * page_size
        data_q = (
            select(AdminOperationLog)
            .where(where_clause)
            .order_by(desc(AdminOperationLog.created_at))
            .limit(page_size)
            .offset(offset)
        )
        result = await db.execute(data_q)
        logs = result.scalars().all()

        items = [
            {
                "id": log.id,
                "admin_id": log.admin_id,
                "admin_name": log.admin_name or "系统",
                "module": log.module,
                "module_label": MODULE_LABELS.get(log.module, log.module),
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "title": log.title,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "status": log.status,
                "error_message": log.error_message,
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else None,
            }
            for log in logs
        ]

        return {"total": total, "items": items, "page": page, "page_size": page_size}

    except Exception as e:
        logger.error(f"查询系统日志失败: {e}")
        raise


@router.get("/admin/system/logs/modules", summary="获取日志模块列表")
async def get_log_modules(
    _current_admin: AdminUser = Depends(get_current_admin),
):
    """返回所有可用的日志模块（用于筛选下拉）"""
    return {"modules": MODULE_LABELS}


@router.get("/admin/system/logs/stats", summary="日志统计")
async def get_log_stats(
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取日志统计概览"""
    try:
        total_q = select(func.count()).select_from(AdminOperationLog)
        total = (await db.execute(total_q)).scalar() or 0

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_q = select(func.count()).select_from(AdminOperationLog).where(
            AdminOperationLog.created_at >= today
        )
        today_count = (await db.execute(today_q)).scalar() or 0

        module_q = (
            select(AdminOperationLog.module, func.count().label("cnt"))
            .group_by(AdminOperationLog.module)
            .order_by(desc(text("cnt")))
        )
        module_result = await db.execute(module_q)
        by_module = {
            row.module: {"count": row.cnt, "label": MODULE_LABELS.get(row.module, row.module)}
            for row in module_result
        }

        return {
            "total": total,
            "today": today_count,
            "by_module": by_module,
        }

    except Exception as e:
        logger.error(f"获取日志统计失败: {e}")
        raise


@router.get("/admin/system/security-stats", summary="安全统计概览")
async def get_security_stats(
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """安全管理统计：管理员登录概况、异常 IP、近期事件"""
    try:
        from datetime import timedelta

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=6)

        login_cond = AdminOperationLog.module == "login"

        # 今日登录成功/失败
        today_success = (await db.execute(
            select(func.count()).select_from(AdminOperationLog).where(
                and_(login_cond, AdminOperationLog.created_at >= today_start,
                     AdminOperationLog.status == "success")
            )
        )).scalar() or 0

        today_failed = (await db.execute(
            select(func.count()).select_from(AdminOperationLog).where(
                and_(login_cond, AdminOperationLog.created_at >= today_start,
                     AdminOperationLog.status == "failed")
            )
        )).scalar() or 0

        # 今日独立 IP 数
        unique_ips = (await db.execute(
            select(func.count(func.distinct(AdminOperationLog.ip_address))).select_from(AdminOperationLog).where(
                and_(login_cond, AdminOperationLog.created_at >= today_start)
            )
        )).scalar() or 0

        # 近 7 天每日登录量（用于趋势）
        daily_q = (
            select(
                func.date(AdminOperationLog.created_at).label("day"),
                func.sum(case((AdminOperationLog.status == "success", 1), else_=0)).label("success"),
                func.sum(case((AdminOperationLog.status == "failed", 1), else_=0)).label("failed"),
            )
            .where(and_(login_cond, AdminOperationLog.created_at >= week_start))
            .group_by(func.date(AdminOperationLog.created_at))
            .order_by(func.date(AdminOperationLog.created_at))
        )
        daily_rows = (await db.execute(daily_q)).all()
        daily_trend = [
            {"day": str(r.day), "success": int(r.success), "failed": int(r.failed)}
            for r in daily_rows
        ]

        # 失败次数最多的 IP（近 30 天，top 10）
        month_start = today_start - timedelta(days=29)
        top_ips_q = (
            select(
                AdminOperationLog.ip_address,
                func.count().label("total"),
                func.sum(case((AdminOperationLog.status == "failed", 1), else_=0)).label("failed"),
                func.max(AdminOperationLog.created_at).label("last_time"),
            )
            .where(and_(login_cond, AdminOperationLog.created_at >= month_start,
                        AdminOperationLog.ip_address.isnot(None)))
            .group_by(AdminOperationLog.ip_address)
            .having(func.sum(case((AdminOperationLog.status == "failed", 1), else_=0)) > 0)
            .order_by(desc(text("failed")))
            .limit(10)
        )
        top_ips_rows = (await db.execute(top_ips_q)).all()
        top_ips = [
            {
                "ip": r.ip_address,
                "total": int(r.total),
                "failed": int(r.failed),
                "last_time": r.last_time.strftime("%Y-%m-%d %H:%M:%S") if r.last_time else None,
            }
            for r in top_ips_rows
        ]

        # 近 50 条登录事件（时间线）
        recent_q = (
            select(AdminOperationLog)
            .where(login_cond)
            .order_by(desc(AdminOperationLog.created_at))
            .limit(50)
        )
        recent_rows = (await db.execute(recent_q)).scalars().all()
        recent_events = [
            {
                "id": r.id,
                "admin_name": r.admin_name or "未知",
                "action": r.action,
                "status": r.status,
                "ip_address": r.ip_address,
                "title": r.title,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
            }
            for r in recent_rows
        ]

        # 近 50 条高风险操作（delete / finance / security / config 模块）
        risky_q = (
            select(AdminOperationLog)
            .where(
                (AdminOperationLog.module.in_(["security", "finance", "config"]))
                | (AdminOperationLog.action == "delete")
            )
            .order_by(desc(AdminOperationLog.created_at))
            .limit(50)
        )
        risky_rows = (await db.execute(risky_q)).scalars().all()
        recent_risky_ops = [
            {
                "id": r.id,
                "admin_name": r.admin_name or "未知",
                "module": r.module,
                "module_label": MODULE_LABELS.get(r.module, r.module),
                "action": r.action,
                "status": r.status,
                "title": r.title,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
            }
            for r in risky_rows
        ]

        return {
            "today_success": today_success,
            "today_failed": today_failed,
            "unique_ips_today": unique_ips,
            "daily_trend": daily_trend,
            "top_failed_ips": top_ips,
            "recent_events": recent_events,
            "recent_risky_ops": recent_risky_ops,
        }

    except Exception as e:
        logger.error(f"获取安全统计失败: {e}")
        raise


@router.get("/admin/system/logs/export", summary="导出系统操作日志")
async def export_system_logs(
    module: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    admin_name: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """导出系统操作日志（不分页，最多 5000 条）"""
    try:
        conditions = []
        if module:
            conditions.append(AdminOperationLog.module == module)
        if action:
            conditions.append(AdminOperationLog.action == action)
        if admin_name:
            conditions.append(AdminOperationLog.admin_name.ilike(f"%{admin_name}%"))
        if keyword:
            conditions.append(
                or_(
                    AdminOperationLog.title.ilike(f"%{keyword}%"),
                    AdminOperationLog.detail.ilike(f"%{keyword}%"),
                )
            )
        if start_date:
            conditions.append(AdminOperationLog.created_at >= start_date)
        if end_date:
            conditions.append(AdminOperationLog.created_at <= end_date)

        where_clause = and_(*conditions) if conditions else True

        data_q = (
            select(AdminOperationLog)
            .where(where_clause)
            .order_by(desc(AdminOperationLog.created_at))
            .limit(5000)
        )
        logs = (await db.execute(data_q)).scalars().all()

        items = [
            {
                "id": log.id,
                "admin_name": log.admin_name or "系统",
                "module": MODULE_LABELS.get(log.module, log.module),
                "action": log.action,
                "title": log.title,
                "ip_address": log.ip_address or "",
                "status": log.status,
                "error_message": log.error_message or "",
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
            }
            for log in logs
        ]

        return items

    except Exception as e:
        logger.error(f"导出系统日志失败: {e}")
        raise


@router.get("/admin/system/services", summary="服务健康状态")
async def get_services_status(
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取所有容器状态 + CPU/内存 + 依赖服务连通性"""
    import os
    import asyncio
    import httpx
    from app.config import settings

    proxy_url = os.getenv("DOCKER_PROXY_URL", "http://docker-proxy:2375")

    async def fetch_container_stats(client: httpx.AsyncClient, name: str):
        try:
            r = await client.get(
                f"{proxy_url}/containers/{name}/stats",
                params={"stream": "false"},
                timeout=6.0,
            )
            d = r.json()
            cpu_usage = d["cpu_stats"]["cpu_usage"]["total_usage"]
            pre_cpu = d["precpu_stats"]["cpu_usage"]["total_usage"]
            sys_usage = d["cpu_stats"].get("system_cpu_usage", 0)
            pre_sys = d["precpu_stats"].get("system_cpu_usage", 0)
            num_cpus = d["cpu_stats"].get("online_cpus", 1)
            cpu_delta = cpu_usage - pre_cpu
            sys_delta = sys_usage - pre_sys
            cpu_pct = round((cpu_delta / sys_delta) * num_cpus * 100, 2) if sys_delta > 0 else 0.0

            mem_stats = d.get("memory_stats", {})
            mem_usage = mem_stats.get("usage", 0)
            mem_cache = mem_stats.get("stats", {}).get("cache", 0)
            mem_limit = mem_stats.get("limit", 1)
            net_mem = max(0, mem_usage - mem_cache)
            mem_pct = round(net_mem / mem_limit * 100, 1) if mem_limit > 0 else 0.0

            # Network I/O
            net_rx, net_tx = 0, 0
            for iface in d.get("networks", {}).values():
                net_rx += iface.get("rx_bytes", 0)
                net_tx += iface.get("tx_bytes", 0)

            return {
                "cpu_pct": cpu_pct,
                "mem_usage_mb": round(net_mem / 1024 / 1024, 1),
                "mem_limit_mb": round(mem_limit / 1024 / 1024, 0),
                "mem_pct": mem_pct,
                "net_rx_mb": round(net_rx / 1024 / 1024, 1),
                "net_tx_mb": round(net_tx / 1024 / 1024, 1),
            }
        except Exception:
            return None

    async def check_mysql():
        try:
            await db.execute(text("SELECT 1"))
            return {"status": "ok", "message": "连接正常"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}

    def check_redis():
        try:
            import redis as _redis
            r = _redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
                socket_connect_timeout=2,
            )
            r.ping()
            return {"status": "ok", "message": "连接正常"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}

    containers = []
    try:
        async with httpx.AsyncClient() as client:
            list_resp = await client.get(
                f"{proxy_url}/containers/json",
                params={"all": "true"},
                timeout=5.0,
            )
            container_list = list_resp.json()

            running_names = [
                c["Names"][0].lstrip("/")
                for c in container_list
                if c.get("State") == "running"
            ]
            stats_results = await asyncio.gather(
                *[fetch_container_stats(client, n) for n in running_names],
                return_exceptions=True,
            )
            stats_map = {
                running_names[i]: (stats_results[i] if not isinstance(stats_results[i], Exception) else None)
                for i in range(len(running_names))
            }

            for c in container_list:
                name = c["Names"][0].lstrip("/")
                state = c.get("State", "unknown")
                st = stats_map.get(name)
                containers.append({
                    "name": name,
                    "state": state,
                    "status": c.get("Status", ""),
                    "cpu_pct": st["cpu_pct"] if st else None,
                    "mem_usage_mb": st["mem_usage_mb"] if st else None,
                    "mem_limit_mb": st["mem_limit_mb"] if st else None,
                    "mem_pct": st["mem_pct"] if st else None,
                    "net_rx_mb": st["net_rx_mb"] if st else None,
                    "net_tx_mb": st["net_tx_mb"] if st else None,
                })
            # running first, then alphabetical
            containers.sort(key=lambda x: (0 if x["state"] == "running" else 1, x["name"]))
    except Exception as e:
        logger.warning(f"Docker proxy 不可达，跳过容器信息: {e}")

    mysql_result, redis_result = await asyncio.gather(
        check_mysql(),
        asyncio.get_event_loop().run_in_executor(None, check_redis),
    )

    return {
        "containers": containers,
        "services": {
            "mysql": {"name": "MySQL", **mysql_result},
            "redis": {"name": "Redis", **redis_result},
        },
    }
