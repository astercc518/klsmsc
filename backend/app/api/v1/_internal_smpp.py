"""
SMPP 入站网关内部回调端点。

Go SMPP 入站服务器在收到客户 SUBMIT_SM 后，通过此端点把请求接入完整的
HTTP 业务管线（号码校验/国家白名单/通道路由/计费扣费/SMSLog 落库/Celery 入队），
避免在 Go 侧重复实现这些逻辑。

仅供 docker 网络内部调用，由 X-Internal-Token 共享密钥保护。
"""
from __future__ import annotations

import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sms import submit_sms_core
from app.config import settings
from app.database import get_db
from app.modules.common.account import Account
from app.schemas.sms import SMSSendResponse
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class InternalSmppSubmit(BaseModel):
    account_id: int = Field(..., description="账号 ID（Go 网关 BIND 阶段已验证）")
    message_id: str = Field(..., min_length=1, max_length=64, description="Go 侧预分配的 message_id")
    source_addr: Optional[str] = None
    dest_addr: str = Field(..., min_length=1, description="目标号码（E.164 或国内本地段）")
    message: str = Field(..., description="短信内容（Go 已合并 concat / 解码 data_coding）")
    ip: Optional[str] = None
    registered_delivery: int = 0


def _verify_internal_token(token: Optional[str]) -> None:
    if not token or not hmac.compare_digest(token, settings.INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid internal token")


@router.post("/smpp_submit", response_model=SMSSendResponse)
async def smpp_submit(
    body: InternalSmppSubmit,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Go SMPP 入站网关收到 SUBMIT_SM 后转发至此。

    - 必须携带 `X-Internal-Token`，与 settings.INTERNAL_TOKEN 严格匹配
    - 复用 `submit_sms_core` 走完所有业务校验/计费/落库/入队
    - 同步返回结果给 Go 侧；若失败由 Go 侧生成 REJECTD DLR 推送给客户
    """
    _verify_internal_token(x_internal_token)

    result = await db.execute(select(Account).where(Account.id == body.account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.status != "active":
        return SMSSendResponse(
            success=False,
            message_id=body.message_id,
            error={"code": "ACCOUNT_INACTIVE", "message": f"Account status: {account.status}"},
        )

    if (account.protocol or "").upper() != "SMPP":
        return SMSSendResponse(
            success=False,
            message_id=body.message_id,
            error={"code": "PROTOCOL_MISMATCH", "message": "Account is not SMPP-enabled"},
        )

    return await submit_sms_core(
        db=db,
        account=account,
        phone_number=body.dest_addr,
        message=body.message,
        channel_id=None,
        http_credentials=None,
        message_id_hint=body.message_id,
    )
