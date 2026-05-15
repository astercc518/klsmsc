"""
IP白名单中间件
"""
import json
import ipaddress
from typing import List, Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.utils.logger import get_logger
from app.utils.cache import get_cache_manager
from app.modules.common.account import Account
from app.database import AsyncSessionLocal
from sqlalchemy import select

logger = get_logger(__name__)


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """IP白名单中间件"""
    
    def __init__(self, app):
        super().__init__(app)
        # 完全跳过白名单的精确路径
        self.skip_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/",
        }
        # 鉴权入口：登录/注册/刷新/找回。这些路径必须始终可达，
        # 不能让浏览器 localStorage 里残留的旧 X-API-Key 把当事用户挡在门外。
        # 之前未跳过 → 老 api_key 指向已删除账户时，登录请求被白名单中间件
        # 误判，前端反复弹「IP 不在白名单」。
        self.auth_path_prefixes = (
            "/api/v1/account/login",
            "/api/v1/account/register",
            "/api/v1/account/forgot-password",
            "/api/v1/account/reset-password",
            "/api/v1/account/telegram/",  # 子路径全跳：send-code / verify
            "/api/v1/admin/login",
            "/api/v1/admin/auth/refresh",
        )

    async def dispatch(self, request: Request, call_next):
        # 跳过不需要IP验证的路径
        path = request.url.path
        if (
            path in self.skip_paths
            or path.startswith("/s/")
            or path.startswith(self.auth_path_prefixes)
        ):
            return await call_next(request)

        # 获取API Key
        # 注意：Authorization Bearer 既可能是 API Key，也可能是管理员 JWT。
        # 这里仅将形如 `ak_...` 的 Bearer 视为 API Key，避免把 JWT 误当作 API Key 导致误拦截。
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                bearer_token = auth_header.replace("Bearer ", "").strip()
                if bearer_token.startswith("ak_"):
                    api_key = bearer_token

        # 如果没有API Key，跳过IP验证（可能是公开接口）
        if not api_key:
            return await call_next(request)

        # 获取客户端IP
        client_ip = self._get_client_ip(request)

        try:
            check = await self._check_ip_whitelist(api_key, client_ip)
        except Exception as e:
            logger.error(f"IP白名单验证异常: {str(e)}")
            check = ("allow", None)  # 降级策略：验证异常时允许访问

        verdict, reason = check
        if verdict != "allow":
            # 区分两种失败原因：账户不存在/已禁用 vs IP 真的不在白名单
            # 错误信息分别返回，前端按 code 决定是否清 localStorage 重登录
            if reason == "account_invalid":
                logger.warning(
                    f"鉴权失败-账户不存在或已禁用: api_key={api_key[:10]}..., 路径={path}"
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "success": False,
                        "error": {
                            "code": "ACCOUNT_INVALID",
                            "message": "账户不存在或已禁用，请重新登录",
                            "details": {}
                        }
                    }
                )
            logger.warning(
                f"IP白名单验证失败: api_key={api_key[:10]}..., "
                f"IP={client_ip}, 路径={path}"
            )
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {
                        "code": "IP_NOT_WHITELISTED",
                        "message": f"IP address {client_ip} is not in whitelist",
                        "details": {}
                    }
                }
            )

        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """获取客户端真实IP（统一走 utils/client_ip.get_client_ip，仅信任已知代理）"""
        from app.utils.client_ip import get_client_ip
        return get_client_ip(request)
    
    def _is_valid_ip(self, ip: str) -> bool:
        """验证IP地址格式"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    async def _check_ip_whitelist(self, api_key: str, client_ip: str):
        """
        检查 api_key 对应账户的 IP 白名单。

        返回 (verdict, reason)：
            ("allow", None)              通过
            ("deny", "account_invalid")  api_key 找不到 active 且未删除的账户
            ("deny", "ip_not_in_list")   账户存在、白名单非空、IP 不在其中

        缓存层把"账户不存在"也缓存成 ['__INVALID__']，避免恶意循环对 DB 造成压力。
        """
        try:
            cache_manager = await get_cache_manager()
            cache_key = f"account:whitelist:{api_key}"
            cached_whitelist = await cache_manager.get(cache_key)

            if cached_whitelist is not None:
                whitelist = cached_whitelist
            else:
                # 缓存未命中，从数据库查询
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Account).where(
                            Account.api_key == api_key,
                            Account.status == 'active',
                            Account.is_deleted == False
                        )
                    )
                    account = result.scalar_one_or_none()

                    if not account:
                        # 用 sentinel 把"账户失效"短期缓存（5min），减少 DB 反复查找
                        await cache_manager.set(cache_key, ["__INVALID__"], ttl=300)
                        return ("deny", "account_invalid")

                    # 解析IP白名单
                    if account.ip_whitelist:
                        try:
                            whitelist = json.loads(account.ip_whitelist)
                        except json.JSONDecodeError:
                            whitelist = [ip.strip() for ip in account.ip_whitelist.split("\n") if ip.strip()]
                    else:
                        whitelist = []

                    await cache_manager.set(cache_key, whitelist, ttl=300)

            # 缓存命中的"账户失效"sentinel
            if whitelist == ["__INVALID__"]:
                return ("deny", "account_invalid")

            # 白名单为空 → 未配置 → 放行
            if not whitelist:
                return ("allow", None)

            if self._is_ip_in_whitelist(client_ip, whitelist):
                return ("allow", None)
            return ("deny", "ip_not_in_list")

        except Exception as e:
            logger.error(f"检查IP白名单失败: {str(e)}", exc_info=e)
            # 出错时允许访问（降级策略）
            return ("allow", None)
    
    def _is_ip_in_whitelist(self, ip: str, whitelist: List[str]) -> bool:
        """
        检查IP是否在白名单中（支持CIDR格式）
        
        Args:
            ip: 要检查的IP地址
            whitelist: 白名单列表（支持IP和CIDR格式）
            
        Returns:
            True if IP is in whitelist
        """
        try:
            client_ip_obj = ipaddress.ip_address(ip)
            
            for whitelist_entry in whitelist:
                whitelist_entry = whitelist_entry.strip()
                if not whitelist_entry:
                    continue
                
                try:
                    # 尝试作为CIDR网络解析
                    if '/' in whitelist_entry:
                        network = ipaddress.ip_network(whitelist_entry, strict=False)
                        if client_ip_obj in network:
                            return True
                    else:
                        # 作为单个IP解析
                        whitelist_ip = ipaddress.ip_address(whitelist_entry)
                        if client_ip_obj == whitelist_ip:
                            return True
                except ValueError:
                    # 无效的IP或CIDR格式，跳过
                    logger.warning(f"无效的白名单条目: {whitelist_entry}")
                    continue
            
            return False
            
        except ValueError:
            logger.warning(f"无效的客户端IP: {ip}")
            return False
