"""
软件授权(License)核心 —— Ed25519 签名 + 机器指纹硬绑定,纯离线可验证。

设计:
- 公钥内嵌在此(下方 _DEFAULT_PUBLIC_KEY_B64,可被 settings.LICENSE_PUBLIC_KEY 覆盖)。
  私钥由厂商离线保管,用 scripts/license_issue.py 签发 .lic。
- .lic = base64( JSON{"payload": {...}, "sig": base64(ed25519签名)} )。
  签名覆盖 payload 的规范化 JSON(sort_keys, 紧凑分隔符)。
- payload 字段:
    license_id, customer, edition(saas|private|oem),
    issued_at(ISO), expires_at(ISO 或 null=永久),
    machine_fingerprint(空串=不绑定,如 SaaS),
    grace_days(到期后宽限,默认0=立即停),
    brand({name, logo} 可选,OEM 白标用),
    limits(预留,本期不强制), nonce
- 验证三关:签名未篡改 → 未过期(含 grace) → 指纹匹配本机。
- 失效即「全停」:发送类端点/worker 拒绝;后台仍可登录看横幅与上传新证。

机器指纹:取宿主 /etc/machine-id(docker 需挂 /etc/machine-id:/etc/host-machine-id:ro)
哈希得到,稳定且唯一标识一台部署机。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import date, datetime
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.utils.logger import logger

# 内嵌公钥(base64 raw 32字节)。私钥离线保管,切勿入库。
_DEFAULT_PUBLIC_KEY_B64 = "sZOZvs9q57Um1ToUhMjxXWbOTTcA7y2rmvtsog13Hac="

# 状态常量
STATE_VALID = "valid"          # 有效
STATE_GRACE = "grace"          # 已过期但在宽限期内(仍可用,前端黄条)
STATE_MISSING = "missing"      # 未安装 license
STATE_INVALID = "invalid"      # 签名非法/格式损坏/被篡改
STATE_EXPIRED = "expired"      # 过期(超出宽限)
STATE_WRONG_MACHINE = "wrong_machine"  # 指纹不匹配(换机/盗用)

# 允许发送的状态(其余一律全停)
_SEND_OK_STATES = {STATE_VALID, STATE_GRACE}

# system_config 中存放 license 的 key
CONFIG_KEY_LICENSE = "license.blob"

# 状态缓存(进程内,短 TTL,避免每请求重复验签)
_CACHE_TTL = 60.0
_cache: Dict[str, Any] = {"at": 0.0, "status": None}


def _settings():
    try:
        from app.config import settings
        return settings
    except Exception:
        return None


def _public_key() -> Ed25519PublicKey:
    s = _settings()
    b64 = getattr(s, "LICENSE_PUBLIC_KEY", None) or _DEFAULT_PUBLIC_KEY_B64
    raw = base64.b64decode(b64)
    return Ed25519PublicKey.from_public_bytes(raw)


def _machine_id_path() -> str:
    s = _settings()
    return getattr(s, "LICENSE_MACHINE_ID_FILE", None) or "/etc/host-machine-id"


def compute_fingerprint() -> str:
    """
    计算本机指纹:优先读挂载进来的宿主 /etc/machine-id,回退容器 /etc/machine-id。
    返回 'fp_' + sha256 前 24 hex。读不到任何稳定标识时返回 'fp_unknown'。
    """
    raw = None
    for p in (_machine_id_path(), "/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            if p and os.path.exists(p):
                with open(p, "r") as f:
                    v = f.read().strip()
                if v:
                    raw = v
                    break
        except Exception:
            continue
    if not raw:
        return "fp_unknown"
    digest = hashlib.sha256(("kaolach-license:" + raw).encode()).hexdigest()
    return "fp_" + digest[:24]


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _parse_date(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "")).date()
    except Exception:
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:
            return None


def verify_blob(blob: Optional[str], fingerprint: Optional[str] = None) -> Dict[str, Any]:
    """
    验证一段 .lic 文本,返回状态 dict(不依赖 DB,便于工具/测试复用)。
    返回:{state, valid_for_send, edition, customer, expires_at, days_left, brand, message}
    """
    base = {
        "state": STATE_MISSING, "valid_for_send": False, "edition": None,
        "customer": None, "expires_at": None, "days_left": None,
        "brand": None, "message": "未安装授权",
    }
    if not blob or not str(blob).strip():
        return base

    # 解码 + 验签
    try:
        outer = json.loads(base64.b64decode(str(blob).strip()))
        payload = outer["payload"]
        sig = base64.b64decode(outer["sig"])
        _public_key().verify(sig, _canonical(payload))
    except (InvalidSignature,) :
        return {**base, "state": STATE_INVALID, "message": "授权签名非法(可能被篡改或非本厂签发)"}
    except Exception:
        return {**base, "state": STATE_INVALID, "message": "授权文件损坏或格式不正确"}

    edition = payload.get("edition")
    customer = payload.get("customer")
    brand = payload.get("brand") or None
    expires_at = payload.get("expires_at")
    grace_days = int(payload.get("grace_days") or 0)
    bound_fp = (payload.get("machine_fingerprint") or "").strip()

    info = {
        "state": STATE_VALID, "valid_for_send": True, "edition": edition,
        "customer": customer, "expires_at": expires_at, "days_left": None,
        "brand": brand, "message": "授权有效",
    }

    # 指纹绑定校验(空串=不绑定,如 SaaS)
    if bound_fp:
        cur = fingerprint or compute_fingerprint()
        if cur != bound_fp:
            return {**info, "state": STATE_WRONG_MACHINE, "valid_for_send": False,
                    "message": "授权与本机器指纹不匹配(疑似换机或盗用)"}

    # 到期校验(永久买断 expires_at=null 跳过)
    exp = _parse_date(expires_at)
    if exp is not None:
        today = date.today()
        days_left = (exp - today).days
        info["days_left"] = days_left
        if days_left < 0:
            if -days_left <= grace_days:
                return {**info, "state": STATE_GRACE, "valid_for_send": True,
                        "message": f"授权已过期,宽限期内({grace_days + days_left}天后停用)"}
            return {**info, "state": STATE_EXPIRED, "valid_for_send": False,
                    "message": "授权已过期,发送已停用"}
    return info


async def get_license_status(db, *, use_cache: bool = True) -> Dict[str, Any]:
    """读取已安装 license 并返回状态(带短 TTL 缓存)。"""
    now = time.monotonic()
    if use_cache and _cache["status"] is not None and (now - _cache["at"]) < _CACHE_TTL:
        return _cache["status"]

    blob = None
    try:
        from app.services.config_service import ConfigService
        blob = await ConfigService.get(CONFIG_KEY_LICENSE, db, default=None)
    except Exception as e:
        logger.warning(f"读取 license 配置失败: {e}")

    # 回退:环境变量指定的 .lic 文件
    if not blob:
        s = _settings()
        path = getattr(s, "LICENSE_FILE", None)
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    blob = f.read().strip()
            except Exception:
                pass

    status = verify_blob(blob)
    status["fingerprint"] = compute_fingerprint()
    status["licensed"] = status["state"] != STATE_MISSING

    # 未安装授权:默认宽松放行(避免未发证即把自家系统锁死);
    # 分发给客户的私有/OEM 版应设 LICENSE_REQUIRE=1,使未装证也全停(防裸跑盗用)。
    s = _settings()
    if status["state"] == STATE_MISSING and not bool(getattr(s, "LICENSE_REQUIRE", False)):
        status["valid_for_send"] = True
        status["message"] = "未安装授权(宽松模式放行;分发版请设 LICENSE_REQUIRE=1 强制)"

    _cache["status"] = status
    _cache["at"] = now
    return status


def invalidate_cache() -> None:
    _cache["status"] = None
    _cache["at"] = 0.0


async def require_valid_license(db=None) -> Dict[str, Any]:
    """
    FastAPI 依赖:授权无效则全停(403)。挂在发送类端点上。
    用法: license=Depends(require_valid_license)
    """
    from fastapi import HTTPException, Depends  # noqa
    if db is None:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as _db:
            status = await get_license_status(_db)
    else:
        status = await get_license_status(db)
    if not status.get("valid_for_send"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "LICENSE_" + str(status.get("state", "invalid")).upper(),
                "message": status.get("message") or "软件授权无效,发送功能已停用,请联系供应商",
            },
        )
    return status
