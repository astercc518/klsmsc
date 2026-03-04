"""
API限流中间件
"""
import time
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.utils.cache import get_redis_client
from app.utils.logger import get_logger
from app.config import settings
from datetime import datetime

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """API限流中间件"""
    
    def __init__(self, app, default_limit: int = None):
        super().__init__(app)
        self.default_limit = default_limit or settings.RATE_LIMIT_PER_MINUTE
        self.skip_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/"
        }
    
    async def dispatch(self, request: Request, call_next):
        # 跳过不需要限流的路径
        if request.url.path in self.skip_paths:
            return await call_next(request)
        
        # 获取API Key
        # 注意：Authorization Bearer 既可能是 API Key，也可能是管理员 JWT。
        # 这里仅将形如 `ak_...` 的 Bearer 视为 API Key，避免把 JWT 误当作 API Key 导致误限流/异常。
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                bearer_token = auth_header.replace("Bearer ", "").strip()
                if bearer_token.startswith("ak_"):
                    api_key = bearer_token
        
        # 如果没有API Key，跳过限流（可能是公开接口）
        if not api_key:
            return await call_next(request)
        
        # 获取客户端IP
        client_ip = request.client.host if request.client else "unknown"
        
        try:
            # 检查限流
            redis_client = await get_redis_client()
            
            # 生成限流键（按分钟）
            current_minute = datetime.now().strftime("%Y%m%d%H%M")
            limit_key = f"ratelimit:{api_key}:{current_minute}"
            
            # 增加计数
            current = await redis_client.incr(limit_key.encode())
            
            # 第一次设置过期时间（60秒）
            if current == 1:
                await redis_client.expire(limit_key.encode(), 60)
            
            # 获取账户限流配置（从缓存）
            account_limit = await self._get_account_limit(api_key, redis_client)
            if account_limit is None:
                account_limit = self.default_limit
            
            # 检查是否超限
            if current > account_limit:
                logger.warning(
                    f"API限流触发: api_key={api_key[:10]}..., "
                    f"IP={client_ip}, "
                    f"当前={current}, "
                    f"限制={account_limit}, "
                    f"路径={request.url.path}"
                )
                
                # BaseHTTPMiddleware 中直接 raise HTTPException 会导致 Starlette 异常传播问题，
                # 这里改为直接返回响应，避免前端看到 500。
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit exceeded: {account_limit} requests per minute",
                            "details": {}
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(account_limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + 60),
                        "Retry-After": "60"
                    }
                )
            
            # 调用下一个中间件
            response = await call_next(request)
            
            # 添加限流响应头
            response.headers["X-RateLimit-Limit"] = str(account_limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, account_limit - current))
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
            
            return response
            
        except Exception as e:
            # 如果限流检查失败，记录日志但继续处理请求（降级策略）
            logger.error(f"限流检查异常: {str(e)}", exc_info=e)
            return await call_next(request)
    
    async def _get_account_limit(self, api_key: str, redis_client) -> Optional[int]:
        """
        从缓存或数据库获取账户限流配置
        
        Args:
            api_key: API密钥
            redis_client: Redis客户端
            
        Returns:
            限流配置或None（使用默认值）
        """
        try:
            # 先查缓存
            cache_key = f"account:limit:{api_key}"
            cached = await redis_client.get(cache_key.encode())
            
            if cached:
                limit = int(cached.decode())
                logger.debug(f"账户限流配置缓存命中: api_key={api_key[:10]}..., limit={limit}")
                return limit
            
            # 缓存未命中，从数据库查询
            # 注意：这里需要数据库连接，但中间件中不应该直接访问数据库
            # 更好的做法是在AuthService中缓存账户信息
            # 为了简化，这里先返回None使用默认值
            # 实际生产环境应该：
            # 1. 在AuthService.verify_api_key中缓存账户信息（包括rate_limit）
            # 2. 或者使用依赖注入获取账户信息
            
            return None
            
        except Exception as e:
            logger.warning(f"获取账户限流配置失败: {str(e)}")
            return None
