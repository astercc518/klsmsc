"""客户端 IP 机器/扫描器识别

返回 (is_bot, reason)。
reason 取值与 bot_ua 同步使用 snake_case，便于按规则名分类展示。

目前覆盖：
- Google 服务/扫描器段（Googlebot、Google Messages Link Preview、Gmail Link Safety
  Scanner、Google Transcoder 等）。这些 IP 段**不包含** GCP 客户托管段，
  误伤普通 GCP 上的真人用户的概率极低。
"""
from __future__ import annotations
import ipaddress
from typing import Tuple


# 已知 Google 服务/扫描器对外出口段（来源：Google 公开发布的 ASN15169 中
# 仅包含 search/messaging/safebrowsing 的子集，不含 GCP 客户租用段）。
# 维护提示：如需新增，参考 https://www.gstatic.com/ipranges/goog.json
# 但避免引入 GCP 客户段（如 35.0.0.0/8 大块），那会误伤普通服务器代理出口。
_GOOGLE_CIDRS_STR = (
    "64.233.160.0/19",
    "66.102.0.0/20",
    "66.249.64.0/19",     # Googlebot 公开段
    "72.14.192.0/18",
    "74.125.0.0/16",
    "108.177.0.0/17",
    "142.250.0.0/15",
    "172.217.0.0/16",
    "173.194.0.0/16",
    "209.85.128.0/17",
    "216.58.192.0/19",
    "216.239.32.0/19",
)

_GOOGLE_NETS = tuple(ipaddress.ip_network(c) for c in _GOOGLE_CIDRS_STR)

# Microsoft Outlook Safe Links / Bing / Defender 等链接预扫描出口段
# 来源：Microsoft 官方 published service tags 中 "Outlook" 与 "Defender" 子集
# （只取明确的扫描器段，不含 Azure 客户租用段）
_MICROSOFT_SCANNER_CIDRS_STR = (
    "40.92.0.0/15",          # Outlook ATP / Safe Links 出口
    "40.107.0.0/16",         # Office 365 邮件扫描
    "52.100.0.0/14",         # Office 365 / Defender ATP
    "104.47.0.0/17",         # Exchange Online Protection
)

_MICROSOFT_NETS = tuple(ipaddress.ip_network(c) for c in _MICROSOFT_SCANNER_CIDRS_STR)


def classify_client_ip(ip: str | None) -> Tuple[bool, str]:
    """判定来源 IP 是否为已知机器/扫描器。

    Returns:
        (is_bot, reason)。未命中时返回 (False, "")，由上层继续走 UA / 扇出判定。
    """
    if not ip:
        return False, ""
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False, ""
    for net in _GOOGLE_NETS:
        if addr in net:
            return True, "google_scanner"
    for net in _MICROSOFT_NETS:
        if addr in net:
            return True, "microsoft_scanner"
    return False, ""
