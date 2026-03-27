"""
VOS（如 VOS3000）可选 HTTP 探测：用于管理端展示是否已配置对接地址。

说明：各厂商/版本 VOS 管理接口不统一，外呼出局以 voice_routes 中
gateway_type=vos + vos_gateway_name + trunk_profile 为准，由外呼网关
（VOICE_GATEWAY_BASE_URL）消费 originate 载荷中的 voice_route 字段。
"""
from __future__ import annotations

from typing import Any, Dict, Tuple, Optional
import time
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

class VOSClient:
    """
    VOS3000 API 客户端实现 (符合 VoiceProvider 抽象)
    由于各版本 VOS 接口不同，此处提供通用的 HTTP JSON 封装
    若无真实配置，回退为模拟返回。
    """
    def __init__(self):
        self.base_url = (getattr(settings, "VOS_HTTP_BASE", None) or "").strip()
        self.username = (getattr(settings, "VOS_HTTP_USERNAME", None) or "").strip()
        self.password = getattr(settings, "VOS_HTTP_PASSWORD", None) or ""
        self.verify_ssl = bool(getattr(settings, "VOS_HTTP_VERIFY_SSL", True))

    async def _request(self, endpoint: str, payload: dict) -> dict:
        if not self.base_url:
            return {"success": False, "message": "VOS_HTTP_BASE 未配置"}
        
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        auth = (self.username, self.password) if self.username else None
        
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl) as client:
                r = await client.post(url, json=payload, auth=auth)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.error(f"VOS API 请求失败: {endpoint} -> {e}")
            return {"success": False, "message": str(e)}

    async def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建 VOS 话机/账户"""
        result = await self._request("api/account/create", data)
        if not result.get("success"):
            if not self.base_url:
                # 模拟返回
                ext = f"VOS_{int(time.time())}"
                name = (data.get("account_name") or "user").replace(" ", "_")[:30]
                return {
                    "success": True,
                    "data": {
                        "external_id": ext,
                        "account": f"vos_{name}",
                        "password": f"pwd_{ext}",
                        "status": "active"
                    }
                }
        return result

    async def sync_status(self, external_id: str) -> Dict[str, Any]:
        """获取 VOS 账户余额与状态"""
        result = await self._request("api/account/sync", {"external_id": external_id})
        if not result.get("success"):
            if not self.base_url:
                # 模拟返回
                return {
                    "success": True,
                    "data": {
                        "status": "active",
                        "balance": 0.0,
                        "total_calls": 0,
                        "total_minutes": 0
                    }
                }
        return result

_vos_client: Optional[VOSClient] = None

def get_vos_client() -> VOSClient:
    global _vos_client
    if _vos_client is None:
        _vos_client = VOSClient()
    return _vos_client
