"""
URL 安全校验：用于「客户提供 URL，系统外联或重定向到」的所有场景。

两个公开函数：
  - validate_external_callback_url(url) — webhook 等系统主动 POST 的场景，
    严格：拒绝所有私网/回环/链路本地/保留段（防 SSRF）
  - validate_redirect_target_url(url)   — 短链等系统返回 302 Location 让浏览器跳的场景，
    宽松：允许公网域名/IP，但仍拒非 http(s) 协议 + 私网（防 javascript: 协议 / 内网钓鱼）

两者共用 scheme 白名单 + DNS 解析私网拒绝。
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Tuple
from urllib.parse import urlparse

_ALLOWED_SCHEMES = ("http", "https")


def _check_scheme_and_host(url: str) -> Tuple[bool, str, str]:
    """返回 (ok, reason, host)。"""
    if not url or not isinstance(url, str):
        return False, "URL 为空", ""
    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        return False, f"URL 解析失败: {e}", ""
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return False, f"仅允许 http/https 协议（当前: {scheme or '空'}）", ""
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "URL 缺少 host", ""
    return True, "", host


def _resolve_addresses(host: str) -> Tuple[bool, str, list]:
    """DNS 解析；返回 (ok, reason, [ip_string, ...])。"""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"DNS 解析失败: {e}", []
    addrs = []
    seen = set()
    for info in infos:
        a = info[4][0]
        if a in seen:
            continue
        seen.add(a)
        addrs.append(a)
    if not addrs:
        return False, "DNS 解析为空", []
    return True, "", addrs


def _addr_is_private(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_external_callback_url(url: str) -> Tuple[bool, str]:
    """SSRF 防护：webhook 等服务端主动外联场景。拒绝所有非公网地址。"""
    ok, reason, host = _check_scheme_and_host(url)
    if not ok:
        return False, reason
    ok, reason, addrs = _resolve_addresses(host)
    if not ok:
        return False, reason
    for a in addrs:
        if _addr_is_private(a):
            return False, f"URL 指向受限地址段: {a}"
    return True, ""


def validate_redirect_target_url(url: str) -> Tuple[bool, str]:
    """重定向目标校验：短链 302 Location 场景。

    与 callback 等价（也拒私网），但允许公网 IP literal（部分客户用 IP 而非域名）。
    若未来想放宽到允许公网 IP literal 但拒域名解析到私网，调整这里即可。
    """
    ok, reason, host = _check_scheme_and_host(url)
    if not ok:
        return False, reason
    # 主机若是 IP literal，直接判断是否私网
    try:
        ip = ipaddress.ip_address(host)
        if _addr_is_private(host):
            return False, f"URL 指向受限地址段: {host}"
        return True, ""
    except ValueError:
        pass
    # 域名 → DNS 解析后任一 IP 落私网即拒
    ok, reason, addrs = _resolve_addresses(host)
    if not ok:
        return False, reason
    for a in addrs:
        if _addr_is_private(a):
            return False, f"URL 解析到受限地址段: {host} -> {a}"
    return True, ""
