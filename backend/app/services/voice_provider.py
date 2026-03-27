"""
语音平台抽象：OKCC 与自建（self_hosted）可切换。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from app.config import settings
from app.services.okcc_client import OKCCClient, get_okcc_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


@runtime_checkable
class VoiceProvider(Protocol):
    """语音平台统一接口"""

    async def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建子账户，返回 success、data{account,password,external_id}"""

    async def sync_status(self, external_id: str) -> Dict[str, Any]:
        """同步余额与统计"""


class SelfHostedVoiceProvider:
    """自建栈：无 HTTP 网关时返回可本地开户的占位数据，便于联调。"""

    async def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        import time

        ext = f"VH_{int(time.time())}"
        name = (data.get("account_name") or "user").replace(" ", "_")[:40]
        sip_user = f"sip_{name}"
        pwd = f"vh_{int(time.time()) % 100000:05d}"
        return {
            "success": True,
            "data": {
                "external_id": ext,
                "account": sip_user,
                "password": pwd,
                "status": "active",
            },
        }

    async def sync_status(self, external_id: str) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "status": "active",
                "balance": 0.0,
                "total_calls": 0,
                "total_minutes": 0,
            },
        }


def get_voice_provider() -> VoiceProvider:
    """根据 VOICE_PROVIDER 返回实现。"""
    provider_name = settings.VOICE_PROVIDER.lower()
    if provider_name == "okcc":
        return get_okcc_client()  # type: ignore[return-value]
    elif provider_name == "vos":
        from app.services.vos_client import get_vos_client
        return get_vos_client()  # type: ignore[return-value]
    return SelfHostedVoiceProvider()
