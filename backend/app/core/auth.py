"""
认证授权模块
"""
import hmac
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import Security, HTTPException, Header, Request, Depends
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.modules.common.account import Account
from app.modules.common.admin_user import AdminUser
from app.database import get_db
from app.config import settings
from app.utils.errors import AuthenticationError
from app.utils.logger import get_logger
from app.utils.cache import get_redis_client

logger = get_logger(__name__)

# API Key Header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# JWT Bearer Token（管理员登录，缺失时报错）
security = HTTPBearer()
# 可选 Bearer：用于识别 Authorization: Bearer ak_xxx（与 X-API-Key 等价）
optional_bearer = HTTPBearer(auto_error=False)

# 可选 HTTP Basic Auth：客户通过 account_name + password 认证
optional_basic = HTTPBasic(auto_error=False)

# 模块级 CryptContext 实例（避免每次调用重复创建）
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _utcnow() -> datetime:
    """返回当前 UTC 时间（timezone-aware）"""
    return datetime.now(timezone.utc)


# ====================================
# FastAPI Dependencies
# ====================================

async def get_current_account(
    request: Request,
    api_key: Optional[str] = Security(api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(optional_bearer),
    basic_creds: Optional[HTTPBasicCredentials] = Security(optional_basic),
    db: AsyncSession = Depends(get_db),
) -> Account:
    """获取当前认证账户：优先 X-API-Key > Bearer ak_xxx > HTTP Basic Auth > URL参数 api_key"""
    effective = api_key
    if not effective and bearer and bearer.credentials:
        token = bearer.credentials.strip()
        if token.startswith("ak_"):
            effective = token

    if not effective:
        effective = request.query_params.get("api_key")

    if effective:
        return await AuthService.verify_api_key(effective, db)

    # HTTP Basic Auth（account_name/email + password）
    if basic_creds and basic_creds.username:
        return await AuthService.verify_basic_credentials(basic_creds, db)

    raise AuthenticationError("Missing API Key or credentials")


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> AdminUser:
    """获取当前管理员（FastAPI Dependency）— 委托给 AuthService 实现"""
    return await AuthService.get_current_admin(credentials, db)




class AuthService:
    """认证服务"""
    
    @staticmethod
    async def verify_api_key(
        api_key: Optional[str] = Security(api_key_header),
        db: AsyncSession = None
    ) -> Account:
        """
        验证API Key
        
        Args:
            api_key: API密钥
            db: 数据库会话
            
        Returns:
            Account对象
            
        Raises:
            AuthenticationError: 认证失败
        """
        if not api_key:
            logger.warning("缺少API Key")
            raise AuthenticationError("Missing API Key")
        
        # 查询账户
        result = await db.execute(
            select(Account).where(
                Account.api_key == api_key,
                Account.status == 'active',
                Account.is_deleted == False
            )
        )
        account = result.scalar_one_or_none()
        
        if not account:
            logger.warning(f"无效的API Key: {api_key[:10]}...")
            raise AuthenticationError("Invalid API Key")
        
        # 缓存账户限流配置（5分钟TTL）
        try:
            redis_client = await get_redis_client()
            cache_key = f"account:limit:{api_key}"
            if account.rate_limit:
                await redis_client.setex(
                    cache_key.encode(),
                    300,  # 5分钟
                    str(account.rate_limit).encode()
                )
        except Exception as e:
            logger.debug(f"缓存账户限流配置失败: {str(e)}")
        
        logger.debug(f"认证成功: 账户 {account.id} ({account.email})")
        return account
    
    @staticmethod
    async def verify_basic_credentials(
        credentials: HTTPBasicCredentials,
        db: AsyncSession,
    ) -> Account:
        """
        通过 HTTP Basic Auth（用户名 + 密码）验证客户账户

        支持 account_name 或 email 作为用户名。
        密码优先匹配 api_secret（接口密码），其次匹配 password_hash（登录密码）。
        """
        from sqlalchemy import or_
        login_id = credentials.username
        result = await db.execute(
            select(Account).where(
                or_(
                    Account.account_name == login_id,
                    Account.email == login_id,
                ),
                Account.status == "active",
                Account.is_deleted == False,
            )
        )
        account = result.scalar_one_or_none()

        if not account:
            logger.warning(f"Basic Auth 失败：账户不存在 login_id={login_id}")
            raise AuthenticationError("Invalid credentials")

        pwd = credentials.password

        # 优先匹配 api_secret（接口密码，明文比对）
        if account.api_secret and pwd == account.api_secret:
            logger.debug(f"Basic Auth(api_secret) 认证成功: 账户 {account.id} ({account.account_name})")
            return account

        # 回退匹配 password_hash（登录密码）
        if account.password_hash and _pwd_context.verify(pwd, account.password_hash):
            logger.debug(f"Basic Auth(login_pwd) 认证成功: 账户 {account.id} ({account.account_name})")
            return account

        logger.warning(f"Basic Auth 密码错误: login_id={login_id}")
        raise AuthenticationError("Invalid credentials")

    @staticmethod
    async def verify_signature(
        request: Request,
        api_key: str,
        timestamp: str = Header(..., alias="X-Timestamp"),
        signature: str = Header(..., alias="X-Signature"),
        db: AsyncSession = None
    ) -> Account:
        """
        验证HMAC签名（高级认证）
        
        Args:
            request: 请求对象
            api_key: API密钥
            timestamp: 时间戳
            signature: HMAC签名
            db: 数据库会话
            
        Returns:
            Account对象
            
        Raises:
            AuthenticationError: 认证失败
        """
        # 1. 查询账户和密钥
        result = await db.execute(
            select(Account).where(
                Account.api_key == api_key,
                Account.status == 'active',
                Account.is_deleted == False
            )
        )
        account = result.scalar_one_or_none()
        
        if not account or not account.api_secret:
            raise AuthenticationError("Invalid API Key")
        
        # 2. 验证时间戳（防重放攻击）
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - request_time) > 300:  # 5分钟有效期
                raise AuthenticationError("Request expired")
        except ValueError:
            raise AuthenticationError("Invalid timestamp")
        
        # 3. 读取请求体
        body = await request.body()
        
        # 4. 计算签名
        message = f"{api_key}{timestamp}{body.decode()}"
        expected_signature = hmac.new(
            account.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # 5. 比较签名
        if not hmac.compare_digest(expected_signature, signature):
            logger.warning(f"签名验证失败: 账户 {account.id}")
            raise AuthenticationError("Invalid signature")
        
        logger.debug(f"签名验证成功: 账户 {account.id}")
        return account
    
    @staticmethod
    def hash_password(password: str) -> str:
        """密码哈希"""
        return _pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return _pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        创建JWT访问令牌
        
        Args:
            data: 要编码的数据（通常是用户ID和角色）
            expires_delta: 过期时间增量
            
        Returns:
            JWT token字符串
        """
        to_encode = data.copy()
        if "sub" in to_encode and to_encode["sub"] is not None:
            to_encode["sub"] = str(to_encode["sub"])
        now = _utcnow()
        expire = now + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
        
        to_encode.update({"exp": expire, "iat": now})
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """
        验证JWT令牌
        
        Args:
            token: JWT token字符串
            
        Returns:
            解码后的payload
            
        Raises:
            AuthenticationError: token无效或过期
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
        except JWTError as e:
            logger.warning(f"JWT验证失败: {str(e)}")
            raise AuthenticationError("Invalid token")
    
    @staticmethod
    async def get_current_admin(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: AsyncSession = Depends(get_db)
    ) -> AdminUser:
        """
        获取当前认证的管理员（JWT认证）
        
        Args:
            credentials: HTTP Bearer token凭证
            db: 数据库会话
            
        Returns:
            AdminUser对象
            
        Raises:
            AuthenticationError: 认证失败
        """
        token = credentials.credentials
        payload = AuthService.verify_token(token)
        
        admin_sub = payload.get("sub")
        if admin_sub is None:
            raise AuthenticationError("Invalid token payload")
        try:
            admin_id = int(admin_sub)
        except (TypeError, ValueError):
            raise AuthenticationError("Invalid token payload")
        
        # 查询管理员
        result = await db.execute(
            select(AdminUser).where(
                AdminUser.id == admin_id,
                AdminUser.status == "active"
            )
        )
        admin = result.scalar_one_or_none()
        
        if not admin:
            raise AuthenticationError("Admin not found or inactive")
        
        
        return admin

