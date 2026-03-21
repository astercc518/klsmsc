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


@router.get("/admin/system/services", summary="服务健康状态")
async def get_services_status(
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取各依赖服务健康状态"""
    from app.config import settings

    async def check_mysql():
        try:
            await db.execute(text("SELECT 1"))
            return {"status": "ok", "message": "连接正常"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}

    def check_redis():
        try:
            import redis
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
                socket_connect_timeout=2
            )
            r.ping()
            return {"status": "ok", "message": "连接正常"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}

    mysql_result = await check_mysql()
    redis_result = check_redis()

    return {
        "services": {
            "mysql": {"name": "MySQL", **mysql_result},
            "redis": {"name": "Redis", **redis_result},
        }
    }
