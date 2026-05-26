"""User-Agent 机器/扫描器识别

返回 (is_bot, reason)。
reason 取值用 snake_case，便于前端按规则名分类展示。

判定策略（2026-05 重构）：**默认放行**，只有显式命中黑名单才判 bot。

历史教训：旧版用"已知真人白名单"做兜底（未命中即视为 bot, reason='unknown_ua'），
随 UA 演进会系统性误杀。例如 iOS 13+ Safari UA 变成
"Mobile/15E148 Safari/604.1"（中间隔 build 号），白名单里的 "mobile safari"
连续子串永远命中不到，导致全部 iPhone 被误杀。HarmonyOS NEXT、KaiOS、
未来 UA Reduction 演进都会以同样方式再次踩雷。

新策略：
- 显式 bot/CLI/预览器/扫描器关键词 → 判 bot（精确黑名单）
- 其余一律放行 → 由 IP 段名单（bot_ip.py）+ IP 扇出（webhook_worker.py）
  这两条机器特征更稳定的线兜底未知扫描器。

判定顺序（先判机器，命中即返回）：
1. UA 为空/过短         → empty_ua
2. 含编程库/CLI 关键字   → http_client
3. 含 IM/链接预览签名    → preview_bot
4. 含安全扫描器签名      → security_scanner
5. 含通用 bot/spider     → generic_bot
6. 其他                  → 放行（False, ""）
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
# 注意：以下几个 IM 的真人 App 内置浏览器 UA 与预览 bot UA 共享品牌词，
# 必须只列预览 bot 的特异签名，不能用品牌词裸子串：
#  - LINE：真人 IAB 形如 "Line/14.2.0/IAB"；预览 bot 形如 "LineBotWebhook"
#  - Viber：真人形如 "Viber/22.x"；预览 bot 形如 "ViberUrlDownloader" / "Viber URL Crawler"
#  - 微信：真人是 "MicroMessenger/..."；预览 bot 是 "WeChat-Bot" / "WeChatLink-"
# 历史教训：旧版列了裸 "line/" / "viber" / "wechat" 会把日/台/泰/菲的 IM
# 内置浏览器真人点击全部误杀。
_PREVIEW_BOT_TOKENS = (
    "facebookexternalhit", "facebot", "whatsapp", "telegrambot", "slackbot",
    "linkedinbot", "twitterbot", "discordbot", "skypeuripreview",
    "linebotwebhook", "line-bot", "linepreview",
    "viberurldownloader", "viber-url-", "viber url crawler", "viberbot",
    "wechat-bot", "wechatlink-",
    "kakaotalk-scrap",
    "googlebot", "bingbot", "yahoo! slurp", "duckduckbot", "yandex", "applebot",
    "embedly", "outbrain", "vkshare", "redditbot", "pinterest",
    "mattermost", "iframely",
)

# 已知反诈/反钓鱼/邮件安全扫描器
_SECURITY_SCANNER_TOKENS = (
    "safebrowsing", "google-safety", "trustwave", "sophos", "symantec",
    "proofpoint", "forcepoint", "bluecoat", "mimecast", "barracuda",
    "messagelabs", "fortinet", "kaspersky", "avast", "mcafee",
    "linkpreview", "urlchecker", "phish", "scanner", "scanurl", "fetcher",
    "antispam",  # 越南运营商反诈扫描器
)

# 通用 bot/spider/monitor 关键词
# 注：放在最后，前置类别命中后已 return，不会因 "googlebot" 含 "bot" 导致归类错。
_GENERIC_BOT_TOKENS = ("bot", "spider", "crawler", "spy", "monitor", "headless")


def classify_user_agent(ua: str | None) -> Tuple[bool, str]:
    """判定 UA 是否为机器/扫描器。

    Returns:
        (is_bot, reason)。命中黑名单时 reason 取规则名；未命中返回 (False, "")。
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

    return False, ""
