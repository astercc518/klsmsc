"""
VOS（如 VOS3000）可选 HTTP 探测：用于管理端展示是否已配置对接地址。

说明：各厂商/版本 VOS 管理接口不统一，外呼出局以 voice_routes 中
gateway_type=vos + vos_gateway_name + trunk_profile 为准，由外呼网关
（VOICE_GATEWAY_BASE_URL）消费 originate 载荷中的 voice_route 字段。
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def vos_http_reachable() -> Tuple[bool, str]:
    """若配置了 VOS_HTTP_BASE，尝试 GET 根路径探测连通性（不要求业务语义）。"""
    base = (getattr(settings, "VOS_HTTP_BASE", None) or "").strip()
    if not base:
        return False, "未配置 VOS_HTTP_BASE"

    url = base.rstrip("/") + "/"
    auth = None
    u = (getattr(settings, "VOS_HTTP_USERNAME", None) or "").strip()
    p = getattr(settings, "VOS_HTTP_PASSWORD", None) or ""
    if u:
        auth = (u, p)

    verify = bool(getattr(settings, "VOS_HTTP_VERIFY_SSL", True))
    try:
        async with httpx.AsyncClient(timeout=8.0, verify=verify) as client:
            r = await client.get(url, auth=auth)
            if r.status_code < 500:
                return True, f"HTTP {r.status_code}"
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        logger.warning("VOS HTTP 探测失败: %s", e)
        return False, str(e)


def vos_settings_summary() -> Dict[str, Any]:
    """脱敏后的配置摘要（供管理端展示）。"""
    base = (getattr(settings, "VOS_HTTP_BASE", None) or "").strip()
    user = (getattr(settings, "VOS_HTTP_USERNAME", None) or "").strip()
    return {
        "vos_http_base_configured": bool(base),
        "vos_http_username_set": bool(user),
    }
