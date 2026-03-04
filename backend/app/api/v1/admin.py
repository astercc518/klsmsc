"""
管理员API路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.modules.common.admin_user import AdminUser
from app.modules.common.account import Account
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
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    status: str = "active"
    # 速率控制
    max_tps: int = 100
    concurrency: int = 1
    rate_control_window: int = 1000
    # 路由参数 (默认)
    priority: int = 0
    weight: int = 100
    default_sender_id: Optional[str] = None
    description: Optional[str] = None
    
    @field_validator('protocol')
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        if v is None:
            raise ValueError('protocol is required')
        if v not in ['HTTP', 'SMPP']:
            raise ValueError('protocol must be either HTTP or SMPP')
        return v
    
    @field_validator('default_sender_id')
    @classmethod
    def validate_default_sender_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == '':
            return None
        return v.strip()


class ChannelUpdateRequest(BaseModel):
    channel_name: Optional[str] = None
    # 速率控制
    max_tps: Optional[int] = None
    concurrency: Optional[int] = None
    rate_control_window: Optional[int] = None
    # 路由参数
    priority: Optional[int] = None
    weight: Optional[int] = None
    status: Optional[str] = None
    # 连接信息（可选）
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    default_sender_id: Optional[str] = None


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
    business_type: Optional[str] = None  # sms/voice/data（旧字段）
    services: Optional[str] = None  # 开通业务：sms,voice,data 逗号分隔
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
            error="Invalid username or password"
        )
    
    # 验证密码
    if not AuthService.verify_password(request.password, admin.password_hash):
        # 增加失败次数
        admin.login_failed_count += 1
        if admin.login_failed_count >= 5:
            admin.status = "locked"
        await db.commit()
        return AdminLoginResponse(
            success=False,
            error="Invalid username or password"
        )
    
    # 检查状态
    if admin.status != "active":
        return AdminLoginResponse(
            success=False,
            error=f"Account is {admin.status}"
        )
    
    # 更新登录信息
    admin.last_login_at = datetime.now()
    admin.login_failed_count = 0
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


# --- Accounts (Admin) ---

@router.get("/accounts", response_model=dict)
async def list_accounts_admin(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    business_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员：获取账户列表"""
    from sqlalchemy import func, or_, and_
    import json

    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    where_clauses = [Account.is_deleted == False]
    if status:
        where_clauses.append(Account.status == status)
    if business_type:
        where_clauses.append(Account.business_type == business_type)
    if keyword:
        kw = f"%{keyword.strip()}%"
        where_clauses.append(or_(Account.email.like(kw), Account.account_name.like(kw)))

    where_expr = and_(*where_clauses)

    total_result = await db.execute(select(func.count(Account.id)).where(where_expr))
    total = total_result.scalar() or 0

    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(Account)
        .options(selectinload(Account.sales))
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

    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # 生成唯一邮箱（内部使用）
    unique_email = f"{uuid.uuid4().hex[:12]}@internal.sms"

    # 生成API Key/Secret（注意长度限制）
    api_key = f"ak_{secrets.token_hex(30)}"  # <= 64
    api_secret = secrets.token_hex(32)
    
    # 生成SMPP System ID (如果是SMPP协议)
    smpp_system_id = None
    smpp_password = None
    if request.protocol == "SMPP":
        smpp_system_id = f"SM{secrets.token_hex(3).upper()}"
        smpp_password = request.smpp_password or secrets.token_hex(8)

    ip_whitelist_raw = None
    if request.ip_whitelist is not None:
        ip_whitelist_raw = json.dumps(request.ip_whitelist, ensure_ascii=False)

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
        balance=0.0,
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
            # 绑定配置
            "sales_id": a.sales_id,
            "channels": channels,
            "channel_ids": [ch["id"] for ch in channels],
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
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

    result = await db.execute(select(Account).where(Account.id == account_id, Account.is_deleted == False))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Account not found")

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

    a.api_key = f"ak_{secrets.token_hex(30)}"
    a.api_secret = secrets.token_hex(32)
    await db.commit()

    return {
        "success": True,
        "api_key": a.api_key,
        "api_secret": a.api_secret,
        "message": "API credentials reset successfully",
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

    return {
        "success": True,
        "account_id": a.id,
        "account_name": a.account_name,
        "api_key": a.api_key,
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

    allowed_types = {"charge", "refund", "deposit", "withdraw", "adjustment"}
    change_type = request.change_type
    if not change_type:
        change_type = "deposit" if amount > 0 else "withdraw"
    if change_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid change_type")

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
                "balance_before": float(l.balance_before),
                "balance_after": float(l.balance_after),
                "currency": l.currency,
                "transaction_id": l.transaction_id,
                "description": l.description,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


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
    
    # 软删除：将状态设为closed并标记删除
    account.status = 'closed'
    account.is_deleted = True
    await db.commit()

    return {
        "success": True,
        "message": "账户已删除"
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
                "priority": ch.priority,
                "weight": ch.weight,
                "max_tps": ch.max_tps,
                "concurrency": ch.concurrency,
                "rate_control_window": ch.rate_control_window,
                "host": ch.host,
                "port": ch.port,
                "username": ch.username,
                "api_url": ch.api_url,
                "default_sender_id": ch.default_sender_id,
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

    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    ch = result.scalar_one_or_none()

    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    return {
        "success": True,
        "channel": {
            "id": ch.id,
            "channel_code": ch.channel_code,
            "channel_name": ch.channel_name,
            "protocol": ch.protocol,
            "status": ch.status,
            "priority": ch.priority,
            "weight": ch.weight,
            "max_tps": ch.max_tps,
            "concurrency": ch.concurrency,
            "rate_control_window": ch.rate_control_window,
            "host": ch.host,
            "port": ch.port,
            "username": ch.username,
            # 安全起见不返回 password/api_key 明文
            "api_url": ch.api_url,
            "default_sender_id": ch.default_sender_id,
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
        api_url=request.api_url,
        api_key=request.api_key,
        priority=request.priority,
        weight=request.weight,
        max_tps=request.max_tps,
        concurrency=request.concurrency,
        rate_control_window=request.rate_control_window,
        default_sender_id=request.default_sender_id.strip() if request.default_sender_id else None,
        status=request.status
    )
    
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    
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
    """通道测试发送"""
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
    
    # 创建测试消息ID
    test_message_id = f"TEST_{uuid.uuid4().hex[:12]}"
    sender_id = request.sender_id or channel.default_sender_id or "TEST"
    
    try:
        if channel.protocol == "SMPP":
            from app.workers.adapters.smpp_adapter import SMPPAdapter
            adapter = SMPPAdapter(channel)
            
            # 创建模拟的 SMSLog 对象
            class MockSMSLog:
                def __init__(self):
                    self.message_id = test_message_id
                    self.phone_number = request.phone
                    self.content = request.content
                    self.message = request.content  # SMPP适配器使用message属性
                    self.sender_id = sender_id
            
            mock_log = MockSMSLog()
            
            # 连接并发送
            connected = await adapter.connect()
            if not connected:
                return {
                    "success": False,
                    "message": "SMPP连接失败",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "host": f"{channel.host}:{channel.port}"
                    }
                }
            
            success, channel_msg_id, error = await adapter.send(mock_log)
            await adapter.disconnect()
            
            if success:
                return {
                    "success": True,
                    "message": "测试发送成功",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "message_id": test_message_id,
                        "channel_message_id": channel_msg_id,
                        "phone": request.phone
                    }
                }
            else:
                return {
                    "success": False,
                    "message": f"发送失败: {error}",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP"
                    }
                }
                
        elif channel.protocol == "HTTP":
            from app.workers.adapters.http_adapter import HTTPAdapter
            adapter = HTTPAdapter(channel)
            
            class MockSMSLog:
                def __init__(self):
                    self.message_id = test_message_id
                    self.phone_number = request.phone
                    self.content = request.content
                    self.message = request.content  # HTTP适配器也可能使用message属性
                    self.sender_id = sender_id
            
            mock_log = MockSMSLog()
            success, channel_msg_id, error = await adapter.send(mock_log)
            
            if success:
                return {
                    "success": True,
                    "message": "测试发送成功",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "HTTP",
                        "message_id": test_message_id,
                        "channel_message_id": channel_msg_id,
                        "phone": request.phone
                    }
                }
            else:
                return {
                    "success": False,
                    "message": f"发送失败: {error}",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "HTTP",
                        "api_url": channel.api_url
                    }
                }
        else:
            return {
                "success": False,
                "message": f"不支持的协议类型: {channel.protocol}"
            }
            
    except Exception as e:
        logger.error(f"测试发送异常: {str(e)}", exc_info=e)
        return {
            "success": False,
            "message": f"测试发送异常: {str(e)}",
            "details": {
                "channel": channel.channel_code
            }
        }


@router.post("/channels/{channel_id}/check-status", response_model=dict)
async def channel_check_status(
    channel_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """通道状态检查"""
    from app.modules.sms.channel import Channel
    import httpx
    import time
    
    result = await db.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    start_time = time.time()
    
    try:
        if channel.protocol == "SMPP":
            from app.workers.adapters.smpp_adapter import SMPPAdapter
            adapter = SMPPAdapter(channel)
            
            connected = await adapter.connect()
            latency_ms = int((time.time() - start_time) * 1000)
            
            if connected:
                await adapter.disconnect()
                return {
                    "success": True,
                    "status": "online",
                    "message": "SMPP连接正常",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "host": channel.host,
                        "port": channel.port,
                        "latency_ms": latency_ms
                    }
                }
            else:
                return {
                    "success": False,
                    "status": "offline",
                    "message": "SMPP连接失败",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "SMPP",
                        "host": channel.host,
                        "port": channel.port,
                        "latency_ms": latency_ms
                    }
                }
                
        elif channel.protocol == "HTTP":
            # HTTP通道检测 - 检测API地址是否可达
            if not channel.api_url:
                return {
                    "success": False,
                    "status": "error",
                    "message": "HTTP通道未配置API地址",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "HTTP",
                        "api_url": None
                    }
                }
            try:
                # 从api_url提取主机和端口进行TCP连接测试
                from urllib.parse import urlparse
                import socket
                
                parsed = urlparse(channel.api_url)
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == 'https' else 80)
                
                # 使用socket进行快速连接测试（5秒超时）
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                try:
                    sock.connect((host, port))
                    sock.close()
                    latency_ms = int((time.time() - start_time) * 1000)
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
                            "latency_ms": latency_ms
                        }
                    }
                except socket.timeout:
                    latency_ms = int((time.time() - start_time) * 1000)
                    return {
                        "success": False,
                        "status": "timeout",
                        "message": f"HTTP接口连接超时 ({host}:{port})",
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "HTTP",
                            "api_url": channel.api_url,
                            "host": host,
                            "port": port,
                            "latency_ms": latency_ms
                        }
                    }
                except (socket.error, OSError) as e:
                    latency_ms = int((time.time() - start_time) * 1000)
                    return {
                        "success": False,
                        "status": "offline",
                        "message": f"HTTP接口连接失败: {str(e)}",
                        "details": {
                            "channel": channel.channel_code,
                            "protocol": "HTTP",
                            "api_url": channel.api_url,
                            "host": host,
                            "port": port,
                            "latency_ms": latency_ms
                        }
                    }
            except Exception as parse_err:
                latency_ms = int((time.time() - start_time) * 1000)
                return {
                    "success": False,
                    "status": "error",
                    "message": f"API地址解析失败: {str(parse_err)}",
                    "details": {
                        "channel": channel.channel_code,
                        "protocol": "HTTP",
                        "api_url": channel.api_url,
                        "latency_ms": latency_ms
                    }
                }
        else:
            return {
                "success": False,
                "status": "unknown",
                "message": f"不支持的协议类型: {channel.protocol}"
            }
            
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"状态检查异常: {str(e)}", exc_info=e)
        return {
            "success": False,
            "status": "error",
            "message": f"状态检查异常: {str(e)}",
            "details": {
                "channel": channel.channel_code,
                "latency_ms": latency_ms
            }
        }


# --- Routing Rules Management ---

class RoutingRuleCreateRequest(BaseModel):
    channel_id: int
    country_code: str
    priority: int = 0
    is_active: bool = True


class RoutingRuleUpdateRequest(BaseModel):
    priority: Optional[int] = None
    is_active: Optional[bool] = None


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
    await db.commit()
    await db.refresh(pricing)
    
    logger.info(f"费率规则创建成功: {pricing.country_code} - {pricing.channel_id}")

    # 失效价格缓存（该通道/国家）
    try:
        from app.utils.cache import get_cache_manager
        cache_manager = await get_cache_manager()
        await cache_manager.invalidate_price_cache(channel_id=pricing.channel_id, country_code=pricing.country_code)
    except Exception:
        pass
    
    return {
        "success": True,
        "pricing_id": pricing.id,
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
    else:
        # 其他角色：空数据
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
    
    logger.info(f"仪表板查询: admin={admin.username}, role={admin.role}")
    
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
        "recent_customers": recent_customers if is_sales else [],
        "permissions": {
            "view_global": is_global_admin,
            "view_finance": admin.role in ['super_admin', 'admin', 'finance'],
            "view_channels": admin.role in ['super_admin', 'admin', 'tech'],
            "view_customers": is_sales or is_global_admin
        }
    }


@router.get("/statistics", response_model=dict)
async def get_admin_statistics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    管理员系统级统计
    """
    from app.modules.sms.sms_log import SMSLog
    from sqlalchemy import func, and_, case
    
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
    
    # 全系统统计
    query = select(
        func.count(SMSLog.id).label("total_sent"),
        func.sum(case((SMSLog.status == "delivered", 1), else_=0)).label("total_delivered"),
        func.sum(case((SMSLog.status == "failed", 1), else_=0)).label("total_failed"),
        func.sum(SMSLog.cost_price).label("total_cost")
    ).where(
        and_(
            SMSLog.submit_time >= start_dt,
            SMSLog.submit_time < end_dt
        )
    )
    
    result = await db.execute(query)
    row = result.first()
    
    total_sent = row.total_sent or 0
    total_delivered = row.total_delivered or 0
    total_failed = row.total_failed or 0
    total_cost = float(row.total_cost or 0)
    success_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
    
    return {
        "total_sent": total_sent,
        "total_delivered": total_delivered,
        "total_failed": total_failed,
        "success_rate": round(success_rate, 2),
        "total_cost": round(total_cost, 4),
        "currency": "USD"
    }


@router.get("/users", response_model=dict)
async def list_admin_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取管理员用户列表（不包含超级管理员和管理员）"""
    query = select(AdminUser)
    
    # 过滤掉超级管理员和管理员，只显示员工
    query = query.where(AdminUser.role.notin_(['super_admin', 'admin']))
    
    # 默认不显示已删除(inactive)的员工
    if status:
        query = query.where(AdminUser.status == status)
    else:
        query = query.where(AdminUser.status != 'inactive')
    
    if role:
        query = query.where(AdminUser.role == role)
    
    query = query.order_by(AdminUser.created_at.desc())
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
                "monthly_commission": float(u.monthly_commission) if u.monthly_commission else 0,
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
    existing = await db.execute(
        select(AdminUser).where(AdminUser.username == request.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 创建员工
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
    if request.real_name is not None:
        staff.real_name = request.real_name
    if request.tg_username is not None:
        staff.tg_username = request.tg_username
    if request.commission_rate is not None:
        staff.commission_rate = request.commission_rate
    if request.role is not None and admin.role == 'super_admin':
        staff.role = request.role
    if request.status is not None:
        staff.status = request.status
    if request.password:
        staff.password_hash = AuthService.hash_password(request.password)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "员工信息已更新"
    }


@router.delete("/users/{user_id}", response_model=dict)
async def delete_staff(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除员工（设为inactive）"""
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
