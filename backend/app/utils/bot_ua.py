"""User-Agent 机器/扫描器识别

返回 (is_bot, reason)。
reason 取值用 snake_case，便于前端按规则名分类展示。

规则按"先判定机器、再判定真人"的顺序执行：
1. UA 为空/过短         → empty_ua
2. 含编程库/CLI 关键字   → http_client
3. 含 IM/链接预览签名    → preview_bot
4. 含安全扫描器签名      → security_scanner
5. 含通用 bot/spider     → generic_bot
6. 命中常见手机浏览器签名 → 真人 (False, "")
7. 其他                  → unknown_ua（保守：默认机器）
"""
from __future__ import annotations
from typing import Tuple


# CLI / 编程库（爬虫、运营商扫描器最常见的签名）
_HTTP_CLIENT_TOKENS = (
    "curl/", "wget/", "python-requests", "python-urllib", "httpx/",
    "go-http-client", "java/", "okhttp", "apache-httpclient", "node-fetch",
    "axios/", "got (", "lwp::simple", "ruby", "guzzlehttp", "aiohttp",
    "winhttp", "libwww-perl",
)

# IM / 链接预览（短信里的 URL 一旦被聊天 App 转发就会触发）
_PREVIEW_BOT_TOKENS = (
    "facebookexternalhit", "facebot", "whatsapp", "telegrambot", "slackbot",
    "linkedinbot", "twitterbot", "discordbot", "skypeuripreview", "viber",
    "line/", "wechat", "kakaotalk-scrap", "googlebot", "bingbot",
    "yahoo! slurp", "duckduckbot", "yandex", "applebot", "embedly",
    "outbrain", "vkshare", "redditbot", "pinterest",
    "mattermost", "iframely",
)

# 已知反诈/反钓鱼/邮件安全扫描器
_SECURITY_SCANNER_TOKENS = (
    "safebrowsing", "google-safety", "trustwave", "sophos", "symantec",
    "proofpoint", "forcepoint", "bluecoat", "mimecast", "barracuda",
    "messagelabs", "fortinet", "kaspersky", "avast", "mcafee",
    "linkpreview", "urlchecker", "phish", "scanner", "scanurl", "fetcher",
)

_GENERIC_BOT_TOKENS = ("bot", "spider", "crawler", "spy", "monitor")

# 真人签名（覆盖移动端 + 主流桌面浏览器；命中即视为人）
_HUMAN_TOKENS = (
    "mobile safari", "chrome mobile", "crios/", "fxios/", "edga/",
    "samsungbrowser", "miuibrowser", "huaweibrowser", "ucbrowser",
    "opera mobi", "opr/",
    # 桌面浏览器（运营商扫描器一般不带这些组合签名）
    "windows nt", "macintosh", "x11; linux",
)


def classify_user_agent(ua: str | None) -> Tuple[bool, str]:
    """判定 UA 是否为机器/扫描器。

    Returns:
        (is_bot, reason)。is_bot=False 时 reason="" 。
    """
    if not ua or len(ua.strip()) < 5:
        return True, "empty_ua"
    s = ua.lower()

    for tok in _HTTP_CLIENT_TOKENS:
        if tok in s:
            return True, "http_client"
    for tok in _PREVIEW_BOT_TOKENS:
        if tok in s:
            return True, "preview_bot"
    for tok in _SECURITY_SCANNER_TOKENS:
        if tok in s:
            return True, "security_scanner"
    for tok in _GENERIC_BOT_TOKENS:
        if tok in s:
            return True, "generic_bot"

    for tok in _HUMAN_TOKENS:
        if tok in s:
            return False, ""

    # 既不像主流浏览器也不像已知 bot，保守视为机器（避免漏判扫描器）
    return True, "unknown_ua"
