"""
账户管理API路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.modules.common.account import Account
from app.core.auth import AuthService, api_key_header
from app.schemas.account import (
    AccountBalanceResponse,
    AccountInfoResponse,
    AccountCreateRequest,
    AccountLoginRequest,
    AccountLoginResponse
)
from app.utils.logger import get_logger
from app.utils.cache import get_cache_manager
import secrets

logger = get_logger(__name__)
router = APIRouter()


async def get_current_account(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> Account:
    """获取当前认证账户"""
    return await AuthService.verify_api_key(api_key, db)


@router.get("/balance", response_model=AccountBalanceResponse)
async def get_balance(
    account: Account = Depends(get_current_account)
):
    """
    查询账户余额（带缓存）
    """
    logger.info(f"查询账户余额: 账户={account.id}")
    
    cache_manager = await get_cache_manager()
    balance_cache_key = f"account:{account.id}:balance"
    
    # 尝试从缓存获取余额
    cached_balance = await cache_manager.get(balance_cache_key)
    
    if cached_balance is not None:
        # 使用缓存余额（1分钟TTL，可能不是最新，但查询速度快）
        balance = float(cached_balance)
        logger.debug(f"余额缓存命中: 账户={account.id}, 余额={balance}")
    else:
        # 缓存未命中，使用数据库中的余额
        balance = float(account.balance)
        # 存入缓存
        await cache_manager.set(balance_cache_key, balance, ttl=60)
        logger.debug(f"余额已缓存: 账户={account.id}, 余额={balance}")
    
    return AccountBalanceResponse(
        account_id=account.id,
        balance=balance,
        currency=account.currency,
        low_balance_threshold=float(account.low_balance_threshold) if account.low_balance_threshold else None
    )


@router.get("/info", response_model=AccountInfoResponse)
async def get_account_info(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    查询账户信息
    """
    logger.info(f"查询账户信息: 账户={account.id}")
    
    # 查询 TG 绑定状态（优先 TelegramBinding 表）
    from app.modules.common.telegram_binding import TelegramBinding
    from app.modules.common.telegram_user import TelegramUser

    tg_id = account.tg_id
    tg_username = account.tg_username

    if not tg_id:
        bind_result = await db.execute(
            select(TelegramBinding).where(
                TelegramBinding.account_id == account.id,
                TelegramBinding.is_active == True
            ).limit(1)
        )
        binding = bind_result.scalar_one_or_none()
        if binding:
            tg_id = binding.tg_id
            tg_user_result = await db.execute(
                select(TelegramUser).where(TelegramUser.tg_id == binding.tg_id)
            )
            tg_user = tg_user_result.scalar_one_or_none()
            if tg_user:
                tg_username = tg_user.username

    return AccountInfoResponse(
        id=account.id,
        account_name=account.account_name,
        email=account.email,
        balance=float(account.balance),
        currency=account.currency,
        status=account.status,
        services=account.services or "sms",
        company_name=account.company_name,
        contact_person=account.contact_person,
        rate_limit=account.rate_limit,
        tg_id=tg_id,
        tg_username=tg_username,
        unit_price=float(account.unit_price) if account.unit_price is not None else None,
        created_at=account.created_at.isoformat()
    )


@router.post("/register", response_model=dict)
async def register_account(
    request: AccountCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    注册新账户
    
    - **account_name**: 账户名称
    - **email**: 邮箱
    - **password**: 密码
    - **company_name**: 公司名称（可选）
    - **contact_person**: 联系人（可选）
    - **contact_phone**: 联系电话（可选）
    """
    logger.info(f"新账户注册: email={request.email}")
    
    # 检查邮箱是否已存在
    result = await db.execute(
        select(Account).where(Account.email == request.email)
    )
    existing_account = result.scalar_one_or_none()
    
    if existing_account:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # 生成API Key和Secret
    # 注意：accounts.api_key 字段为 VARCHAR(64)，需要保证长度 <= 64
    api_key = f"ak_{secrets.token_hex(30)}"  # 3 + 60 = 63
    api_secret = secrets.token_hex(32)
    
    # 创建账户
    new_account = Account(
        account_name=request.account_name,
        email=request.email,
        password_hash=AuthService.hash_password(request.password),
        balance=0.0,
        currency="USD",
        status="active",
        api_key=api_key,
        api_secret=api_secret,
        company_name=request.company_name,
        contact_person=request.contact_person,
        contact_phone=request.contact_phone
    )
    
    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)
    
    logger.info(f"账户创建成功: id={new_account.id}, email={new_account.email}")
    
    return {
        "success": True,
        "account_id": new_account.id,
        "api_key": api_key,
        "api_secret": api_secret,
        "message": "Account created successfully. Please save your API credentials."
    }


@router.post("/login", response_model=AccountLoginResponse)
async def login(
    request: AccountLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    账户登录
    
    - **email**: 邮箱或用户名
    - **password**: 密码
    """
    from sqlalchemy import or_
    
    login_id = request.email  # 可以是邮箱或用户名
    logger.info(f"账户登录: login_id={login_id}")
    
    # 查询账户 - 支持邮箱或用户名登录
    result = await db.execute(
        select(Account).where(
            or_(
                Account.email == login_id,
                Account.account_name == login_id
            ),
            Account.is_deleted == False
        )
    )
    account = result.scalar_one_or_none()
    
    if not account:
        return AccountLoginResponse(
            success=False,
            error="invalid_credentials"
        )
    
    # 验证密码
    if not AuthService.verify_password(request.password, account.password_hash):
        logger.warning(f"密码验证失败: email={request.email}")
        return AccountLoginResponse(
            success=False,
            error="invalid_credentials"
        )
    
    # 检查账户状态
    if account.status != 'active':
        return AccountLoginResponse(
            success=False,
            error="account_disabled"
        )
    
    logger.info(f"登录成功: 账户={account.id}")
    
    # 登录成功，更新活跃度 +5 和最近登录时间
    from datetime import datetime
    current_score = account.activity_score if account.activity_score is not None else 100
    last_update = account.activity_updated_at or account.created_at
    if last_update:
        days_passed = (datetime.now() - last_update).days
        actual_score = max(0, current_score - (days_passed * 5))
    else:
        actual_score = current_score
    account.activity_score = actual_score + 5
    account.activity_updated_at = datetime.now()
    account.last_login_at = datetime.now()
    await db.commit()
    
    # 返回API Key作为token
    return AccountLoginResponse(
        success=True,
        token=account.api_key,
        account_id=account.id
    )


@router.post("/telegram-bind-code", response_model=dict)
async def generate_account_tg_bind_code(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """客户生成 Telegram 绑定码"""
    import random
    from app.utils.cache import get_redis_client

    redis_client = await get_redis_client()
    code = f"{random.randint(100000, 999999)}"
    bind_key = f"acct_tg_bind:{code}"
    await redis_client.setex(bind_key, 300, str(account.id).encode("utf-8"))

    logger.info(f"客户 TG 绑定码生成: account_id={account.id}, code={code}")
    return {"success": True, "code": code, "expires_in": 300}


@router.post("/telegram-unbind", response_model=dict)
async def unbind_account_telegram(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """客户解绑 Telegram"""
    from app.modules.common.telegram_binding import TelegramBinding

    # 清除 Account 表上的 tg_id
    if account.tg_id:
        account.tg_id = None
        account.tg_username = None

    # 停用 TelegramBinding 记录
    bind_result = await db.execute(
        select(TelegramBinding).where(
            TelegramBinding.account_id == account.id,
            TelegramBinding.is_active == True
        )
    )
    bindings = bind_result.scalars().all()
    for b in bindings:
        b.is_active = False

    await db.commit()
    logger.info(f"客户解绑 TG: account_id={account.id}")
    return {"success": True, "message": "unbound"}

