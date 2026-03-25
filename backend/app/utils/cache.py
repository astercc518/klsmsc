"""
Redis缓存管理模块
"""
import json
import asyncio
from typing import Optional, Any, Callable, Dict
from functools import wraps
import redis.asyncio as redis
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 全局Redis连接池
_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """获取Redis客户端（单例模式）"""
    global _redis_client, _redis_pool
    
    if _redis_client is None:
        # 创建连接池
        _redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=False  # 使用bytes模式，手动处理JSON
        )
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        
        # 测试连接
        try:
            await _redis_client.ping()
            logger.info("✅ Redis连接成功")
        except Exception as e:
            logger.error(f"❌ Redis连接失败: {str(e)}")
            raise
    
    return _redis_client


async def close_redis():
    """关闭Redis连接"""
    global _redis_client, _redis_pool
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
    
    logger.info("Redis连接已关闭")


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self._redis = redis_client
        self._local_cache: Dict[str, Any] = {}  # 本地缓存（进程内）
    
    @property
    async def redis(self) -> redis.Redis:
        """获取Redis客户端"""
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis
    
    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值或None
        """
        try:
            # 先查本地缓存
            if key in self._local_cache:
                return self._local_cache[key]
            
            # 查Redis
            redis_client = await self.redis
            value = await redis_client.get(key)
            
            if value is None:
                return None
            
            # 反序列化
            try:
                decoded = json.loads(value.decode('utf-8'))
                # 存入本地缓存（短期）
                self._local_cache[key] = decoded
                return decoded
            except json.JSONDecodeError:
                # 如果不是JSON，直接返回字符串
                return value.decode('utf-8')
                
        except Exception as e:
            logger.warning(f"缓存获取失败: {key}, 错误: {str(e)}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），默认5分钟
        """
        try:
            redis_client = await self.redis
            
            # 序列化
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value, ensure_ascii=False).encode('utf-8')
            elif isinstance(value, str):
                serialized = value.encode('utf-8')
            else:
                serialized = json.dumps(value, ensure_ascii=False).encode('utf-8')
            
            # 存入Redis
            await redis_client.setex(key, ttl, serialized)
            
            # 存入本地缓存
            self._local_cache[key] = value
            
            logger.debug(f"缓存已设置: {key}, TTL: {ttl}s")
            
        except Exception as e:
            logger.warning(f"缓存设置失败: {key}, 错误: {str(e)}")
    
    async def delete(self, key: str):
        """删除缓存"""
        try:
            redis_client = await self.redis
            await redis_client.delete(key)
            
            # 删除本地缓存
            self._local_cache.pop(key, None)
            
            logger.debug(f"缓存已删除: {key}")
        except Exception as e:
            logger.warning(f"缓存删除失败: {key}, 错误: {str(e)}")
    
    async def delete_pattern(self, pattern: str):
        """
        删除匹配模式的缓存
        
        Args:
            pattern: 匹配模式，如 "route:*" 或 "price:1:*"
        """
        try:
            redis_client = await self.redis
            keys = await redis_client.keys(pattern)
            
            if keys:
                await redis_client.delete(*keys)
                logger.info(f"已删除 {len(keys)} 个匹配的缓存: {pattern}")
            
            # 清理本地缓存中匹配的键
            keys_to_delete = [k for k in self._local_cache.keys() if self._match_pattern(k, pattern)]
            for k in keys_to_delete:
                self._local_cache.pop(k, None)
                
        except Exception as e:
            logger.warning(f"批量删除缓存失败: {pattern}, 错误: {str(e)}")
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """简单的模式匹配（支持*通配符）"""
        import re
        regex = pattern.replace('*', '.*')
        return bool(re.match(regex, key))
    
    async def get_or_set(
        self,
        key: str,
        func: Callable,
        ttl: int = 300,
        *args,
        **kwargs
    ) -> Any:
        """
        获取或设置缓存（Cache-Aside模式）
        
        Args:
            key: 缓存键
            func: 获取数据的异步函数
            ttl: 过期时间（秒）
            *args, **kwargs: 传递给func的参数
            
        Returns:
            缓存值或函数返回值
        """
        # 先查缓存
        cached = await self.get(key)
        if cached is not None:
            logger.debug(f"缓存命中: {key}")
            return cached
        
        # 缓存未命中，调用函数
        logger.debug(f"缓存未命中: {key}, 调用函数获取")
        value = await func(*args, **kwargs)
        
        # 存入缓存
        if value is not None:
            await self.set(key, value, ttl)
        
        return value
    
    async def invalidate_route_cache(self, country_code: Optional[str] = None):
        """失效路由缓存（国码与ISO两种格式均会失效）"""
        if country_code:
            from app.utils.phone_utils import country_to_dial_code, dial_to_country_code
            codes = [country_code]
            if country_code.isdigit():
                codes.append(dial_to_country_code(country_code))
            else:
                codes.append(country_to_dial_code(country_code))
            for c in set(codes):
                await self.delete_pattern(f"route:{c}")
        else:
            await self.delete_pattern("route:*")
    
    async def invalidate_price_cache(
        self,
        channel_id: Optional[int] = None,
        country_code: Optional[str] = None
    ):
        """
        失效价格缓存。
        与 app.core.pricing.PricingEngine.get_price 键一致：
        price:{account_id}:{channel_id}:{country_code}:{mnc}
        """
        if channel_id is not None and country_code:
            await self.delete_pattern(f"price:*:{channel_id}:{country_code}:*")
        elif channel_id is not None:
            await self.delete_pattern(f"price:*:{channel_id}:*")
        elif country_code:
            # 第四段为国家/区号
            await self.delete_pattern(f"price:*:*:{country_code}:*")
        else:
            await self.delete_pattern("price:*")

    async def invalidate_price_cache_for_account(self, account_id: int):
        """
        按账户失效短信售价缓存。
        修改账户统一单价、通道绑定后必须调用，否则 Redis 中旧单价最长可残留 1 小时。
        """
        await self.delete_pattern(f"price:{account_id}:*")
    
    async def invalidate_balance_cache(self, account_id: Optional[int] = None):
        """失效余额缓存"""
        if account_id:
            await self.delete(f"account:{account_id}:balance")
        else:
            await self.delete_pattern("account:*:balance")
    
    async def warm_up(self):
        """缓存预热（可选）"""
        logger.info("开始缓存预热...")
        # TODO: 实现缓存预热逻辑
        # 例如：预加载常用国家的路由规则、价格信息等
        logger.info("缓存预热完成")


# 全局缓存管理器实例
_cache_manager: Optional[CacheManager] = None


async def get_cache_manager() -> CacheManager:
    """获取缓存管理器（单例模式）"""
    global _cache_manager
    
    if _cache_manager is None:
        _cache_manager = CacheManager()
    
    return _cache_manager


def cache_result(ttl: int = 300, key_prefix: str = ""):
    """
    缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 键前缀
        
    Usage:
        @cache_result(ttl=300, key_prefix="route")
        async def get_channels(country_code: str):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key_parts = [key_prefix] if key_prefix else []
            
            # 从参数生成键
            for arg in args:
                if isinstance(arg, (str, int, float)):
                    cache_key_parts.append(str(arg))
            
            for k, v in sorted(kwargs.items()):
                if isinstance(v, (str, int, float)):
                    cache_key_parts.append(f"{k}:{v}")
            
            cache_key = ":".join(cache_key_parts)
            
            # 获取缓存管理器
            cache_manager = await get_cache_manager()
            
            # 尝试从缓存获取
            cached = await cache_manager.get(cache_key)
            if cached is not None:
                return cached
            
            # 调用原函数
            result = await func(*args, **kwargs)
            
            # 存入缓存
            if result is not None:
                await cache_manager.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator
