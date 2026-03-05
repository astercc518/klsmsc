"""
操作日志记录服务
提供便捷方法在各模块中记录管理员操作
"""
import json
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.common.admin_operation_log import AdminOperationLog
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def log_operation(
    db: AsyncSession,
    *,
    admin_id: Optional[int] = None,
    admin_name: Optional[str] = None,
    module: str,
    action: str,
    title: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    detail: Optional[Any] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
):
    """
    记录一条操作日志

    Args:
        db: 数据库会话
        admin_id: 管理员 ID
        admin_name: 管理员用户名
        module: 模块名 (system/account/channel/sms/finance/security/config/login)
        action: 操作类型 (create/update/delete/login/export/import/query)
        title: 操作描述（人类可读）
        target_type: 对象类型
        target_id: 对象 ID
        detail: 额外信息（dict/list 自动序列化为 JSON）
        ip_address: IP 地址
        user_agent: User-Agent
        status: 结果 (success/failed)
        error_message: 错误信息
    """
    try:
        detail_str = None
        if detail is not None:
            if isinstance(detail, (dict, list)):
                detail_str = json.dumps(detail, ensure_ascii=False, default=str)
            else:
                detail_str = str(detail)

        entry = AdminOperationLog(
            admin_id=admin_id,
            admin_name=admin_name,
            module=module,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            title=title,
            detail=detail_str,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
        )
        db.add(entry)
        await db.flush()
    except Exception as e:
        logger.error(f"记录操作日志失败: {e}")
