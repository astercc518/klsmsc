"""安全策略读取：把 system_config 里的安全相关配置解析为带下限保护的整数。

键缺失 / 为 0 / 非法时回退到安全默认值（与前端 system_config_meta 的下限/惯例对齐）。
下限保护很关键：存量数据里这些键曾是 '0'，若直接采用会把锁定/密码策略意外关掉
或导致除零，故 <1 一律回退默认。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config_service import ConfigService

# 与前端 system_config_meta 的默认/惯例对齐
SECURITY_DEFAULTS = {
    "max_login_attempts": 5,
    "login_lock_minutes": 30,
    "password_min_length": 8,
    "api_rate_limit_per_minute": 1000,
    "jwt_token_expire_hours": 2,
}


async def get_int_policy(key: str, db: AsyncSession) -> int:
    """读取一个整数型安全策略；缺失/非法/<1 时回退默认。"""
    default = SECURITY_DEFAULTS.get(key, 0)
    raw = await ConfigService.get(key, db, default=default)
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return v if v >= 1 else default
