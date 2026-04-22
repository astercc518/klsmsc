"""
管理员API路由
"""
import asyncio
from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
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
from app.core.auth import AuthService
from app.config import settings
from app.utils.logger import get_logger
from datetime import timedelta

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


# Schemas
class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    admin_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None
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
    virtual_config: Optional[dict] = None
    # 与 channels.config_json 对应：strip_leading_plus、payload_template 等
    gateway_config: Optional[dict] = None

    @field_validator('protocol')
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        if v is None:
            raise ValueError('protocol is required')
        if v not in ['HTTP', 'SMPP', 'VIRTUAL']:
            raise ValueError('protocol must be HTTP, SMPP or VIRTUAL')
        return v
    
    @field_validator('default_sender_id')
    @classmethod
    def validate_default_sender_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == '':
            return None
        return v.strip()


class ChannelUpdateRequest(BaseModel):
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
    virtual_config: Optional[dict] = None
    gateway_config: Optional[dict] = None


class PricingCreateRequest(BaseModel):
    channel_id: int
    country_code: str
    country_name: str
    price_per_sms: float
    currency: str = "USD"
    mnc: Optional[str] = None
    operator_name: Optional[str] = None
    effective_date: Optional[str] = None


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
    ip_whitelist: Optional[List[str]] = None
    low_balance_threshold: Optional[float] = None
    # 绑定配置
    sales_id: Optional[int] = None  # 绑定员工ID（传0表示解绑）
    channel_ids: Optional[List[int]] = None  # 绑定通道ID列表


class AdminAccountBalanceAdjustRequest(BaseModel):
    amount: float
    change_type: Optional[str] = None  # deposit/withdraw/adjustment/refund/charge
    description: Optional[str] = None
    transaction_id: Optional[str] = None


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
    db: AsyncSession = Depends(get_db)
):
    """管理员登录"""
    logger.info(f"管理员登录: {request.username}")
    
    # 查询管理员
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == request.username)
    )
    admin = result.scalar_one_or_none()
    
    if not admin:
        return AdminLoginResponse(
            success=False,
            error="invalid_credentials"
        )
    
    # 检查状态（密码验证前先检查，避免已锁定账户继续累加失败次数）
    if admin.status == "locked":
        return AdminLoginResponse(
            success=False,
            error="account_locked"
        )
    if admin.status != "active":
        return AdminLoginResponse(
            success=False,
            error="account_disabled"
        )
    
    # 验证密码
    if not AuthService.verify_password(request.password, admin.password_hash):
        admin.login_failed_count += 1
        remaining = 5 - admin.login_failed_count
        if admin.login_failed_count >= 5:
            admin.status = "locked"
            await db.commit()
            return AdminLoginResponse(
                success=False,
                error="account_locked"
            )
        await db.commit()
        return AdminLoginResponse(
            success=False,
            error=f"invalid_credentials:{remaining}"
        )
    
    # 更新登录信息
    admin.last_login_at = datetime.now()
    admin.login_failed_count = 0
    
    from app.services.operation_log import log_operation
    await log_operation(
        db, admin_id=admin.id, admin_name=admin.username,
        module="login", action="login", target_type="admin",
        target_id=str(admin.id), title=f"管理员 {admin.username} 登录成功",
    )
    await db.commit()
    
    logger.info(f"管理员登录成功: {admin.username} ({admin.role})")
    
    # 生成JWT token
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    token = AuthService.create_access_token(
        data={"sub": admin.id, "role": admin.role, "username": admin.username},
        expires_delta=access_token_expires
    )
    
    return AdminLoginResponse(
        success=True,
        token=token,
        admin_id=admin.id,
        username=admin.username,
        role=admin.role
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

    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    token = AuthService.create_access_token(
        data={"sub": admin.id, "role": admin.role, "username": admin.username},
        expires_delta=access_token_expires
    )

    return AdminLoginResponse(
        success=True,
        token=token,
        admin_id=admin.id,
        username=admin.username,
        role=admin.role
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

    if len(request.new_password) < 6:
        return {"success": False, "error": "password_too_short"}

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
    from sqlalchemy import func, or_, and_, exists
    import json

    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    # 销售角色只能看到自己名下的客户
    if admin.role == "sales":
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

    total_result = await db.execute(select(func.count(Account.id)).where(where_expr))
    total = total_result.scalar() or 0

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
                "unit_price": float(a.unit_price) if a.unit_price is not None else 0.05,
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
                "channels": [
                    {"id": ac.channel.id, "channel_code": ac.channel.channel_code}
                    for ac in (a.account_channels or [])
                    if ac.channel
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

    if admin.role == "sales":
        raise HTTPException(status_code=403, detail="销售人员无权新建客户账户")

    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # 生成唯一邮箱（内部使用）
    unique_email = f"{uuid.uuid4().hex[:12]}@internal.sms"

    # 生成API Key/Secret（注意长度限制）
    api_key = f"ak_{secrets.token_hex(30)}"  # <= 64
    api_secret = secrets.token_urlsafe(4)[:6]  # 6 位随机接口密码
    
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
        low_balance_threshold=request.low_balance_threshold,
        created_by=admin.id,
        sales_id=request.sales_id,
    )

    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)

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

    if admin.role == "sales" and a.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="只能查看自己名下的客户")

    try:
        whitelist = json.loads(a.ip_whitelist) if a.ip_whitelist else []
        if not isinstance(whitelist, list):
            whitelist = []
    except Exception:
        whitelist = []

    # 获取绑定的通道
    channel_result = await db.execute(
        select(AccountChannel, Channel)
        .join(Channel, AccountChannel.channel_id == Channel.id)
        .where(AccountChannel.account_id == account_id)
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
            "unit_price": float(a.unit_price) if a.unit_price is not None else 0.05,
            "status": a.status,
            "balance": float(a.balance or 0),
            "currency": a.currency,
            # 风控配置
            "low_balance_threshold": float(a.low_balance_threshold) if a.low_balance_threshold is not None else None,
            "rate_limit": a.rate_limit,
            "ip_whitelist": whitelist,
            # API凭证
            "api_key": a.api_key,
            "api_secret": a.api_secret,
            # 绑定配置
            "sales_id": a.sales_id,
            "channels": channels,
            "channel_ids": [ch["id"] for ch in channels],
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

    # 销售人员：仅可修改名下客户的在用/已暂停状态（停用/启用），不可改其他信息
    if admin.role == "sales":
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
        try:
            from app.utils.cache import get_cache_manager
            cache_manager = await get_cache_manager()
            await cache_manager.invalidate_balance_cache(account_id=account_id)
        except Exception:
            pass
        return {"success": True, "message": "Account updated successfully"}

    if request.account_name is not None:
        a.account_name = request.account_name
    if request.tg_username is not None:
        a.tg_username = request.tg_username
    if request.country_code is not None:
        a.country_code = request.country_code
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
    if request.unit_price is not None:
        a.unit_price = request.unit_price
    if request.status is not None:
        a.status = request.status
    if request.currency is not None:
        a.currency = request.currency
    # 风控配置
    if request.rate_limit is not None:
        a.rate_limit = request.rate_limit
    if request.low_balance_threshold is not None:
        a.low_balance_threshold = request.low_balance_threshold
    if request.ip_whitelist is not None:
        a.ip_whitelist = json.dumps(request.ip_whitelist, ensure_ascii=False)
    
    # 更新绑定员工
    if request.sales_id is not None:
        a.sales_id = request.sales_id if request.sales_id > 0 else None
    
    # 更新绑定通道
    if request.channel_ids is not None:
        # 删除旧的绑定
        await db.execute(
            AccountChannel.__table__.delete().where(AccountChannel.account_id == account_id)
        )
        # 添加新的绑定
        for idx, channel_id in enumerate(request.channel_ids):
            account_channel = AccountChannel(
                account_id=account_id,
                channel_id=channel_id,
                is_default=(idx == 0),
                priority=idx
            )
            db.add(account_channel)

    await db.commit()

    # 失效余额缓存（阈值/状态更新也可能影响展示）
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_balance_cache(account_id=account_id)
        # 统一单价或通道变化时清除该账户售价缓存，否则买即发/发送仍可能按旧价计费
        if request.unit_price is not None or request.channel_ids is not None:
            await cache_manager.invalidate_price_cache_for_account(account_id)
    except Exception:
        pass

    return {"success": True, "message": "Account updated successfully"}


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

    if admin.role == "sales":
        raise HTTPException(status_code=403, detail="销售人员无权重置 API Key")

    a.api_key = f"ak_{secrets.token_hex(30)}"
    a.api_secret = secrets.token_urlsafe(4)[:6]  # 6 位随机接口密码
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
    if not secret or not x_telegram_staff_secret or x_telegram_staff_secret != secret:
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
    login_url = (
        f"{base}/login?impersonate=1"
        f"&api_key={quote(a.api_key or '', safe='')}"
        f"&account_id={a.id}"
        f"&account_name={quote(a.account_name or '', safe='')}"
    )

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
    if admin.role == "sales" and a.sales_id != admin.id:
        raise HTTPException(status_code=403, detail="只能模拟登录自己名下的客户")

    base = (settings.PUBLIC_WEB_BASE_URL or "https://www.kaolach.com").rstrip("/")
    login_url = (
        f"{base}/login?impersonate=1"
        f"&api_key={quote(a.api_key or '', safe='')}"
        f"&account_id={a.id}"
        f"&account_name={quote(a.account_name or '', safe='')}"
    )

    return {
        "success": True,
        "account_id": a.id,
        "account_name": a.account_name,
        "api_key": a.api_key,
        "login_url": login_url,
        "message": f"Impersonating account: {a.account_name}",
    }


@router.post("/accounts/{account_id}/reset-password", response_model=dict)
async def reset_account_password(
    account_id: int,
    request: AdminAccountResetPasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：重置账户密码"""
    from app.modules.common.account import Account

    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

    if admin.role == "sales" and a.sales_id != admin.id:
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

    if admin.role == "sales":
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

    # 失效余额缓存
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_balance_cache(account_id=account_id)
    except Exception:
        pass

    return {
        "success": True,
        "balance_before": float(balance_before),
        "balance_after": float(balance_after),
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
    # 充值相关类型
    recharge_types = ["deposit", "withdraw", "refund_recharge"]
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

    # 软删除：将状态设为closed并标记删除
    account.status = "closed"
    account.is_deleted = True
    account.tg_id = None
    account.tg_username = None
    # 解除 TG 业务助手绑定，避免 telegram_bindings 仍指向已删除账户
    await db.execute(
        delete(TelegramBinding).where(TelegramBinding.account_id == account_id)
    )
    await db.commit()

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
    from app.modules.sms.supplier import SupplierChannel, Supplier
    
    result = await db.execute(
        select(Channel).where(
            Channel.is_deleted == False
        ).order_by(Channel.created_at.desc())
    )
    channels = result.scalars().all()
    
    # 获取所有通道的供应商关联
    channel_ids = [ch.id for ch in channels]
    supplier_map = {}
    if channel_ids:
        supplier_result = await db.execute(
            select(SupplierChannel, Supplier)
            .join(Supplier, SupplierChannel.supplier_id == Supplier.id)
            .where(SupplierChannel.channel_id.in_(channel_ids))
        )
        for sc, supplier in supplier_result:
            supplier_map[sc.channel_id] = {
                "id": supplier.id,
                "supplier_code": supplier.supplier_code,
                "supplier_name": supplier.supplier_name
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
                "default_sender_id": ch.default_sender_id,
                "virtual_config": ch.get_virtual_config() if ch.protocol == "VIRTUAL" else None,
                "gateway_config": ch.get_gateway_config(),
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
            "default_sender_id": ch.default_sender_id,
            "virtual_config": ch.get_virtual_config() if ch.protocol == "VIRTUAL" else None,
            "gateway_config": ch.get_gateway_config(),
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
    )

    # 虚拟通道无外部连接，默认可用状态为「正常」
    if request.protocol == "VIRTUAL":
        channel.connection_status = "online"
        channel.connection_checked_at = datetime.utcnow()
    
    if request.virtual_config and request.protocol == 'VIRTUAL':
        import json
        channel.virtual_config = json.dumps(request.virtual_config, ensure_ascii=False)

    if request.gateway_config:
        import json
        channel.config_json = json.dumps(request.gateway_config, ensure_ascii=False)

    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    
    # 关联供应商
    if request.supplier_id:
        from app.modules.sms.supplier import SupplierChannel
        sc = SupplierChannel(
            supplier_id=request.supplier_id,
            channel_id=channel.id,
            status='active'
        )
        db.add(sc)
        await db.commit()
    
    logger.info(f"通道创建成功: {channel.channel_code}")
    
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
    if "virtual_config" in updated_fields:
        import json
        channel.virtual_config = json.dumps(request.virtual_config, ensure_ascii=False) if request.virtual_config else None
    if "gateway_config" in updated_fields:
        import json
        channel.config_json = json.dumps(request.gateway_config, ensure_ascii=False) if request.gateway_config else None

    # 更新供应商关联（仅当请求中显式包含 supplier_id 时处理，传 null 表示清除）
    if 'supplier_id' in updated_fields:
        from app.modules.sms.supplier import SupplierChannel
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
    
    channel.is_deleted = True
    channel.status = "inactive"
    await db.commit()
    
    logger.info(f"通道删除成功: {channel.channel_code}")
    
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
                "expiry_date": getattr(p, 'expiry_date', None).isoformat() if hasattr(p, 'expiry_date') and getattr(p, 'expiry_date', None) else None
            }
            for p in pricing_list
        ]
    }


@router.post("/pricing", response_model=dict)
async def create_pricing(
    request: PricingCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建费率规则"""
    from app.modules.sms.country_pricing import CountryPricing
    from decimal import Decimal
    from datetime import date
    
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
        effective_date=eff_date
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
        "message": "Pricing rule created successfully"
    }


@router.put("/pricing/{pricing_id}", response_model=dict)
async def update_pricing(
    pricing_id: int,
    price_per_sms: Optional[float] = None,
    currency: Optional[str] = None,
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
    
    if price_per_sms is not None:
        pricing.price_per_sms = Decimal(str(price_per_sms))
    if currency is not None:
        pricing.currency = currency
    
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
    from app.modules.sms.channel import Channel
    from app.modules.sms.sms_log import SMSLog
    from app.modules.common.account import Account
    from sqlalchemy import func, and_, case
    from datetime import timedelta
    
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = today_start + timedelta(days=1)
    
    # 根据角色决定数据范围
    is_global_admin = admin.role in ['super_admin', 'admin']
    is_sales = admin.role == 'sales'
    
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
            func.sum(SMSLog.cost_price).label("total_cost"),
            func.sum(SMSLog.selling_price).label("total_revenue"),
            func.sum(SMSLog.profit).label("total_profit")
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
            func.sum(SMSLog.cost_price).label("total_cost"),
            func.sum(SMSLog.selling_price).label("total_revenue"),
            func.sum(SMSLog.profit).label("total_profit")
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
            func.sum(SMSLog.cost_price).label("total_cost"),
            func.sum(SMSLog.selling_price).label("total_revenue"),
            func.sum(SMSLog.profit).label("total_profit")
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
            func.sum(SMSLog.cost_price).label("total_cost"),
            func.sum(SMSLog.selling_price).label("total_revenue"),
            func.sum(SMSLog.profit).label("total_profit")
        ).where(
            and_(
                SMSLog.submit_time >= today_start,
                SMSLog.submit_time < today_end
            )
        )
    
    today_result = await db.execute(today_stats_query)
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
        func.sum(SMSLog.selling_price).label("total_revenue"),
    ).where(yest_filter)
    yest_row = (await db.execute(yest_q)).first()
    yesterday_stats = {
        "sent": yest_row.total_sent or 0,
        "delivered": int(yest_row.total_delivered or 0),
        "failed": int(yest_row.total_failed or 0),
        "revenue": round(float(yest_row.total_revenue or 0), 4),
    }

    # 7天趋势
    week_ago = today_start - timedelta(days=6)
    if is_global_admin or (not is_sales):
        trend_filter = and_(SMSLog.submit_time >= week_ago, SMSLog.submit_time < today_end)
    elif is_sales and my_account_ids:
        trend_filter = and_(SMSLog.submit_time >= week_ago, SMSLog.submit_time < today_end,
                            SMSLog.account_id.in_(my_account_ids))
    else:
        trend_filter = and_(SMSLog.submit_time >= week_ago, SMSLog.submit_time < today_end, SMSLog.id < 0)

    trend_q = select(
        func.date(SMSLog.submit_time).label("dt"),
        func.count(SMSLog.id).label("cnt"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("delivered"),
        func.sum(SMSLog.selling_price).label("revenue"),
    ).where(trend_filter).group_by(func.date(SMSLog.submit_time)).order_by(func.date(SMSLog.submit_time))
    trend_rows = (await db.execute(trend_q)).fetchall()
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
                func.sum(SMSLog.selling_price).label("revenue"),
            )
            .join(Account, SMSLog.account_id == Account.id)
            .where(and_(*top_filter))
            .group_by(Account.account_name)
            .order_by(func.count(SMSLog.id).desc())
            .limit(10)
        )
        for r in (await db.execute(top_q)).fetchall():
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
        for r in (await db.execute(ch_q)).fetchall():
            channel_stats.append({
                "channel_name": r.channel_name,
                "sent": r.sent,
                "delivered": int(r.delivered or 0),
                "rate": round(int(r.delivered or 0) / r.sent * 100, 1) if r.sent > 0 else 0,
            })

    logger.info(f"仪表板查询: admin={admin.username}, role={admin.role}")

    view_system_monitor = admin.role in ("super_admin", "admin", "tech")
    server_metrics = None
    service_status = None
    if view_system_monitor:
        service_status = []
        try:
            await db.execute(text("SELECT 1"))
            service_status.append({"id": "mysql", "status": "ok"})
        except Exception as e:
            service_status.append({"id": "mysql", "status": "error", "message": str(e)[:160]})
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                await r.ping()
                service_status.append({"id": "redis", "status": "ok"})
            finally:
                await r.aclose()
        except Exception as e:
            service_status.append({"id": "redis", "status": "error", "message": str(e)[:160]})
        try:
            from app.utils.server_metrics import check_rabbitmq_sync

            await asyncio.to_thread(check_rabbitmq_sync)
            service_status.append({"id": "rabbitmq", "status": "ok"})
        except Exception as e:
            service_status.append({"id": "rabbitmq", "status": "error", "message": str(e)[:160]})
        try:
            from app.utils.server_metrics import collect_host_metrics_sync

            server_metrics = await asyncio.to_thread(collect_host_metrics_sync)
        except Exception as e:
            logger.warning("采集主机指标失败: %s", e)
            server_metrics = {"error": str(e)[:200]}

    return {
        "success": True,
        "admin_name": admin.username,
        "admin_role": admin.role,
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
        "yesterday_stats": yesterday_stats,
        "daily_trend": daily_trend,
        "top_customers": top_customers,
        "batch_overview": batch_overview,
        "channel_stats": channel_stats,
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
    if admin.role == "sales":
        query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            func.sum(case((or_(SMSLog.status == "pending", SMSLog.status == "queued"), 1), else_=0)).label("total_pending"),
            func.sum(SMSLog.cost_price).label("total_cost"),
            func.sum(SMSLog.selling_price).label("total_revenue"),
        ).select_from(SMSLog).join(Account, SMSLog.account_id == Account.id).where(
            and_(time_filter, Account.sales_id == admin.id, Account.is_deleted == False)
        )
    else:
        query = select(
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            func.sum(case((or_(SMSLog.status == "pending", SMSLog.status == "queued"), 1), else_=0)).label("total_pending"),
            func.sum(SMSLog.cost_price).label("total_cost"),
            func.sum(SMSLog.selling_price).label("total_revenue"),
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


@router.get("/send-statistics", response_model=dict)
async def get_send_statistics(
    account_id: Optional[int] = Query(None, description="客户账户ID"),
    sales_id: Optional[int] = Query(None, description="归属销售/员工ID"),
    channel_id: Optional[int] = Query(None, description="通道ID"),
    country_code: Optional[str] = Query(None, description="国家代码"),
    group_by: str = Query("account", description="分组维度: account/channel/country/sales"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """发送统计查询：支持多维度分组（客户/通道/国家）+ 多条件筛选"""
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

    if admin.role == "sales":
        sales_id = admin.id

    agg_cols = [
        func.count(SMSLog.id).label("submit_total"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("success_count"),
        func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("failed_count"),
        func.sum(case((or_(SMSLog.status == "pending", SMSLog.status == "queued"), 1), else_=0)).label("pending_count"),
        func.avg(SMSLog.selling_price).label("avg_unit_price"),
        func.sum(SMSLog.cost_price).label("total_cost"),
        func.sum(SMSLog.selling_price).label("total_revenue"),
    ]

    need_account_join = group_by == "sales" or bool(sales_id)

    if group_by == "channel":
        base = select(SMSLog.channel_id, *agg_cols)
    elif group_by == "country":
        base = select(SMSLog.country_code, *agg_cols)
    elif group_by == "sales":
        base = select(Account.sales_id, *agg_cols)
    else:
        base = select(SMSLog.account_id, *agg_cols)

    if need_account_join:
        base = base.join(Account, SMSLog.account_id == Account.id)

    base = base.where(and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt))

    if account_id:
        base = base.where(SMSLog.account_id == account_id)
    if channel_id:
        base = base.where(SMSLog.channel_id == channel_id)
    if country_code:
        base = base.where(func.upper(SMSLog.country_code) == country_code.upper())
    if sales_id:
        base = base.where(Account.sales_id == sales_id)

    if group_by == "channel":
        base = base.where(SMSLog.channel_id.isnot(None)).group_by(SMSLog.channel_id)
    elif group_by == "country":
        base = base.where(SMSLog.country_code.isnot(None)).group_by(SMSLog.country_code)
    elif group_by == "sales":
        base = base.group_by(Account.sales_id)
    else:
        base = base.group_by(SMSLog.account_id)

    result = await db.execute(base)
    rows = result.all()

    name_map: dict = {}
    if group_by == "channel":
        ch_ids = list({r.channel_id for r in rows if r.channel_id})
        if ch_ids:
            ch_res = await db.execute(select(Channel.id, Channel.channel_name, Channel.channel_code).where(Channel.id.in_(ch_ids)))
            for r in ch_res:
                name_map[r.id] = {"name": r.channel_name, "code": r.channel_code}
    elif group_by == "account":
        acc_ids = list({r.account_id for r in rows if r.account_id})
        if acc_ids:
            acc_res = await db.execute(select(Account.id, Account.account_name).where(Account.id.in_(acc_ids)))
            for r in acc_res:
                name_map[r.id] = r.account_name
    elif group_by == "sales":
        staff_ids = list({r.sales_id for r in rows if r.sales_id})
        if staff_ids:
            staff_res = await db.execute(select(AdminUser.id, AdminUser.real_name, AdminUser.username).where(AdminUser.id.in_(staff_ids)))
            for r in staff_res:
                name_map[r.id] = r.real_name or r.username

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
        }

        if group_by == "channel":
            ch_info = name_map.get(r.channel_id, {})
            item["channel_id"] = r.channel_id
            item["channel_name"] = ch_info.get("name", "-") if isinstance(ch_info, dict) else "-"
            item["channel_code"] = ch_info.get("code", "-") if isinstance(ch_info, dict) else "-"
            item["dim_label"] = item["channel_name"]
        elif group_by == "country":
            item["country_code"] = r.country_code
            item["dim_label"] = r.country_code
        elif group_by == "sales":
            item["sales_id"] = r.sales_id
            item["sales_name"] = name_map.get(r.sales_id, "未分配")
            item["dim_label"] = item["sales_name"]
        else:
            item["account_id"] = r.account_id
            item["account_name"] = name_map.get(r.account_id, "-")
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
    }

    return {
        "success": True,
        "total": len(items),
        "items": items,
        "summary": summary,
        "filters": {"start_date": start_date, "end_date": end_date, "group_by": group_by},
    }


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
    if admin.role == "sales":
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
    if admin.role == "sales":
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
    if admin.role == "sales":
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
    country_code: Optional[str] = Query(None, description="国家代码"),
    sales_id: Optional[int] = Query(None, description="归属销售/员工ID"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """管理员：每日统计（用于图表）。支持按客户/通道/国家筛选。销售角色仅统计归属客户。"""
    from app.modules.sms.sms_log import SMSLog
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

    if admin.role == "sales":
        sales_id = admin.id

    base = (
        select(
            func.date(SMSLog.submit_time).label("date"),
            func.count(SMSLog.id).label("total_sent"),
            func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
            func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
            func.sum(SMSLog.cost_price).label("total_cost"),
            func.sum(SMSLog.selling_price).label("total_revenue"),
        )
        .where(and_(SMSLog.submit_time >= start_dt, SMSLog.submit_time < end_dt))
    )

    if account_id:
        base = base.where(SMSLog.account_id == account_id)
    if channel_id:
        base = base.where(SMSLog.channel_id == channel_id)
    if country_code:
        base = base.where(func.upper(SMSLog.country_code) == country_code.upper())
    if sales_id:
        base = base.join(Account, SMSLog.account_id == Account.id).where(
            and_(Account.sales_id == sales_id, Account.is_deleted == False)
        )

    base = base.group_by(func.date(SMSLog.submit_time)).order_by(func.date(SMSLog.submit_time).asc())
    result = await db.execute(base)

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
    return {"success": True, "days": (end_dt - start_dt).days, "statistics": statistics}


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
        # 获取本月起始时间
        first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        from app.modules.sms.sms_log import SMSLog
        from app.modules.sms.channel import Channel

        # 从 SMSLog 起表，便于命中 (submit_time, status, account_id) 等索引，减少全表扫描
        comm_query = (
            select(Account.sales_id, func.sum(SMSLog.profit * SMSLog.message_count).label("total_profit"))
            .select_from(SMSLog)
            .join(Account, SMSLog.account_id == Account.id)
            .join(Channel, SMSLog.channel_id == Channel.id)
            .where(
                and_(
                    SMSLog.submit_time >= first_day,
                    SMSLog.status == "delivered",
                    Channel.protocol != "VIRTUAL",
                )
            )
            .group_by(Account.sales_id)
        )
        comm_result = await db.execute(comm_query)
        comm_map = {r.sales_id: float(r.total_profit or 0) for r in comm_result}
    
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
    
    if existing_staff:
        # 若为在职状态，不允许重复创建
        if existing_staff.status == 'active':
            raise HTTPException(status_code=400, detail="用户名已存在")
        # 若为已禁用/锁定状态，复用该账户并重新激活
        existing_staff.password_hash = AuthService.hash_password(request.password)
        existing_staff.real_name = request.real_name
        existing_staff.tg_username = request.tg_username
        existing_staff.commission_rate = request.commission_rate or 0
        existing_staff.role = request.role
        existing_staff.status = 'active'
        existing_staff.login_failed_count = 0  # 重置登录失败次数
        await db.commit()
        await db.refresh(existing_staff)
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
        tg_username=request.tg_username,
        commission_rate=request.commission_rate or 0,
        role=request.role,
        status='active'
    )
    db.add(new_staff)
    await db.commit()
    await db.refresh(new_staff)
    
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

    msg = "员工信息已更新"
    if cleared_tg_for_username_change:
        msg += "：已解除原 Telegram 绑定，请新员工在 TG 业务助手内用登录名+密码完成绑定"

    return {
        "success": True,
        "message": msg,
        "telegram_rebind_required": cleared_tg_for_username_change,
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
    
    staff.status = 'inactive'
    # 删除员工时同步清除业务助手绑定
    _clear_staff_telegram_binding(staff)
    await db.commit()
    
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
    
    # 生成临时JWT token
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    token = AuthService.create_access_token(
        data={
            "sub": staff.id, 
            "role": staff.role, 
            "username": staff.username,
            "impersonated_by": admin.id  # 标记是被模拟的
        },
        expires_delta=access_token_expires
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
    if admin.role == 'sales':
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
    if admin.role == 'sales' and account.sales_id != admin.id:
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
