"""
统一获取客户端真实 IP，**仅信任来自已知代理的 X-Forwarded-For**。

历史问题：
  - 旧实现 `parts[-1]` 在单值 XFF 时返回客户端伪造值
  - 直连 API（绕过 Nginx）的攻击者可设任意 X-Forwarded-For 头
  - X-Real-IP 同理可被伪造

修复：
  - 仅当 request.client.host 在 TRUSTED_PROXY_CIDRS 时，才信任 XFF/X-Real-IP
  - Docker 网络的 nginx → api 是唯一可信路径
  - 默认信任 RFC1918 私网 + 127/8（Docker 网络通常 172.16-32/12）
  - 可通过 TRUSTED_PROXY_CIDRS 环境变量自定义（逗号分隔 CIDR）

Nginx 设置 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` 时，
XFF 末尾追加客户端真实 IP；可信代理路径 → 取 parts[-1]。
"""
import ipaddress
import os
from typing import List, Optional

from fastapi import Request


def _parse_cidrs(s: str) -> List[ipaddress._BaseNetwork]:
    out = []
    for tok in s.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(ipaddress.ip_network(tok, strict=False))
        except ValueError:
            pass
    return out


# 默认信任的代理 CIDR（Docker 内网 + 私网 + 本机）
_DEFAULT_TRUSTED = "172.16.0.0/12,192.168.0.0/16,10.0.0.0/8,127.0.0.0/8"
_TRUSTED_PROXIES: List[ipaddress._BaseNetwork] = _parse_cidrs(
    os.getenv("TRUSTED_PROXY_CIDRS", _DEFAULT_TRUSTED)
)


def _is_trusted_proxy(ip: str) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_PROXIES)


def _is_valid_ip(ip: Optional[str]) -> bool:
    if not ip:
        return False
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """
    返回客户端真实 IP。
    - request 直连 IP 不在 trusted_proxies 时：直接返回 request.client.host（忽略所有 XFF/X-Real-IP）
    - 直连 IP 是 trusted proxy 时：按 XFF 末尾 → X-Real-IP → 直连 IP 顺序
    """
    direct_ip = request.client.host if request.client else ""

    # 直连方不可信 → 不读任何 forwarding header
    if not _is_trusted_proxy(direct_ip):
        return direct_ip or "unknown"

    # 来自可信代理：先 XFF 末尾（nginx $proxy_add_x_forwarded_for 追加格式）
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts and _is_valid_ip(parts[-1]):
            return parts[-1]

    # 退化到 X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if _is_valid_ip(real_ip):
        return real_ip

    return direct_ip or "unknown"
