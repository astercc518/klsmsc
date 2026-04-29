"""
代理 IP 管理器：从数据库读取代理配置，返回 Playwright 兼容的代理参数
"""
from typing import Optional, Dict
from app.utils.logger import get_logger

logger = get_logger(__name__)


def parse_proxy_endpoint(endpoint: str, country_code: str = "", country_auto: bool = False) -> Dict:
    """
    解析代理地址，返回 Playwright 格式的 proxy 配置。
    支持 {country} 占位符自动替换。

    Args:
        endpoint: 代理地址，如 http://user:pass@host:port
        country_code: 目标国家代码（用于替换占位符）
        country_auto: 是否启用占位符替换

    Returns:
        Playwright proxy dict: {"server": "...", "username": "...", "password": "..."}
    """
    if country_auto and country_code and '{country}' in endpoint:
        endpoint = endpoint.replace('{country}', country_code.lower())

    from urllib.parse import urlparse
    parsed = urlparse(endpoint)

    result = {"server": f"{parsed.scheme}://{parsed.hostname}"}
    if parsed.port:
        result["server"] += f":{parsed.port}"
    if parsed.username:
        result["username"] = parsed.username
    if parsed.password:
        result["password"] = parsed.password

    return result


async def get_proxy_for_country(db, country_code: str, proxy_id: Optional[int] = None) -> Optional[Dict]:
    """
    从数据库获取适合目标国家的代理配置。

    优先级：
    1. 指定 proxy_id
    2. 匹配 country_code 的活跃代理
    3. 通用（country_code='*'）的活跃代理

    Returns:
        Playwright proxy dict 或 None
    """
    from sqlalchemy import select
    from app.modules.water.models import WaterProxy

    proxy = None

    if proxy_id:
        result = await db.execute(
            select(WaterProxy).where(WaterProxy.id == proxy_id, WaterProxy.status == 'active')
        )
        proxy = result.scalar_one_or_none()

    if not proxy and country_code:
        result = await db.execute(
            select(WaterProxy).where(
                WaterProxy.country_code == country_code,
                WaterProxy.status == 'active'
            ).limit(1)
        )
        proxy = result.scalar_one_or_none()

    if not proxy:
        result = await db.execute(
            select(WaterProxy).where(
                WaterProxy.country_code == '*',
                WaterProxy.status == 'active'
            ).limit(1)
        )
        proxy = result.scalar_one_or_none()

    if not proxy:
        logger.warning(f"未找到可用代理: country={country_code}, proxy_id={proxy_id}")
        return None

    return parse_proxy_endpoint(proxy.endpoint, country_code, proxy.country_auto)


async def test_proxy_connectivity(endpoint: str, country_code: str = "", country_auto: bool = False) -> Dict:
    """
    测试代理连通性，通过代理访问 api.ipify.org 获取出口 IP。
    如果代理支持国家路由（country_auto=True），测试时使用指定国家。

    Returns:
        {"success": bool, "ip": str, "latency_ms": int, "error": str, "test_country": str}
    """
    import time
    import httpx

    test_country = country_code or ("th" if country_auto else "")
    proxy_config = parse_proxy_endpoint(endpoint, test_country, country_auto)
    proxy_url = proxy_config["server"]
    if proxy_config.get("username"):
        from urllib.parse import urlparse, quote
        p = urlparse(proxy_url)
        user = quote(proxy_config['username'], safe='')
        pwd = quote(proxy_config.get('password', ''), safe='')
        proxy_url = f"{p.scheme}://{user}:{pwd}@{p.hostname}:{p.port}"

    logger.info(f"测试代理: server={proxy_config['server']}, country={test_country}")

    start = time.time()
    try:
        async with httpx.AsyncClient(proxies={"all://": proxy_url}, timeout=20) as client:
            resp = await client.get("https://api.ipify.org?format=json")
            latency = int((time.time() - start) * 1000)
            data = resp.json()
            return {
                "success": True,
                "ip": data.get("ip", "unknown"),
                "latency_ms": latency,
                "error": None,
                "test_country": test_country,
            }
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return {
            "success": False,
            "ip": None,
            "latency_ms": latency,
            "error": str(e),
            "test_country": test_country,
        }
