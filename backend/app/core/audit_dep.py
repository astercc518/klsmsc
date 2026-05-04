"""
审计 helper —— 用 FastAPI Depends 给端点注入"待提交"的审计闭包。

设计动机：
  现有 log_operation 是手动写的，需要每个端点构造 admin_id/name/ip/ua。
  此 helper 把 admin 鉴权 + Request 上下文一次抽取，端点拿到 (admin, audit) 后
  在业务逻辑收尾时调 await audit(target_id=..., detail={...}) 即可。

用法：
    from app.core.audit_dep import audited

    @router.post("/suppliers")
    async def create_supplier(
        payload: SupplierIn,
        db: AsyncSession = Depends(get_db),
        auth = Depends(audited("supplier", "create")),
    ):
        admin, audit = auth
        sup = ...  # 业务逻辑
        await audit(target_id=sup.id, target_type="supplier",
                    detail={"name": sup.name})
        return sup

异常分支可选地调 await audit(status="failed", error_message=str(e))；
不调也无害（不写日志）。
"""
from typing import Any, Awaitable, Callable, Optional, Tuple

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin
from app.database import get_db
from app.modules.common.admin_user import AdminUser
from app.services.operation_log import log_operation


# audit 闭包签名
AuditCommit = Callable[..., Awaitable[None]]


def audited(module: str, action: str, default_title: Optional[str] = None):
    """
    生成审计 dependency。返回 (admin, audit_commit)。

    audit_commit 接受 kwargs：target_id / target_type / title / detail /
                              status='success'|'failed' / error_message
    """

    async def _dep(
        request: Request,
        db: AsyncSession = Depends(get_db),
        admin: AdminUser = Depends(get_current_admin),
    ) -> Tuple[AdminUser, AuditCommit]:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

        async def _commit(
            *,
            target_id: Any = None,
            target_type: Optional[str] = None,
            title: Optional[str] = None,
            detail: Any = None,
            status: str = "success",
            error_message: Optional[str] = None,
        ):
            await log_operation(
                db,
                admin_id=admin.id,
                admin_name=admin.username,
                module=module,
                action=action,
                title=title or default_title or f"{action} {target_type or module}",
                target_type=target_type,
                target_id=target_id,
                detail=detail,
                ip_address=ip,
                user_agent=ua,
                status=status,
                error_message=error_message,
            )

        return admin, _commit

    return _dep
