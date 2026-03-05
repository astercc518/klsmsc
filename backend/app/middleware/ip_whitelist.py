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
        self.skip_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/"
        }
    
    async def dispatch(self, request: Request, call_next):
        # 跳过不需要IP验证的路径
        if request.url.path in self.skip_paths:
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
            is_allowed = await self._check_ip_whitelist(api_key, client_ip)
        except Exception as e:
            logger.error(f"IP白名单验证异常: {str(e)}")
            is_allowed = True  # 降级策略：验证异常时允许访问

        if not is_allowed:
            logger.warning(
                f"IP白名单验证失败: api_key={api_key[:10]}..., "
                f"IP={client_ip}, "
                f"路径={request.url.path}"
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
        """
        获取客户端真实IP地址
        
        优先从X-Forwarded-For或X-Real-IP获取（代理场景）
        """
        # P2-FIX: 仅在信任代理环境下取 X-Forwarded-For
        # Nginx 已在最外层，取最后一个由 Nginx 追加的 IP（倒数第一个）
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            parts = [p.strip() for p in forwarded_for.split(",")]
            client_ip = parts[0] if len(parts) == 1 else parts[-1]
            if self._is_valid_ip(client_ip):
                return client_ip
        
        # 检查X-Real-IP头
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and self._is_valid_ip(real_ip):
            return real_ip
        
        # 使用直接连接的IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _is_valid_ip(self, ip: str) -> bool:
        """验证IP地址格式"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    async def _check_ip_whitelist(self, api_key: str, client_ip: str) -> bool:
        """
        检查IP是否在白名单中
        
        Args:
            api_key: API密钥
            client_ip: 客户端IP
            
        Returns:
            True if allowed, False otherwise
        """
        try:
            # 先查缓存
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
                        return False  # 账户不存在，拒绝访问
                    
                    # 解析IP白名单
                    if account.ip_whitelist:
                        try:
                            whitelist = json.loads(account.ip_whitelist)
                        except json.JSONDecodeError:
                            # 如果不是JSON，尝试按行分割
                            whitelist = [ip.strip() for ip in account.ip_whitelist.split("\n") if ip.strip()]
                    else:
                        whitelist = []
                    
                    # 存入缓存（5分钟TTL）
                    await cache_manager.set(cache_key, whitelist, ttl=300)
            
            # 如果白名单为空，允许所有IP（未配置白名单）
            if not whitelist:
                return True
            
            # 检查IP是否在白名单中
            return self._is_ip_in_whitelist(client_ip, whitelist)
            
        except Exception as e:
            logger.error(f"检查IP白名单失败: {str(e)}", exc_info=e)
            # 出错时允许访问（降级策略）
            return True
    
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
