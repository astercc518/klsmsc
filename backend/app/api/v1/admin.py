"""
管理员API路由
"""
import asyncio
import contextvars
import json
import random
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, text, update as sa_update, func, and_
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from urllib.parse import quote
from datetime import datetime

from app.database import get_db
from app.modules.common.admin_user import AdminUser
from app.modules.common.account import Account
from app.services.okcc_sync import OKCC_SERVERS, fetch_okcc_customers, sync_okcc_to_accounts
from app.services.sms_finance import net_cost, net_revenue, net_profit
from app.core.auth import AuthService
from app.utils.errors import AuthenticationError
from app.utils.client_ip import get_client_ip as _get_client_ip


def _safe_client_ip(req):
    """request 可能是 None 的小封装；保留旧 None 行为兼容上游 log_operation。"""
    return _get_client_ip(req) if req is not None else None
from app.core.auth_scope import (
    apply_account_scope,
    assert_account_in_scope,
    is_sales_scoped,
    sales_id_filter,
)
from app.config import settings
from app.utils.logger import get_logger
from app.utils.errors import InsufficientBalanceError
from datetime import timedelta

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

# 无歧义字符集：排除 0/O、1/I/l 等易混淆字符
_UNAMBIGUOUS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"

def _gen_api_secret(length: int = 8) -> str:
    return "".join(random.SystemRandom().choices(_UNAMBIGUOUS, k=length))


def _mask_secret(s: Optional[str]) -> Optional[str]:
    """admin 后台返回时把 api_secret 打码，仅保留后 4 位。
    DB 字段仍是明文（迁移到 hash 单独排期），但 HTTP 出口屏蔽明文，限缩泄漏面。
    重置/旋转端点 **不**走这里——那些场景明文一次性返回让 admin 复制是预期。"""
    if not s:
        return s
    if len(s) <= 4:
        return "****"
    return "****" + s[-4:]


# Schemas
class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None              # access token (短期 30min)
    refresh_token: Optional[str] = None      # refresh token (长期 24h)
    expires_in: Optional[int] = None         # access token 剩余秒数（前端用于调度刷新）
    admin_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None
    error: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    error: Optional[str] = None


class TelegramSendCodeRequest(BaseModel):
    username: str


class TelegramVerifyRequest(BaseModel):
    username: str
    code: str


class AdminUserResponse(BaseModel):
    id: int
    username: str
    real_name: Optional[str]
    email: Optional[str]
    role: str
    status: str
    last_login_at: Optional[str]
    created_at: str


class ChannelCreateRequest(BaseModel):
    channel_code: str
    channel_name: str
    protocol: str
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    smpp_bind_mode: Optional[str] = "transceiver"
    smpp_system_type: Optional[str] = ""
    smpp_interface_version: Optional[int] = 0x34
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    status: str = "active"
    max_tps: int = 100
    concurrency: int = 1
    rate_control_window: int = 1000
    priority: int = 0
    weight: int = 100
    default_sender_id: Optional[str] = None
    description: Optional[str] = None
    supplier_id: Optional[int] = None  # 关联供应商ID
    # DLR / SMPP：空则使用全局环境变量
    smpp_dlr_socket_hold_seconds: Optional[int] = Field(None, ge=60, le=86400)
    dlr_sent_timeout_hours: Optional[int] = Field(None, ge=4, le=720)
    banned_words: Optional[str] = None
    remark: Optional[str] = None
    virtual_config: Optional[dict] = None
    # 与 channels.config_json 对应：strip_leading_plus、payload_template 等
    gateway_config: Optional[dict] = None

    @field_validator('protocol')
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        if v is None:
            raise ValueError('protocol is required')
        # RCS 不是独立协议：它走 HTTP，靠 config_json.rcs.vendor 标记上游厂商
        if v not in ['HTTP', 'SMPP', 'VIRTUAL']:
            raise ValueError('protocol must be HTTP, SMPP or VIRTUAL')
        return v

    @field_validator('default_sender_id')
    @classmethod
    def validate_default_sender_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == '':
            return None
        return v.strip()

    @field_validator(
        'host', 'username', 'password',
        'smpp_system_type', 'api_url', 'api_key',
        mode='before',
    )
    @classmethod
    def _strip_credential_str(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class ChannelUpdateRequest(BaseModel):
    channel_code: Optional[str] = None
    channel_name: Optional[str] = None
    max_tps: Optional[int] = None
    concurrency: Optional[int] = None
    rate_control_window: Optional[int] = None
    priority: Optional[int] = None
    weight: Optional[int] = None
    status: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    smpp_bind_mode: Optional[str] = None
    smpp_system_type: Optional[str] = None
    smpp_interface_version: Optional[int] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    default_sender_id: Optional[str] = None
    supplier_id: Optional[int] = None
    smpp_dlr_socket_hold_seconds: Optional[int] = Field(None, ge=60, le=86400)
    dlr_sent_timeout_hours: Optional[int] = Field(None, ge=4, le=720)
    banned_words: Optional[str] = None
    remark: Optional[str] = None
    virtual_config: Optional[dict] = None
    gateway_config: Optional[dict] = None

    @field_validator(
        'host', 'username', 'password',
        'smpp_system_type', 'api_url', 'api_key',
        mode='before',
    )
    @classmethod
    def _strip_credential_str(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


# ── 通道扩展配置（config_json）中的 RCS 密钥脱敏 ──────────────────────────────
# appSecret / webhook secret 属于上游凭据，与 channels.password / api_key 一样
# 不能随列表接口回吐给前端。回读时替换为掩码，回写时掩码代表「保持原值」。
_RCS_SECRET_KEYS = ("app_secret", "webhook_secret")
_SECRET_MASK = "******"


def _mask_gateway_config(cfg: Optional[dict]) -> dict:
    """返回给管理端的通道扩展配置：屏蔽 RCS 密钥明文。"""
    if not isinstance(cfg, dict):
        return {}
    out = dict(cfg)
    rcs = out.get("rcs")
    if isinstance(rcs, dict):
        masked = dict(rcs)
        for k in _RCS_SECRET_KEYS:
            if masked.get(k):
                masked[k] = _SECRET_MASK
        out["rcs"] = masked
    return out


def _merge_gateway_config(existing_raw, incoming: Optional[dict]) -> Optional[dict]:
    """
    合并前端提交的扩展配置。

    前端拿到的是掩码值，原样提交回来时必须保留库里的真实密钥，
    否则一次「只改 TPS」的保存就会把 appSecret 抹成 ******，通道当场鉴权失败。
    """
    if incoming is None:
        return None
    merged = dict(incoming)
    rcs_in = merged.get("rcs")
    if not isinstance(rcs_in, dict):
        return merged

    old: dict = {}
    if existing_raw:
        try:
            parsed = existing_raw if isinstance(existing_raw, dict) else json.loads(existing_raw)
            old = parsed.get("rcs") if isinstance(parsed.get("rcs"), dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            old = {}

    rcs_out = dict(rcs_in)
    for k in _RCS_SECRET_KEYS:
        v = rcs_out.get(k)
        if v == _SECRET_MASK or (isinstance(v, str) and set(v.strip()) == {"*"}):
            if old.get(k):
                rcs_out[k] = old[k]
            else:
                rcs_out.pop(k, None)
    merged["rcs"] = rcs_out
    return merged


def _gateway_config_is_rcs(gateway_config) -> bool:
    """扩展配置里是否带 RCS 上游标记（config_json.rcs.vendor）。"""
    rcs = gateway_config.get("rcs") if isinstance(gateway_config, dict) else None
    if not isinstance(rcs, dict):
        return False
    return bool(str(rcs.get("vendor") or "").strip())


async def _channel_is_rcs(db: AsyncSession, channel_id) -> bool:
    """按通道 ID 判断是否 RCS 上游（读 config_json.rcs.vendor）。"""
    from app.modules.sms.channel import Channel as _Ch

    cfg = (await db.execute(
        select(_Ch.config_json).where(_Ch.id == int(channel_id))
    )).scalar_one_or_none()
    return bool(_Ch(config_json=cfg).is_rcs())


def _assert_rcs_channel_ready(api_url, username, password, api_key, gateway_config):
    """RCS 通道保存前的必填校验：缺凭据就直接报错，别等发送时才失败。

    触发条件是 config_json.rcs.vendor（RCS 不占 protocol 枚举，protocol 恒为 HTTP）。
    """
    if not _gateway_config_is_rcs(gateway_config):
        return
    rcs = gateway_config.get("rcs")
    rcs = rcs if isinstance(rcs, dict) else {}

    def _has(*vals):
        return any(isinstance(v, str) and v.strip() for v in vals)

    missing = []
    if not _has(api_url, rcs.get("base_url")):
        missing.append("接口地址 api_url（如 https://域名/service/api）")
    if not _has(username, rcs.get("app_key")):
        missing.append("appKey（填在用户名或 rcs.app_key）")
    if not _has(password, api_key, rcs.get("app_secret")):
        missing.append("appSecret（填在密码或 rcs.app_secret）")
    if missing:
        raise HTTPException(status_code=400, detail="RCS 通道配置不完整，缺少：" + "；".join(missing))


class PricingCreateRequest(BaseModel):
    channel_id: int
    country_code: str
    country_name: str
    price_per_sms: float
    currency: str = "USD"
    mnc: Optional[str] = None
    operator_name: Optional[str] = None
    effective_date: Optional[str] = None
    remark: Optional[str] = None


class PricingUpdateRequest(BaseModel):
    price_per_sms: Optional[float] = None
    currency: Optional[str] = None
    remark: Optional[str] = None


# --- Account Management ---

class AdminAccountCreateRequest(BaseModel):
    account_name: str
    password: str
    tg_username: Optional[str] = None
    country_code: Optional[str] = None  # 国家代码
    business_type: str = "sms"  # sms/voice/data
    # 接入协议
    protocol: str = "HTTP"  # HTTP/SMPP
    smpp_password: Optional[str] = None  # SMPP密码(仅SMPP模式)
    # 计费配置
    payment_type: str = "prepaid"  # prepaid/postpaid
    unit_price: float = 0.05  # 短信单价
    currency: str = "USD"
    # 风控配置
    rate_limit: int = 30  # 发送限速(条/秒)
    smpp_max_binds: int = 5  # SMPP 最大并发绑定数
    ip_whitelist: Optional[List[str]] = None
    low_balance_threshold: Optional[float] = None
    # 绑定配置
    sales_id: Optional[int] = None  # 绑定员工ID
    channel_ids: Optional[List[int]] = None  # 绑定通道ID列表


class AdminAccountUpdateRequest(BaseModel):
    account_name: Optional[str] = None
    tg_username: Optional[str] = None
    country_code: Optional[str] = None  # 国家代码
    business_type: Optional[str] = None  # sms/voice/data
    services: Optional[str] = None  # 开通业务：sms,data 逗号分隔
    # 接入协议
    protocol: Optional[str] = None  # HTTP/SMPP
    smpp_password: Optional[str] = None  # SMPP密码
    # 计费配置
    payment_type: Optional[str] = None  # prepaid/postpaid
    unit_price: Optional[float] = None  # 短信单价
    status: Optional[str] = None
    currency: Optional[str] = None
    # 风控配置
    rate_limit: Optional[int] = None  # 发送限速(条/秒)
    smpp_max_binds: Optional[int] = None  # SMPP 最大并发绑定数
    ip_whitelist: Optional[List[str]] = None
    low_balance_threshold: Optional[float] = None
    # 绑定配置
    sales_id: Optional[int] = None  # 绑定员工ID（传0表示解绑）
    channel_ids: Optional[List[int]] = None  # 绑定通道ID列表
    # 客户门户展示控制（部分销售要求对其客户隐藏敏感项；仅影响客户门户显示）
    hide_price: Optional[bool] = None  # 隐藏客户门户价格(单价/剩余条数估算)
    hide_tg: Optional[bool] = None  # 隐藏客户门户TG(自绑TG卡片+归属商务联系TG)


class AdminAccountBalanceAdjustRequest(BaseModel):
    amount: float
    change_type: Optional[str] = None  # deposit/withdraw/adjustment/refund/charge
    description: Optional[str] = None
    transaction_id: Optional[str] = None


class SalesRechargeRequest(BaseModel):
    """销售用授信额度给自己名下客户充值"""
    amount: float  # 充值金额（>0）
    description: Optional[str] = None
    idempotency_key: Optional[str] = None  # 幂等键，防重复扣款（前端每次弹窗生成一个）


class StaffCreditAdjustRequest(BaseModel):
    """管理员调整销售授信额度：设置额度上限 / 结算冲销（二选一或同时）"""
    credit_limit: Optional[float] = None   # 设为新的额度上限（绝对值，不能低于已用）
    settle_amount: Optional[float] = None  # 结算冲销：减少已用授信（腾出额度）
    description: Optional[str] = None


class AdminAccountResetPasswordRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# 依赖注入 - 使用JWT认证
get_current_admin = AuthService.get_current_admin


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    request: AdminLoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """管理员登录"""
    from app.services.operation_log import log_operation
    username = request.username
    client_ip = _safe_client_ip(http_request)
    logger.info(f"管理员登录: {username}")

    # 查询管理员
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == username)
    )
    admin = result.scalar_one_or_none()

    if not admin:
        await log_operation(
            db, admin_id=None, admin_name=username,
            module="login", action="login",
            title=f"管理员 {username} 登录失败：账号不存在",
            ip_address=client_ip, status="failed",
            error_message="账号不存在",
        )
        return AdminLoginResponse(
            success=False,
            error="invalid_credentials"
        )

    # 检查状态（密码验证前先检查，避免已锁定账户继续累加失败次数）
    if admin.status == "locked":
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="login", action="login",
            title=f"管理员 {admin.username} 登录失败：账号已永久锁定",
            ip_address=client_ip, status="failed",
            error_message="账号已锁定",
        )
        return AdminLoginResponse(
            success=False,
            error="account_locked"
        )

    # 临时锁定（5 次错密自动 15 分钟）：到期自动放行
    now = datetime.now()
    if admin.locked_until is not None:
        if admin.locked_until > now:
            remaining_min = max(1, int((admin.locked_until - now).total_seconds() / 60) + 1)
            await log_operation(
                db, admin_id=admin.id, admin_name=admin.username,
                module="login", action="login",
                title=f"管理员 {admin.username} 登录被临时锁定，剩余 {remaining_min} 分钟",
                ip_address=client_ip, status="failed",
                error_message=f"账号临时锁定中（{remaining_min}分钟后自动解除）",
            )
            await db.commit()
            return AdminLoginResponse(
                success=False,
                error=f"temporarily_locked:{remaining_min}",
            )
        # 锁过期：清掉
        admin.locked_until = None
        admin.login_failed_count = 0

    if admin.status != "active":
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="login", action="login",
            title=f"管理员 {admin.username} 登录失败：账号已停用",
            ip_address=client_ip, status="failed",
            error_message="账号已停用",
        )
        return AdminLoginResponse(
            success=False,
            error="account_disabled"
        )

    # 验证密码
    if not AuthService.verify_password(request.password, admin.password_hash):
        # 锁定策略读自系统配置（max_login_attempts / login_lock_minutes），带下限保护
        from app.core.security_policy import get_int_policy
        max_attempts = await get_int_policy("max_login_attempts", db)
        lock_minutes = await get_int_policy("login_lock_minutes", db)
        admin.login_failed_count += 1
        remaining = max_attempts - admin.login_failed_count
        if admin.login_failed_count >= max_attempts:
            # 时限锁（之前是 status='locked' 永久锁，要 super_admin 手动解）
            admin.locked_until = datetime.now() + timedelta(minutes=lock_minutes)
            admin.login_failed_count = 0
            await log_operation(
                db, admin_id=admin.id, admin_name=admin.username,
                module="login", action="login",
                title=f"管理员 {admin.username} 登录失败：{max_attempts} 次错密 → 临时锁 {lock_minutes} 分钟",
                ip_address=client_ip, status="failed",
                error_message=f"临时锁定 {lock_minutes} 分钟",
            )
            await db.commit()
            return AdminLoginResponse(
                success=False,
                error=f"temporarily_locked:{lock_minutes}",
            )
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="login", action="login",
            title=f"管理员 {admin.username} 登录失败：密码错误，剩余 {remaining} 次",
            ip_address=client_ip, status="failed",
            error_message=f"密码错误，剩余 {remaining} 次机会",
        )
        await db.commit()
        return AdminLoginResponse(
            success=False,
            error=f"invalid_credentials:{remaining}"
        )

    # 更新登录信息
    admin.last_login_at = datetime.now()
    admin.login_failed_count = 0
    admin.locked_until = None  # 成功登录清除遗留临时锁

    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="login", action="login", target_type="admin",
        target_id=str(admin.id), title=f"管理员 {admin.username} 登录成功",
        ip_address=client_ip,
    )
    await db.commit()
    
    logger.info(f"管理员登录成功: {admin.username} ({admin.role})")

    # 生成 access + refresh token 对（refresh 携带 token_version 用于失效检测）
    access_token = AuthService.create_access_token(
        data={"sub": admin.id, "role": admin.role, "username": admin.username},
    )
    refresh_token = AuthService.create_refresh_token(
        data={"sub": admin.id, "tv": int(getattr(admin, "token_version", 1) or 1)}
    )

    return AdminLoginResponse(
        success=True,
        token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        admin_id=admin.id,
        username=admin.username,
        role=admin.role,
    )


@router.post("/auth/refresh", response_model=RefreshTokenResponse)
async def refresh_admin_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    用 refresh token 换新 access token + 新 refresh token（轮换式刷新）。
    旧 refresh token 立即失效（前端必须用新发的 refresh，否则下次刷新会 401）。
    """
    try:
        payload = AuthService.verify_token(request.refresh_token, expected_type="refresh")
    except AuthenticationError as e:
        return RefreshTokenResponse(success=False, error=str(e))

    admin_id = payload.get("sub")
    if not admin_id:
        return RefreshTokenResponse(success=False, error="invalid_subject")

    # 重新读取 admin 当前状态（角色可能已变 / 已禁用）
    res = await db.execute(select(AdminUser).where(AdminUser.id == int(admin_id)))
    admin = res.scalar_one_or_none()
    if not admin or admin.status != "active":
        return RefreshTokenResponse(success=False, error="admin_not_active")

    # 旋转版本校验：refresh token 的 tv 必须等于当前 admin.token_version。
    # 历史 token 没有 tv 字段时按 1 处理；新 token 之后必须严格匹配。
    current_tv = int(getattr(admin, "token_version", 1) or 1)
    token_tv = payload.get("tv")
    if token_tv is None:
        token_tv = 1  # 向后兼容：未带 tv 的老 refresh 视为 v1
    if int(token_tv) != current_tv:
        logger.warning(f"Refresh token 版本已失效: admin={admin.username} tv={token_tv} current={current_tv}")
        return RefreshTokenResponse(success=False, error="refresh_revoked")

    # 旋转：bump token_version，让本次使用的 refresh 立即失效（下次再发同样的 refresh 会被拒）
    admin.token_version = current_tv + 1
    await db.commit()

    new_access = AuthService.create_access_token(
        data={"sub": admin.id, "role": admin.role, "username": admin.username},
    )
    new_refresh = AuthService.create_refresh_token(data={"sub": admin.id, "tv": admin.token_version})

    return RefreshTokenResponse(
        success=True,
        token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/telegram-login/send-code", response_model=dict)
async def telegram_login_send_code(
    request: TelegramSendCodeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Telegram 验证登录 - 发送验证码"""
    import random
    from app.utils.cache import get_redis_client
    from app.services.notification_service import notification_service

    username = (request.username or "").strip()
    if not username:
        return {"success": False, "error": "invalid_username"}

    result = await db.execute(
        select(AdminUser).where(
            AdminUser.username == username,
            AdminUser.status == "active",
        )
    )
    admin = result.scalar_one_or_none()

    if not admin or not admin.tg_id:
        return {"success": False, "error": "account_not_bound"}

    redis_client = await get_redis_client()
    cooldown_key = f"tg_otp_cd:{username}"

    # 60 秒冷却
    if await redis_client.exists(cooldown_key):
        ttl = await redis_client.ttl(cooldown_key)
        return {"success": False, "error": "cooldown", "remaining": max(ttl, 1)}

    code = f"{random.randint(100000, 999999)}"
    otp_key = f"tg_otp:{username}"

    await redis_client.setex(otp_key, 300, code.encode("utf-8"))
    await redis_client.setex(cooldown_key, 60, b"1")

    msg = (
        f"🔐 *考拉出海 登录验证码*\n\n"
        f"验证码: `{code}`\n"
        f"有效期: 5 分钟\n\n"
        f"如非本人操作，请忽略此消息。"
    )
    sent = await notification_service.notify_user(str(admin.tg_id), msg)

    if not sent:
        await redis_client.delete(otp_key)
        await redis_client.delete(cooldown_key)
        return {"success": False, "error": "send_failed"}

    logger.info(f"Telegram 验证码已发送: {username} -> tg_id={admin.tg_id}")
    return {"success": True, "message": "code_sent"}


@router.post("/telegram-login/verify", response_model=AdminLoginResponse)
async def telegram_login_verify(
    request: TelegramVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """Telegram 验证登录 - 校验验证码并登录"""
    from app.utils.cache import get_redis_client

    username = (request.username or "").strip()
    code = (request.code or "").strip()
    if not username or not code or len(code) != 6 or not code.isdigit():
        return AdminLoginResponse(success=False, error="code_invalid")

    # 验证码错误次数限制（防暴力破解）
    redis_client = await get_redis_client()
    verify_fail_key = f"tg_otp_fail:{username}"
    fail_count = await redis_client.get(verify_fail_key)
    if fail_count and int(fail_count) >= 5:
        return AdminLoginResponse(success=False, error="too_many_attempts")

    result = await db.execute(
        select(AdminUser).where(
            AdminUser.username == username,
            AdminUser.status == "active",
        )
    )
    admin = result.scalar_one_or_none()

    if not admin or not admin.tg_id:
        return AdminLoginResponse(success=False, error="tg_not_bound")

    otp_key = f"tg_otp:{username}"
    stored = await redis_client.get(otp_key)

    if not stored:
        return AdminLoginResponse(success=False, error="code_expired")

    if stored.decode("utf-8") != code:
        await redis_client.incr(verify_fail_key)
        if not await redis_client.ttl(verify_fail_key):
            await redis_client.expire(verify_fail_key, 900)  # 15 分钟内 5 次错误则锁定
        return AdminLoginResponse(success=False, error="code_invalid")

    # 验证通过，删除 OTP 和失败计数
    await redis_client.delete(otp_key)
    await redis_client.delete(verify_fail_key)

    admin.last_login_at = datetime.now()
    admin.login_failed_count = 0

    from app.services.operation_log import log_operation
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="login", action="login", target_type="admin",
        target_id=str(admin.id),
        title=f"管理员 {admin.username} 通过 Telegram 验证登录",
    )
    await db.commit()

    logger.info(f"Telegram 验证登录成功: {admin.username} ({admin.role})")

    access_token = AuthService.create_access_token(
        data={"sub": admin.id, "role": admin.role, "username": admin.username},
    )
    refresh_token = AuthService.create_refresh_token(data={"sub": admin.id})

    return AdminLoginResponse(
        success=True,
        token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        admin_id=admin.id,
        username=admin.username,
        role=admin.role,
    )


# --- Admin Profile ---

@router.get("/profile", response_model=dict)
async def get_admin_profile(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取当前管理员个人资料"""
    return {
        "success": True,
        "profile": {
            "id": admin.id,
            "username": admin.username,
            "real_name": admin.real_name,
            "email": admin.email,
            "phone": admin.phone,
            "role": admin.role,
            "tg_id": admin.tg_id,
            "tg_username": admin.tg_username,
            "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
            "created_at": admin.created_at.isoformat() if admin.created_at else None,
        }
    }


@router.post("/profile/change-password", response_model=dict)
async def change_own_password(
    request: ChangePasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """管理员修改自己的密码"""
    if not AuthService.verify_password(request.old_password, admin.password_hash):
        return {"success": False, "error": "old_password_wrong"}

    from app.core.security_policy import get_int_policy
    _min_len = await get_int_policy("password_min_length", db)
    if len(request.new_password) < _min_len:
        return {"success": False, "error": "password_too_short", "min_length": _min_len}

    admin.password_hash = AuthService.hash_password(request.new_password)
    
    from app.services.operation_log import log_operation
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="profile", action="update", target_type="admin",
        target_id=str(admin.id), title=f"管理员 {admin.username} 修改密码",
    )
    await db.commit()
    logger.info(f"管理员 {admin.username} 修改密码成功")
    return {"success": True, "message": "password_changed"}


@router.post("/profile/telegram-bind-code", response_model=dict)
async def generate_telegram_bind_code(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """生成 Telegram 绑定码（管理员在 TG Bot 中发送 /bind <code> 完成绑定）"""
    import random
    from app.utils.cache import get_redis_client

    redis_client = await get_redis_client()

    code = f"{random.randint(100000, 999999)}"
    bind_key = f"tg_bind_code:{code}"
    # 存储 admin_id，有效 5 分钟
    await redis_client.setex(bind_key, 300, str(admin.id).encode("utf-8"))

    logger.info(f"Telegram 绑定码生成: admin={admin.username}, code={code}")
    return {
        "success": True,
        "code": code,
        "expires_in": 300,
    }


@router.post("/profile/telegram-unbind", response_model=dict)
async def unbind_telegram(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """解绑 Telegram"""
    if not admin.tg_id:
        return {"success": False, "error": "not_bound"}

    old_tg_id = admin.tg_id
    admin.tg_id = None
    admin.tg_username = None

    from app.services.operation_log import log_operation
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="profile", action="update", target_type="admin",
        target_id=str(admin.id),
        title=f"管理员 {admin.username} 解绑 Telegram (tg_id={old_tg_id})",
    )
    await db.commit()
    logger.info(f"管理员 {admin.username} 解绑 Telegram: tg_id={old_tg_id}")
    return {"success": True, "message": "unbound"}


# --- Accounts (Admin) ---

@router.get("/accounts", response_model=dict)
async def list_accounts_admin(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    business_type: Optional[str] = None,
    sales_id: Optional[int] = None,
    tg_username: Optional[str] = None,
    country_codes: Optional[str] = Query(
        None,
        description="逗号分隔 ISO 国码，匹配账户 country_code",
    ),
    channel_keyword: Optional[str] = Query(
        None,
        description="通道编码或名称模糊匹配（账户已绑定的通道）",
    ),
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：获取账户列表（支持按员工、TG、国家、通道等筛选）"""
    from sqlalchemy import func, or_, and_, exists, case
    import json

    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    # 销售角色只能看到自己名下的客户
    if is_sales_scoped(admin):
        sales_id = admin.id

    where_clauses = [Account.is_deleted == False]
    if status:
        where_clauses.append(Account.status == status)
    if business_type:
        where_clauses.append(Account.business_type == business_type)
    if sales_id is not None:
        where_clauses.append(Account.sales_id == sales_id)
    if keyword:
        kw = f"%{keyword.strip()}%"
        where_clauses.append(or_(Account.email.like(kw), Account.account_name.like(kw)))
    if tg_username and tg_username.strip():
        tg = tg_username.strip().lstrip("@")
        if tg:
            tg_kw = f"%{tg.lower()}%"
            where_clauses.append(func.lower(Account.tg_username).like(tg_kw))
    if country_codes and country_codes.strip():
        codes = [x.strip().upper() for x in country_codes.split(",") if x.strip()]
        if codes:
            cc_col = func.upper(func.trim(Account.country_code))
            where_clauses.append(or_(*[cc_col == c for c in codes]))
    if channel_keyword and channel_keyword.strip():
        from app.modules.common.account import AccountChannel
        from app.modules.sms.channel import Channel

        ck = f"%{channel_keyword.strip().lower()}%"
        ch_exists = exists().where(
            AccountChannel.account_id == Account.id,
            AccountChannel.channel_id == Channel.id,
            or_(
                func.lower(Channel.channel_code).like(ck),
                func.lower(Channel.channel_name).like(ck),
            ),
        )
        where_clauses.append(ch_exists)

    where_expr = and_(*where_clauses)

    # 全表统计（按相同筛选条件，不受分页影响）
    stats_result = await db.execute(
        select(
            func.count(Account.id),
            func.coalesce(func.sum(Account.balance), 0),
            func.sum(case((Account.status == "active", 1), else_=0)),
            func.sum(case((Account.sales_id.isnot(None), 1), else_=0)),
        ).where(where_expr)
    )
    total, total_balance, active_count, bound_sales_count = stats_result.one()
    total = total or 0
    total_balance = float(total_balance or 0)
    active_count = int(active_count or 0)
    bound_sales_count = int(bound_sales_count or 0)

    from sqlalchemy.orm import selectinload, joinedload
    from app.modules.common.account import AccountChannel
    
    result = await db.execute(
        select(Account)
        .options(
            selectinload(Account.sales),
            selectinload(Account.account_channels).joinedload(AccountChannel.channel),
        )
        .where(where_expr)
        .order_by(Account.created_at.desc())
        .limit(safe_limit)
        .offset(safe_offset)
    )
    accounts = result.scalars().all()

    def _parse_whitelist(raw: Optional[str]):
        if not raw:
            return []
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except Exception:
            return []

    return {
        "success": True,
        "total": total,
        "total_balance": total_balance,
        "active_count": active_count,
        "bound_sales_count": bound_sales_count,
        "accounts": [
            {
                "id": a.id,
                "account_name": a.account_name,
                "email": a.email,
                "tg_username": a.tg_username,
                "tg_id": a.tg_id,
                "country_code": a.country_code,
                "business_type": a.business_type or "sms",
                # 接入协议
                "protocol": getattr(a, 'protocol', None) or "HTTP",
                # 计费配置
                "payment_type": a.payment_type or "prepaid",
                "unit_price": float(a.unit_price) if a.unit_price is not None else None,
                "status": a.status,
                "balance": float(a.balance or 0),
                "currency": a.currency,
                # 风控配置
                "low_balance_threshold": float(a.low_balance_threshold) if a.low_balance_threshold is not None else None,
                "rate_limit": a.rate_limit,
                "ip_whitelist": _parse_whitelist(a.ip_whitelist),
                "api_key": a.api_key,
                # 绑定配置
                "sales": {
                    "id": a.sales.id if a.sales else None,
                    "username": a.sales.username if a.sales else None,
                    "real_name": a.sales.real_name if a.sales else None,
                    "email": a.sales.email if a.sales else None
                } if a.sales else None,
                "sales_id": a.sales_id,
                # 仅"全国默认"绑定(country_code 为空)进入通道列；按国家专属绑定在「国家路由」里单独管理。
                # 默认绑定为空 = 可用全部通道(走全局路由)，前端显示为 *
                "channels": [
                    {"id": ac.channel.id, "channel_code": ac.channel.channel_code}
                    for ac in (a.account_channels or [])
                    if ac.channel and ac.country_code is None
                ] if a.account_channels else [],
                "supplier_url": a.supplier_url,
                "supplier_credentials": a.supplier_credentials if a.supplier_credentials else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None,
                "activity_score": a.activity_score,
            }
            for a in accounts
        ],
    }


@router.post("/accounts", response_model=dict)
async def create_account_admin(
    request: AdminAccountCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：创建账户（返回 API Key/Secret 一次）"""
    from app.modules.common.account import Account, AccountChannel
    import secrets
    import json
    import uuid

    if is_sales_scoped(admin):
        raise HTTPException(status_code=403, detail="销售人员无权新建客户账户")

    from app.core.security_policy import get_int_policy
    _min_len = await get_int_policy("password_min_length", db)
    if len(request.password) < _min_len:
        raise HTTPException(status_code=400, detail=f"密码长度至少 {_min_len} 位")

    # 检查账户名是否已被未删除的账户使用
    _dup = await db.execute(
        select(Account.id).where(Account.account_name == request.account_name, Account.is_deleted == False)
    )
    if _dup.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"账户名 '{request.account_name}' 已存在，请使用其他名称")

    # 生成唯一邮箱（内部使用）
    unique_email = f"{uuid.uuid4().hex[:12]}@internal.sms"

    # 生成API Key/Secret（注意长度限制）
    api_key = f"ak_{secrets.token_hex(30)}"  # <= 64
    api_secret = _gen_api_secret()  # 8 位无歧义接口密码
    
    # 生成SMPP System ID (如果是SMPP协议)
    smpp_system_id = None
    smpp_password = None
    if request.protocol == "SMPP":
        smpp_system_id = f"SM{secrets.token_hex(3).upper()}"
        smpp_password = request.smpp_password or secrets.token_hex(8)

    ip_whitelist_raw = None
    if request.ip_whitelist is not None:
        ip_whitelist_raw = json.dumps(request.ip_whitelist, ensure_ascii=False)

    # 新开短信账户默认赠送 1 USD
    initial_balance = 1.0 if request.business_type == 'sms' else 0.0

    new_account = Account(
        account_name=request.account_name,
        email=unique_email,
        tg_username=request.tg_username,
        country_code=request.country_code,
        business_type=request.business_type,
        protocol=request.protocol,
        smpp_system_id=smpp_system_id,
        smpp_password=smpp_password,
        payment_type=request.payment_type,
        unit_price=request.unit_price,
        password_hash=AuthService.hash_password(request.password),
        balance=initial_balance,
        currency=request.currency,
        status="active",
        api_key=api_key,
        api_secret=api_secret,
        ip_whitelist=ip_whitelist_raw,
        rate_limit=request.rate_limit,
        smpp_max_binds=request.smpp_max_binds,
        low_balance_threshold=request.low_balance_threshold,
        created_by=admin.id,
        sales_id=request.sales_id,
    )

    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="account", action="create", target_type="account",
        target_id=str(new_account.id),
        title=f"创建客户账户 {request.account_name}",
        detail=f'{{"account_id": {new_account.id}, "business_type": "{request.business_type}", "protocol": "{request.protocol}"}}',
    )

    # 新开短信账户赠送 1U：记录余额日志
    if initial_balance > 0:
        from app.modules.common.balance_log import BalanceLog
        db.add(BalanceLog(
            account_id=new_account.id,
            change_type='deposit',
            amount=initial_balance,
            balance_after=initial_balance,
            description='新开短信账户赠送',
        ))
        await db.commit()

    # 绑定通道
    if request.channel_ids:
        for idx, channel_id in enumerate(request.channel_ids):
            account_channel = AccountChannel(
                account_id=new_account.id,
                channel_id=channel_id,
                is_default=(idx == 0),
                priority=idx
            )
            db.add(account_channel)
        await db.commit()

    # 自动创建数据账户（国家与主账户一致）并开通 data 服务
    try:
        from app.modules.data.data_account import DataAccount
        da = DataAccount(
            account_id=new_account.id,
            country_code=request.country_code or "",
            balance=0,
            total_extracted=0,
            total_spent=0,
            status="active",
        )
        db.add(da)
        svc = new_account.services or "sms"
        svc_list = [s.strip() for s in svc.split(",") if s.strip()]
        if "data" not in svc_list:
            svc_list.append("data")
            new_account.services = ",".join(svc_list)
        await db.commit()
    except Exception as e:
        logger.warning(f"自动创建数据账户失败: {e}")

    result = {
        "success": True,
        "account_id": new_account.id,
        "protocol": request.protocol,
        "message": "Account created successfully",
    }
    
    # 根据协议返回不同凭证
    if request.protocol == "SMPP":
        result["smpp_system_id"] = smpp_system_id
        result["smpp_password"] = smpp_password
    else:
        result["api_key"] = api_key
        result["api_secret"] = api_secret
    
    return result


@router.get("/accounts/{account_id}", response_model=dict)
async def get_account_admin(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：获取账户详情"""
    from app.modules.common.account import Account, AccountChannel
    from app.modules.sms.channel import Channel
    import json

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    if is_sales_scoped(admin) and a.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="只能查看自己名下的客户")

    try:
        whitelist = json.loads(a.ip_whitelist) if a.ip_whitelist else []
        if not isinstance(whitelist, list):
            whitelist = []
    except Exception:
        whitelist = []

    # 获取绑定的通道（仅"全国默认"绑定 country_code 为空；按国家专属绑定由「国家路由」管理，不进编辑表单的通道多选）
    channel_result = await db.execute(
        select(AccountChannel, Channel)
        .join(Channel, AccountChannel.channel_id == Channel.id)
        .where(AccountChannel.account_id == account_id, AccountChannel.country_code.is_(None))
        .order_by(AccountChannel.priority)
    )
    channel_rows = channel_result.all()
    channels = [
        {
            "id": ch.id,
            "channel_code": ch.channel_code,
            "channel_name": ch.channel_name,
            "protocol": ch.protocol,
            "is_default": ac.is_default
        }
        for ac, ch in channel_rows
    ]

    from app.config import settings
    api_base = (settings.PUBLIC_WEB_BASE_URL or "https://www.kaolach.com").rstrip("/")

    return {
        "success": True,
        "account": {
            "id": a.id,
            "account_name": a.account_name,
            "email": a.email,
            "tg_username": a.tg_username,
            "country_code": a.country_code,
            "business_type": a.business_type or "sms",
            # 接入协议
            "protocol": getattr(a, 'protocol', None) or "HTTP",
            "smpp_system_id": getattr(a, 'smpp_system_id', None),
            "smpp_password": getattr(a, 'smpp_password', None),
            # 计费配置
            "payment_type": a.payment_type or "prepaid",
            "unit_price": float(a.unit_price) if a.unit_price is not None else None,
            "status": a.status,
            "balance": float(a.balance or 0),
            "currency": a.currency,
            # 风控配置
            "low_balance_threshold": float(a.low_balance_threshold) if a.low_balance_threshold is not None else None,
            "rate_limit": a.rate_limit,
            "smpp_max_binds": a.smpp_max_binds if a.smpp_max_binds is not None else 5,
            "ip_whitelist": whitelist,
            # API凭证：账号摘要需把接口密码原文给管理员转交客户（与 api_key 一致全显）；
            # 接口为管理员鉴权，客户做 Basic Auth 必须用完整 api_secret，打码会导致无法使用
            "api_key": a.api_key,
            "api_secret": a.api_secret,
            # 绑定配置
            "sales_id": a.sales_id,
            "channels": channels,
            "channel_ids": [ch["id"] for ch in channels],
            # 客户门户展示控制
            "hide_price": bool(getattr(a, "hide_price", False)),
            "hide_tg": bool(getattr(a, "hide_tg", False)),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            # 平台对接配置
            "api_base_url": f"{api_base}/api/v1",
            "smpp_server_host": settings.SMPP_SERVER_HOST,
            "smpp_server_port": settings.SMPP_SERVER_PORT,
        },
    }


@router.put("/accounts/{account_id}", response_model=dict)
async def update_account_admin(
    account_id: int,
    request: AdminAccountUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：更新账户信息（不含密码/API Key）"""
    from app.modules.common.account import Account, AccountChannel
    import json
    import secrets

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    # 显式提供的字段集合（区分"传了 null=清空" 与 "未传=不变"）
    provided = request.model_dump(exclude_unset=True)

    # 销售人员：仅可修改名下客户的在用/已暂停状态（停用/启用），不可改其他信息
    if is_sales_scoped(admin):
        if a.sales_id != admin.id:
            raise HTTPException(status_code=403, detail="只能操作自己名下的客户")
        payload = request.model_dump(exclude_unset=True)
        if not payload:
            raise HTTPException(status_code=400, detail="无更新字段")
        if set(payload.keys()) != {"status"}:
            raise HTTPException(status_code=403, detail="销售人员仅可修改客户状态（停用/启用）")
        st = payload.get("status")
        if st not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="销售仅可在「在用」与「已暂停」之间切换")
        a.status = st
        await db.commit()
        return {"success": True, "message": "Account updated successfully"}

    if request.account_name is not None:
        a.account_name = request.account_name
    if request.tg_username is not None:
        a.tg_username = request.tg_username
    if request.country_code is not None:
        # 空串视为"清空国家限制"（改为多国/不限），统一存 NULL
        a.country_code = request.country_code or None
    if request.business_type is not None:
        a.business_type = request.business_type
    if request.services is not None:
        a.services = request.services
    # 接入协议
    if request.protocol is not None:
        a.protocol = request.protocol
        # 如果切换到SMPP且没有system_id，自动生成
        if request.protocol == "SMPP" and not a.smpp_system_id:
            a.smpp_system_id = f"SM{secrets.token_hex(3).upper()}"
            a.smpp_password = request.smpp_password or secrets.token_hex(8)
    if request.smpp_password is not None and a.protocol == "SMPP":
        a.smpp_password = request.smpp_password
    # 计费配置
    if request.payment_type is not None:
        a.payment_type = request.payment_type
    # 统一单价：显式提供即生效；传 null 表示"清空统一单价"→ 回退到账户国家定价/全局价
    if 'unit_price' in provided:
        a.unit_price = request.unit_price
    if request.status is not None:
        a.status = request.status
    if request.currency is not None:
        a.currency = request.currency
    # 风控配置
    if request.rate_limit is not None:
        a.rate_limit = request.rate_limit
    if request.smpp_max_binds is not None:
        a.smpp_max_binds = max(1, request.smpp_max_binds)
    if request.low_balance_threshold is not None:
        a.low_balance_threshold = request.low_balance_threshold
    if request.ip_whitelist is not None:
        a.ip_whitelist = json.dumps(request.ip_whitelist, ensure_ascii=False)
    # 客户门户展示控制（管理员专属；销售侧在上方已被限制仅可改 status）
    if request.hide_price is not None:
        a.hide_price = request.hide_price
    if request.hide_tg is not None:
        a.hide_tg = request.hide_tg

    # 更新绑定员工
    if request.sales_id is not None:
        a.sales_id = request.sales_id if request.sales_id > 0 else None
    
    # 更新绑定通道（仅管理"全国默认"绑定：country_code 为空；按国家专属绑定由「国家路由」端点单独管理，勿在此误删）
    if request.channel_ids is not None:
        # 删除旧的默认绑定
        await db.execute(
            AccountChannel.__table__.delete().where(
                AccountChannel.account_id == account_id,
                AccountChannel.country_code.is_(None),
            )
        )
        # 添加新的默认绑定
        for idx, channel_id in enumerate(request.channel_ids):
            account_channel = AccountChannel(
                account_id=account_id,
                channel_id=channel_id,
                country_code=None,
                is_default=(idx == 0),
                priority=idx
            )
            db.add(account_channel)

    await db.commit()

    from app.services.operation_log import log_operation as _log_op
    updated_fields = request.model_dump(exclude_unset=True, exclude_none=True)
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="account", action="update", target_type="account",
        target_id=str(account_id),
        title=f"更新客户账户 #{account_id}",
        detail=str(list(updated_fields.keys())),
    )

    # 统一单价或通道变化时清除该账户售价缓存，否则买即发/发送仍可能按旧价计费
    if request.unit_price is not None or request.channel_ids is not None:
        try:
            from app.utils.cache import get_cache_manager
            cache_manager = await get_cache_manager()
            await cache_manager.invalidate_price_cache_for_account(account_id)
        except Exception:
            pass

    return {"success": True, "message": "Account updated successfully"}


# ==================== 账户「国家路由与报价」（代理商批发：每账户每国家指定通道+销售价） ====================

class CountryRouteItem(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=10, description="国家代码(ISO2，如 US)")
    channel_id: int = Field(..., description="该国家路由到的上游通道ID")
    price: Optional[float] = Field(None, ge=0, description="该国家销售单价(USD/条)；留空=不覆盖，回退通道/全局价")


class CountryRoutesRequest(BaseModel):
    routes: List[CountryRouteItem] = Field(default_factory=list)


@router.get("/accounts/{account_id}/country-routes", response_model=dict)
async def get_account_country_routes(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取账户的「国家路由与报价」：每个国家 → 通道 + 销售价。"""
    from app.modules.common.account import Account, AccountChannel
    from app.modules.common.account_pricing import AccountPricing
    from app.modules.sms.channel import Channel
    from app.utils.country_code import normalize_country_code

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Account not found")

    rows = await db.execute(
        select(
            AccountChannel.country_code, AccountChannel.channel_id,
            Channel.channel_code, Channel.channel_name,
        )
        .join(Channel, Channel.id == AccountChannel.channel_id)
        .where(AccountChannel.account_id == account_id, AccountChannel.country_code.isnot(None))
        .order_by(AccountChannel.country_code)
    )
    price_rows = await db.execute(
        select(AccountPricing.country_code, AccountPricing.price).where(
            AccountPricing.account_id == account_id,
            AccountPricing.business_type == 'sms',
        )
    )
    price_map = {normalize_country_code(cc): float(p) for cc, p in price_rows.all()}

    routes = []
    for cc, ch_id, ch_code, ch_name in rows.all():
        iso = normalize_country_code(cc)
        routes.append({
            "country_code": iso,
            "channel_id": ch_id,
            "channel_code": ch_code,
            "channel_name": ch_name,
            "price": price_map.get(iso),
        })
    return {"success": True, "routes": routes}


@router.put("/accounts/{account_id}/country-routes", response_model=dict)
async def set_account_country_routes(
    account_id: int,
    request: CountryRoutesRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """整表替换账户「国家路由与报价」（每条 = 国家 + 通道 + 可选销售价）。

    - account_channels：替换该账户所有 country_code 非空（按国家）的绑定
    - account_pricing：替换该账户 business_type='sms' 的国家定价（仅写入提供了 price 的条目）
    - 不影响该账户的「全国默认」通道绑定(country_code 为空) 与账户统一单价
    """
    from app.modules.common.account import Account, AccountChannel
    from app.modules.common.account_pricing import AccountPricing
    from app.modules.sms.channel import Channel
    from app.utils.country_code import normalize_country_code

    if is_sales_scoped(admin):
        raise HTTPException(status_code=403, detail="销售人员无权配置账户路由")

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Account not found")

    # 规范化 + 去重
    norm_routes = []
    seen = set()
    for it in request.routes:
        iso = normalize_country_code(it.country_code)
        if not iso:
            raise HTTPException(status_code=400, detail=f"无效国家代码: {it.country_code}")
        if iso in seen:
            raise HTTPException(status_code=400, detail=f"国家重复配置: {iso}")
        seen.add(iso)
        norm_routes.append((iso, it.channel_id, it.price))

    # 校验通道存在
    if norm_routes:
        ch_ids = {r[1] for r in norm_routes}
        ch_res = await db.execute(
            select(Channel.id).where(Channel.id.in_(ch_ids), Channel.is_deleted == False)
        )
        valid = {r[0] for r in ch_res.all()}
        missing = ch_ids - valid
        if missing:
            raise HTTPException(status_code=400, detail=f"通道不存在或已删除: {sorted(missing)}")

    # 替换按国家通道绑定（仅 country_code 非空）
    await db.execute(
        AccountChannel.__table__.delete().where(
            AccountChannel.account_id == account_id,
            AccountChannel.country_code.isnot(None),
        )
    )
    # 替换账户国家定价（business_type='sms'）
    await db.execute(
        AccountPricing.__table__.delete().where(
            AccountPricing.account_id == account_id,
            AccountPricing.business_type == 'sms',
        )
    )
    for iso, ch_id, price in norm_routes:
        db.add(AccountChannel(
            account_id=account_id, channel_id=ch_id, country_code=iso,
            is_default=False, priority=0,
        ))
        if price is not None:
            db.add(AccountPricing(
                account_id=account_id, country_code=iso,
                business_type='sms', price=price,
            ))

    await db.commit()

    try:
        from app.utils.cache import get_cache_manager
        cm = await get_cache_manager()
        await cm.invalidate_price_cache_for_account(account_id)
    except Exception:
        pass

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="account", action="update", target_type="account",
        target_id=str(account_id),
        title=f"配置账户国家路由 #{account_id}",
        detail=f"{len(norm_routes)} 国: " + ",".join(r[0] for r in norm_routes),
    )
    return {"success": True, "message": f"已保存 {len(norm_routes)} 个国家路由", "count": len(norm_routes)}


@router.post("/accounts/{account_id}/generate-password", response_model=dict)
async def generate_account_password(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：仅生成/重置接口密码（不动 API Key）"""
    from app.modules.common.account import Account
    import secrets

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    if is_sales_scoped(admin):
        raise HTTPException(status_code=403, detail="销售人员无权生成接口密码")

    a.api_secret = _gen_api_secret()  # 8 位无歧义接口密码
    await db.commit()

    return {
        "success": True,
        "api_secret": a.api_secret,
    }


@router.post("/accounts/{account_id}/reset-api-key", response_model=dict)
async def reset_account_api_key(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：重置 API Key/Secret（返回一次）"""
    from app.modules.common.account import Account
    import secrets

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    if is_sales_scoped(admin):
        raise HTTPException(status_code=403, detail="销售人员无权重置 API Key")

    a.api_key = f"ak_{secrets.token_hex(30)}"
    a.api_secret = _gen_api_secret()  # 8 位无歧义接口密码
    await db.commit()

    return {
        "success": True,
        "api_key": a.api_key,
        "api_secret": a.api_secret,
        "message": "API credentials reset successfully",
    }


class TelegramSalesImpersonateBody(BaseModel):
    """TG 业务助手：销售快捷登录客户"""

    tg_id: int
    account_id: int


async def _create_impersonate_token(account) -> str:
    """生成一次性模拟登录 token（Redis TTL 90s）"""
    import json as _json
    import secrets as _secrets
    from app.utils.cache import get_redis_client
    token = _secrets.token_urlsafe(32)
    redis = await get_redis_client()
    payload = _json.dumps({
        "api_key": account.api_key,
        "account_id": account.id,
        "account_name": account.account_name,
    })
    await redis.set(f"impersonate:{token}", payload, ex=90)
    return token


@router.post("/telegram/sales-impersonate", response_model=dict)
async def telegram_sales_impersonate(
    body: TelegramSalesImpersonateBody,
    db: AsyncSession = Depends(get_db),
    x_telegram_staff_secret: Optional[str] = Header(None, alias="X-Telegram-Staff-Secret"),
):
    """
    供 Telegram Bot 调用：校验共享密钥后，按 TG 用户解析员工身份，
    仅允许销售登录其名下客户（与网页端模拟登录规则一致）。
    """
    from app.modules.common.account import Account

    secret = (settings.TELEGRAM_STAFF_API_SECRET or "").strip()
    import hmac as _hmac_mod
    if not secret or not x_telegram_staff_secret or not _hmac_mod.compare_digest(x_telegram_staff_secret, secret):
        raise HTTPException(status_code=403, detail="Invalid or missing staff secret")

    result = await db.execute(
        select(AdminUser).where(
            AdminUser.tg_id == body.tg_id,
            AdminUser.status == "active",
        )
    )
    staff = result.scalar_one_or_none()
    if not staff or staff.role != "sales":
        raise HTTPException(status_code=403, detail="仅销售可使用快捷登录客户")

    acc_r = await db.execute(
        select(Account).where(
            Account.id == body.account_id,
            Account.is_deleted == False,
        )
    )
    a = acc_r.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")
    if a.status != "active":
        raise HTTPException(status_code=400, detail="Account is not active")
    if a.sales_id != staff.id:
        raise HTTPException(status_code=403, detail="只能登录您名下的客户")

    base = (settings.PUBLIC_WEB_BASE_URL or "https://www.kaolach.com").rstrip("/")
    imp_token = await _create_impersonate_token(a)
    login_url = f"{base}/login?impersonate=1&token={imp_token}"

    return {
        "success": True,
        "account_id": a.id,
        "account_name": a.account_name,
        "api_key": a.api_key,
        "login_url": login_url,
        "message": "ok",
    }


@router.post("/accounts/{account_id}/impersonate", response_model=dict)
async def impersonate_account(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：模拟登录客户账户（获取临时凭证）"""
    from app.modules.common.account import Account

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    if a.status != "active":
        raise HTTPException(status_code=400, detail="Account is not active")

    # 销售仅能模拟自己名下的客户
    if is_sales_scoped(admin) and a.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="只能模拟登录自己名下的客户")

    base = (settings.PUBLIC_WEB_BASE_URL or "https://www.kaolach.com").rstrip("/")
    imp_token = await _create_impersonate_token(a)
    login_url = f"{base}/login?impersonate=1&token={imp_token}"

    return {
        "success": True,
        "account_id": a.id,
        "account_name": a.account_name,
        "api_key": a.api_key,
        "login_url": login_url,
        "message": f"Impersonating account: {a.account_name}",
    }


@router.get("/auth/impersonate-exchange/{token}", response_model=dict)
async def impersonate_exchange(token: str):
    """凭一次性 token 换取模拟登录凭证（TTL 90s，使用后立即删除）"""
    from app.utils.cache import get_redis_client
    import json as _json
    redis = await get_redis_client()
    key = f"impersonate:{token}"
    raw = await redis.getdel(key)
    if not raw:
        raise HTTPException(status_code=404, detail="token 无效或已过期")
    data = _json.loads(raw)
    return {"success": True, **data}


@router.post("/accounts/{account_id}/reset-password", response_model=dict)
async def reset_account_password(
    account_id: int,
    request: AdminAccountResetPasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：重置账户密码"""
    from app.modules.common.account import Account
    from app.core.security_policy import get_int_policy

    _min_len = await get_int_policy("password_min_length", db)
    if len(request.password) < _min_len:
        raise HTTPException(status_code=400, detail=f"密码长度至少 {_min_len} 位")

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    if is_sales_scoped(admin) and a.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="只能为自己名下的客户重置密码")

    a.password_hash = AuthService.hash_password(request.password)
    await db.commit()

    return {"success": True, "message": "Password reset successfully"}


@router.post("/accounts/{account_id}/balance/adjust", response_model=dict)
async def adjust_account_balance(
    account_id: int,
    request: AdminAccountBalanceAdjustRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：充值/扣减/调账（写入 balance_logs）"""
    from app.modules.common.account import Account
    from app.modules.common.balance_log import BalanceLog
    from decimal import Decimal

    amount = Decimal(str(request.amount))
    if amount == 0:
        raise HTTPException(status_code=400, detail="Amount cannot be zero")

    allowed_types = {"charge", "refund", "deposit", "withdraw", "adjustment", "refund_recharge"}
    change_type = request.change_type
    if not change_type:
        change_type = "deposit" if amount > 0 else "withdraw"
    if change_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid change_type")

    # 按类型强制符号：扣减类型始终为负，充值类型始终为正
    if change_type in {"withdraw"} and amount > 0:
        amount = -amount
    elif change_type in {"deposit", "refund_recharge"} and amount < 0:
        amount = -amount

    if is_sales_scoped(admin):
        raise HTTPException(status_code=403, detail="销售人员无权为客户充值或调账")

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    balance_before = Decimal(str(a.balance or 0))
    balance_after = balance_before + amount
    if balance_after < 0:
        raise HTTPException(status_code=400, detail="Balance cannot be negative")

    a.balance = balance_after
    
    # 构建描述信息
    desc_parts = [request.description] if request.description else []
    if request.transaction_id:
        desc_parts.append(f"Transaction ID: {request.transaction_id}")
    desc_parts.append(f"Admin({admin.username}) balance adjust ({a.currency})")
    description = " | ".join(desc_parts)
    
    log = BalanceLog(
        account_id=account_id,
        change_type=change_type,
        amount=amount,
        balance_after=balance_after,
        description=description
    )
    db.add(log)
    await db.commit()

    from app.services.operation_log import log_operation as _log_op
    sign = "+" if amount > 0 else ""
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="finance", action="update", target_type="account",
        target_id=str(account_id),
        title=f"余额调整 账户#{account_id} {sign}{float(amount)} {a.currency}（{change_type}）",
        detail=f'{{"change_type": "{change_type}", "amount": {float(amount)}, "balance_before": {float(balance_before)}, "balance_after": {float(balance_after)}}}',
    )

    return {
        "success": True,
        "balance_before": float(balance_before),
        "balance_after": float(balance_after),
    }


@router.post("/accounts/{account_id}/sales-recharge", response_model=dict)
async def sales_recharge_account(
    account_id: int,
    request: SalesRechargeRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """销售：用授信额度给自己名下客户充值（扣减授信 + 加客户余额，原子+行锁+幂等）"""
    from app.modules.common.account import Account
    from app.modules.common.balance_log import BalanceLog
    from app.modules.common.sales_credit_log import SalesCreditLog
    from sqlalchemy.exc import IntegrityError
    from decimal import Decimal

    if not is_sales_scoped(admin):
        raise HTTPException(status_code=403, detail="该接口仅供销售使用；管理员请用余额调整")

    amount = Decimal(str(request.amount))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于 0")
    idem = (request.idempotency_key or "").strip() or None

    def _summary(prior: "SalesCreditLog") -> dict:
        return {
            "success": True,
            "duplicate": True,
            "credit_limit_after": float(prior.credit_limit_after),
            "credit_used_after": float(prior.credit_used_after),
            "credit_available": float(Decimal(str(prior.credit_limit_after)) - Decimal(str(prior.credit_used_after))),
        }

    # 幂等：同一 key 已处理则直接回放，不重复扣款
    if idem:
        prior = (await db.execute(
            select(SalesCreditLog).where(SalesCreditLog.idempotency_key == idem)
        )).scalar_one_or_none()
        if prior:
            return _summary(prior)

    # 固定加锁顺序（先销售后账户）防死锁；SELECT ... FOR UPDATE 串行化并发充值
    me = (await db.execute(
        select(AdminUser).where(AdminUser.id == admin.id).with_for_update()
    )).scalar_one()
    acc = (await db.execute(
        select(Account).where(Account.id == account_id, Account.is_deleted == False).with_for_update()
    )).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="客户不存在")
    if acc.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="只能给自己名下的客户充值")

    credit_limit = Decimal(str(me.credit_limit or 0))
    credit_used = Decimal(str(me.credit_used or 0))
    available = credit_limit - credit_used
    if amount > available:
        raise HTTPException(
            status_code=400,
            detail=f"授信额度不足：可用 {float(available)}，本次需 {float(amount)}",
        )

    balance_before = Decimal(str(acc.balance or 0))
    balance_after = balance_before + amount
    acc.balance = balance_after
    credit_used_after = credit_used + amount
    me.credit_used = credit_used_after

    note = (request.description or "").strip()
    blog = BalanceLog(
        account_id=account_id,
        change_type="sales_credit",
        amount=amount,
        balance_after=balance_after,
        description=f"销售({admin.username})授信充值 +{float(amount)} {acc.currency}"
        + (f" | {note}" if note else ""),
    )
    db.add(blog)
    await db.flush()  # 取 blog.id 关联进授信账本

    clog = SalesCreditLog(
        sales_id=admin.id,
        change_type="recharge",
        amount=amount,
        credit_limit_after=credit_limit,
        credit_used_after=credit_used_after,
        account_id=account_id,
        related_balance_log_id=blog.id,
        operator_id=admin.id,
        operator_name=admin.username,
        idempotency_key=idem,
        description=note or None,
    )
    db.add(clog)
    try:
        await db.commit()
    except IntegrityError:
        # 幂等键唯一冲突=并发重复提交，回滚后回放已处理结果
        await db.rollback()
        if idem:
            prior = (await db.execute(
                select(SalesCreditLog).where(SalesCreditLog.idempotency_key == idem)
            )).scalar_one_or_none()
            if prior:
                return _summary(prior)
        raise

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="finance", action="recharge", target_type="account",
        target_id=str(account_id),
        title=f"销售授信充值 账户#{account_id} +{float(amount)} {acc.currency}",
        detail=f'{{"amount": {float(amount)}, "balance_after": {float(balance_after)}, "credit_used_after": {float(credit_used_after)}}}',
    )

    return {
        "success": True,
        "balance_before": float(balance_before),
        "balance_after": float(balance_after),
        "credit_limit_after": float(credit_limit),
        "credit_used_after": float(credit_used_after),
        "credit_available": float(credit_limit - credit_used_after),
    }


@router.get("/accounts/{account_id}/balance-logs", response_model=dict)
async def list_balance_logs_admin(
    account_id: int,
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：余额变动记录"""
    from app.modules.common.balance_log import BalanceLog
    from sqlalchemy import func

    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    await _ensure_account_access_for_sales(account_id, admin, db)

    total_result = await db.execute(
        select(func.count(BalanceLog.id)).where(BalanceLog.account_id == account_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(BalanceLog)
        .where(BalanceLog.account_id == account_id)
        .order_by(BalanceLog.created_at.desc())
        .limit(safe_limit)
        .offset(safe_offset)
    )
    logs = result.scalars().all()

    return {
        "success": True,
        "total": total,
        "logs": [
            {
                "id": l.id,
                "change_type": l.change_type,
                "amount": float(l.amount),
                "balance_before": float(l.balance_after or 0) - float(l.amount),
                "balance_after": float(l.balance_after),
                "description": l.description,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


async def _ensure_account_access_for_sales(
    account_id: int, admin: AdminUser, db: AsyncSession
) -> None:
    """销售仅能访问自己名下的账户相关接口。"""
    if admin.role != "sales":
        return
    from app.modules.common.account import Account

    r = await db.execute(
        select(Account.id).where(
            Account.id == account_id,
            Account.is_deleted == False,
            Account.sales_id == admin.id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="只能操作自己名下的客户")


@router.get("/recharge-logs", response_model=dict)
async def list_recharge_logs_admin(
    account_id: Optional[int] = Query(None, description="客户账户ID"),
    sales_id: Optional[int] = Query(None, description="归属销售ID"),
    change_type: Optional[str] = Query(None, description="变动类型: deposit/withdraw/refund_recharge"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """充值记录查询（含退补充值，退补充值不计算业绩/成本）"""
    from app.modules.common.balance_log import BalanceLog
    from sqlalchemy import func, and_
    # 充值相关类型（sales_credit=销售授信充值，与现金 deposit 区分展示）
    recharge_types = ["deposit", "withdraw", "refund_recharge", "sales_credit"]
    if change_type:
        recharge_types = [change_type] if change_type in recharge_types else []

    query = select(BalanceLog, Account).join(Account, BalanceLog.account_id == Account.id).where(BalanceLog.change_type.in_(recharge_types))
    if account_id:
        query = query.where(BalanceLog.account_id == account_id)
    if sales_id:
        query = query.where(Account.sales_id == sales_id)
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            query = query.where(BalanceLog.created_at >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
            query = query.where(BalanceLog.created_at < end_dt)
        except ValueError:
            pass

    # 先查总数
    count_q = select(func.count(BalanceLog.id)).select_from(BalanceLog).join(Account, BalanceLog.account_id == Account.id)
    count_q = count_q.where(BalanceLog.change_type.in_(recharge_types))
    if account_id:
        count_q = count_q.where(BalanceLog.account_id == account_id)
    if sales_id:
        count_q = count_q.where(Account.sales_id == sales_id)
    if start_date:
        try:
            count_q = count_q.where(BalanceLog.created_at >= datetime.fromisoformat(start_date))
        except ValueError:
            pass
    if end_date:
        try:
            count_q = count_q.where(BalanceLog.created_at < datetime.fromisoformat(end_date) + timedelta(days=1))
        except ValueError:
            pass
    total = await db.scalar(count_q) or 0

    query = query.order_by(BalanceLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.all()

    logs = []
    for l, acc in rows:
        logs.append({
            "id": l.id,
            "account_id": l.account_id,
            "account_name": acc.account_name if acc else None,
            "change_type": l.change_type,
            "amount": float(l.amount),
            "balance_after": float(l.balance_after),
            "description": l.description,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "exclude_performance": l.change_type == "refund_recharge",
        })
    return {"success": True, "total": total, "page": page, "page_size": page_size, "logs": logs}


@router.delete("/accounts/{account_id}", response_model=dict)
async def delete_account_admin(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：删除账户（设为closed状态）"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限删除账户")
    
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    from app.modules.common.telegram_binding import TelegramBinding

    account_name = account.account_name or f"#{account_id}"
    # 软删除：将状态设为closed并标记删除
    account.status = "closed"
    account.is_deleted = True
    account.tg_id = None
    account.tg_username = None
    # 清空 webhook 配置：残留的 webhook_url 会被 _account_has_webhook 当成有效配置，
    # 导致已删除客户的回执仍被推送到其端点（数据/隐私隐患）。
    account.webhook_url = None
    account.webhook_secret = None
    # 解除 TG 业务助手绑定，避免 telegram_bindings 仍指向已删除账户
    await db.execute(
        delete(TelegramBinding).where(TelegramBinding.account_id == account_id)
    )
    await db.commit()

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="account", action="delete", target_type="account",
        target_id=str(account_id),
        title=f"删除客户账户 {account_name}",
    )

    return {
        "success": True,
        "message": "账户已删除",
    }


@router.get("/channels", response_model=dict)
async def list_channels_admin(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取所有通道列表（管理员）"""
    from app.modules.sms.channel import Channel

    result = await db.execute(
        select(Channel).where(
            Channel.is_deleted == False
        ).order_by(Channel.created_at.desc())
    )
    channels = result.scalars().all()

    # 供应商关联与发送统计供应商维度共用同一份映射，避免两处口径分叉
    supplier_map = {
        cid: {"id": info["id"], "supplier_code": info["code"], "supplier_name": info["name"]}
        for cid, info in (await _channel_supplier_map(db)).items()
    }

    return {
        "success": True,
        "total": len(channels),
        "channels": [
            {
                "id": ch.id,
                "channel_code": ch.channel_code,
                "channel_name": ch.channel_name,
                "protocol": ch.protocol,
                "status": ch.status,
                "connection_status": ch.connection_status or "unknown",
                "connection_checked_at": ch.connection_checked_at.isoformat() if ch.connection_checked_at else None,
                "priority": ch.priority,
                "weight": ch.weight,
                "max_tps": ch.max_tps,
                "concurrency": ch.concurrency,
                "rate_control_window": ch.rate_control_window,
                "host": ch.host,
                "port": ch.port,
                "username": ch.username,
                "api_url": ch.api_url,
                "smpp_bind_mode": ch.smpp_bind_mode or "transceiver",
                "smpp_system_type": ch.smpp_system_type or "",
                "smpp_interface_version": ch.smpp_interface_version or 0x34,
                "smpp_dlr_socket_hold_seconds": getattr(ch, "smpp_dlr_socket_hold_seconds", None),
                "dlr_sent_timeout_hours": getattr(ch, "dlr_sent_timeout_hours", None),
                "banned_words": getattr(ch, "banned_words", None),
                "remark": getattr(ch, "remark", None),
                "default_sender_id": ch.default_sender_id,
                "virtual_config": ch.get_virtual_config() if ch.protocol == "VIRTUAL" else None,
                "gateway_config": _mask_gateway_config(ch.get_gateway_config()),
                "supplier": supplier_map.get(ch.id),
                "created_at": ch.created_at.isoformat() if ch.created_at else None
            }
            for ch in channels
        ]
    }


@router.get("/channels/{channel_id}", response_model=dict)
async def get_channel_admin(
    channel_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取通道详情（管理员）"""
    from app.modules.sms.channel import Channel
    from app.modules.sms.supplier import SupplierChannel, Supplier

    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    ch = result.scalar_one_or_none()

    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    # 获取关联供应商
    supplier_info = None
    sc_result = await db.execute(
        select(SupplierChannel, Supplier)
        .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
        .where(SupplierChannel.channel_id == channel_id, SupplierChannel.status == 'active')
        .limit(1)
    )
    sc_row = sc_result.first()
    if sc_row:
        _, supplier = sc_row
        supplier_info = {"id": supplier.id, "supplier_code": supplier.supplier_code, "supplier_name": supplier.supplier_name}

    return {
        "success": True,
        "channel": {
            "id": ch.id,
            "channel_code": ch.channel_code,
            "channel_name": ch.channel_name,
            "protocol": ch.protocol,
            "status": ch.status,
            "connection_status": ch.connection_status or "unknown",
            "connection_checked_at": ch.connection_checked_at.isoformat() if ch.connection_checked_at else None,
            "priority": ch.priority,
            "weight": ch.weight,
            "max_tps": ch.max_tps,
            "concurrency": ch.concurrency,
            "rate_control_window": ch.rate_control_window,
            "host": ch.host,
            "port": ch.port,
            "username": ch.username,
            "api_url": ch.api_url,
            "smpp_bind_mode": ch.smpp_bind_mode or "transceiver",
            "smpp_system_type": ch.smpp_system_type or "",
            "smpp_interface_version": ch.smpp_interface_version or 0x34,
            "smpp_dlr_socket_hold_seconds": getattr(ch, "smpp_dlr_socket_hold_seconds", None),
            "dlr_sent_timeout_hours": getattr(ch, "dlr_sent_timeout_hours", None),
            "banned_words": getattr(ch, "banned_words", None),
            "remark": getattr(ch, "remark", None),
            "default_sender_id": ch.default_sender_id,
            "virtual_config": ch.get_virtual_config() if ch.protocol == "VIRTUAL" else None,
            "gateway_config": _mask_gateway_config(ch.get_gateway_config()),
            "supplier": supplier_info,
            "supplier_id": supplier_info["id"] if supplier_info else None,
            "created_at": ch.created_at.isoformat() if ch.created_at else None,
            "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
        },
    }


@router.post("/channels", response_model=dict)
async def create_channel(
    request: ChannelCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建通道"""
    from app.modules.sms.channel import Channel
    
    # 检查通道代码是否已存在
    result = await db.execute(
        select(Channel).where(Channel.channel_code == request.channel_code)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Channel code already exists")

    _assert_rcs_channel_ready(
        request.api_url, request.username,
        request.password, request.api_key, request.gateway_config,
    )

    # 创建通道
    channel = Channel(
        channel_code=request.channel_code,
        channel_name=request.channel_name,
        protocol=request.protocol,
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        smpp_bind_mode=request.smpp_bind_mode or "transceiver",
        smpp_system_type=request.smpp_system_type or "",
        smpp_interface_version=request.smpp_interface_version or 0x34,
        api_url=request.api_url,
        api_key=request.api_key,
        priority=request.priority,
        weight=request.weight,
        max_tps=request.max_tps,
        concurrency=request.concurrency,
        rate_control_window=request.rate_control_window,
        default_sender_id=request.default_sender_id.strip() if request.default_sender_id else None,
        status=request.status,
        smpp_dlr_socket_hold_seconds=request.smpp_dlr_socket_hold_seconds,
        dlr_sent_timeout_hours=request.dlr_sent_timeout_hours,
        banned_words=request.banned_words,
        remark=request.remark,
    )

    # 虚拟通道无外部连接，默认可用状态为「正常」
    if request.protocol == "VIRTUAL":
        channel.connection_status = "online"
        channel.connection_checked_at = datetime.utcnow()
    
    if request.virtual_config and request.protocol == 'VIRTUAL':
        channel.virtual_config = json.dumps(request.virtual_config, ensure_ascii=False)

    if request.gateway_config:
        channel.config_json = json.dumps(request.gateway_config, ensure_ascii=False)

    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    # 关联供应商：同时写 channels.supplier_id 硬主键（价格联动据此定位供应商）与 supplier_channels 关联表
    if request.supplier_id:
        from app.modules.sms.supplier import SupplierChannel
        channel.supplier_id = request.supplier_id
        sc = SupplierChannel(
            supplier_id=request.supplier_id,
            channel_id=channel.id,
            status='active'
        )
        db.add(sc)
        await db.commit()

    logger.info(f"通道创建成功: {channel.channel_code}")

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="channel", action="create", target_type="channel",
        target_id=str(channel.id),
        title=f"创建通道 {channel.channel_name}（{channel.channel_code}）",
    )

    return {
        "success": True,
        "channel_id": channel.id,
        "message": "Channel created successfully"
    }


@router.put("/channels/{channel_id}", response_model=dict)
async def update_channel(
    channel_id: int,
    request: ChannelUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新通道"""
    from app.modules.sms.channel import Channel
    
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # 更新字段
    if request.channel_code is not None:
        channel.channel_code = request.channel_code
    if request.channel_name is not None:
        channel.channel_name = request.channel_name
    if request.max_tps is not None:
        channel.max_tps = request.max_tps
    if request.concurrency is not None:
        channel.concurrency = request.concurrency
    if request.rate_control_window is not None:
        channel.rate_control_window = request.rate_control_window
    if request.priority is not None:
        channel.priority = request.priority
    if request.weight is not None:
        channel.weight = request.weight
    if request.status is not None:
        channel.status = request.status
    if request.host is not None:
        channel.host = request.host
    if request.port is not None:
        channel.port = request.port
    if request.username is not None:
        channel.username = request.username
    if request.password is not None:
        channel.password = request.password
    if request.api_url is not None:
        channel.api_url = request.api_url
    if request.api_key is not None:
        channel.api_key = request.api_key
    if request.default_sender_id is not None:
        channel.default_sender_id = request.default_sender_id
    if request.smpp_bind_mode is not None:
        channel.smpp_bind_mode = request.smpp_bind_mode
    if request.smpp_system_type is not None:
        channel.smpp_system_type = request.smpp_system_type
    if request.smpp_interface_version is not None:
        channel.smpp_interface_version = request.smpp_interface_version

    updated_fields = request.model_dump(exclude_unset=True)
    if "smpp_dlr_socket_hold_seconds" in updated_fields:
        channel.smpp_dlr_socket_hold_seconds = request.smpp_dlr_socket_hold_seconds
    if "dlr_sent_timeout_hours" in updated_fields:
        channel.dlr_sent_timeout_hours = request.dlr_sent_timeout_hours
    if "banned_words" in updated_fields:
        channel.banned_words = request.banned_words
    if "remark" in updated_fields:
        channel.remark = request.remark
    if "virtual_config" in updated_fields:
        channel.virtual_config = json.dumps(request.virtual_config, ensure_ascii=False) if request.virtual_config else None
    if "gateway_config" in updated_fields:
        # 掩码回写保护：前端提交的 ****** 表示「保持库里的原密钥」
        merged_cfg = _merge_gateway_config(channel.config_json, request.gateway_config)
        channel.config_json = json.dumps(merged_cfg, ensure_ascii=False) if merged_cfg else None

    _assert_rcs_channel_ready(
        channel.api_url, channel.username, channel.password, channel.api_key,
        channel.get_gateway_config(),
    )

    # 更新供应商关联（仅当请求中显式包含 supplier_id 时处理，传 null 表示清除）
    # 同时维护 channels.supplier_id 硬主键与 supplier_channels 关联表，二者保持一致
    if 'supplier_id' in updated_fields:
        from app.modules.sms.supplier import SupplierChannel
        channel.supplier_id = request.supplier_id or None
        await db.execute(
            SupplierChannel.__table__.delete().where(SupplierChannel.channel_id == channel_id)
        )
        if request.supplier_id:
            sc = SupplierChannel(
                supplier_id=request.supplier_id,
                channel_id=channel_id,
                status='active'
            )
            db.add(sc)
    
    await db.commit()
    await db.refresh(channel)

    logger.info(f"通道更新成功: {channel.channel_code}")

    from app.services.operation_log import log_operation as _log_op
    _updated_fields = list(request.model_dump(exclude_unset=True).keys())
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="channel", action="update", target_type="channel",
        target_id=str(channel_id),
        title=f"更新通道 {channel.channel_name}（{channel.channel_code}）",
        detail=str(_updated_fields),
    )

    # 失效相关缓存（路由/价格）
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_route_cache()
        await cache_manager.invalidate_price_cache(channel_id=channel.id)
    except Exception:
        # 缓存失效失败不阻断主流程
        pass

    return {
        "success": True,
        "message": "Channel updated successfully"
    }


@router.delete("/channels/{channel_id}", response_model=dict)
async def delete_channel(
    channel_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除通道（软删除）"""
    from app.modules.sms.channel import Channel
    
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel_name = channel.channel_name
    channel_code = channel.channel_code
    channel.is_deleted = True
    channel.status = "inactive"
    await db.commit()

    logger.info(f"通道删除成功: {channel_code}")

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="channel", action="delete", target_type="channel",
        target_id=str(channel_id),
        title=f"删除通道 {channel_name}（{channel_code}）",
    )

    return {
        "success": True,
        "message": "Channel deleted successfully"
    }


@router.get("/channels/{channel_id}/banned-words", response_model=dict)
async def get_channel_banned_words(
    channel_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取通道的全局违禁词及各国家专属违禁词"""
    from app.modules.sms.channel import Channel
    from app.modules.sms.routing_rule import RoutingRule

    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    rules_result = await db.execute(
        select(RoutingRule).where(
            RoutingRule.channel_id == channel_id,
            RoutingRule.is_active == True
        )
    )
    rules = rules_result.scalars().all()

    country_words = {}
    for r in rules:
        if r.banned_words:
            country_words[r.country_code] = r.banned_words

    return {
        "success": True,
        "channel_banned_words": channel.banned_words or "",
        "country_banned_words": country_words,
    }


# --- Channel Test & Status Check ---

class TestSendRequest(BaseModel):
    phone: str
    content: str
    sender_id: Optional[str] = None


@router.post("/channels/{channel_id}/test-send", response_model=dict)
async def channel_test_send(
    channel_id: int,
    request: TestSendRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """通道测试发送 — 创建真实 SMSLog 记录"""
    from app.modules.sms.channel import Channel
    from app.modules.sms.sms_log import SMSLog
    import uuid
    from datetime import datetime

    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    test_message_id = f"TEST_{uuid.uuid4().hex[:12]}"
    sender_id = request.sender_id or channel.default_sender_id or "TEST"

    # 解析国家代码（统一为 ISO2）
    country_code = ""
    phone = request.phone.lstrip("+")
    try:
        import phonenumbers
        from app.utils.country_code import normalize_country_code as _norm_cc
        pn = phonenumbers.parse("+" + phone, None)
        region = phonenumbers.region_code_for_number(pn)
        country_code = _norm_cc(region) or _norm_cc(str(pn.country_code)) or str(pn.country_code)
    except Exception:
        pass

    # 先在数据库创建 SMSLog 记录（状态 pending）
    sms_log = SMSLog(
        message_id=test_message_id,
        account_id=0,
        channel_id=channel.id,
        phone_number=request.phone,
        country_code=country_code,
        message=request.content,
        message_count=1,
        status="pending",
        cost_price=0,
        selling_price=0,
        currency="USD",
    )
    db.add(sms_log)
    await db.flush()

    try:
        if channel.protocol == "SMPP":
            # 短链占位符替换（admin 测试也直推 Go 网关；为防误用，同样替换）
            try:
                from app.utils.short_link import has_track_url_placeholder, replace_track_url_in_message
                from app.config import settings as _cfg_sl
                if has_track_url_placeholder(sms_log.message or ""):
                    sms_log.message = await replace_track_url_in_message(
                        db, sms_log.id, sms_log.message,
                        getattr(_cfg_sl, "SHORT_LINK_BASE_URL", "") or "",
                        getattr(_cfg_sl, "SHORT_LINK_DEFAULT_TARGET_URL", "") or "",
                    )
            except Exception as _sl_err:
                logger.warning(f"admin 测试短链替换异常（已忽略）: {_sl_err}")

            # 直投 sms_send_smpp，与 Worker 重投格式一致，由 Go gateway 消费；不依赖 worker-sms 抢 sms_send
            await db.commit()

            from app.utils.queue import QueueManager
            from app.utils.smpp_payload import smpp_payload_public_dict

            ok = QueueManager.queue_smpp_gateway(smpp_payload_public_dict(sms_log, ""), None)
            if not ok:
                await db.refresh(sms_log)
                sms_log.status = "failed"
                sms_log.error_message = (
                    "测试任务加入发送队列失败，请检查 RabbitMQ、smpp-gateway 是否运行及网络可达"
                )
                await db.commit()
                return {
                    "success": False,
                    "message": sms_log.error_message,
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "host": f"{channel.host}:{channel.port}",
                        "message_id": test_message_id,
                    },
                }

            return {
                "success": True,
                "message": "测试任务已加入发送队列，SMPP 由网关异步下发，请在发送记录中查看结果",
                "details": {
                    "channel": channel.channel_code,
                    "protocol": "SMPP",
                    "host": f"{channel.host}:{channel.port}",
                    "message_id": test_message_id,
                    "phone": request.phone,
                },
            }

        elif channel.protocol == "HTTP" and channel.is_rcs():
            # RCS 也是 HTTP 协议，靠 config_json.rcs.vendor 区分；须排在通用 HTTP 之前
            from app.workers.adapters.rcs_adapter import get_rcs_adapter

            # 测试发送同样受上游 160 字符 / 禁 emoji 限制；sender_id 走本条自选
            sms_log.sender_id = request.sender_id or None
            rcs_result = await get_rcs_adapter(channel).send_one(sms_log)
            success = rcs_result.success
            channel_msg_id = rcs_result.upstream_message_id
            error = rcs_result.error
            if rcs_result.duplicated:
                logger.info(
                    f"RCS 测试发送命中上游幂等(clientRef 复用): {test_message_id}, "
                    f"batch={rcs_result.batch_id}"
                )

        elif channel.protocol == "HTTP":
            from app.workers.adapters.http_adapter import HTTPAdapter
            adapter = HTTPAdapter(channel)
            success, channel_msg_id, error = await adapter.send(sms_log)

        else:
            sms_log.status = "failed"
            sms_log.error_message = f"不支持的协议: {channel.protocol}"
            await db.commit()
            return {"success": False, "message": sms_log.error_message}

        # 更新 SMSLog 状态
        now = datetime.now()
        if success:
            sms_log.status = "sent"
            sms_log.upstream_message_id = channel_msg_id
            sms_log.sent_time = now
        else:
            sms_log.status = "failed"
            sms_log.error_message = error

        await db.commit()

        if success:
            return {
                "success": True,
                "message": "测试发送成功",
                "details": {
                    "channel": channel.channel_code,
                    "protocol": channel.protocol,
                    "message_id": test_message_id,
                    "channel_message_id": channel_msg_id,
                    "phone": request.phone,
                },
            }
        else:
            return {
                "success": False,
                "message": f"发送失败: {error}",
                "details": {
                    "channel": channel.channel_code,
                    "protocol": channel.protocol,
                    "message_id": test_message_id,
                },
            }

    except Exception as e:
        logger.error(f"测试发送异常: {str(e)}", exc_info=e)
        sms_log.status = "failed"
        sms_log.error_message = str(e)[:500]
        await db.commit()
        return {
            "success": False,
            "message": f"测试发送异常: {str(e)}",
            "details": {"channel": channel.channel_code, "message_id": test_message_id},
        }


@router.post("/channels/check-all-status", response_model=dict)
async def channel_check_all_status(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """一键检测所有通道连接状态，结果持久化到 connection_status 字段"""
    from app.modules.sms.channel import Channel
    
    result = await db.execute(
        select(Channel).where(Channel.is_deleted == False).order_by(Channel.id)
    )
    channels = result.scalars().all()
    
    if not channels:
        return {
            "success": True,
            "total": 0,
            "online": 0,
            "offline": 0,
            "unknown": 0,
            "results": [],
            "message": "暂无通道需要检测",
        }
    
    # 复用单通道检测逻辑
    results = []
    online_count = 0
    offline_count = 0
    unknown_count = 0

    for channel in channels:
        check_result = await _run_channel_check(channel)
        raw = check_result.get("status") or "unknown"
        if raw == "online":
            conn_status = "online"
        elif raw == "offline":
            conn_status = "offline"
        else:
            conn_status = "unknown"
        channel.connection_status = conn_status
        channel.connection_checked_at = datetime.utcnow()

        if conn_status == "online":
            online_count += 1
        elif conn_status == "offline":
            offline_count += 1
        else:
            unknown_count += 1

        results.append({
            "channel_id": channel.id,
            "channel_code": channel.channel_code,
            "channel_name": channel.channel_name,
            "status": conn_status,
            "success": check_result.get("success", False),
            "message": check_result.get("message", ""),
        })
    
    await db.commit()
    
    return {
        "success": True,
        "total": len(channels),
        "online": online_count,
        "offline": offline_count,
        "unknown": unknown_count,
        "results": results,
        "message": (
            f"已检测 {len(channels)} 个通道：在线 {online_count} 个，离线 {offline_count} 个"
            + (
                f"，未判定 {unknown_count} 个（多为 SMPP 未配网关 bind 探测、仅 TCP，或 bind/账号失败）"
                if unknown_count
                else ""
            )
        ),
    }


def _tcp_connect_probe(host: str, port: int, *, timeout: float = 5.0):
    """
    TCP 连通探测（含 DNS / IPv4+IPv6，与 AF_INET 手工 connect 相比误判更少）。
    返回 (是否成功, 失败原因简述或 None)。
    """
    import socket
    from urllib.parse import urlparse

    raw = (host or "").strip()
    if not raw:
        return False, "主机为空"
    h = raw
    p = int(port)
    if "://" in raw:
        pr = urlparse(raw)
        if pr.hostname:
            h = pr.hostname
        if pr.port:
            p = int(pr.port)
    try:
        sock = socket.create_connection((h, p), timeout=timeout)
        sock.close()
        return True, None
    except socket.timeout:
        return False, "连接超时"
    except OSError as e:
        return False, (str(e) or "网络错误")


async def _smpp_bind_probe_via_gateway(channel) -> dict:
    """
    调用 go-smpp-gateway 的 POST /probe-bind 执行真实 SMPP bind（须配置 URL 与 Token）。
    返回与 _run_channel_check 一致形态的结果字典。
    """
    import httpx

    base = (settings.SMPP_GATEWAY_PROBE_URL or "").strip().rstrip("/")
    token = (settings.SMPP_PROBE_TOKEN or "").strip()
    url = f"{base}/probe-bind"
    payload = {
        "host": str(channel.host or "").strip(),
        "port": int(channel.port),
        "system_id": (channel.username or "").strip(),
        "password": (channel.password or "").strip(),
        "bind_mode": (channel.smpp_bind_mode or "transceiver").strip(),
        "system_type": (channel.smpp_system_type or "").strip(),
        "channel_ref": channel.channel_code,
    }
    timeout = httpx.Timeout(40.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"X-Smpp-Probe-Token": token},
        )
    text = (resp.text or "")[:500]
    try:
        data = resp.json()
    except Exception:
        data = {}
    msg = (data.get("message") if isinstance(data, dict) else None) or text or f"HTTP {resp.status_code}"
    st = (data.get("status") if isinstance(data, dict) else None) or "offline"
    ok = bool(isinstance(data, dict) and data.get("success"))
    if resp.status_code == 401:
        return {
            "success": False,
            "status": "offline",
            "message": "探测服务拒绝认证，请核对 API 与 smpp-gateway 的 SMPP_PROBE_TOKEN 是否一致",
        }
    if resp.status_code >= 400 and not isinstance(data, dict):
        return {
            "success": False,
            "status": "offline",
            "message": f"探测服务 HTTP {resp.status_code}: {msg}",
        }
    return {
        "success": ok,
        "status": st if st in ("online", "offline", "unknown") else ("online" if ok else "offline"),
        "message": msg,
    }


async def _run_channel_check(channel) -> dict:
    """执行单通道连接检测，返回结果字典（不持久化）"""
    import time

    start_time = time.time()

    try:
        if channel.protocol == "SMPP":
            if not channel.host or not channel.port:
                latency_ms = int((time.time() - start_time) * 1000)
                return {
                    "success": False,
                    "status": "offline",
                    "message": "SMPP 未配置主机或端口",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "host": channel.host,
                        "port": channel.port,
                        "latency_ms": latency_ms,
                    },
                }
            probe_base = (settings.SMPP_GATEWAY_PROBE_URL or "").strip()
            probe_token = (settings.SMPP_PROBE_TOKEN or "").strip()
            if probe_base and probe_token:
                if not (channel.username and channel.password):
                    latency_ms = int((time.time() - start_time) * 1000)
                    return {
                        "success": False,
                        "status": "offline",
                        "message": "SMPP 未配置用户名(system_id)或密码，无法执行 bind 探测",
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "SMPP",
                            "host": channel.host,
                            "port": channel.port,
                            "latency_ms": latency_ms,
                        },
                    }
                try:
                    out = await _smpp_bind_probe_via_gateway(channel)
                    latency_ms = int((time.time() - start_time) * 1000)
                    return {
                        "success": out["success"],
                        "status": out["status"],
                        "message": out["message"],
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "SMPP",
                            "host": channel.host,
                            "port": channel.port,
                            "latency_ms": latency_ms,
                            "probe": "gateway_bind",
                        },
                    }
                except Exception as e:
                    latency_ms = int((time.time() - start_time) * 1000)
                    logger.opt(exception=True).warning(
                        "SMPP 网关 bind 探测失败 channel={}: {}",
                        channel.channel_code,
                        str(e),
                    )
                    return {
                        "success": False,
                        "status": "offline",
                        "message": f"SMPP 网关 bind 探测不可用: {str(e)}",
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "SMPP",
                            "host": channel.host,
                            "port": channel.port,
                            "latency_ms": latency_ms,
                            "probe": "gateway_bind",
                        },
                    }
            # 未同时配置网关 URL 与 Token：仅 TCP 兜底并提示如何启用真实 bind
            try:
                ok, err = _tcp_connect_probe(str(channel.host), int(channel.port), timeout=5.0)
                latency_ms = int((time.time() - start_time) * 1000)
                if probe_token:
                    hint = (
                        "已配置 SMPP_PROBE_TOKEN，但未配置 SMPP_GATEWAY_PROBE_URL，无法调用网关执行 bind；"
                        "请在 API 环境设置 SMPP_GATEWAY_PROBE_URL（如 http://smpp-gateway:8090）并重启。"
                    )
                elif probe_base:
                    hint = (
                        "已配置 SMPP_GATEWAY_PROBE_URL，但未配置 SMPP_PROBE_TOKEN（或网关未设置同名变量），"
                        "网关不会启动探测接口；请在 api 与 smpp-gateway 设置相同 SMPP_PROBE_TOKEN 后重启。"
                    )
                else:
                    hint = (
                        "未配置 SMPP_GATEWAY_PROBE_URL 与 SMPP_PROBE_TOKEN，无法执行真实 bind；"
                        "请在 .env 为 api 与 smpp-gateway 设置相同 Token 与网关地址后重启。"
                    )
                if ok:
                    return {
                        "success": False,
                        "status": "unknown",
                        "message": f"{hint} TCP 可达 ({channel.host}:{channel.port})，不代表鉴权通过。",
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "SMPP",
                            "host": channel.host,
                            "port": channel.port,
                            "latency_ms": latency_ms,
                            "probe": "tcp_only",
                        },
                    }
                return {
                    "success": False,
                    "status": "offline",
                    "message": f"{hint} TCP 不可达: {err}",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "host": channel.host,
                        "port": channel.port,
                        "latency_ms": latency_ms,
                        "probe": "tcp_only",
                    },
                }
            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                return {
                    "success": False,
                    "status": "unknown",
                    "message": f"SMPP 检测过程异常: {str(e)}",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "host": channel.host,
                        "port": channel.port,
                        "latency_ms": latency_ms,
                    },
                }

        elif channel.protocol == "HTTP" and channel.is_rcs():
            # 用 /balance 做真实探测：一次调用同时验证 base_url 可达 + appKey/appSecret + 签名路径，
            # 比 TCP 探测有用得多（TCP 通≠鉴权过，历史上 SMPP 就吃过这个亏）。
            from app.workers.adapters.rcs_adapter import RCSConfigError, get_rcs_adapter

            base_details = {
                "channel": channel.channel_code,
                "protocol": "HTTP",
                "api_type": "RCS",
                "rcs_vendor": channel.rcs_vendor(),
            }
            try:
                probe = await get_rcs_adapter(channel).get_balance()
            except RCSConfigError as e:
                return {
                    "success": False,
                    "status": "offline",
                    "message": str(e),
                    "details": {**base_details, "latency_ms": int((time.time() - start_time) * 1000)},
                }
            except Exception as e:
                return {
                    "success": False,
                    "status": "offline",
                    "message": f"RCS 接口不可达: {str(e)[:200]}",
                    "details": {**base_details, "latency_ms": int((time.time() - start_time) * 1000)},
                }
            latency_ms = int((time.time() - start_time) * 1000)
            if probe.get("success"):
                return {
                    "success": True,
                    "status": "online",
                    "message": "RCS 鉴权通过，接口可用",
                    "details": {**base_details, "latency_ms": latency_ms},
                }
            return {
                "success": False,
                "status": "offline",
                "message": f"RCS 鉴权/接口异常: {probe.get('error_code') or ''} {probe.get('error') or ''}".strip(),
                "details": {**base_details, "latency_ms": latency_ms},
            }
        elif channel.protocol == "HTTP":
            if not channel.api_url:
                return {
                    "success": False,
                    "status": "offline",
                    "message": "HTTP通道未配置API地址",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "HTTP",
                        "api_url": None
                    }
                }
            try:
                from urllib.parse import urlparse

                parsed = urlparse(channel.api_url)
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == 'https' else 80)
                if not host:
                    latency_ms = int((time.time() - start_time) * 1000)
                    return {
                        "success": False,
                        "status": "offline",
                        "message": "HTTP 地址中无有效主机名",
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "HTTP",
                            "api_url": channel.api_url,
                            "latency_ms": latency_ms,
                        },
                    }
                ok, err = _tcp_connect_probe(host, int(port), timeout=5.0)
                latency_ms = int((time.time() - start_time) * 1000)
                if ok:
                    return {
                        "success": True,
                        "status": "online",
                        "message": f"HTTP接口可达 ({host}:{port})",
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "HTTP",
                            "api_url": channel.api_url,
                            "host": host,
                            "port": port,
                            "latency_ms": latency_ms,
                        },
                    }
                return {
                    "success": False,
                    "status": "offline",
                    "message": f"HTTP 无法连通 ({host}:{port}): {err}",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "HTTP",
                        "api_url": channel.api_url,
                        "host": host,
                        "port": port,
                        "latency_ms": latency_ms,
                    },
                }
            except Exception as parse_err:
                latency_ms = int((time.time() - start_time) * 1000)
                return {
                    "success": False,
                    "status": "offline",
                    "message": f"API地址解析失败: {str(parse_err)}",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "HTTP",
                        "api_url": channel.api_url,
                        "latency_ms": latency_ms
                    }
                }
        elif channel.protocol == "VIRTUAL":
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "status": "online",
                "message": "虚拟通道无需外部连接，状态为正常",
                "details": {
                    "channel": channel.channel_code,
                    "protocol": "VIRTUAL",
                    "latency_ms": latency_ms,
                },
            }
        else:
            return {
                "success": False,
                "status": "offline",
                "message": f"不支持的协议类型: {channel.protocol}"
            }
            
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"通道 {channel.channel_code} 状态检查异常: {str(e)}", exc_info=e)
        return {
            "success": False,
            "status": "offline",
            "message": f"状态检查异常: {str(e)}",
            "details": {
                "channel": channel.channel_code,
                "latency_ms": latency_ms
            }
        }


@router.post("/channels/{channel_id}/check-status", response_model=dict)
async def channel_check_status(
    channel_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """通道状态检查，检测结果会持久化到 connection_status 字段"""
    from app.modules.sms.channel import Channel
    
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    check_result = await _run_channel_check(channel)

    raw = check_result.get("status") or "unknown"
    if raw == "online":
        conn_status = "online"
    elif raw == "offline":
        conn_status = "offline"
    else:
        conn_status = "unknown"
    channel.connection_status = conn_status
    channel.connection_checked_at = datetime.utcnow()
    await db.commit()

    return check_result


# --- DLR 手动拉取（调试用）---

@router.post("/dlr/fetch", response_model=dict)
async def admin_dlr_fetch(
    admin: AdminUser = Depends(get_current_admin),
):
    """
    手动触发 DLR 拉取任务（调试用）
    将 fetch_dlr_reports_task 加入队列，Worker 会拉取 HTTP 通道及配置了 dlr_report_url_override 的 SMPP 通道的送达回执
    """
    from app.workers.sms_worker import fetch_dlr_reports_task
    try:
        fetch_dlr_reports_task.delay()
        return {
            "success": True,
            "message": "DLR 拉取任务已加入队列，请查看 Worker 日志获取结果",
        }
    except Exception as e:
        logger.error(f"手动 DLR 拉取失败: {str(e)}", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


# --- Routing Rules Management ---

class RoutingRuleCreateRequest(BaseModel):
    channel_id: int
    country_code: str
    priority: int = 0
    is_active: bool = True
    banned_words: Optional[str] = None


class RoutingRuleUpdateRequest(BaseModel):
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    banned_words: Optional[str] = None


@router.get("/routing-rules", response_model=dict)
async def list_routing_rules(
    channel_id: Optional[int] = None,
    country_code: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取路由规则列表"""
    from app.modules.sms.routing_rule import RoutingRule

    query = select(RoutingRule).where(True)
    if channel_id is not None:
        query = query.where(RoutingRule.channel_id == channel_id)
    if country_code:
        query = query.where(RoutingRule.country_code == country_code)
    query = query.order_by(RoutingRule.country_code.asc(), RoutingRule.priority.desc())

    result = await db.execute(query)
    rules = result.scalars().all()

    return {
        "success": True,
        "total": len(rules),
        "rules": [
            {
                "id": r.id,
                "channel_id": r.channel_id,
                "country_code": r.country_code,
                "priority": r.priority,
                "is_active": r.is_active,
                "banned_words": r.banned_words,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rules
        ],
    }


@router.post("/routing-rules", response_model=dict)
async def create_routing_rule(
    request: RoutingRuleCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建路由规则（国家 -> 通道）"""
    from app.modules.sms.routing_rule import RoutingRule

    # 避免重复插入
    exists = await db.execute(
        select(RoutingRule).where(
            RoutingRule.channel_id == request.channel_id,
            RoutingRule.country_code == request.country_code
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Routing rule already exists")

    rule = RoutingRule(
        channel_id=request.channel_id,
        country_code=request.country_code,
        priority=request.priority,
        is_active=request.is_active,
        banned_words=request.banned_words,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    # 失效路由缓存
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_route_cache(country_code=request.country_code)
    except Exception:
        pass

    return {"success": True, "rule_id": rule.id, "message": "Routing rule created successfully"}


@router.put("/routing-rules/{rule_id}", response_model=dict)
async def update_routing_rule(
    rule_id: int,
    request: RoutingRuleUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新路由规则"""
    from app.modules.sms.routing_rule import RoutingRule

    result = await db.execute(select(RoutingRule).where(RoutingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Routing rule not found")

    if request.priority is not None:
        rule.priority = request.priority
    if request.is_active is not None:
        rule.is_active = request.is_active
    updated_fields = request.model_dump(exclude_unset=True)
    if "banned_words" in updated_fields:
        rule.banned_words = request.banned_words

    await db.commit()

    # 失效路由缓存
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_route_cache(country_code=rule.country_code)
    except Exception:
        pass

    return {"success": True, "message": "Routing rule updated successfully"}


@router.delete("/routing-rules/{rule_id}", response_model=dict)
async def delete_routing_rule(
    rule_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除路由规则"""
    from app.modules.sms.routing_rule import RoutingRule

    result = await db.execute(select(RoutingRule).where(RoutingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Routing rule not found")

    _country_code = rule.country_code
    await db.delete(rule)
    await db.commit()

    # 失效路由缓存
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_route_cache(country_code=_country_code)
    except Exception:
        pass

    return {"success": True, "message": "Routing rule deleted successfully"}


@router.get("/pricing", response_model=dict)
async def list_pricing(
    channel_id: Optional[int] = None,
    country_code: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取费率列表"""
    from app.modules.sms.country_pricing import CountryPricing
    
    query = select(CountryPricing).where(True)
    
    if channel_id:
        query = query.where(CountryPricing.channel_id == channel_id)
    if country_code:
        query = query.where(CountryPricing.country_code == country_code)
    
    query = query.order_by(CountryPricing.effective_date.desc())
    
    result = await db.execute(query)
    pricing_list = result.scalars().all()
    
    return {
        "success": True,
        "total": len(pricing_list),
        "pricing": [
            {
                "id": p.id,
                "channel_id": p.channel_id,
                "country_code": p.country_code,
                "country_name": p.country_name,
                "price_per_sms": float(p.price_per_sms),
                "currency": p.currency,
                "mnc": getattr(p, 'mnc', None),
                "operator_name": getattr(p, 'operator_name', None),
                "effective_date": p.effective_date.isoformat() if p.effective_date else None,
                "expiry_date": getattr(p, 'expiry_date', None).isoformat() if hasattr(p, 'expiry_date') and getattr(p, 'expiry_date', None) else None,
                "remark": p.remark,
            }
            for p in pricing_list
        ]
    }


async def _resolve_channel_supplier_id(db: AsyncSession, channel_id: int):
    """
    解析通道归属的供应商 id。

    优先取 channels.supplier_id 硬主键；历史通道该列可能为空（早期保存只写了
    supplier_channels 关联表），故回退取 supplier_channels 中最新的有效关联行。
    两条价格联动（开户模板底价、资源报价）都靠它定位供应商，统一从这里取，
    既覆盖新数据也兼容旧数据，无需手工重存通道。返回 None 表示通道未关联任何供应商。
    """
    from app.modules.sms.channel import Channel
    from app.modules.sms.supplier import SupplierChannel

    supplier_id = (await db.execute(
        select(Channel.supplier_id).where(Channel.id == int(channel_id))
    )).scalar_one_or_none()
    if supplier_id:
        return supplier_id
    return (await db.execute(
        select(SupplierChannel.supplier_id)
        .where(
            SupplierChannel.channel_id == int(channel_id),
            SupplierChannel.status == 'active',
        )
        .order_by(SupplierChannel.id.desc())
        .limit(1)
    )).scalar_one_or_none()


async def _sync_template_floor_price(
    db: AsyncSession, channel_id: int, country_code: str, price, country_name: str = None
) -> int:
    """
    通道价格（成本价）即时联动开户模板「底价」(account_templates.default_price)。

    匹配维度：通道 + 国家。注意两表 country_code 格式不同——
    country_pricing 存国际区号(如 63)，account_templates 存 ISO2(如 PH)，
    故用 get_country_variants() 取同一国家的全部等价写法做 IN 匹配；
    channel_ids 是整数 JSON 数组(可能为 NULL)，用 json_contains 判断包含。
    模板业务类型跟随通道协议：RCS 通道联动 business_type='rcs' 的模板，其余走 'sms'
    —— RCS 单价与短信量级不同，串到 sms 模板会把短信底价改错。

    行为：
    - 已有匹配模板 → 更新 default_price。
    - 无匹配模板 → 自动新建一个，供应商群与命名风格优先继承同通道其它短信模板；
      同通道尚无任何短信模板时（全新供应商/通道首次配价），回退用 channels.supplier_id
      → suppliers 推断供应商群，仍自动建出首个开户模板。仅当通道也未关联供应商时
      才跳过新建（返回 0）。

    返回受影响（更新或新建）模板数。
    """
    from app.modules.common.account_template import AccountTemplate
    from app.modules.sms.channel import Channel
    from app.utils.country_code import get_country_variants, normalize_country_code
    from decimal import Decimal

    variants = get_country_variants(country_code)
    if not variants:
        return 0
    new_price = Decimal(str(price))

    # 模板业务类型跟随通道的 RCS 上游标记（config_json.rcs.vendor），RCS 通道 → rcs 模板
    biz_type = 'rcs' if await _channel_is_rcs(db, channel_id) else 'sms'

    result = await db.execute(
        select(AccountTemplate).where(
            AccountTemplate.business_type == biz_type,
            AccountTemplate.country_code.in_(variants),
            func.json_contains(AccountTemplate.channel_ids, str(int(channel_id))),
        )
    )
    templates = result.scalars().all()
    if templates:
        for tpl in templates:
            tpl.default_price = new_price
        logger.info(
            f"通道价格联动开户模板底价: channel={channel_id} country={country_code} "
            f"biz={biz_type} price={new_price} 命中模板 {len(templates)} 个"
        )
        return len(templates)

    # 无匹配模板：自动新建一个。供应商群与命名风格的推断有两条来源——
    # 1) 优先继承同通道任一短信模板(sibling)，沿用其供应商群与命名风格；
    # 2) 全新通道尚无任何短信模板时，回退用 channels.supplier_id → suppliers 推断，
    #    使全新供应商/通道首次配价也能自动建出首个开户模板（无需先手工补建）。
    from app.api.v1.account_templates import generate_template_code
    iso2 = normalize_country_code(country_code) or str(country_code).strip().upper()
    cn_name = country_name or iso2

    sibling = (await db.execute(
        select(AccountTemplate).where(
            AccountTemplate.business_type == biz_type,
            func.json_contains(AccountTemplate.channel_ids, str(int(channel_id))),
        ).limit(1)
    )).scalar_one_or_none()

    if sibling is not None:
        group_id = sibling.supplier_group_id
        group_name = sibling.supplier_group_name
        # 沿用 sibling 的命名风格：把其国家名替换为新国家名（如 "KMI通信加纳" -> "KMI通信赞比亚"）
        if sibling.country_name and sibling.template_name and sibling.country_name in sibling.template_name:
            new_name = sibling.template_name.replace(sibling.country_name, cn_name)
        else:
            new_name = f"{group_name or ''}{cn_name}".strip() or cn_name
    else:
        # 回退：从通道关联的供应商推断供应商群（兼容 channels.supplier_id 与 supplier_channels）
        from app.modules.sms.supplier import Supplier
        supplier_id = await _resolve_channel_supplier_id(db, channel_id)
        supplier = (await db.execute(
            select(Supplier).where(Supplier.id == int(supplier_id))
        )).scalar_one_or_none() if supplier_id else None
        if supplier is None:
            logger.info(
                f"通道价格联动开户模板底价: channel={channel_id} country={country_code} "
                f"无同通道 {biz_type} 模板且通道未关联供应商，跳过自动新建"
            )
            return 0
        group_name = supplier.supplier_group or supplier.supplier_name
        # 模板 supplier_group_id 语义为供应商TG群ID(BigInteger)；仅当 telegram_group_id 为纯数字时填入
        group_id = None
        tg = (supplier.telegram_group_id or '').strip()
        if tg.lstrip('-').isdigit():
            group_id = int(tg)
        new_name = f"{group_name or ''}{cn_name}".strip() or cn_name

    # 生成唯一模板编码
    template_code = None
    for _ in range(10):
        candidate = generate_template_code(biz_type, iso2)
        exists = await db.execute(
            select(AccountTemplate).where(AccountTemplate.template_code == candidate)
        )
        if exists.scalar_one_or_none() is None:
            template_code = candidate
            break
    if template_code is None:
        logger.warning(
            f"通道价格联动开户模板底价: channel={channel_id} country={country_code} "
            f"无法生成唯一模板编码，跳过自动新建"
        )
        return 0

    db.add(AccountTemplate(
        template_code=template_code,
        template_name=new_name,
        business_type=biz_type,
        country_code=iso2,
        country_name=cn_name,
        supplier_group_id=group_id,
        supplier_group_name=group_name,
        channel_ids=[int(channel_id)],
        default_price=new_price,
        status='active',
    ))
    logger.info(
        f"通道价格自动新建开户模板: channel={channel_id} country={country_code} "
        f"price={new_price} 模板={new_name}({template_code})"
    )
    return 1


async def _sync_supplier_rate(
    db: AsyncSession, channel_id: int, country_code: str, price,
    country_name: str = None, currency: str = "USD",
) -> int:
    """
    通道价格（成本价）即时联动资源报价 supplier_rates.cost_price。

    定位供应商靠 channels.supplier_id 硬主键——未关联供应商则跳过（不做名字模糊匹配）。
    两表 country_code 格式不同，复用 get_country_variants() 做等价匹配。
    业务类型跟随通道协议：RCS 通道走 'rcs' 行，其余走 'sms'。

    - 命中已有报价行（供应商+国家+业务类型）→ 更新 cost_price 并标记 price_source='channel'，
      sell_price 不动（人工维护）。
    - 无 → 新建一行：cost=sell=price，resource_type 取该供应商同业务已有行众数（缺省 'card'）。

    price_source 标记用于与 Excel 导入隔离：导入逻辑不覆盖 price_source='channel' 的行。
    返回受影响（更新或新建）行数。
    """
    from app.modules.sms.supplier import SupplierRate
    from app.modules.sms.channel import Channel
    from app.utils.country_code import get_country_variants, normalize_country_code
    from collections import Counter
    from decimal import Decimal

    supplier_id = await _resolve_channel_supplier_id(db, channel_id)
    if not supplier_id:
        logger.info(f"资源报价联动跳过: channel={channel_id} 未关联供应商(supplier_id 为空)")
        return 0

    variants = get_country_variants(country_code)
    if not variants:
        return 0
    new_price = Decimal(str(price))

    biz_type = 'rcs' if await _channel_is_rcs(db, channel_id) else 'sms'

    rows = (await db.execute(
        select(SupplierRate).where(
            SupplierRate.supplier_id == supplier_id,
            SupplierRate.business_type == biz_type,
            SupplierRate.country_code.in_(variants),
        )
    )).scalars().all()
    if rows:
        for r in rows:
            r.cost_price = new_price
            r.price_source = 'channel'  # sell_price 保持不动
            r.channel_id = int(channel_id)  # 记录设此成本的通道
        logger.info(
            f"通道价格联动资源报价: channel={channel_id} supplier={supplier_id} "
            f"country={country_code} cost={new_price} 更新 {len(rows)} 行"
        )
        return len(rows)

    iso2 = normalize_country_code(country_code) or str(country_code).strip().upper()
    rtypes = (await db.execute(
        select(SupplierRate.resource_type).where(
            SupplierRate.supplier_id == supplier_id,
            SupplierRate.business_type == biz_type,
        )
    )).scalars().all()
    rtype_mode = Counter([t for t in rtypes if t]).most_common(1)
    resource_type = rtype_mode[0][0] if rtype_mode else 'card'

    db.add(SupplierRate(
        supplier_id=supplier_id,
        channel_id=int(channel_id),  # 记录设此成本的通道
        business_type=biz_type,
        country_code=iso2,
        resource_type=resource_type,
        business_scope='otp',
        cost_price=new_price,
        sell_price=new_price,  # 新建行 sell=cost；之后人工维护
        currency=currency or 'USD',
        status='active',
        price_source='channel',
    ))
    logger.info(
        f"通道价格自动新建资源报价: channel={channel_id} supplier={supplier_id} "
        f"country={country_code} cost={new_price} resource_type={resource_type}"
    )
    return 1


@router.post("/pricing", response_model=dict)
async def create_pricing(
    request: PricingCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建费率规则"""
    from app.modules.sms.country_pricing import CountryPricing
    from app.utils.country_code import normalize_country_code
    from decimal import Decimal
    from datetime import date

    # 入库 country_code 统一规范为 ISO2（避免管理员误填区号如 381 导致与
    # 号码归属国 RS 不一致，进而触发账户国家限制/路由匹配失败、TG 开户显示裸代码）
    request.country_code = normalize_country_code(request.country_code) or request.country_code

    # 默认生效日期：今天（避免 effective_date 为空导致查询取不到最新价格）
    if request.effective_date:
        try:
            eff_date = date.fromisoformat(request.effective_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid effective_date format, expected YYYY-MM-DD")
    else:
        eff_date = date.today()

    pricing = CountryPricing(
        channel_id=request.channel_id,
        country_code=request.country_code,
        country_name=request.country_name,
        price_per_sms=Decimal(str(request.price_per_sms)),
        currency=request.currency,
        effective_date=eff_date,
        remark=request.remark,
    )
    
    db.add(pricing)
    await db.flush()

    # 自动创建路由规则：若该通道+国家尚无路由，则新增一条
    from app.modules.sms.routing_rule import RoutingRule
    from app.utils.phone_utils import country_to_dial_code, dial_to_country_code
    codes_to_check = [request.country_code]
    if request.country_code.isdigit():
        codes_to_check.append(dial_to_country_code(request.country_code))
    else:
        codes_to_check.append(country_to_dial_code(request.country_code))
    route_exists = await db.execute(
        select(RoutingRule).where(
            RoutingRule.channel_id == request.channel_id,
            RoutingRule.country_code.in_(codes_to_check)
        )
    )
    routing_auto_created = False
    if route_exists.scalar_one_or_none() is None:
        route = RoutingRule(
            channel_id=request.channel_id,
            country_code=request.country_code,
            priority=0,
            is_active=True,
        )
        db.add(route)
        routing_auto_created = True
        logger.info(f"自动创建路由规则: {request.country_code} -> channel {request.channel_id}")

    # 通道价格（成本价）即时联动开户模板底价
    synced_templates = await _sync_template_floor_price(
        db, pricing.channel_id, pricing.country_code, pricing.price_per_sms,
        country_name=pricing.country_name,
    )
    # 通道价格（成本）即时联动资源报价（supplier_rates），靠 channels.supplier_id 定位供应商
    await _sync_supplier_rate(
        db, pricing.channel_id, pricing.country_code, pricing.price_per_sms,
        country_name=pricing.country_name, currency=pricing.currency,
    )

    await db.commit()
    await db.refresh(pricing)

    logger.info(f"费率规则创建成功: {pricing.country_code} - {pricing.channel_id}")

    # 失效价格与路由缓存
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_price_cache(channel_id=pricing.channel_id, country_code=pricing.country_code)
        await cache_manager.invalidate_route_cache(country_code=pricing.country_code)
    except Exception:
        pass

    return {
        "success": True,
        "pricing_id": pricing.id,
        "routing_auto_created": routing_auto_created,
        "synced_templates": synced_templates,
        "message": "Pricing rule created successfully"
    }


@router.put("/pricing/{pricing_id}", response_model=dict)
async def update_pricing(
    pricing_id: int,
    request: PricingUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新费率规则"""
    from app.modules.sms.country_pricing import CountryPricing
    from decimal import Decimal

    result = await db.execute(
        select(CountryPricing).where(CountryPricing.id == pricing_id)
    )
    pricing = result.scalar_one_or_none()

    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing rule not found")

    if request.price_per_sms is not None:
        pricing.price_per_sms = Decimal(str(request.price_per_sms))
    if request.currency is not None:
        pricing.currency = request.currency
    _upd_fields = request.model_dump(exclude_unset=True)
    if "remark" in _upd_fields:
        pricing.remark = request.remark

    # 通道价格（成本价）即时联动开户模板底价（仅价格变更时）
    synced_templates = 0
    if request.price_per_sms is not None:
        synced_templates = await _sync_template_floor_price(
            db, pricing.channel_id, pricing.country_code, pricing.price_per_sms,
            country_name=pricing.country_name,
        )
        await _sync_supplier_rate(
            db, pricing.channel_id, pricing.country_code, pricing.price_per_sms,
            country_name=pricing.country_name, currency=pricing.currency,
        )

    await db.commit()

    logger.info(f"费率规则更新成功: {pricing_id}")

    # 失效价格缓存（该通道/国家）
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_price_cache(channel_id=pricing.channel_id, country_code=pricing.country_code)
    except Exception:
        pass
    
    return {
        "success": True,
        "synced_templates": synced_templates,
        "message": "Pricing rule updated successfully"
    }


@router.delete("/pricing/{pricing_id}", response_model=dict)
async def delete_pricing(
    pricing_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除费率规则"""
    from app.modules.sms.country_pricing import CountryPricing
    
    result = await db.execute(
        select(CountryPricing).where(CountryPricing.id == pricing_id)
    )
    pricing = result.scalar_one_or_none()
    
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing rule not found")

    # 先记录用于缓存失效
    _channel_id = pricing.channel_id
    _country_code = pricing.country_code

    await db.delete(pricing)
    await db.commit()
    
    logger.info(f"费率规则删除成功: {pricing_id}")

    # 失效价格缓存（该通道/国家）
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_price_cache(channel_id=_channel_id, country_code=_country_code)
    except Exception:
        pass
    
    return {
        "success": True,
        "message": "Pricing rule deleted successfully"
    }


# --- Sender ID Management ---

class SenderIDAuditRequest(BaseModel):
    status: str
    rejection_reason: Optional[str] = None



# 预热任务通过此 ContextVar 强制重算并覆盖缓存（跳过缓存读/单飞锁，不删旧键，保证重算期间
# 在线请求始终命中旧热缓存、绝不与预热并发冷扫描同一分区）。见 batch_inspector.refresh_admin_dashboard_cache_task。
_dashboard_preheat_force = contextvars.ContextVar("dashboard_preheat_force", default=False)

# 热缓存 TTL。预热任务每 240s 续一次，这里取 900s（=容忍连续 3 轮预热失败仍不掉出热缓存），
# 避免「预热一坏就有用户被罚同步冷算」的悬崖。真实新鲜度由预热周期决定（≤4 分钟），
# 与 TTL 无关；响应里的 generated_at 供前端显示数据时间。
DASHBOARD_LIVE_TTL = 900
DASHBOARD_STALE_TTL = 86400

# 历史单日聚合缓存：已完结的日期结果不再变化，长期复用；昨天用短 TTL 兜迟到 DLR。
_DAY_AGG_KEY = "dash:day:{tag}:{d}"
_DAY_AGG_TTL_RECENT = 1800        # 昨天：迟到 DLR 仍会把 sent 改成 delivered
_DAY_AGG_TTL_SETTLED = 86400 * 30  # 前天及更早：视为已定稿
_DAY_AGG_EMPTY = {"sent": 0, "delivered": 0, "failed": 0, "cost": 0.0, "revenue": 0.0}


async def _dashboard_day_aggs(db, days, not_virtual, virtual_ids):
    """按天返回全局聚合(sent/delivered/failed/cost/revenue)，历史天走 Redis 长缓存。

    仪表板的「本周 / 本月 / 7 天趋势」原本各是一条跨天扫描：实测本月聚合 15.8s、
    7 天趋势 7.0s，占整个冷算 26s 的九成（EXPLAIN 对当月分区 563 万行 type=ALL）。
    按天切开后只有「今天」必须实时扫（≈3 万行、亚秒），已完结的天缓存复用，
    冷算降到秒级，也不再每 4 分钟把 10GB 分区刷穿 buffer pool。

    仅用于全局角色（super_admin/admin/finance/tech）；sales 带 account 过滤走
    idx_account_time 本来就便宜，仍走原查询，避免缓存串号。
    """
    import json as _json
    import redis.asyncio as _aioredis
    from datetime import date as _date
    from app.modules.sms.sms_log import SMSLog
    from sqlalchemy import func, and_, case

    today = datetime.now().date()
    out: dict = {}
    rc = None
    # 缓存键绑定「被剔除的虚拟通道集合」：新增/删除虚拟通道会改变历史天的口径，
    # 不进键名的话旧数字会一直被复用到 TTL 到期（最长 30 天）。
    tag = ",".join(str(i) for i in sorted(virtual_ids or ())) or "all"
    try:
        rc = _aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        raws = await rc.mget([_DAY_AGG_KEY.format(tag=tag, d=d.isoformat()) for d in days])
        for d, raw in zip(days, raws or []):
            if raw and d < today:  # 今天永不吃缓存
                try:
                    out[d] = _json.loads(raw)
                except Exception:
                    pass
    except Exception:
        rc = None

    missing = [d for d in days if d not in out]
    if missing:
        lo = datetime.combine(min(missing), datetime.min.time())
        hi = datetime.combine(max(missing), datetime.min.time()) + timedelta(days=1)
        q = (
            select(
                func.date(SMSLog.submit_time).label("d"),
                func.count(SMSLog.id).label("sent"),
                func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
                func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("failed"),
                net_cost("cost"),
                net_revenue("revenue"),
            )
            .where(and_(SMSLog.submit_time >= lo, SMSLog.submit_time < hi, not_virtual))
            .group_by(func.date(SMSLog.submit_time))
        )
        got = {}
        for r in (await db.execute(q)).fetchall():
            dd = r.d if isinstance(r.d, _date) else datetime.strptime(str(r.d), "%Y-%m-%d").date()
            got[dd] = {
                "sent": int(r.sent or 0),
                "delivered": int(r.delivered or 0),
                "failed": int(r.failed or 0),
                "cost": round(float(r.cost or 0), 4),
                "revenue": round(float(r.revenue or 0), 4),
            }
        for d in missing:
            out[d] = got.get(d, dict(_DAY_AGG_EMPTY))
        if rc is not None:
            try:
                pipe = rc.pipeline()
                for d in missing:
                    if d >= today:
                        continue
                    ttl = _DAY_AGG_TTL_RECENT if d >= today - timedelta(days=1) else _DAY_AGG_TTL_SETTLED
                    pipe.setex(_DAY_AGG_KEY.format(tag=tag, d=d.isoformat()), ttl, _json.dumps(out[d]))
                await pipe.execute()
            except Exception:
                pass
    if rc is not None:
        try:
            await rc.aclose()
        except Exception:
            pass
    return out


@router.get("/dashboard", response_model=dict)
async def get_admin_dashboard(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    管理员仪表板数据
    根据角色返回不同级别的统计信息：
    - super_admin/admin: 全局系统数据
    - sales: 仅负责客户的数据
    - finance: 财务相关数据
    - tech: 技术运维数据
    """
    import json
    import redis.asyncio as aioredis

    # super_admin/admin/finance/tech 看到的数据完全一致，按 role 共享缓存，避免每个用户单独 cold start
    # sales 看到的是「自己名下客户」，仍按 admin.id 隔离
    if admin.role in ("super_admin", "admin", "finance", "tech"):
        _cache_key = f"admin_dashboard:role:{admin.role}"
    else:
        _cache_key = f"admin_dashboard:{admin.id}:{admin.role}"
    _cache_ttl = DASHBOARD_LIVE_TTL   # 热缓存；由 refresh_admin_dashboard_cache_task 每 4 分钟预热，用户常态命中
    _stale_ttl = DASHBOARD_STALE_TTL  # 陈旧兜底副本(24h)：只要 seed 过一次，热缓存过期时其余请求即时吃旧数据，
                           # 永不让用户同步等 ~60-120s 冷扫描(撞前端 120s 超时)；刷新交给后台预热任务
    _stale_key = f"{_cache_key}:stale"
    _lock_key = f"{_cache_key}:lock"
    _have_lock = False
    _force_recompute = _dashboard_preheat_force.get()  # 预热任务置 True：跳过下方缓存读，强制重算覆盖
    if not _force_recompute:
        try:
            _rc = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                _cached = await _rc.get(_cache_key)
                if _cached:
                    _r = json.loads(_cached)
                    # role 共享缓存里的 admin_name 是首个请求者的名字，按当前请求者覆盖
                    _r["admin_name"] = admin.username
                    return _r
                # 热缓存已过期：单飞锁，只放一个请求去冷算（十几条 sms_logs 全表聚合 ~60-120s），
                # 其余并发请求吃 stale，杜绝缓存击穿时多请求同时全表扫描把 DB 打爆 → 集体 120s 超时。
                _have_lock = await _rc.set(_lock_key, "1", nx=True, ex=240)
                if not _have_lock:
                    _stale = await _rc.get(_stale_key)
                    if _stale:
                        _r = json.loads(_stale)
                        _r["admin_name"] = admin.username
                        return _r
                    # 冷启动且无 stale：绝不和持锁者一起冷扫描（双重全表扫描会撞 net_write_timeout=60s→2013），
                    # 轮询等持锁者(在线请求或预热任务)把缓存写好，最多 ~90s < 前端 120s。
                    for _ in range(60):
                        await asyncio.sleep(1.5)
                        _hit = await _rc.get(_cache_key) or await _rc.get(_stale_key)
                        if _hit:
                            _r = json.loads(_hit)
                            _r["admin_name"] = admin.username
                            return _r
                    # 等不到（持锁者异常退出）→ 落到下方兜底自算
                # 拿到锁、或等待超时兜底 → 落到下方真算
            finally:
                await _rc.aclose()
        except Exception:
            pass

    from app.modules.sms.channel import Channel
    from app.modules.sms.sms_log import SMSLog
    from app.modules.common.account import Account
    from sqlalchemy import func, and_, case, or_, true as _sa_true
    from datetime import timedelta

    # 剔除虚拟通道(注水/演示流量)，保留 channel_id 为 NULL 的真实失败记录。
    # 仅过滤读查询，不动 sms_logs 任何数据。无虚拟通道时退化为 true() 空过滤。
    _virtual_ids = await _virtual_channel_ids(db)
    _not_virtual = (
        or_(SMSLog.channel_id.is_(None), SMSLog.channel_id.notin_(_virtual_ids))
        if _virtual_ids else _sa_true()
    )

    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = today_start + timedelta(days=1)
    
    # 根据角色决定数据范围
    is_global_admin = admin.role in ['super_admin', 'admin']
    is_sales = is_sales_scoped(admin)
    
    # 获取销售负责的客户ID列表
    my_account_ids = []
    if is_sales:
        accounts_query = select(Account.id).where(
            and_(
                Account.sales_id == admin.id,
                Account.is_deleted == False
            )
        )
        accounts_result = await db.execute(accounts_query)
        my_account_ids = [row[0] for row in accounts_result.fetchall()]
    
    # 统计可用通道数
    channel_query = select(func.count(Channel.id)).where(
        and_(
            Channel.is_deleted == False,
            Channel.status == "active"
        )
    )
    channel_result = await db.execute(channel_query)
    active_channels = channel_result.scalar() or 0
    
    # 今日发送统计
    if is_global_admin:
        # 全局统计
        today_stats_query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
            net_profit("total_profit")
        ).where(
            and_(
                SMSLog.submit_time >= today_start,
                SMSLog.submit_time < today_end
            )
        )
    elif is_sales and my_account_ids:
        # 销售只看自己客户的数据
        today_stats_query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
            net_profit("total_profit")
        ).where(
            and_(
                SMSLog.submit_time >= today_start,
                SMSLog.submit_time < today_end,
                SMSLog.account_id.in_(my_account_ids)
            )
        )
    elif is_sales:
        # 销售无客户：返回零数据
        today_stats_query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
            net_profit("total_profit")
        ).where(
            and_(
                SMSLog.submit_time >= today_start,
                SMSLog.submit_time < today_end,
                SMSLog.id < 0  # 永假条件，保证返回零
            )
        )
    else:
        # finance/tech：全局数据
        today_stats_query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
            net_profit("total_profit")
        ).where(
            and_(
                SMSLog.submit_time >= today_start,
                SMSLog.submit_time < today_end
            )
        )
    
    today_result = await db.execute(today_stats_query.where(_not_virtual))
    today_row = today_result.first()
    
    today_sent = today_row.total_sent or 0
    today_delivered = today_row.total_delivered or 0
    today_failed = today_row.total_failed or 0
    today_cost = float(today_row.total_cost or 0)
    today_revenue = float(today_row.total_revenue or 0)
    today_profit = float(today_row.total_profit or 0)
    today_success_rate = (today_delivered / today_sent * 100) if today_sent > 0 else 0.0
    
    # 账户统计
    if is_global_admin:
        active_accounts_query = select(func.count(Account.id)).where(
            and_(
                Account.is_deleted == False,
                Account.status == "active"
            )
        )
        total_balance_query = select(func.sum(Account.balance)).where(
            Account.is_deleted == False
        )
    elif is_sales:
        active_accounts_query = select(func.count(Account.id)).where(
            and_(
                Account.sales_id == admin.id,
                Account.is_deleted == False,
                Account.status == "active"
            )
        )
        total_balance_query = select(func.sum(Account.balance)).where(
            and_(
                Account.sales_id == admin.id,
                Account.is_deleted == False
            )
        )
    else:
        active_accounts_query = select(func.count(Account.id)).where(
            and_(
                Account.is_deleted == False,
                Account.status == "active"
            )
        )
        total_balance_query = select(func.sum(Account.balance)).where(
            Account.is_deleted == False
        )
    
    accounts_result = await db.execute(active_accounts_query)
    active_accounts = accounts_result.scalar() or 0
    
    balance_result = await db.execute(total_balance_query)
    total_balance = float(balance_result.scalar() or 0)
    
    # 获取最近活跃客户 (销售角色专用)
    recent_customers = []
    if is_sales and my_account_ids:
        customers_query = select(
            Account.id,
            Account.account_name,
            Account.balance,
            Account.status,
            Account.last_login_at
        ).where(
            and_(
                Account.sales_id == admin.id,
                Account.is_deleted == False
            )
        ).order_by(Account.last_login_at.desc()).limit(5)
        
        customers_result = await db.execute(customers_query)
        for row in customers_result.fetchall():
            recent_customers.append({
                "id": row.id,
                "account_name": row.account_name,
                "balance": float(row.balance or 0),
                "status": row.status,
                "last_login": row.last_login_at.isoformat() if row.last_login_at else None
            })
    
    # ========== 丰富数据：昨日对比 / 7天趋势 / 客户TOP / 批次概览 ==========
    from app.modules.sms.sms_batch import SmsBatch

    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_start

    # 构建昨日统计查询（与今日同口径）
    if is_global_admin:
        yest_filter = and_(SMSLog.submit_time >= yesterday_start, SMSLog.submit_time < yesterday_end)
    elif is_sales and my_account_ids:
        yest_filter = and_(SMSLog.submit_time >= yesterday_start, SMSLog.submit_time < yesterday_end,
                           SMSLog.account_id.in_(my_account_ids))
    elif is_sales:
        yest_filter = and_(SMSLog.submit_time >= yesterday_start, SMSLog.submit_time < yesterday_end, SMSLog.id < 0)
    else:
        yest_filter = and_(SMSLog.submit_time >= yesterday_start, SMSLog.submit_time < yesterday_end)

    yest_q = select(
        func.count(SMSLog.id).label("total_sent"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
        func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
        net_revenue("total_revenue"),
    ).where(yest_filter)
    yest_row = (await db.execute(yest_q.where(_not_virtual))).first()
    yesterday_stats = {
        "sent": yest_row.total_sent or 0,
        "delivered": int(yest_row.total_delivered or 0),
        "failed": int(yest_row.total_failed or 0),
        "revenue": round(float(yest_row.total_revenue or 0), 4),
    }

    # 7天趋势
    week_ago = today_start - timedelta(days=6)
    # 全局角色（无 account 过滤）走按天缓存：趋势 / 本周 / 本月三处共用同一份日聚合，
    # 只有「今天」需要实时扫描，历史天命中缓存 → 原本 7 天趋势 7.0s + 本月 15.8s 变秒级。
    _use_day_cache = not is_sales
    _day_aggs: dict = {}
    _trend_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    _month_first = today.replace(day=1)
    _week_first = today - timedelta(days=today.weekday())
    if _use_day_cache:
        _span_start = min(_trend_days[0], _month_first, _week_first)
        _all_days = [_span_start + timedelta(days=i) for i in range((today - _span_start).days + 1)]
        _day_aggs = await _dashboard_day_aggs(db, _all_days, _not_virtual, _virtual_ids)
        daily_trend = [
            {
                "date": d.isoformat(),
                "sent": (_day_aggs.get(d) or _DAY_AGG_EMPTY)["sent"],
                "delivered": (_day_aggs.get(d) or _DAY_AGG_EMPTY)["delivered"],
                "revenue": round((_day_aggs.get(d) or _DAY_AGG_EMPTY)["revenue"], 2),
            }
            for d in _trend_days
        ]
    else:
        if is_sales and my_account_ids:
            trend_filter = and_(SMSLog.submit_time >= week_ago, SMSLog.submit_time < today_end,
                                SMSLog.account_id.in_(my_account_ids))
        else:
            trend_filter = and_(SMSLog.submit_time >= week_ago, SMSLog.submit_time < today_end, SMSLog.id < 0)

        trend_q = select(
            func.date(SMSLog.submit_time).label("dt"),
            func.count(SMSLog.id).label("cnt"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
            net_revenue("revenue"),
        ).where(trend_filter).group_by(func.date(SMSLog.submit_time)).order_by(func.date(SMSLog.submit_time))
        trend_rows = (await db.execute(trend_q.where(_not_virtual))).fetchall()
        daily_trend = [
            {"date": str(r.dt), "sent": r.cnt, "delivered": int(r.delivered or 0),
             "revenue": round(float(r.revenue or 0), 2)}
            for r in trend_rows
        ]

    # 今日客户发送TOP10
    top_customers = []
    if is_global_admin or (is_sales and my_account_ids):
        top_filter = [SMSLog.submit_time >= today_start, SMSLog.submit_time < today_end]
        if is_sales and my_account_ids:
            top_filter.append(SMSLog.account_id.in_(my_account_ids))
        top_q = (
            select(
                Account.account_name,
                func.count(SMSLog.id).label("sent"),
                func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
                net_revenue("revenue"),
            )
            .join(Account, SMSLog.account_id == Account.id)
            .where(and_(*top_filter))
            .group_by(Account.account_name)
            .order_by(func.count(SMSLog.id).desc())
            .limit(10)
        )
        for r in (await db.execute(top_q.where(_not_virtual))).fetchall():
            top_customers.append({
                "account_name": r.account_name,
                "sent": r.sent,
                "delivered": int(r.delivered or 0),
                "revenue": round(float(r.revenue or 0), 4),
            })

    # 今日批次概览
    batch_filter = [SmsBatch.created_at >= today_start, SmsBatch.created_at < today_end]
    if is_sales and my_account_ids:
        batch_filter.append(SmsBatch.account_id.in_(my_account_ids))
    elif is_sales:
        batch_filter.append(SmsBatch.id < 0)
    batch_overview_q = select(
        func.count(SmsBatch.id).label("total"),
        func.sum(case((SmsBatch.status == "processing", 1), else_=0)).label("processing"),
        func.sum(case((SmsBatch.status == "completed", 1), else_=0)).label("completed"),
        func.sum(case((SmsBatch.status == "failed", 1), else_=0)).label("failed"),
    ).where(and_(*batch_filter))
    bo_row = (await db.execute(batch_overview_q)).first()
    batch_overview = {
        "total": bo_row.total or 0,
        "processing": int(bo_row.processing or 0),
        "completed": int(bo_row.completed or 0),
        "failed": int(bo_row.failed or 0),
    }

    # 今日各通道发送统计 TOP8
    channel_stats = []
    if is_global_admin or admin.role == 'tech':
        ch_q = (
            select(
                Channel.channel_name,
                func.count(SMSLog.id).label("sent"),
                func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
            )
            .join(Channel, SMSLog.channel_id == Channel.id)
            .where(and_(SMSLog.submit_time >= today_start, SMSLog.submit_time < today_end))
            .group_by(Channel.channel_name)
            .order_by(func.count(SMSLog.id).desc())
            .limit(8)
        )
        for r in (await db.execute(ch_q.where(_not_virtual))).fetchall():
            channel_stats.append({
                "channel_name": r.channel_name,
                "sent": r.sent,
                "delivered": int(r.delivered or 0),
                "rate": round(int(r.delivered or 0) / r.sent * 100, 1) if r.sent > 0 else 0,
            })

    # 通道送达率异常榜：今日有量通道按送达率「升序」（最差排前），含小量但低送达的通道。
    # HAVING sent>=30 滤掉一两条的噪声；与 channel_stats（按量Top8）口径不同，单独取。
    worst_channels = []
    if is_global_admin or admin.role == 'tech':
        wc_sent = func.count(SMSLog.id)
        wc_dlv = func.sum(case((SMSLog.status == "delivered", 1), else_=0))
        wc_q = (
            select(Channel.channel_name, wc_sent.label("sent"), wc_dlv.label("delivered"))
            .join(Channel, SMSLog.channel_id == Channel.id)
            .where(and_(SMSLog.submit_time >= today_start, SMSLog.submit_time < today_end))
            .group_by(Channel.channel_name)
            .having(wc_sent >= 30)
            .order_by((wc_dlv * 1.0 / wc_sent).asc(), wc_sent.desc())
            .limit(8)
        )
        for r in (await db.execute(wc_q.where(_not_virtual))).fetchall():
            worst_channels.append({
                "channel_name": r.channel_name,
                "sent": r.sent,
                "delivered": int(r.delivered or 0),
                "rate": round(int(r.delivered or 0) / r.sent * 100, 1) if r.sent > 0 else 0,
            })

    # 今日各国发送 TOP8（按发送量排序，附送达率）
    top_countries = []
    if is_global_admin or admin.role == 'tech' or (is_sales and my_account_ids):
        tc_filter = [SMSLog.submit_time >= today_start, SMSLog.submit_time < today_end]
        if is_sales and my_account_ids:
            tc_filter.append(SMSLog.account_id.in_(my_account_ids))
        tc_q = (
            select(
                SMSLog.country_code,
                func.count(SMSLog.id).label("sent"),
                func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
            )
            .where(and_(*tc_filter))
            .group_by(SMSLog.country_code)
            .order_by(func.count(SMSLog.id).desc())
            .limit(8)
        )
        for r in (await db.execute(tc_q.where(_not_virtual))).fetchall():
            sent = r.sent or 0
            dlv = int(r.delivered or 0)
            top_countries.append({
                "country_code": r.country_code or "?",
                "sent": sent,
                "delivered": dlv,
                "rate": round(dlv / sent * 100, 1) if sent > 0 else 0,
            })

    # 余额不足客户预警（balance < 各自 low_balance_threshold，最缺的排前面）
    low_balance_accounts = []
    if is_global_admin or (is_sales and my_account_ids):
        thr = func.coalesce(Account.low_balance_threshold, 100)
        lb_filter = [
            Account.is_deleted == False,  # noqa: E712
            Account.status == "active",
            Account.balance < thr,
        ]
        if is_sales and my_account_ids:
            lb_filter.append(Account.id.in_(my_account_ids))
        lb_q = (
            select(Account.id, Account.account_name, Account.balance, Account.currency, thr.label("threshold"))
            .where(and_(*lb_filter))
            .order_by(Account.balance.asc())
            .limit(10)
        )
        for r in (await db.execute(lb_q)).fetchall():
            low_balance_accounts.append({
                "id": r.id,
                "account_name": r.account_name,
                "balance": round(float(r.balance or 0), 2),
                "currency": r.currency or "USD",
                "threshold": round(float(r.threshold or 0), 2),
            })

    # 异常/进行中批次（处理中/已暂停/失败，最近优先）
    active_batches = []
    if is_global_admin or admin.role == 'tech' or (is_sales and my_account_ids):
        ab_filter = [
            SmsBatch.is_deleted == False,  # noqa: E712
            SmsBatch.status.in_(["processing", "paused", "failed"]),
        ]
        if is_sales and my_account_ids:
            ab_filter.append(SmsBatch.account_id.in_(my_account_ids))
        ab_q = (
            select(
                SmsBatch.id, SmsBatch.batch_name, SmsBatch.status, SmsBatch.account_id,
                SmsBatch.total_count, SmsBatch.success_count, SmsBatch.failed_count,
                Account.account_name,
            )
            .join(Account, SmsBatch.account_id == Account.id, isouter=True)
            .where(and_(*ab_filter))
            .order_by(SmsBatch.id.desc())
            .limit(8)
        )
        for r in (await db.execute(ab_q)).fetchall():
            total = r.total_count or 0
            done = (r.success_count or 0) + (r.failed_count or 0)
            active_batches.append({
                "id": r.id,
                "batch_name": r.batch_name,
                "status": getattr(r.status, "value", r.status),
                "account_name": r.account_name,
                "total": total,
                "progress": round(done / total * 100, 1) if total > 0 else 0,
            })

    # ========== 业绩概览：今日 / 本周 / 本月 聚合（前端 perf-overview 卡片） ==========
    # 口径与今日统计一致，按角色复用相同的数据范围
    week_start = today_start - timedelta(days=today.weekday())  # 本周一 00:00
    month_start = datetime.combine(today.replace(day=1), datetime.min.time())

    def _period_scope(start, end):
        conds = [SMSLog.submit_time >= start, SMSLog.submit_time < end]
        if is_sales and my_account_ids:
            conds.append(SMSLog.account_id.in_(my_account_ids))
        elif is_sales:
            conds.append(SMSLog.id < 0)  # 销售无客户：永假，返回零
        return and_(*conds)

    async def _period_agg(start, end):
        q = select(
            func.count(SMSLog.id).label("sent"),
            net_cost("cost"),
            net_revenue("revenue"),
            net_profit("profit"),
        ).where(_period_scope(start, end))
        row = (await db.execute(q.where(_not_virtual))).first()
        return {
            "sent": int(row.sent or 0),
            "cost": round(float(row.cost or 0), 4),
            "revenue": round(float(row.revenue or 0), 4),
            "profit": round(float(row.profit or 0), 4),
        }

    def _sum_days(first_day):
        """按天聚合求和（全局角色）。profit = revenue - cost：sms_logs.profit 是
        STORED 生成列且不在 idx_sms_report_cov2 内，SUM(profit) 会让覆盖索引失效、
        退化成对整个分区逐行回表（实测本月聚合 15.8s vs 10.2s）。两者数值恒等。"""
        sent = 0
        cost = 0.0
        revenue = 0.0
        d = first_day
        while d <= today:
            a = _day_aggs.get(d) or _DAY_AGG_EMPTY
            sent += a["sent"]
            cost += a["cost"]
            revenue += a["revenue"]
            d += timedelta(days=1)
        return {
            "sent": sent,
            "cost": round(cost, 4),
            "revenue": round(revenue, 4),
            "profit": round(revenue - cost, 4),
        }

    period_stats = {
        "today": {
            "sent": int(today_sent),
            "cost": round(today_cost, 4),
            "revenue": round(today_revenue, 4),
            "profit": round(today_profit, 4),
        },
        "week": _sum_days(_week_first) if _use_day_cache else await _period_agg(week_start, today_end),
        "month": _sum_days(_month_first) if _use_day_cache else await _period_agg(month_start, today_end),
    }

    logger.info(f"仪表板查询: admin={admin.username}, role={admin.role}")

    view_system_monitor = admin.role in ("super_admin", "admin", "tech")
    server_metrics = None
    service_status = None
    if view_system_monitor:
        async def _check_mysql():
            try:
                await db.execute(text("SELECT 1"))
                return {"id": "mysql", "status": "ok"}
            except Exception as e:
                return {"id": "mysql", "status": "error", "message": str(e)[:160]}

        async def _check_redis():
            try:
                _r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                try:
                    await _r.ping()
                    return {"id": "redis", "status": "ok"}
                finally:
                    await _r.aclose()
            except Exception as e:
                return {"id": "redis", "status": "error", "message": str(e)[:160]}

        async def _check_rabbitmq():
            try:
                from app.utils.server_metrics import check_rabbitmq_sync
                await asyncio.to_thread(check_rabbitmq_sync)
                return {"id": "rabbitmq", "status": "ok"}
            except Exception as e:
                return {"id": "rabbitmq", "status": "error", "message": str(e)[:160]}

        async def _collect_metrics():
            try:
                from app.utils.server_metrics import collect_host_metrics_sync
                return await asyncio.to_thread(collect_host_metrics_sync)
            except Exception as e:
                logger.warning("采集主机指标失败: %s", e)
                return {"error": str(e)[:200]}

        _svc_results, server_metrics = await asyncio.gather(
            asyncio.gather(_check_mysql(), _check_redis(), _check_rabbitmq()),
            _collect_metrics(),
        )
        service_status = list(_svc_results)

    _result = {
        "success": True,
        "admin_name": admin.username,
        "admin_role": admin.role,
        # 数据快照时间：响应常来自 4 分钟一轮的预热缓存，前端据此显示「更新于 x 分钟前」，
        # 而不是让用户以为看到的是实时值。
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "statistics": {
            "today_sent": today_sent,
            "today_delivered": today_delivered,
            "today_failed": today_failed,
            "today_success_rate": round(today_success_rate, 2),
            "today_cost": round(today_cost, 4),
            "today_revenue": round(today_revenue, 4),
            "today_profit": round(today_profit, 4),
            "active_channels": active_channels,
            "active_accounts": active_accounts,
            "total_balance": round(total_balance, 2)
        },
        "period_stats": period_stats,
        "yesterday_stats": yesterday_stats,
        "daily_trend": daily_trend,
        "top_customers": top_customers,
        "batch_overview": batch_overview,
        "channel_stats": channel_stats,
        "worst_channels": worst_channels,
        "top_countries": top_countries,
        "low_balance_accounts": low_balance_accounts,
        "active_batches": active_batches,
        "recent_customers": recent_customers if is_sales else [],
        "permissions": {
            "view_global": is_global_admin,
            "view_finance": admin.role in ['super_admin', 'admin', 'finance'],
            "view_channels": admin.role in ['super_admin', 'admin', 'tech'],
            "view_customers": is_sales or is_global_admin,
            "view_system_monitor": view_system_monitor,
        },
        "server_metrics": server_metrics,
        "service_status": service_status,
    }
    try:
        _rc2 = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            _payload = json.dumps(_result, default=str)
            await _rc2.setex(_cache_key, _cache_ttl, _payload)
            await _rc2.setex(_stale_key, _stale_ttl, _payload)  # 陈旧兜底副本，供击穿期其余请求即时返回
            if _have_lock:
                await _rc2.delete(_lock_key)
        finally:
            await _rc2.aclose()
    except Exception:
        pass
    return _result


@router.get("/statistics", response_model=dict)
async def get_admin_statistics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    管理员系统级统计。销售角色仅统计归属客户（accounts.sales_id = 当前员工）的发送数据。
    """
    from app.modules.sms.sms_log import SMSLog
    from sqlalchemy import func, and_, case, or_
    
    # 默认时间范围：最近30天
    if not end_date:
        end_date = datetime.now().date().isoformat()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")
    
    time_filter = and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt)
    # 销售：仅本人名下客户
    if is_sales_scoped(admin):
        query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            func.sum(case((or_(SMSLog.status == "pending", SMSLog.status == "queued"), 1), else_=0)).label("total_pending"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
        ).select_from(SMSLog).join(Account, SMSLog.account_id == Account.id).where(
            and_(time_filter, Account.sales_id == admin.id, Account.is_deleted == False)
        )
    else:
        query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            func.sum(case((or_(SMSLog.status == "pending", SMSLog.status == "queued"), 1), else_=0)).label("total_pending"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
        ).where(time_filter)
    
    result = await db.execute(query)
    row = result.first()
    
    total_sent = row.total_sent or 0
    total_delivered = row.total_delivered or 0
    total_failed = row.total_failed or 0
    total_pending = row.total_pending or 0
    total_cost = float(row.total_cost or 0)
    total_revenue = float(row.total_revenue or 0)
    total_profit = total_revenue - total_cost
    success_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
    
    return {
        "total_sent": total_sent,
        "total_delivered": total_delivered,
        "total_failed": total_failed,
        "total_pending": total_pending,
        "success_rate": round(success_rate, 2),
        "total_cost": round(total_cost, 4),
        "total_revenue": round(total_revenue, 4),
        "total_profit": round(total_profit, 4),
        "currency": "USD"
    }


async def _virtual_channel_ids(db: AsyncSession) -> list:
    """返回所有虚拟通道(protocol=VIRTUAL)的ID。

    虚拟通道是注水/演示流量，需从发送统计中剔除，避免污染真实业务数据。
    仅用于过滤聚合查询，不改动 sms_logs 任何记录。
    """
    from app.modules.sms.channel import Channel
    res = await db.execute(select(Channel.id).where(Channel.protocol == "VIRTUAL"))
    return [r[0] for r in res.all()]


async def _channel_supplier_map(db: AsyncSession) -> dict:
    """通道ID → {id, name, code} 供应商信息；未关联供应商的通道不出现在返回值中。

    口径与 _resolve_channel_supplier_id 一致：channels.supplier_id 硬主键优先，
    早期只写了 supplier_channels 关联表的历史通道回退取其中最新的有效关联。
    差别只是这里一次性构建全表映射（通道仅百级），供批量场景使用。
    """
    from app.modules.sms.channel import Channel
    from app.modules.sms.supplier import Supplier, SupplierChannel

    mapping: dict = {}
    # 按 id 升序遍历，后写覆盖先写，等价于单通道回退时的 order_by(id.desc()).limit(1)
    link_res = await db.execute(
        select(SupplierChannel.channel_id, Supplier.id, Supplier.supplier_name, Supplier.supplier_code)
        .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
        .where(SupplierChannel.status == "active")
        .order_by(SupplierChannel.id.asc())
    )
    for cid, sid, sname, scode in link_res.all():
        mapping[cid] = {"id": sid, "name": sname, "code": scode}
    col_res = await db.execute(
        select(Channel.id, Supplier.id, Supplier.supplier_name, Supplier.supplier_code)
        .join(Supplier, Channel.supplier_id == Supplier.id)
    )
    for cid, sid, sname, scode in col_res.all():
        mapping[cid] = {"id": sid, "name": sname, "code": scode}
    return mapping


async def _supplier_channel_ids(db: AsyncSession, supplier_id: int) -> list:
    """返回归属该供应商的通道ID列表。

    sms_logs / sms_daily_stats 都没有供应商字段，供应商筛选统一先反查通道再按
    channel_id 过滤，避免聚合查询 JOIN channels 拖慢大表扫描。
    """
    return [cid for cid, info in (await _channel_supplier_map(db)).items() if info["id"] == supplier_id]


@router.get("/send-statistics", response_model=dict)
async def get_send_statistics(
    account_id: Optional[int] = Query(None, description="客户账户ID"),
    sales_id: Optional[int] = Query(None, description="归属销售/员工ID"),
    channel_id: Optional[int] = Query(None, description="通道ID"),
    supplier_id: Optional[int] = Query(None, description="供应商ID"),
    country_code: Optional[str] = Query(None, description="国家代码"),
    group_by: str = Query("account", description="分组维度: account/channel/supplier/country/sales"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """发送统计查询：支持多维度分组（客户/通道/供应商/国家/员工）+ 多条件筛选"""
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.channel import Channel
    from sqlalchemy import func, and_, case, or_

    if not end_date:
        end_date = datetime.now().date().isoformat()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    if is_sales_scoped(admin):
        sales_id = admin.id

    # 缓存兜底：正常情况下下方读取日聚合表；尚未回填的历史区间才扫描 sms_logs。
    import json as _json
    from app.utils.cache import get_redis_client
    _ck = (
        f"send_stats:v2:{group_by}:{start_date}:{end_date}:a{account_id}:s{sales_id}:"
        f"c{channel_id}:sp{supplier_id}:cc{country_code}"
    )
    try:
        _hit = await (await get_redis_client()).get(_ck)
        if _hit:
            return _json.loads(_hit)
    except Exception:
        pass

    virtual_ids = await _virtual_channel_ids(db)
    _sacc_ids = None
    if sales_id:
        # 限定该员工名下账户，避免 JOIN accounts
        _sacc = (await db.execute(select(Account.id).where(Account.sales_id == sales_id))).all()
        _sacc_ids = [a for (a,) in _sacc]
    # 供应商筛选：先反查其通道，再按 channel_id 过滤（无通道时用不可能条件，返回空集）
    _sup_ch_ids = await _supplier_channel_ids(db, supplier_id) if supplier_id else None

    # 覆盖完整时从日聚合表读取：整月约几千行，而不是 sms_logs 的 919 万行。
    _use_daily_rollup = False
    try:
        from app.services.sms_daily_stats import has_complete_daily_stats

        _use_daily_rollup = await has_complete_daily_stats(
            db, start_dt.date(), end_dt.date() - timedelta(days=1)
        )
        # 高频聚合刻意不携带 country_code，避免刷新时对明细做随机回表；
        # 国家分组/筛选保持原 SQL + Redis 缓存，统计口径不变。
        _use_daily_rollup = _use_daily_rollup and group_by != "country" and not country_code
    except Exception as exc:
        logger.warning("发送统计日聚合覆盖检查失败，回退明细查询: {}", exc)

    if _use_daily_rollup:
        from app.modules.sms.sms_daily_stat import SMSDailyStat

        D = SMSDailyStat
        _total = func.sum(D.submit_total)
        _priced = func.sum(D.priced_count)
        agg_cols = [
            _total.label("submit_total"),
            func.sum(case((D.status == "delivered", D.submit_total), else_=0)).label("success_count"),
            func.sum(case((D.status == "failed", D.submit_total), else_=0)).label("failed_count"),
            func.sum(case((D.status.in_(("pending", "queued")), D.submit_total), else_=0)).label("pending_count"),
            (func.sum(D.total_revenue) / func.nullif(_priced, 0)).label("avg_unit_price"),
            func.sum(D.total_cost).label("total_cost"),
            func.sum(D.total_revenue).label("total_revenue"),
        ]
        # 供应商维度先按 channel_id 聚合，再在 Python 归约到供应商（日聚合表无供应商字段）
        if group_by in ("channel", "supplier"):
            gcol = D.channel_id
        elif group_by == "country":
            gcol = D.country_code
        else:
            gcol = D.account_id
        base = select(gcol.label("gid"), *agg_cols).where(
            D.stat_date >= start_dt.date(), D.stat_date < end_dt.date()
        )
        if virtual_ids:
            base = base.where(D.channel_id.notin_(virtual_ids))
        if account_id:
            base = base.where(D.account_id == account_id)
        if channel_id:
            base = base.where(D.channel_id == channel_id)
        if _sup_ch_ids is not None:
            base = base.where(D.channel_id.in_(_sup_ch_ids) if _sup_ch_ids else (D.channel_id < 0))
        if country_code:
            base = base.where(func.upper(D.country_code) == country_code.upper())
        if sales_id:
            base = base.where(D.account_id.in_(_sacc_ids) if _sacc_ids else (D.account_id < 0))
        if group_by in ("channel", "supplier"):
            base = base.where(D.channel_id != 0)
        elif group_by == "country":
            base = base.where(D.country_code != "")
    else:
        agg_cols = [
            func.count(SMSLog.id).label("submit_total"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("success_count"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("failed_count"),
            func.sum(case((or_(SMSLog.status == "pending", SMSLog.status == "queued"), 1), else_=0)).label("pending_count"),
            func.avg(SMSLog.selling_price).label("avg_unit_price"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
        ]
        # account 与 sales 均先按 account_id 聚合，sales 再在 Python 归约到员工；
        # supplier 同理，先按 channel_id 聚合再归约到供应商。
        if group_by in ("channel", "supplier"):
            gcol = SMSLog.channel_id
        elif group_by == "country":
            gcol = SMSLog.country_code
        else:
            gcol = SMSLog.account_id
        base = select(gcol.label("gid"), *agg_cols).where(
            and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt)
        )
        if virtual_ids:
            base = base.where(or_(SMSLog.channel_id.is_(None), SMSLog.channel_id.notin_(virtual_ids)))
        if account_id:
            base = base.where(SMSLog.account_id == account_id)
        if channel_id:
            base = base.where(SMSLog.channel_id == channel_id)
        if _sup_ch_ids is not None:
            base = base.where(SMSLog.channel_id.in_(_sup_ch_ids) if _sup_ch_ids else (SMSLog.id < 0))
        if country_code:
            base = base.where(func.upper(SMSLog.country_code) == country_code.upper())
        if sales_id:
            base = base.where(SMSLog.account_id.in_(_sacc_ids) if _sacc_ids else (SMSLog.id < 0))
        if group_by in ("channel", "supplier"):
            base = base.where(SMSLog.channel_id.isnot(None))
        elif group_by == "country":
            base = base.where(SMSLog.country_code.isnot(None))

    base = base.group_by(gcol)

    agg_rows = (await db.execute(base)).all()

    name_map: dict = {}

    # sales 维度：按 account_id 的聚合结果在 Python 里归约到 sales_id
    if group_by == "sales":
        _acct_ids = [r.gid for r in agg_rows if r.gid is not None]
        _a2s: dict = {}
        if _acct_ids:
            for aid, sid in (await db.execute(
                select(Account.id, Account.sales_id).where(Account.id.in_(_acct_ids))
            )).all():
                _a2s[aid] = sid
        _sb: dict = {}
        for r in agg_rows:
            sid = _a2s.get(r.gid)
            if sid is None:
                continue
            b = _sb.setdefault(sid, {"submit_total": 0, "success_count": 0, "failed_count": 0,
                                     "pending_count": 0, "total_cost": 0.0, "total_revenue": 0.0})
            b["submit_total"] += int(r.submit_total or 0)
            b["success_count"] += int(r.success_count or 0)
            b["failed_count"] += int(r.failed_count or 0)
            b["pending_count"] += int(r.pending_count or 0)
            b["total_cost"] += float(r.total_cost or 0)
            b["total_revenue"] += float(r.total_revenue or 0)
        from types import SimpleNamespace
        rows = [SimpleNamespace(
            gid=sid, submit_total=b["submit_total"], success_count=b["success_count"],
            failed_count=b["failed_count"], pending_count=b["pending_count"],
            total_cost=b["total_cost"], total_revenue=b["total_revenue"],
            avg_unit_price=(b["total_revenue"] / b["submit_total"] if b["submit_total"] else 0),
        ) for sid, b in _sb.items()]
    elif group_by == "supplier":
        # 通道维度的聚合结果按 channels.supplier_id 归约到供应商；
        # 未关联供应商的通道并入 gid=0 的“未关联供应商”桶，保证总量不丢。
        _ch2sup = await _channel_supplier_map(db)
        _pb: dict = {}
        for r in agg_rows:
            info = _ch2sup.get(r.gid)
            sid = info["id"] if info else 0
            if info:
                name_map[sid] = {"name": info["name"], "code": info["code"]}
            b = _pb.setdefault(sid, {"submit_total": 0, "success_count": 0, "failed_count": 0,
                                     "pending_count": 0, "total_cost": 0.0, "total_revenue": 0.0,
                                     "price_weight": 0.0})
            _st = int(r.submit_total or 0)
            b["submit_total"] += _st
            b["success_count"] += int(r.success_count or 0)
            b["failed_count"] += int(r.failed_count or 0)
            b["pending_count"] += int(r.pending_count or 0)
            b["total_cost"] += float(r.total_cost or 0)
            b["total_revenue"] += float(r.total_revenue or 0)
            b["price_weight"] += float(r.avg_unit_price or 0) * _st
        from types import SimpleNamespace
        rows = [SimpleNamespace(
            gid=sid, submit_total=b["submit_total"], success_count=b["success_count"],
            failed_count=b["failed_count"], pending_count=b["pending_count"],
            total_cost=b["total_cost"], total_revenue=b["total_revenue"],
            # 单价按条数加权，与通道维度显示的单价口径保持一致
            avg_unit_price=(b["price_weight"] / b["submit_total"] if b["submit_total"] else 0),
        ) for sid, b in _pb.items()]
    else:
        rows = agg_rows

    if group_by == "channel":
        ch_ids = list({r.gid for r in rows if r.gid})
        if ch_ids:
            ch_res = await db.execute(select(Channel.id, Channel.channel_name, Channel.channel_code).where(Channel.id.in_(ch_ids)))
            for r in ch_res:
                name_map[r.id] = {"name": r.channel_name, "code": r.channel_code}
    elif group_by == "account":
        acc_ids = list({r.gid for r in rows if r.gid})
        if acc_ids:
            acc_res = await db.execute(select(Account.id, Account.account_name).where(Account.id.in_(acc_ids)))
            for r in acc_res:
                name_map[r.id] = r.account_name
    elif group_by == "sales":
        staff_ids = list({r.gid for r in rows if r.gid})
        if staff_ids:
            staff_res = await db.execute(select(AdminUser.id, AdminUser.real_name, AdminUser.username).where(AdminUser.id.in_(staff_ids)))
            for r in staff_res:
                name_map[r.id] = r.real_name or r.username

    # 退补充值(refund_recharge)：来自 balance_logs，按 账户→员工 归属；仅列示，不计入成本/收入/利润。
    # 通道/国家维度无字段可归属（balance_logs 无 channel/country），行内不显示，仅汇总体现总额。
    from app.modules.common.balance_log import BalanceLog
    rr_where = [
        BalanceLog.change_type == "refund_recharge",
        BalanceLog.created_at >= start_dt,
        BalanceLog.created_at < end_dt,
    ]
    if account_id:
        rr_where.append(BalanceLog.account_id == account_id)
    if sales_id:
        rr_where.append(Account.sales_id == sales_id)
    rr_rows = (await db.execute(
        select(
            BalanceLog.account_id.label("acc"),
            Account.sales_id.label("sid"),
            func.count(BalanceLog.id).label("cnt"),
            func.coalesce(func.sum(BalanceLog.amount), 0).label("amt"),
        )
        .join(Account, BalanceLog.account_id == Account.id)
        .where(and_(*rr_where))
        .group_by(BalanceLog.account_id, Account.sales_id)
    )).all()
    rr_by_account: dict = {}
    rr_by_sales: dict = {}
    rr_total_cnt = 0
    rr_total_amt = 0.0
    for rr in rr_rows:
        _c = int(rr.cnt or 0)
        _a = float(rr.amt or 0)
        rr_by_account[rr.acc] = {"cnt": _c, "amt": _a}
        if rr.sid is not None:
            _b = rr_by_sales.setdefault(rr.sid, {"cnt": 0, "amt": 0.0})
            _b["cnt"] += _c
            _b["amt"] += _a
        rr_total_cnt += _c
        rr_total_amt += _a

    # 汇总
    sum_submit = sum_success = sum_failed = sum_pending = 0
    sum_cost = sum_revenue = 0.0

    items = []
    for r in rows:
        submit_total = r.submit_total or 0
        success_count = r.success_count or 0
        failed_count = r.failed_count or 0
        pending_count = r.pending_count or 0
        total_cost = round(float(r.total_cost or 0), 5)
        total_revenue = round(float(r.total_revenue or 0), 5)
        profit = round(total_revenue - total_cost, 5)
        if group_by == "account":
            _rr = rr_by_account.get(r.gid)
        elif group_by == "sales":
            _rr = rr_by_sales.get(r.gid)
        else:
            _rr = None  # 通道/供应商/国家维度无法归属退补
        refunded = _rr["cnt"] if _rr else 0
        refund_amt = round(_rr["amt"], 5) if _rr else 0.0
        success_rate = round((success_count / submit_total * 100) if submit_total > 0 else 0, 2)

        sum_submit += submit_total
        sum_success += success_count
        sum_failed += failed_count
        sum_pending += pending_count
        sum_cost += total_cost
        sum_revenue += total_revenue

        item: dict = {
            "submit_total": submit_total,
            "success_count": success_count,
            "failed_count": failed_count,
            "pending_count": pending_count,
            "success_rate": success_rate,
            "avg_unit_price": round(float(r.avg_unit_price or 0), 5),
            "total_cost": total_cost,
            "total_revenue": total_revenue,
            "profit": profit,
            "refunded_count": refunded,
            "refund_amount": refund_amt,
        }

        if group_by == "channel":
            ch_info = name_map.get(r.gid, {})
            item["channel_id"] = r.gid
            item["channel_name"] = ch_info.get("name", "-") if isinstance(ch_info, dict) else "-"
            item["channel_code"] = ch_info.get("code", "-") if isinstance(ch_info, dict) else "-"
            item["dim_label"] = item["channel_name"]
        elif group_by == "supplier":
            sp_info = name_map.get(r.gid) or {}
            item["supplier_id"] = r.gid or None
            item["supplier_name"] = sp_info.get("name") or "未关联供应商"
            item["supplier_code"] = sp_info.get("code") or ""
            item["dim_label"] = item["supplier_name"]
        elif group_by == "country":
            item["country_code"] = r.gid
            item["dim_label"] = r.gid
        elif group_by == "sales":
            item["sales_id"] = r.gid
            item["sales_name"] = name_map.get(r.gid, "未分配")
            item["dim_label"] = item["sales_name"]
        else:
            item["account_id"] = r.gid
            item["account_name"] = name_map.get(r.gid, "-")
            item["dim_label"] = item["account_name"]

        items.append(item)

    items.sort(key=lambda x: x["submit_total"], reverse=True)

    summary = {
        "submit_total": sum_submit,
        "success_count": sum_success,
        "failed_count": sum_failed,
        "pending_count": sum_pending,
        "success_rate": round((sum_success / sum_submit * 100) if sum_submit > 0 else 0, 2),
        "total_cost": round(sum_cost, 5),
        "total_revenue": round(sum_revenue, 5),
        "profit": round(sum_revenue - sum_cost, 5),
        "refunded_count": rr_total_cnt,
        "refund_amount": round(rr_total_amt, 5),
    }

    resp = {
        "success": True,
        "total": len(items),
        "items": items,
        "summary": summary,
        "filters": {"start_date": start_date, "end_date": end_date, "group_by": group_by},
    }
    try:
        # 已结束区间数据冻结，长缓存；包含今天的区间保留 15 分钟兜底缓存。
        _ttl = 86400 if end_dt.date() <= datetime.now().date() else 900
        await (await get_redis_client()).set(_ck, _json.dumps(resp, default=str), ex=_ttl)
    except Exception:
        pass
    return resp


@router.get("/reports/success-rate", response_model=dict)
async def get_admin_success_rate(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """管理员：按通道/国家成功率分析（全系统）"""
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.channel import Channel
    from sqlalchemy import func, and_, case

    if not end_date:
        end_date = datetime.now().date().isoformat()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    base_filter = and_(
        SMSLog.submit_time >= start_dt,
        SMSLog.submit_time < end_dt
    )

    # 按通道统计（销售仅看归属客户）
    ch_query = select(
        Channel.id, Channel.channel_code, Channel.channel_name,
        func.count(SMSLog.id).label("total"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
    ).join(SMSLog, Channel.id == SMSLog.channel_id)
    if is_sales_scoped(admin):
        ch_query = ch_query.join(Account, SMSLog.account_id == Account.id).where(
            and_(base_filter, Account.sales_id == admin.id, Account.is_deleted == False)
        )
    else:
        ch_query = ch_query.where(base_filter)
    ch_query = ch_query.group_by(Channel.id, Channel.channel_code, Channel.channel_name)
    ch_result = await db.execute(ch_query)
    by_channel = []
    for r in ch_result:
        t, d = r.total or 0, r.delivered or 0
        by_channel.append({
            "channel_id": r.id, "channel_code": r.channel_code, "channel_name": r.channel_name,
            "total": t, "delivered": d, "success_rate": round(d / t * 100, 2) if t > 0 else 0
        })

    # 按国家统计 Top 15
    country_query = select(
        SMSLog.country_code,
        func.count(SMSLog.id).label("total"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
    )
    if is_sales_scoped(admin):
        country_query = country_query.select_from(SMSLog).join(
            Account, SMSLog.account_id == Account.id
        ).where(
            and_(
                base_filter,
                SMSLog.country_code.isnot(None),
                Account.sales_id == admin.id,
                Account.is_deleted == False,
            )
        )
    else:
        country_query = country_query.where(base_filter, SMSLog.country_code.isnot(None))
    country_query = country_query.group_by(SMSLog.country_code).order_by(
        func.count(SMSLog.id).desc()
    ).limit(15)
    country_result = await db.execute(country_query)
    by_country = []
    for r in country_result:
        t, d = r.total or 0, r.delivered or 0
        by_country.append({
            "country_code": r.country_code, "total": t, "delivered": d,
            "success_rate": round(d / t * 100, 2) if t > 0 else 0
        })

    total_query = select(
        func.count(SMSLog.id).label("total"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
    )
    if is_sales_scoped(admin):
        total_query = total_query.select_from(SMSLog).join(
            Account, SMSLog.account_id == Account.id
        ).where(and_(base_filter, Account.sales_id == admin.id, Account.is_deleted == False))
    else:
        total_query = total_query.where(base_filter)
    tr = (await db.execute(total_query)).first()
    overall = round((tr.delivered or 0) / (tr.total or 1) * 100, 2)

    return {"overall_rate": overall, "by_channel": by_channel, "by_country": by_country}


@router.get("/reports/daily-stats", response_model=dict)
async def get_admin_daily_stats(
    days: int = Query(7, ge=1, le=90),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_id: Optional[int] = Query(None, description="客户账户ID"),
    channel_id: Optional[int] = Query(None, description="通道ID"),
    supplier_id: Optional[int] = Query(None, description="供应商ID"),
    country_code: Optional[str] = Query(None, description="国家代码"),
    sales_id: Optional[int] = Query(None, description="归属销售/员工ID"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """管理员：每日统计（用于图表）。支持按客户/通道/供应商/国家筛选。销售角色仅统计归属客户。"""
    import json as _json
    from app.modules.sms.sms_log import SMSLog
    from app.utils.cache import get_redis_client
    from sqlalchemy import func, and_, case, or_ as sa_or

    if start_date and end_date:
        try:
            start_dt = datetime.fromisoformat(start_date).date()
            end_dt = datetime.fromisoformat(end_date).date() + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        end_dt = datetime.now().date() + timedelta(days=1)
        start_dt = end_dt - timedelta(days=max(1, min(90, days)))

    if is_sales_scoped(admin):
        sales_id = admin.id

    _ck = (
        f"admin_daily_stats:v1:{start_dt}:{end_dt}:a{account_id}:s{sales_id}:"
        f"c{channel_id}:sp{supplier_id}:cc{country_code}"
    )
    try:
        _hit = await (await get_redis_client()).get(_ck)
        if _hit:
            return _json.loads(_hit)
    except Exception:
        pass

    virtual_ids = await _virtual_channel_ids(db)
    _sacc_ids = None
    if sales_id:
        _sacc = (await db.execute(
            select(Account.id).where(Account.sales_id == sales_id, Account.is_deleted == False)
        )).all()
        _sacc_ids = [a for (a,) in _sacc]
    _sup_ch_ids = await _supplier_channel_ids(db, supplier_id) if supplier_id else None

    _use_daily_rollup = False
    try:
        from app.services.sms_daily_stats import has_complete_daily_stats

        _use_daily_rollup = await has_complete_daily_stats(
            db, start_dt, end_dt - timedelta(days=1)
        )
        _use_daily_rollup = _use_daily_rollup and not country_code
    except Exception as exc:
        logger.warning("每日趋势日聚合覆盖检查失败，回退明细查询: {}", exc)

    if _use_daily_rollup:
        from app.modules.sms.sms_daily_stat import SMSDailyStat

        D = SMSDailyStat
        base = select(
            D.stat_date.label("date"),
            func.sum(D.submit_total).label("total_sent"),
            func.sum(case((D.status == "delivered", D.submit_total), else_=0)).label("total_delivered"),
            func.sum(case((D.status == "failed", D.submit_total), else_=0)).label("total_failed"),
            func.sum(D.total_cost).label("total_cost"),
            func.sum(D.total_revenue).label("total_revenue"),
        ).where(D.stat_date >= start_dt, D.stat_date < end_dt)
        if virtual_ids:
            base = base.where(D.channel_id.notin_(virtual_ids))
        if account_id:
            base = base.where(D.account_id == account_id)
        if channel_id:
            base = base.where(D.channel_id == channel_id)
        if _sup_ch_ids is not None:
            base = base.where(D.channel_id.in_(_sup_ch_ids) if _sup_ch_ids else (D.channel_id < 0))
        if country_code:
            base = base.where(func.upper(D.country_code) == country_code.upper())
        if sales_id:
            base = base.where(D.account_id.in_(_sacc_ids) if _sacc_ids else (D.account_id < 0))
        base = base.group_by(D.stat_date).order_by(D.stat_date.asc())
    else:
        base = select(
            func.date(SMSLog.submit_time).label("date"),
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            net_cost("total_cost"),
            net_revenue("total_revenue"),
        ).where(and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt))
        if virtual_ids:
            base = base.where(sa_or(SMSLog.channel_id.is_(None), SMSLog.channel_id.notin_(virtual_ids)))
        if account_id:
            base = base.where(SMSLog.account_id == account_id)
        if channel_id:
            base = base.where(SMSLog.channel_id == channel_id)
        if _sup_ch_ids is not None:
            base = base.where(SMSLog.channel_id.in_(_sup_ch_ids) if _sup_ch_ids else (SMSLog.id < 0))
        if country_code:
            base = base.where(func.upper(SMSLog.country_code) == country_code.upper())
        if sales_id:
            base = base.where(SMSLog.account_id.in_(_sacc_ids) if _sacc_ids else (SMSLog.id < 0))
        base = base.group_by(func.date(SMSLog.submit_time)).order_by(func.date(SMSLog.submit_time).asc())

    result = (await db.execute(base)).all()

    statistics = []
    for row in result:
        ts, td = row.total_sent or 0, row.total_delivered or 0
        tf = row.total_failed or 0
        cost, rev = float(row.total_cost or 0), float(row.total_revenue or 0)
        statistics.append({
            "date": row.date.isoformat() if row.date else None,
            "total_sent": ts,
            "total_delivered": td,
            "total_failed": tf,
            "success_rate": round(td / ts * 100, 2) if ts > 0 else 0,
            "total_cost": round(cost, 4),
            "total_revenue": round(rev, 4),
            "total_profit": round(rev - cost, 4),
        })
    resp = {"success": True, "days": (end_dt - start_dt).days, "statistics": statistics}
    try:
        _ttl = 86400 if end_dt <= datetime.now().date() else 900
        await (await get_redis_client()).set(_ck, _json.dumps(resp, default=str), ex=_ttl)
    except Exception:
        pass
    return resp


@router.get("/users", response_model=dict)
async def list_admin_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    include_monthly_stats: bool = Query(
        True,
        description="为 false 时跳过本月 sms_logs 聚合，避免大数据量下请求过慢导致网关/Cloudflare 522",
    ),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取管理员用户列表（不包含超级管理员）"""
    query = select(AdminUser)
    
    # 只过滤掉超级管理员（id=1），其他角色均显示
    query = query.where(AdminUser.role != 'super_admin')
    
    # 默认不显示已删除(inactive)的员工
    if status:
        query = query.where(AdminUser.status == status)
    else:
        query = query.where(AdminUser.status != 'inactive')
    
    if role:
        query = query.where(AdminUser.role == role)
    
    comm_map: dict = {}
    if include_monthly_stats:
        import json as _json
        from app.utils.cache import get_redis_client

        ym = datetime.now().strftime("%Y-%m")
        _cache_key = f"admin:monthly_commission:{ym}"
        _CACHE_TTL = 1800  # 30 分钟；员工业绩无需实时，避免每次扫描 200 万行 sms_logs

        _redis = await get_redis_client()
        _cached = await _redis.get(_cache_key)
        if _cached:
            try:
                comm_map = {int(k): v for k, v in _json.loads(_cached).items()}
            except Exception:
                comm_map = {}
        else:
            # 缓存未命中：执行聚合查询，再存入 Redis
            # profit 已是整条(含分段)总利润，勿再乘 message_count（审计 P0-1）
            from app.services.staff_commission import get_monthly_commission_map

            comm_map = await get_monthly_commission_map(db)
            try:
                await _redis.setex(_cache_key, _CACHE_TTL, _json.dumps(comm_map))
            except Exception:
                pass
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return {
        "success": True,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "real_name": u.real_name,
                "tg_username": u.tg_username,
                "role": u.role,
                "status": u.status,
                "tg_id": u.tg_id,
                "commission_rate": float(u.commission_rate) if u.commission_rate else 0,
                # 销售授信（循环信用额度）
                "credit_limit": float(u.credit_limit or 0),
                "credit_used": float(u.credit_used or 0),
                "credit_available": float((u.credit_limit or 0) - (u.credit_used or 0)),
                "monthly_performance": round(comm_map.get(u.id, 0.0), 2),
                "monthly_commission": round(comm_map.get(u.id, 0.0) * (float(u.commission_rate or 0) / 100.0), 2),
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    }


# ========== 员工管理 API ==========
class StaffCreateRequest(BaseModel):
    username: str
    password: str
    real_name: str
    tg_username: Optional[str] = None
    commission_rate: Optional[float] = 0
    role: str = "sales"  # sales, tech, finance, admin
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        allowed = ['sales', 'tech', 'finance', 'admin']
        if v not in allowed:
            raise ValueError(f'角色必须是 {allowed} 之一')
        return v


class StaffUpdateRequest(BaseModel):
    real_name: Optional[str] = None
    tg_username: Optional[str] = None
    commission_rate: Optional[float] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None  # 可选重置密码


def _normalize_staff_tg_username(v: Optional[str]) -> Optional[str]:
    """员工 TG 展示名：去空白、去前导 @，空串视为未填"""
    if v is None:
        return None
    s = str(v).strip().lstrip("@")
    return s or None


def _clear_staff_telegram_binding(staff: AdminUser) -> bool:
    """清除员工的业务助手(Telegram Bot)绑定数据，删除/禁用/锁定时同步调用"""
    if staff.tg_id or staff.tg_username:
        staff.tg_id = None
        staff.tg_username = None
        logger.info(f"员工 {staff.username} 已同步清除业务助手绑定")
        return True
    return False


@router.post("/users", response_model=dict)
async def create_staff(
    request: StaffCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建员工账户（销售/技术/财务）"""
    # 仅超级管理员和管理员可创建
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限创建员工")
    
    # 检查用户名是否已存在
    existing_result = await db.execute(
        select(AdminUser).where(AdminUser.username == request.username)
    )
    existing_staff = existing_result.scalar_one_or_none()
    
    from app.services.operation_log import log_operation as _log_op

    if existing_staff:
        # 若为在职状态，不允许重复创建
        if existing_staff.status == 'active':
            raise HTTPException(status_code=400, detail="用户名已存在")
        # 若为已禁用/锁定状态，复用该账户并重新激活
        existing_staff.password_hash = AuthService.hash_password(request.password)
        existing_staff.real_name = request.real_name
        existing_staff.tg_username = _normalize_staff_tg_username(request.tg_username)
        existing_staff.commission_rate = request.commission_rate or 0
        existing_staff.role = request.role
        existing_staff.status = 'active'
        existing_staff.login_failed_count = 0  # 重置登录失败次数
        await db.commit()
        await db.refresh(existing_staff)
        await _log_op(
            db, admin_id=admin.id, admin_name=admin.username,
            module="security", action="create", target_type="admin_user",
            target_id=str(existing_staff.id),
            title=f"重新激活管理员账号 {request.username}（{request.role}）",
        )
        return {
            "success": True,
            "message": "员工创建成功",
            "user": {
                "id": existing_staff.id,
                "username": existing_staff.username,
                "real_name": existing_staff.real_name,
                "role": existing_staff.role
            }
        }

    # 创建新员工
    new_staff = AdminUser(
        username=request.username,
        password_hash=AuthService.hash_password(request.password),
        real_name=request.real_name,
        tg_username=_normalize_staff_tg_username(request.tg_username),
        commission_rate=request.commission_rate or 0,
        role=request.role,
        status='active'
    )
    db.add(new_staff)
    await db.commit()
    await db.refresh(new_staff)

    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="security", action="create", target_type="admin_user",
        target_id=str(new_staff.id),
        title=f"创建管理员账号 {request.username}（{request.role}）",
    )

    return {
        "success": True,
        "message": "员工创建成功",
        "user": {
            "id": new_staff.id,
            "username": new_staff.username,
            "real_name": new_staff.real_name,
            "role": new_staff.role
        }
    }


@router.put("/users/{user_id}", response_model=dict)
async def update_staff(
    user_id: int,
    request: StaffUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新员工信息"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限修改员工")
    
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    staff = result.scalar_one_or_none()
    
    if not staff:
        raise HTTPException(status_code=404, detail="员工不存在")
    
    # 不能修改超级管理员
    if staff.role == 'super_admin' and admin.role != 'super_admin':
        raise HTTPException(status_code=403, detail="无权限修改超级管理员")
    
    # 更新字段
    cleared_tg_for_username_change = False
    if request.real_name is not None:
        staff.real_name = request.real_name
    # Bot 以 tg_id（数字 ID）识别员工，仅改 tg_username 不会换绑。若展示名变更则清除 tg_id，避免旧号仍被视为该员工。
    if "tg_username" in request.model_fields_set:
        old_norm = _normalize_staff_tg_username(staff.tg_username)
        new_norm = _normalize_staff_tg_username(request.tg_username)
        old_cmp = (old_norm or "").lower()
        new_cmp = (new_norm or "").lower()
        if old_cmp != new_cmp and staff.tg_id is not None:
            staff.tg_id = None
            cleared_tg_for_username_change = True
            logger.info(
                "员工 %s 修改 Telegram 用户名展示字段 (%r -> %r)，已清除 tg_id，需在 Bot 内重新绑定",
                staff.username,
                old_norm,
                new_norm,
            )
        staff.tg_username = new_norm
    if request.commission_rate is not None:
        staff.commission_rate = request.commission_rate
    if request.role is not None and admin.role == 'super_admin':
        staff.role = request.role
    if request.status is not None:
        staff.status = request.status
        # 设为 inactive 或 locked 时同步清除业务助手绑定
        if request.status in ('inactive', 'locked'):
            _clear_staff_telegram_binding(staff)
    if request.password:
        staff.password_hash = AuthService.hash_password(request.password)
    
    await db.commit()

    from app.services.operation_log import log_operation as _log_op
    _updated = list(request.model_dump(exclude_unset=True).keys())
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="security", action="update", target_type="admin_user",
        target_id=str(user_id),
        title=f"更新管理员账号 {staff.username}",
        detail=str(_updated),
    )

    msg = "员工信息已更新"
    if cleared_tg_for_username_change:
        msg += "：已解除原 Telegram 绑定，请新员工在 TG 业务助手内用登录名+密码完成绑定"

    return {
        "success": True,
        "message": msg,
        "telegram_rebind_required": cleared_tg_for_username_change,
    }


def _credit_log_dict(l) -> dict:
    return {
        "id": l.id,
        "sales_id": l.sales_id,
        "change_type": l.change_type,
        "amount": float(l.amount),
        "credit_limit_after": float(l.credit_limit_after),
        "credit_used_after": float(l.credit_used_after),
        "account_id": l.account_id,
        "operator_name": l.operator_name,
        "description": l.description,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }


@router.post("/users/{user_id}/credit/adjust", response_model=dict)
async def adjust_staff_credit(
    user_id: int,
    request: StaffCreditAdjustRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：调整销售授信（设置额度上限 / 结算冲销）。均写授信账本。"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限调整授信额度")
    from app.modules.common.sales_credit_log import SalesCreditLog
    from decimal import Decimal

    me = (await db.execute(
        select(AdminUser).where(AdminUser.id == user_id).with_for_update()
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(status_code=404, detail="员工不存在")
    if me.role != 'sales':
        raise HTTPException(status_code=400, detail="授信额度仅对销售角色有效")

    credit_limit = Decimal(str(me.credit_limit or 0))
    credit_used = Decimal(str(me.credit_used or 0))
    note = (request.description or "").strip() or None
    changed = []

    if request.credit_limit is not None:
        new_limit = Decimal(str(request.credit_limit))
        if new_limit < 0:
            raise HTTPException(status_code=400, detail="额度不能为负")
        if new_limit < credit_used:
            raise HTTPException(status_code=400, detail=f"新额度不能低于已用授信 {float(credit_used)}")
        delta = new_limit - credit_limit
        me.credit_limit = new_limit
        credit_limit = new_limit
        db.add(SalesCreditLog(
            sales_id=user_id, change_type="limit_change", amount=abs(delta),
            credit_limit_after=credit_limit, credit_used_after=credit_used,
            operator_id=admin.id, operator_name=admin.username,
            description=(note + f"（额度调整 {float(delta):+g}）") if note else f"额度调整 {float(delta):+g}",
        ))
        changed.append("limit")

    if request.settle_amount is not None:
        settle = Decimal(str(request.settle_amount))
        if settle <= 0:
            raise HTTPException(status_code=400, detail="结算金额必须大于 0")
        if settle > credit_used:
            raise HTTPException(status_code=400, detail=f"结算金额不能超过已用授信 {float(credit_used)}")
        credit_used = credit_used - settle
        me.credit_used = credit_used
        db.add(SalesCreditLog(
            sales_id=user_id, change_type="settlement", amount=settle,
            credit_limit_after=credit_limit, credit_used_after=credit_used,
            operator_id=admin.id, operator_name=admin.username,
            description=(note + "（结算冲销）") if note else "结算冲销",
        ))
        changed.append("settle")

    if not changed:
        raise HTTPException(status_code=400, detail="无调整内容")

    await db.commit()

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="finance", action="update", target_type="admin_user",
        target_id=str(user_id),
        title=f"调整销售授信 {me.username}（{'/'.join(changed)}）",
        detail=f'{{"credit_limit": {float(credit_limit)}, "credit_used": {float(credit_used)}}}',
    )

    return {
        "success": True,
        "credit_limit": float(credit_limit),
        "credit_used": float(credit_used),
        "credit_available": float(credit_limit - credit_used),
    }


@router.get("/users/{user_id}/credit/logs", response_model=dict)
async def list_staff_credit_logs(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：查看某销售的授信流水账本"""
    if admin.role not in ['super_admin', 'admin', 'finance']:
        raise HTTPException(status_code=403, detail="无权限查看授信账本")
    from app.modules.common.sales_credit_log import SalesCreditLog
    from sqlalchemy import func

    total = await db.scalar(
        select(func.count(SalesCreditLog.id)).where(SalesCreditLog.sales_id == user_id)
    ) or 0
    rows = (await db.execute(
        select(SalesCreditLog).where(SalesCreditLog.sales_id == user_id)
        .order_by(SalesCreditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"success": True, "total": total, "page": page, "page_size": page_size,
            "logs": [_credit_log_dict(l) for l in rows]}


@router.get("/my-credit", response_model=dict)
async def get_my_credit(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """销售：查看自己的授信额度与最近流水（非销售返回 applicable=False）"""
    from decimal import Decimal
    applicable = is_sales_scoped(admin)
    credit_limit = Decimal(str(admin.credit_limit or 0))
    credit_used = Decimal(str(admin.credit_used or 0))
    logs = []
    if applicable:
        from app.modules.common.sales_credit_log import SalesCreditLog
        rows = (await db.execute(
            select(SalesCreditLog).where(SalesCreditLog.sales_id == admin.id)
            .order_by(SalesCreditLog.created_at.desc()).limit(50)
        )).scalars().all()
        logs = [_credit_log_dict(l) for l in rows]
    return {
        "success": True,
        "applicable": applicable,
        "credit_limit": float(credit_limit),
        "credit_used": float(credit_used),
        "credit_available": float(credit_limit - credit_used),
        "logs": logs,
    }


@router.post("/users/sync-inactive-telegram", response_model=dict)
async def sync_inactive_staff_telegram(
    username: Optional[str] = Query(None, description="指定用户名则强制清除该员工的TG绑定（不限状态）"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """清除已删除(inactive)员工的 Telegram 绑定。传 username 可强制清除指定员工（如 KL04）"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限")
    
    from sqlalchemy import func
    
    if username:
        # 强制清除指定用户名的 TG 绑定（不限 status）
        result = await db.execute(
            sa_update(AdminUser)
            .where(AdminUser.username == username.strip())
            .where(AdminUser.tg_id.isnot(None))
            .values(tg_id=None, tg_username=None)
        )
        await db.commit()
        cleared = 1 if result.rowcount and result.rowcount > 0 else 0
        logger.info(f"强制清除员工 {username} 的 Telegram 绑定, rowcount={result.rowcount}")
        return {
            "success": True,
            "message": f"已清除 {username} 的 Telegram 绑定",
            "cleared_count": cleared,
        }
    
    # 清除所有 inactive/locked 且仍有 tg_id 的员工（非 active 即视为已删除/禁用）
    from sqlalchemy import or_
    non_active = or_(AdminUser.status == 'inactive', AdminUser.status == 'locked')
    count_result = await db.execute(
        select(func.count()).select_from(AdminUser).where(
            non_active,
            AdminUser.tg_id.isnot(None),
        )
    )
    to_clear = count_result.scalar() or 0
    
    await db.execute(
        sa_update(AdminUser)
        .where(non_active)
        .where(AdminUser.tg_id.isnot(None))
        .values(tg_id=None, tg_username=None)
    )
    await db.commit()
    
    logger.info(f"已清除 {to_clear} 个已删除员工的 Telegram 绑定")
    
    return {
        "success": True,
        "message": "已清除已删除员工的 Telegram 绑定",
        "cleared_count": to_clear,
    }


class OffboardStaffRequest(BaseModel):
    """离职处理请求"""
    reassign_sales_id: Optional[int] = None  # 客户转移目标销售ID，0或null表示解绑不分配


@router.get("/users/{user_id}/offboard-preview", response_model=dict)
async def offboard_staff_preview(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """离职处理预览：返回该员工关联的客户数、未使用邀请码数等"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限")
    
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="员工不存在")
    
    from sqlalchemy import func
    from app.modules.common.invitation_code import InvitationCode
    
    # 客户数
    cust_result = await db.execute(
        select(func.count()).select_from(Account).where(
            Account.sales_id == user_id,
            Account.is_deleted == False,
            Account.status != 'closed',
        )
    )
    customer_count = cust_result.scalar() or 0
    
    # 未使用邀请码数
    invite_result = await db.execute(
        select(func.count()).select_from(InvitationCode).where(
            InvitationCode.sales_id == user_id,
            InvitationCode.status == 'unused',
        )
    )
    unused_invite_count = invite_result.scalar() or 0
    
    return {
        "success": True,
        "staff": {
            "id": staff.id,
            "username": staff.username,
            "real_name": staff.real_name,
            "role": staff.role,
        },
        "customer_count": customer_count,
        "unused_invite_count": unused_invite_count,
    }


@router.post("/users/{user_id}/offboard", response_model=dict)
async def offboard_staff(
    user_id: int,
    request: OffboardStaffRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """员工离职处理：禁用账户、清除Bot绑定、转移客户、转移邀请码"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限")
    
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="员工不存在")
    
    if staff.role == 'super_admin':
        raise HTTPException(status_code=403, detail="不能删除超级管理员")
    
    if staff.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    
    from app.modules.common.invitation_code import InvitationCode
    
    # 1. 转移客户
    customers_reassigned = 0
    if request.reassign_sales_id and request.reassign_sales_id > 0:
        new_sales = await db.execute(
            select(AdminUser).where(
                AdminUser.id == request.reassign_sales_id,
                AdminUser.status == 'active',
            )
        )
        if new_sales.scalar_one_or_none():
            acc_result = await db.execute(
                sa_update(Account)
                .where(
                    Account.sales_id == user_id,
                    Account.is_deleted == False,
                )
                .values(sales_id=request.reassign_sales_id)
            )
            customers_reassigned = acc_result.rowcount or 0
            logger.info(f"员工 {staff.username} 离职：{customers_reassigned} 个客户已转移至 {request.reassign_sales_id}")
    
    # 2. 转移未使用邀请码（sales_id 非空，需转移给他人）
    invites_transferred = 0
    target_sales_id = request.reassign_sales_id if (request.reassign_sales_id and request.reassign_sales_id > 0) else admin.id
    inv_result = await db.execute(
        sa_update(InvitationCode)
        .where(
            InvitationCode.sales_id == user_id,
            InvitationCode.status == 'unused',
        )
        .values(sales_id=target_sales_id)
    )
    invites_transferred = inv_result.rowcount or 0
    if invites_transferred > 0:
        logger.info(f"员工 {staff.username} 离职：{invites_transferred} 个未使用邀请码已转移")
    
    # 3. 禁用账户 + 清除 Bot 绑定
    staff.status = 'inactive'
    _clear_staff_telegram_binding(staff)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "员工离职处理完成",
        "customers_reassigned": customers_reassigned,
        "invites_transferred": invites_transferred,
    }


@router.delete("/users/{user_id}", response_model=dict)
async def delete_staff(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除员工（设为inactive），仅清除Bot绑定，不转移客户。建议使用 /offboard 接口"""
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限删除员工")
    
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    staff = result.scalar_one_or_none()
    
    if not staff:
        raise HTTPException(status_code=404, detail="员工不存在")
    
    if staff.role == 'super_admin':
        raise HTTPException(status_code=403, detail="不能删除超级管理员")
    
    if staff.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    
    staff_username = staff.username
    staff.status = 'inactive'
    # 删除员工时同步清除业务助手绑定
    _clear_staff_telegram_binding(staff)
    await db.commit()

    from app.services.operation_log import log_operation as _log_op
    await _log_op(
        db, admin_id=admin.id, admin_name=admin.username,
        module="security", action="delete", target_type="admin_user",
        target_id=str(user_id),
        title=f"删除管理员账号 {staff_username}",
    )

    return {
        "success": True,
        "message": "员工已禁用"
    }


@router.post("/users/{user_id}/impersonate", response_model=dict)
async def impersonate_staff(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """以员工身份登录（获取临时JWT token）"""
    # 只有超级管理员和管理员可以模拟登录
    if admin.role not in ['super_admin', 'admin']:
        raise HTTPException(status_code=403, detail="无权限执行此操作")
    
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    staff = result.scalar_one_or_none()
    
    if not staff:
        raise HTTPException(status_code=404, detail="员工不存在")
    
    if staff.status != 'active':
        raise HTTPException(status_code=400, detail="员工账户未激活")
    
    # 模拟登录 token：固定 2 小时（不签发 refresh token，到期需重新模拟）
    # 故意短于普通 access token+refresh，避免被冒名身份长期持有
    token = AuthService.create_access_token(
        data={
            "sub": staff.id,
            "role": staff.role,
            "username": staff.username,
            "impersonated_by": admin.id,
        },
        expires_delta=timedelta(hours=2),
    )
    
    logger.info(f"管理员 {admin.username} 以 {staff.username} ({staff.role}) 身份登录")
    
    return {
        "success": True,
        "token": token,
        "user_id": staff.id,
        "username": staff.username,
        "real_name": staff.real_name,
        "role": staff.role,
        "message": f"以 {staff.real_name or staff.username} 身份登录"
    }


@router.get("/debug/supplier-group")
async def debug_supplier_group(
    account_id: Optional[int] = Query(None, description="账户ID"),
    tg_id: Optional[int] = Query(None, description="Telegram用户ID，与account_id二选一"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    诊断供应商群 ID 解析逻辑，用于排查「供应商群未配置」问题。
    返回账户绑定的通道、通道关联的供应商、供应商的 telegram_group_id 等信息。
    支持 account_id 或 tg_id 参数。
    """
    from app.modules.common.account import AccountChannel
    from app.modules.common.telegram_binding import TelegramBinding
    from app.modules.sms.channel import Channel
    from app.modules.sms.supplier import SupplierChannel, Supplier

    if not account_id and tg_id:
        bind_r = await db.execute(
            select(TelegramBinding.account_id).where(
                TelegramBinding.tg_id == tg_id,
                TelegramBinding.is_active == True
            ).limit(1)
        )
        bind_row = bind_r.first()
        if not bind_row:
            return {"error": "该 TG 用户未绑定账户", "tg_id": tg_id}
        account_id = bind_row[0]
        result = {"tg_id": tg_id, "account_id": account_id, "bound_channels": [], "all_channels": [], "resolved_group_id": None}
    elif account_id:
        result = {"account_id": account_id, "bound_channels": [], "all_channels": [], "resolved_group_id": None}
    else:
        return {"error": "请提供 account_id 或 tg_id 参数"}
    try:
        # 1. 账户绑定的通道
        ac_result = await db.execute(
            select(AccountChannel.channel_id, AccountChannel.priority)
            .where(AccountChannel.account_id == account_id)
            .order_by(AccountChannel.priority.desc())
        )
        bound = ac_result.all()
        channel_ids = [r[0] for r in bound]
        result["bound_channels"] = [{"channel_id": r[0], "priority": r[1]} for r in bound]

        # 2. 若无绑定，取全部通道
        if not channel_ids:
            ch_result = await db.execute(
                select(Channel.id, Channel.channel_code, Channel.channel_name)
                .where(Channel.status == 'active', Channel.is_deleted == False)
                .order_by(Channel.priority.desc())
            )
            channel_ids = [r[0] for r in ch_result.all()]
            result["all_channels"] = [{"id": r[0], "code": r[1], "name": r[2]} for r in ch_result.all()]

        # 3. 遍历通道查供应商
        checked = []
        for ch_id in channel_ids:
            sc_result = await db.execute(
                select(SupplierChannel, Supplier)
                .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
                .where(
                    SupplierChannel.channel_id == ch_id,
                    SupplierChannel.status == 'active',
                    Supplier.is_deleted == False
                )
                .limit(1)
            )
            sc_row = sc_result.first()
            if sc_row:
                _, supplier = sc_row
                supp_tg = getattr(supplier, 'telegram_group_id', None)
                checked.append({"channel_id": ch_id, "supplier": getattr(supplier, 'supplier_name', ''), "telegram_group_id": str(supp_tg) if supp_tg else None})
                if supp_tg and str(supp_tg).strip():
                    result["resolved_group_id"] = str(supp_tg).strip()
                    result["resolved_from"] = f"channel_id={ch_id} supplier={getattr(supplier, 'supplier_name', '')}"
                    break
            else:
                checked.append({"channel_id": ch_id, "supplier": None, "telegram_group_id": None})
        result["checked"] = checked
    except Exception as e:
        result["error"] = str(e)
    return result


# ============================================================
#  业务账户管理（语音/数据 — TG助手创建的 OKCC 等外部账户）
# ============================================================

@router.get("/business-accounts", response_model=dict)
async def list_business_accounts(
    business_type: Optional[str] = None,
    country_code: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = None,
    sales_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取业务账户列表（语音/数据），含供应商凭据"""
    from sqlalchemy import or_, func, cast, String

    query = select(Account).where(
        Account.is_deleted == False,
        Account.business_type.in_(['voice', 'data']),
    )

    if business_type:
        query = query.where(Account.business_type == business_type)
    if country_code:
        query = query.where(Account.country_code == country_code)
    if status_filter:
        query = query.where(Account.status == status_filter)
    if sales_id:
        query = query.where(Account.sales_id == sales_id)
    if keyword and (k := keyword.strip()):
        kw = f"%{k}%"
        cred_text = func.lower(cast(Account.supplier_credentials, String(8000)))
        query = query.where(or_(
            Account.account_name.ilike(kw),
            Account.company_name.ilike(kw),
            Account.country_code.ilike(kw),
            Account.supplier_url.ilike(kw),
            cred_text.like(func.lower(kw)),
        ))

    # 销售只能看自己的客户
    if is_sales_scoped(admin):
        query = query.where(Account.sales_id == admin.id)

    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    query = query.order_by(Account.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    accounts = result.scalars().all()

    items = []
    for a in accounts:
        # 获取销售名称
        sales_name = None
        if a.sales_id:
            sr = await db.execute(
                select(AdminUser.real_name, AdminUser.username)
                .where(AdminUser.id == a.sales_id)
            )
            row = sr.first()
            if row:
                sales_name = row[0] or row[1]

        creds = a.supplier_credentials or {}
        items.append({
            "id": a.id,
            "account_name": a.account_name,
            "business_type": a.business_type,
            "country_code": a.country_code,
            "okcc_balance": creds.get("okcc_balance"),
            "okcc_synced_at": creds.get("okcc_synced_at"),
            "okcc_server": creds.get("okcc_server"),
            "status": a.status,
            "unit_price": float(a.unit_price) if a.unit_price else 0,
            "balance": float(a.balance) if a.balance else 0,
            "currency": a.currency or "CNY",
            "supplier_url": a.supplier_url,
            "supplier_credentials": a.supplier_credentials,
            "company_name": a.company_name,
            "contact_person": a.contact_person,
            "contact_phone": a.contact_phone,
            "sales_id": a.sales_id,
            "sales_name": sales_name,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        })

    return {"success": True, "total": total, "items": items, "page": page, "page_size": page_size}


@router.get("/business-accounts/{account_id}", response_model=dict)
async def get_business_account(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取业务账户详情"""
    account = await db.get(Account, account_id)
    if not account or account.is_deleted:
        raise HTTPException(status_code=404, detail="账户不存在")
    if is_sales_scoped(admin) and account.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="无权查看")

    sales_name = None
    if account.sales_id:
        sr = await db.execute(
            select(AdminUser.real_name, AdminUser.username)
            .where(AdminUser.id == account.sales_id)
        )
        row = sr.first()
        if row:
            sales_name = row[0] or row[1]

    return {
        "success": True,
        "account": {
            "id": account.id,
            "account_name": account.account_name,
            "business_type": account.business_type,
            "country_code": account.country_code,
            "status": account.status,
            "unit_price": float(account.unit_price) if account.unit_price else 0,
            "balance": float(account.balance) if account.balance else 0,
            "supplier_url": account.supplier_url,
            "supplier_credentials": account.supplier_credentials,
            "company_name": account.company_name,
            "contact_person": account.contact_person,
            "contact_phone": account.contact_phone,
            "sales_id": account.sales_id,
            "sales_name": sales_name,
            "api_key": account.api_key,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        }
    }


class BusinessAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    status: Optional[str] = None
    company_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    unit_price: Optional[float] = None
    supplier_url: Optional[str] = None
    supplier_credentials: Optional[dict] = None


@router.put("/business-accounts/{account_id}", response_model=dict)
async def update_business_account(
    account_id: int,
    data: BusinessAccountUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新业务账户"""
    account = await db.get(Account, account_id)
    if not account or account.is_deleted:
        raise HTTPException(status_code=404, detail="账户不存在")
    if admin.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="权限不足")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.commit()
    return {"success": True, "message": "更新成功"}


@router.delete("/business-accounts/{account_id}", response_model=dict)
async def delete_business_account(
    account_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """软删除业务账户"""
    if admin.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="权限不足")
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    account.is_deleted = True
    # 清空 webhook 配置：避免残留 webhook_url 仍被当成有效配置触发回执推送（同 delete_account_admin）。
    account.webhook_url = None
    account.webhook_secret = None
    await db.commit()
    return {"success": True, "message": "已删除"}


# ============================================================
#  OKCC 余额同步（逻辑见 app.services.okcc_sync，供 Celery 定时任务复用）
# ============================================================

@router.post("/okcc/sync", response_model=dict)
async def okcc_sync(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """手动触发 OKCC 余额同步"""
    if admin.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="权限不足")

    stats = await sync_okcc_to_accounts(db)
    return {"success": True, "message": "同步完成", "stats": stats}


@router.get("/okcc/customers", response_model=dict)
async def okcc_customer_list(
    server: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """查看 OKCC 客户原始数据（不需要同步即可查看）"""
    if admin.role not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="权限不足")

    all_customers = []
    servers_to_query = [server] if server and server in OKCC_SERVERS else OKCC_SERVERS.keys()
    for sid in servers_to_query:
        customers = await fetch_okcc_customers(sid)
        for c in customers:
            c["okcc_server"] = sid
            c["okcc_label"] = OKCC_SERVERS[sid]["label"]
        all_customers.extend(customers)

    return {"success": True, "total": len(all_customers), "data": all_customers}


# ============ SMS 退款（P0-1：系统问题导致提交失败的人工审核退款） ============

class SmsRefundExecuteRequest(BaseModel):
    note: Optional[str] = None  # 可选备注，记入 BalanceLog
    force: bool = False         # True 时走管理员强制退款，绕过 eligible 校验


class SmsRefundBatchRequest(BaseModel):
    sms_log_ids: List[int]
    note: Optional[str] = None
    force: bool = False         # True 时走管理员强制退款，绕过 eligible 校验


@router.get("/sms/refundable", response_model=dict)
async def list_sms_refundable(
    account_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    include_ineligible: bool = False,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出退款候选。include_ineligible=true 时返回批次内所有失败记录（含不可退款的），
    供管理员查看完整失败情况；默认仅返回可退款记录。
    """
    from app.services.sms_refund import list_refundable
    total, candidates = await list_refundable(
        db,
        account_id=account_id, batch_id=batch_id, channel_id=channel_id,
        keyword=keyword, page=page, page_size=page_size,
        include_ineligible=include_ineligible,
    )
    items = []
    for c in candidates:
        log = c.sms_log
        items.append({
            "sms_log_id": log.id,
            "message_id": log.message_id,
            "account_id": log.account_id,
            "channel_id": log.channel_id,
            "batch_id": log.batch_id,
            "phone_number": log.phone_number,
            "country_code": log.country_code,
            "cost_price": float(log.cost_price or 0),
            "selling_price": float(log.selling_price or 0),
            "currency": log.currency,
            "status": log.status,
            "error_message": log.error_message,
            "submit_time": log.submit_time.isoformat() if log.submit_time else None,
            "upstream_message_id": log.upstream_message_id,
            "category": c.reason,
            "eligible": c.eligible,
            "ineligible_reason": None if c.eligible else c.reason,
        })
    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/sms/{sms_log_id}/refund/preview", response_model=dict)
async def preview_sms_refund(
    sms_log_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """预览单条退款资格（不执行）。"""
    from app.services.sms_refund import get_refund_preview
    cand = await get_refund_preview(db, sms_log_id)
    if not cand:
        return {"success": False, "error": "not_found"}
    log = cand.sms_log
    return {
        "success": True,
        "eligible": cand.eligible,
        "reason": cand.reason,
        "sms_log_id": log.id,
        "message_id": log.message_id,
        "account_id": log.account_id,
        "amount_to_refund": float(log.selling_price or 0),
        "currency": log.currency,
        "error_message": log.error_message,
        "upstream_message_id": log.upstream_message_id,
        "refunded_at": log.refunded_at.isoformat() if log.refunded_at else None,
    }


@router.post("/sms/{sms_log_id}/refund", response_model=dict)
async def execute_sms_refund(
    sms_log_id: int,
    request: SmsRefundExecuteRequest,
    http_request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """对单条短信执行退款（管理员手动审核确认）。force=True 时绕过 eligible 校验。"""
    from app.services.sms_refund import execute_refund, execute_admin_force_refund
    from app.services.operation_log import log_operation

    if request.force:
        result = await execute_admin_force_refund(db, sms_log_id, admin.username, note=request.note)
        op_action = "refund_force"
    else:
        result = await execute_refund(db, sms_log_id, admin.username, note=request.note)
        op_action = "refund"
    client_ip = _safe_client_ip(http_request)

    if result.get("success"):
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="finance", action=op_action,
            title=f"短信退款 message_id={result.get('message_id')} amount={result.get('amount')}{' [force]' if request.force else ''}",
            detail={
                "sms_log_id": sms_log_id,
                "message_id": result.get("message_id"),
                "account_id": result.get("account_id"),
                "amount": result.get("amount"),
                "balance_after": result.get("balance_after"),
                "category": result.get("category"),
                "note": request.note,
            },
            ip_address=client_ip, status="success",
        )
    else:
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="finance", action=op_action,
            title=f"短信退款失败 sms_log_id={sms_log_id} reason={result.get('reason')}",
            detail={"sms_log_id": sms_log_id, "reason": result.get("reason"), "force": request.force},
            ip_address=client_ip, status="failed",
            error_message=str(result.get("reason"))[:500],
        )
    return result


@router.post("/sms/refund-batch", response_model=dict)
async def execute_sms_refund_batch(
    request: SmsRefundBatchRequest,
    http_request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """批量退款（每条独立事务）。一次最多 200 条。force=True 时绕过 eligible。"""
    from app.services.sms_refund import execute_refund_batch, execute_admin_force_refund_batch
    from app.services.operation_log import log_operation

    ids = list(request.sms_log_ids or [])
    if len(ids) == 0:
        return {"success": False, "error": "sms_log_ids 为空"}
    if len(ids) > 200:
        return {"success": False, "error": "单次最多 200 条"}

    if request.force:
        result = await execute_admin_force_refund_batch(db, ids, admin.username, note=request.note)
        op_action = "refund_batch_force"
    else:
        result = await execute_refund_batch(db, ids, admin.username, note=request.note)
        op_action = "refund_batch"
    client_ip = _safe_client_ip(http_request)
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="finance", action=op_action,
        title=f"批量退款{'[force] ' if request.force else ''}：成功 {result['ok']} 条 / 失败 {result['failed']} 条 / 总额 {result['total_amount']}",
        detail={
            "requested": len(ids),
            "ok": result["ok"],
            "failed": result["failed"],
            "total_amount": result["total_amount"],
            "first_failures": result["failures"][:10],
            "note": request.note,
        },
        ip_address=client_ip,
        status="success" if result["failed"] == 0 else "partial",
    )
    return {"success": True, **result}


# ============ 管理员批次任务管理（暂停/恢复/清空/通道切换） ============

class BatchResumeRequest(BaseModel):
    new_channel_id: Optional[int] = None


class BatchPreviewSwitchRequest(BaseModel):
    new_channel_id: int


def _serialize_batch_row(b, patch: Optional[dict] = None) -> dict:
    """统一序列化 SmsBatch 行（管理员视图）。patch 来自 _smslog_batch_display_patches 修正。"""
    p = patch or {}
    return {
        "id": b.id,
        "account_id": b.account_id,
        "batch_name": b.batch_name,
        "total_count": b.total_count,
        "success_count": p.get("success_count", b.success_count or 0),
        "delivered_count": p.get("delivered_count", b.delivered_count or 0),
        "failed_count": p.get("failed_count", b.failed_count or 0),
        "processing_count": p.get("processing_count", b.processing_count or 0),
        "status": (b.status.value if hasattr(b.status, "value") else b.status),
        "progress": p.get("progress", b.progress or 0),
        "error_message": b.error_message,
        "sender_id": b.sender_id,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
        "scheduled_at": b.scheduled_at.isoformat() if getattr(b, "scheduled_at", None) else None,
    }


@router.get("/batches", response_model=dict)
async def admin_list_batches(
    account_id: Optional[int] = None,
    account: Optional[str] = None,
    channel_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    content: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """全局批次列表（管理员）。支持账户/通道/状态/关键词/时间范围筛选。"""
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.sms_log import SMSLog
    from app.api.v1.batches import _smslog_batch_display_patches
    from sqlalchemy import or_ as sa_or, func as sa_func
    from datetime import datetime as _dt

    if admin.role not in ("admin", "super_admin"):
        return {"success": False, "error": "permission_denied"}

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))

    from app.modules.common.account import Account as _Acc

    where = [SmsBatch.is_deleted == False]  # noqa: E712
    if account_id:
        where.append(SmsBatch.account_id == int(account_id))
    # account：支持账户名或账户ID 统一入口（纯数字按ID精确，否则按账户名模糊）
    if account and account.strip():
        av = account.strip()
        if av.isdigit():
            where.append(SmsBatch.account_id == int(av))
        else:
            where.append(
                SmsBatch.account_id.in_(
                    select(_Acc.id).where(_Acc.account_name.like(f"%{av}%"))
                )
            )
    if batch_id:
        where.append(SmsBatch.id == int(batch_id))
    if status:
        try:
            where.append(SmsBatch.status == BatchStatus(status))
        except Exception:
            return {"success": False, "error": f"invalid status: {status}"}
    if keyword:
        kw = f"%{keyword.strip()}%"
        where.append(SmsBatch.batch_name.like(kw))
    if start_date:
        try:
            where.append(SmsBatch.created_at >= _dt.fromisoformat(start_date))
        except Exception:
            pass
    if end_date:
        try:
            where.append(SmsBatch.created_at <= _dt.fromisoformat(end_date))
        except Exception:
            pass

    # channel_id 筛选：批次本身没存通道，需要通过 sms_logs 反查；用 EXISTS 子查询避免大表 JOIN
    if channel_id:
        where.append(
            SmsBatch.id.in_(
                select(SMSLog.batch_id).where(SMSLog.channel_id == int(channel_id)).distinct()
            )
        )

    # 短信内容筛选：批次表不存内容，同样通过 sms_logs.message 反查
    if content and content.strip():
        ct = f"%{content.strip()}%"
        where.append(
            SmsBatch.id.in_(
                select(SMSLog.batch_id).where(SMSLog.message.like(ct)).distinct()
            )
        )

    total = (await db.execute(
        select(sa_func.count(SmsBatch.id)).where(*where)
    )).scalar() or 0

    rows = (await db.execute(
        select(SmsBatch).where(*where).order_by(SmsBatch.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    # 用 sms_logs 实时校正 processing/paused 批次的进度
    live_ids = [
        b.id for b in rows
        if b.status in (BatchStatus.PROCESSING, BatchStatus.PAUSED, BatchStatus.PENDING)
    ]
    patches = {}
    if live_ids:
        totals_map = {b.id: (b.total_count or 0) for b in rows if b.id in live_ids}
        from datetime import timedelta as _td
        live_since = min(b.created_at for b in rows if b.id in live_ids) - _td(seconds=60)
        patches = await _smslog_batch_display_patches(db, live_ids, totals_map, since=live_since)

    items = [_serialize_batch_row(b, patches.get(b.id)) for b in rows]

    # 关联账户名（一次性查）
    if items:
        acct_ids = list({i["account_id"] for i in items if i.get("account_id")})
        if acct_ids:
            from app.modules.common.account import Account as _Acc
            r = await db.execute(select(_Acc.id, _Acc.account_name).where(_Acc.id.in_(acct_ids)))
            name_map = {row[0]: row[1] for row in r.all()}
            for i in items:
                i["account_name"] = name_map.get(i["account_id"])

    # 短信内容 + 发送通道：批次表不存这两项，取每批代表性 sms_logs 反查。
    # 内容用最早一条 MIN(id)；通道单独取「最早一条 channel_id 非空」的行——
    # 大批次首行常是 channel_id=NULL 的占位/种子行，直接用 MIN(id) 会误显示为「-」。
    if items:
        batch_ids = [i["id"] for i in items]
        # 内容：MIN(id)
        msg_sub = (
            select(SMSLog.batch_id, sa_func.min(SMSLog.id).label("mid"))
            .where(SMSLog.batch_id.in_(batch_ids))
            .group_by(SMSLog.batch_id)
        ).subquery()
        msg_rows = (await db.execute(
            select(SMSLog.batch_id, SMSLog.message)
            .join(msg_sub, SMSLog.id == msg_sub.c.mid)
        )).all()
        msg_map = {bid: msg for bid, msg in msg_rows}
        # 通道：MIN(id) 且 channel_id IS NOT NULL
        ch_sub = (
            select(SMSLog.batch_id, sa_func.min(SMSLog.id).label("cid_min"))
            .where(SMSLog.batch_id.in_(batch_ids), SMSLog.channel_id.isnot(None))
            .group_by(SMSLog.batch_id)
        ).subquery()
        ch_rows = (await db.execute(
            select(SMSLog.batch_id, SMSLog.channel_id)
            .join(ch_sub, SMSLog.id == ch_sub.c.cid_min)
        )).all()
        bid_chan = {bid: cid for bid, cid in ch_rows}
        chan_ids = {cid for cid in bid_chan.values() if cid}
        chan_map = {}
        if chan_ids:
            from app.modules.sms.channel import Channel as _Ch
            cr = await db.execute(
                select(_Ch.id, _Ch.channel_code, _Ch.channel_name).where(_Ch.id.in_(chan_ids))
            )
            chan_map = {row[0]: (row[1], row[2]) for row in cr.all()}
        for i in items:
            i["content"] = msg_map.get(i["id"])
            cid = bid_chan.get(i["id"])
            cc = chan_map.get(cid) if cid else None
            i["channel_code"] = cc[0] if cc else None
            i["channel_name"] = cc[1] if cc else None

        # 定时批(pending)派发前没有任何 sms_logs 行，上面反查取不到内容/通道，列表会留空白。
        # 回退从 send_config 读创建时落库的 message_preview + channel_id 补齐（与客户端 /batches 一致）。
        cfg_by_id = {int(b.id): b.send_config for b in rows if isinstance(b.send_config, dict)}
        fb_cids: dict = {}
        for i in items:
            cfg = cfg_by_id.get(i["id"]) or {}
            if not i.get("content") and cfg.get("message_preview"):
                i["content"] = cfg["message_preview"]
            if not i.get("channel_code") and cfg.get("channel_id"):
                try:
                    fb_cids[i["id"]] = int(cfg["channel_id"])
                except (TypeError, ValueError):
                    pass
        if fb_cids:
            from app.modules.sms.channel import Channel as _Ch
            fr = await db.execute(
                select(_Ch.id, _Ch.channel_code, _Ch.channel_name)
                .where(_Ch.id.in_(set(fb_cids.values())))
            )
            fb_map = {row[0]: (row[1], row[2]) for row in fr.all()}
            for i in items:
                cc2 = fb_map.get(fb_cids.get(i["id"]))
                if cc2:
                    i["channel_code"], i["channel_name"] = cc2

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/batches/{batch_id}", response_model=dict)
async def admin_get_batch(
    batch_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """批次详情：基础字段 + 各状态计数 + 当前主用通道 + 可退款数量。"""
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.channel import Channel as _Ch
    from app.modules.common.account import Account as _Acc
    from sqlalchemy import func as sa_func

    if admin.role not in ("admin", "super_admin"):
        return {"success": False, "error": "permission_denied"}

    b = (await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))).scalar_one_or_none()
    if not b:
        return {"success": False, "error": "not_found"}

    # 状态分布
    status_rows = (await db.execute(
        select(SMSLog.status, sa_func.count(SMSLog.id))
        .where(SMSLog.batch_id == batch_id)
        .group_by(SMSLog.status)
    )).all()
    status_counts = {str(s or ""): int(c or 0) for s, c in status_rows}

    # 失败原因分析：failed/expired 行按 error_message 聚合 Top12
    fr_stmt = select(SMSLog.error_message, sa_func.count(SMSLog.id)).where(
        and_(SMSLog.batch_id == batch_id, SMSLog.status.in_(["failed", "expired"]))
    )
    if b.created_at is not None:
        fr_stmt = fr_stmt.where(SMSLog.submit_time >= b.created_at - timedelta(seconds=60))
    fr_rows = (await db.execute(
        fr_stmt.group_by(SMSLog.error_message)
        .order_by(sa_func.count(SMSLog.id).desc())
        .limit(12)
    )).all()
    failure_reasons = [
        {
            "reason": (str(r).strip() if r and str(r).strip() else "未知原因"),
            "count": int(c or 0),
        }
        for r, c in fr_rows
    ]

    # 当前未发主用通道（取众数）
    ch_rows = (await db.execute(
        select(SMSLog.channel_id, sa_func.count(SMSLog.id))
        .where(and_(SMSLog.batch_id == batch_id, SMSLog.status.in_(["pending", "queued"])))
        .group_by(SMSLog.channel_id)
        .order_by(sa_func.count(SMSLog.id).desc()).limit(1)
    )).first()
    current_channel = None
    if ch_rows and ch_rows[0]:
        ch = (await db.execute(select(_Ch).where(_Ch.id == ch_rows[0]))).scalar_one_or_none()
        if ch:
            current_channel = {
                "id": ch.id, "channel_code": ch.channel_code, "channel_name": ch.channel_name,
                "protocol": ch.protocol, "status": ch.status, "connection_status": ch.connection_status,
            }

    # 可退款数量（与 sms_refund.list_refundable 资格规则一致）
    refundable = (await db.execute(
        select(sa_func.count(SMSLog.id)).where(and_(
            SMSLog.batch_id == batch_id,
            SMSLog.status == "failed",
            SMSLog.refunded_at.is_(None),
            SMSLog.cost_price > 0,
            SMSLog.upstream_message_id.is_(None),
        ))
    )).scalar() or 0

    # 账户名
    acct_name = None
    if b.account_id:
        r = await db.execute(select(_Acc.account_name).where(_Acc.id == b.account_id))
        acct_name = r.scalar()

    base = _serialize_batch_row(b)
    base.update({
        "account_name": acct_name,
        "status_counts": status_counts,
        "failure_reasons": failure_reasons,
        "current_channel": current_channel,
        "refundable_count": refundable,
    })
    return {"success": True, "batch": base}


@router.post("/batches/{batch_id}/pause", response_model=dict)
async def admin_pause_batch(
    batch_id: int,
    http_request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role not in ("admin", "super_admin"):
        return {"success": False, "error": "permission_denied"}
    from app.services.batch_admin import pause_batch
    from app.services.operation_log import log_operation
    result = await pause_batch(db, batch_id, admin.username)
    client_ip = _safe_client_ip(http_request)
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="sms", action="batch_pause",
        title=f"暂停批次 #{batch_id}",
        detail={"batch_id": batch_id, **{k: v for k, v in result.items() if k != "success"}},
        ip_address=client_ip,
        status="success" if result.get("success") else "failed",
        error_message=str(result.get("reason"))[:500] if not result.get("success") else None,
    )
    return result


@router.post("/batches/{batch_id}/resume", response_model=dict)
async def admin_resume_batch(
    batch_id: int,
    request: BatchResumeRequest,
    http_request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role not in ("admin", "super_admin"):
        return {"success": False, "error": "permission_denied"}
    from app.services.batch_admin import resume_batch
    from app.services.operation_log import log_operation
    try:
        result = await resume_batch(db, batch_id, admin.username, new_channel_id=request.new_channel_id)
    except InsufficientBalanceError as e:
        result = {"success": False, "reason": f"余额不足，无法切换通道: 需 {e.required}, 当前 {e.available}"}
        try:
            await db.rollback()
        except Exception:
            pass
    client_ip = _safe_client_ip(http_request)
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="sms", action="batch_resume",
        title=f"恢复批次 #{batch_id}" + (f"（切换通道→#{request.new_channel_id}）" if request.new_channel_id else ""),
        detail={"batch_id": batch_id, "new_channel_id": request.new_channel_id,
                **{k: v for k, v in result.items() if k != "success"}},
        ip_address=client_ip,
        status="success" if result.get("success") else "failed",
        error_message=str(result.get("reason"))[:500] if not result.get("success") else None,
    )
    return result


@router.post("/batches/{batch_id}/clear-queue", response_model=dict)
async def admin_clear_batch_queue(
    batch_id: int,
    http_request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if admin.role not in ("admin", "super_admin"):
        return {"success": False, "error": "permission_denied"}
    from app.services.batch_admin import clear_batch_queue
    from app.services.operation_log import log_operation
    result = await clear_batch_queue(db, batch_id, admin.username)
    client_ip = _safe_client_ip(http_request)
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="sms", action="batch_clear_queue",
        title=f"清空批次 #{batch_id} 未发队列",
        detail={"batch_id": batch_id, **{k: v for k, v in result.items() if k != "success"}},
        ip_address=client_ip,
        status="success" if result.get("success") else "failed",
        error_message=str(result.get("reason"))[:500] if not result.get("success") else None,
    )
    return result


@router.post("/batches/{batch_id}/preview-switch-channel", response_model=dict)
async def admin_preview_switch_channel(
    batch_id: int,
    request: BatchPreviewSwitchRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """通道切换预览（只读）：返回未发条数、调差、余额变化预估。"""
    if admin.role not in ("admin", "super_admin"):
        return {"success": False, "error": "permission_denied"}
    from app.services.batch_admin import preview_switch_channel
    return await preview_switch_channel(db, batch_id, request.new_channel_id)


# 号码导出分类 → sms_logs.status 过滤
_BATCH_PHONE_CATEGORY_FILTERS = {
    "total": None,
    "success": ("sent", "delivered"),     # 通道已受理
    "delivered": ("delivered",),           # 已收到送达回执
    "awaiting": ("sent",),                 # 已发出、等待回执
    "failed": ("failed", "expired"),       # 失败 + 过期
}


@router.get("/batches/{batch_id}/phones.txt")
async def admin_export_batch_phones(
    batch_id: int,
    http_request: Request,
    category: str = Query("total", description="total|success|delivered|awaiting|failed"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """按分类下载批次内号码（TXT，一行一个）。管理员专用。"""
    from fastapi.responses import Response
    from app.modules.sms.sms_log import SMSLog
    from app.modules.sms.sms_batch import SmsBatch
    from app.services.operation_log import log_operation

    if admin.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="permission_denied")

    if category not in _BATCH_PHONE_CATEGORY_FILTERS:
        raise HTTPException(status_code=400, detail=f"invalid category: {category}")

    batch = (await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))).scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="batch_not_found")

    where = [SMSLog.batch_id == batch_id]
    statuses = _BATCH_PHONE_CATEGORY_FILTERS[category]
    if statuses:
        where.append(SMSLog.status.in_(statuses))

    rows = (await db.execute(
        select(SMSLog.phone_number).where(*where).order_by(SMSLog.id.asc())
    )).all()
    # 去掉 E.164 前导「+」：sms_logs 落库时号码统一带 +，但运营商导入/外部工具大多
    # 期望纯数字格式（如 8801304590882）；保留前面的国码数字，仅剥离 +。
    phones = [(r[0] or "").lstrip("+") for r in rows if r[0]]
    phones = [p for p in phones if p]

    body = ("\n".join(phones) + "\n") if phones else ""

    client_ip = _safe_client_ip(http_request)
    try:
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="sms", action="batch_export_phones",
            target_type="sms_batch", target_id=str(batch_id),
            title=f"下载批次 #{batch_id} 号码（{category}）",
            detail={"batch_id": batch_id, "category": category, "count": len(phones)},
            ip_address=client_ip,
        )
    except Exception as e:
        logger.warning(f"批次号码下载审计日志写入失败: {e}")

    filename = f"batch_{batch_id}_{category}.txt"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============ 失败重发（生成新批次）：已挪到 batches.py 客户侧，本端点保留以便排障/特殊场景 ============

class AdminRetryAsNewBatchRequest(BaseModel):
    include_all: bool = False           # True 时连"已提交上游"和"内容/号码被拒"类一起重发；
                                        # 默认仅重发 eligible（未提交上游）
    new_batch_name: Optional[str] = None # 不传则自动生成「重发-原批次名」


@router.post("/batches/{batch_id}/retry-as-new-batch", response_model=dict, deprecated=True)
async def admin_retry_failed_as_new_batch(
    batch_id: int,
    request: AdminRetryAsNewBatchRequest,
    http_request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    将原批次的 failed 条目作为「新批次」重发，正常计费、正常路由。

    - 默认仅取"未提交上游"类失败（与退款资格规则同源）；include_all=True 时把所有 failed 都拿
    - 新批次回指原批次：sms_batches.source_batch_id
    - 客户账户按当前路由 + 当前定价正常扣费（与新建批次一致）
    - 原批次失败行保持 failed，在 error_message 末尾追加「已转批次 #NEW_ID 重发」溯源
    - Redis 互斥锁：batch_op_lock:{原批次id}，防止并发重发同一批次
    """
    from app.modules.sms.sms_batch import SmsBatch, BatchStatus
    from app.modules.sms.sms_log import SMSLog
    from app.modules.common.account import Account
    from app.modules.common.balance_log import BalanceLog
    from app.core.pricing import PricingEngine
    from app.core.router import RoutingEngine
    from app.utils.queue import QueueManager
    from app.utils.errors import InsufficientBalanceError, PricingNotFoundError, ChannelNotAvailableError
    from app.utils.cache import get_cache_manager
    from app.services.sms_refund import _looks_submitted_to_upstream, is_content_rejected
    from app.services.operation_log import log_operation
    from decimal import Decimal
    import uuid as _uuid

    if admin.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="permission_denied")

    cm = await get_cache_manager()
    redis_client = await cm.redis
    lock_key = f"batch_op_lock:{batch_id}"
    if not await redis_client.set(lock_key, b"1", ex=300, nx=True):
        raise HTTPException(status_code=409, detail="该批次正在重发处理中，请稍候重试")

    try:
        src_batch = (await db.execute(
            select(SmsBatch).where(SmsBatch.id == batch_id, SmsBatch.is_deleted == False)
        )).scalar_one_or_none()
        if not src_batch:
            raise HTTPException(status_code=404, detail="原批次不存在")

        # 拉失败条目
        failed_rows = (await db.execute(
            select(SMSLog).where(
                SMSLog.batch_id == batch_id,
                or_(SMSLog.status == "failed", SMSLog.status == "expired"),
            ).order_by(SMSLog.id.asc())
        )).scalars().all()

        if not failed_rows:
            raise HTTPException(status_code=400, detail="原批次无 failed/expired 条目可重发")

        # 过滤：默认仅"未提交上游"类
        if request.include_all:
            candidate_rows = list(failed_rows)
        else:
            # 排除两类：①已提交上游（重发=重复投递）②上游因内容/号码拒收（原样重发必然再拒，
            # 还要再扣一次费）。后者该走的是「改文案/去上游报备模板」，不是重发。
            candidate_rows = [
                r for r in failed_rows
                if not _looks_submitted_to_upstream(r) and not is_content_rejected(r)
            ]
        if not candidate_rows:
            raise HTTPException(status_code=400, detail="按当前规则无可重发条目（默认已排除「已提交上游」和「上游因内容/号码拒收」两类；后者原样重发必然再次被拒，请先改文案或去上游报备模板。确要重发可勾「全部失败」）")

        account_id = src_batch.account_id
        account = (await db.execute(
            select(Account).where(Account.id == account_id)
        )).scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=400, detail=f"账户 {account_id} 不存在")

        new_batch_name = request.new_batch_name or f"重发-{src_batch.batch_name}"[:200]

        # 创建新批次
        new_batch = SmsBatch(
            account_id=account_id,
            batch_name=new_batch_name,
            status=BatchStatus.PROCESSING,
            total_count=len(candidate_rows),
            success_count=0, delivered_count=0, failed_count=0, processing_count=0,
            sender_id=src_batch.sender_id,
            source_batch_id=batch_id,
        )
        db.add(new_batch)
        await db.flush()
        new_batch_id = new_batch.id

        # 复制并入队
        pricing_engine = PricingEngine(db)
        routing_engine = RoutingEngine(db)
        retried = 0
        skipped = 0
        out_of_balance = False
        err_lines: List[str] = []
        max_err_show = 20
        annotate_ids: List[int] = []
        new_msg_ids: List[str] = []
        total_charged_d = Decimal("0")

        for sms_log in candidate_rows:
            if out_of_balance:
                skipped += 1
                continue
            if not sms_log.country_code or not (sms_log.message or "").strip():
                skipped += 1
                if len(err_lines) < max_err_show:
                    err_lines.append(f"{sms_log.message_id}: 缺少国家或正文")
                continue

            # 重新路由（账户当前绑定 + 当前通道状态决定）
            try:
                channel = await routing_engine.route(
                    country_code=str(sms_log.country_code),
                    account_id=account_id,
                )
            except ChannelNotAvailableError as e:
                skipped += 1
                if len(err_lines) < max_err_show:
                    err_lines.append(f"{sms_log.message_id}: 路由失败 {e.message}")
                continue
            if not channel:
                skipped += 1
                if len(err_lines) < max_err_show:
                    err_lines.append(f"{sms_log.message_id}: 无可用通道")
                continue

            # 计费扣款
            try:
                charge_result = await pricing_engine.calculate_and_charge(
                    account_id=account_id,
                    channel_id=channel.id,
                    country_code=str(sms_log.country_code),
                    message=str(sms_log.message),
                    channel=channel,
                    skip_balance_log=True,
                )
            except InsufficientBalanceError:
                out_of_balance = True
                skipped += 1
                continue
            except PricingNotFoundError as e:
                skipped += 1
                if len(err_lines) < max_err_show:
                    err_lines.append(f"{sms_log.message_id}: 计费失败 {e.message}")
                continue

            new_mid = f"msg_{_uuid.uuid4().hex}"
            new_log = SMSLog(
                message_id=new_mid,
                account_id=account_id,
                channel_id=channel.id,
                batch_id=new_batch_id,
                phone_number=sms_log.phone_number,
                country_code=sms_log.country_code,
                message=sms_log.message,
                message_count=int(charge_result.get("message_count") or 1),
                status="queued",
                cost_price=charge_result["total_base_cost"],
                selling_price=charge_result["total_cost"],
                currency=charge_result.get("currency") or "USD",
            )
            db.add(new_log)
            new_msg_ids.append(new_mid)
            annotate_ids.append(sms_log.id)
            total_charged_d += Decimal(str(charge_result["total_cost"]))
            retried += 1

        if total_charged_d > 0:
            bal_after = (await db.execute(
                select(Account.balance).where(Account.id == account_id)
            )).scalar() or 0
            db.add(BalanceLog(
                account_id=account_id,
                change_type='charge',
                amount=-total_charged_d,
                balance_after=bal_after,
                description=f"失败重发新批次 batch#{new_batch_id} (源 #{batch_id}): {retried} 条"[:500],
            ))

        # 原批次失败行追加溯源注记（仅注记成功重发的那批）
        if annotate_ids:
            await db.execute(
                update(SMSLog).where(SMSLog.id.in_(annotate_ids)).values(
                    error_message=func.concat(
                        func.ifnull(SMSLog.error_message, ""),
                        f" [已转批次 #{new_batch_id} 重发]",
                    )
                )
            )

        await db.commit()

        # 入队（commit 后再做，避免事务失败仍入队）
        enqueued_ok = 0
        queue_failed_msg_ids: List[str] = []
        for new_mid in new_msg_ids:
            if QueueManager.queue_sms(new_mid):
                enqueued_ok += 1
            else:
                queue_failed_msg_ids.append(new_mid)

        if queue_failed_msg_ids:
            # 入队失败的标 failed（已扣费；管理员可走"系统退款 force"补救）
            await db.execute(
                update(SMSLog).where(SMSLog.message_id.in_(queue_failed_msg_ids)).values(
                    status="failed",
                    error_message="加入发送队列失败，请检查 RabbitMQ/worker-sms",
                )
            )
            await db.commit()

        client_ip = _safe_client_ip(http_request)
        await log_operation(
            db, admin_id=admin.id, admin_name=admin.username,
            module="sms", action="batch_retry_as_new_batch",
            target_type="sms_batch", target_id=str(batch_id),
            title=f"失败重发→新批次 #{new_batch_id}（源 #{batch_id}）: 重发 {retried} 条 / 跳 {skipped} 条",
            detail={
                "source_batch_id": batch_id,
                "new_batch_id": new_batch_id,
                "retried": retried,
                "enqueued": enqueued_ok,
                "skipped": skipped,
                "include_all": request.include_all,
                "out_of_balance": out_of_balance,
                "charged_amount": float(total_charged_d),
            },
            ip_address=client_ip,
            status="success" if retried > 0 else "failed",
        )

        return {
            "success": True,
            "source_batch_id": batch_id,
            "new_batch_id": new_batch_id,
            "retried": retried,
            "enqueued": enqueued_ok,
            "skipped": skipped,
            "out_of_balance": out_of_balance,
            "charged_amount": float(total_charged_d),
            "errors": err_lines,
        }
    finally:
        try:
            await redis_client.delete(lock_key)
        except Exception:
            pass
