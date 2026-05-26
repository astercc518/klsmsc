"""User-Agent → 可读"设备 浏览器"标签（仅用于展示/导出）。

精神对齐前端 frontend/src/utils/userAgent.ts；不参与 bot 判定。bot 判定走
utils/bot_ua.py。两边保持一致：先识别已知 bot 关键词，再识别真人设备/浏览器，
都识别不出返回"未识别"。
"""
from __future__ import annotations
import re


_BOT_SIGS = (
    # (regex/substr 列表, 显示标签)
    ((r"\bgooglebot\b", "bingbot", "yandex", "duckduckbot", "applebot", "baiduspider"), "搜索引擎爬虫"),
    ((
        "facebookexternalhit", "facebot", "whatsapp", "telegrambot", "slackbot",
        "linkedinbot", "twitterbot", "discordbot", "skypeuripreview",
        "linebotwebhook", "line-bot", "linepreview",
        "viberurldownloader", "viber-url-", "viber url crawler", "viberbot",
        "wechat-bot", "wechatlink-", "kakaotalk-scrap", "embedly", "iframely",
    ), "IM 链接预览"),
    ((
        "antispam", "safebrowsing", "google-safety", "trustwave", "sophos",
        "symantec", "proofpoint", "forcepoint", "bluecoat", "mimecast",
        "barracuda", "messagelabs", "fortinet", "kaspersky", "avast", "mcafee",
        "linkpreview", "urlchecker", "phish", "scanner", "scanurl", "fetcher",
    ), "安全扫描器"),
    ((
        "curl/", "wget/", "python-requests", "python-urllib", "httpx/",
        "go-http-client", "java/", "okhttp", "apache-httpclient", "node-fetch",
        "axios/", "guzzlehttp", "aiohttp", "winhttp", "libwww-perl",
    ), "编程客户端"),
    (("headlesschrome", "phantomjs", "puppeteer", "playwright"), "无头浏览器"),
)


def format_device_browser(ua: str | None) -> str:
    """把原始 UA 翻译成简短的"设备 浏览器"标签。

    返回示例："iPhone Safari" / "Android Chrome" / "Mac Safari" /
    "搜索引擎爬虫" / "未识别" / "空 UA"
    """
    if not ua or len(ua.strip()) < 5:
        return "空 UA"
    s = ua.lower()

    # 1) 已知 bot：优先返回类别（与前端口径一致）
    for tokens, label in _BOT_SIGS:
        for tok in tokens:
            if tok.startswith(r"\b"):
                if re.search(tok, s):
                    return label
            elif tok in s:
                return label

    # 2) 设备
    device = ""
    if "iphone" in s:
        device = "iPhone"
    elif "ipad" in s:
        device = "iPad"
    elif "ipod" in s:
        device = "iPod"
    elif "openharmony" in s or "harmonyos" in s:
        device = "HarmonyOS"
    elif "android" in s:
        device = "Android"
    elif "windows nt" in s or "windows phone" in s:
        device = "Windows"
    elif "macintosh" in s or "mac os x" in s:
        device = "Mac"
    elif "cros" in s:
        device = "ChromeOS"
    elif "x11; linux" in s or "linux" in s:
        device = "Linux"

    # 3) 浏览器（特异性优先）
    browser = ""
    if "edg/" in s or "edga/" in s or "edgios/" in s:
        browser = "Edge"
    elif "opr/" in s or "opera" in s:
        browser = "Opera"
    elif "samsungbrowser" in s:
        browser = "Samsung"
    elif "miuibrowser" in s:
        browser = "MIUI"
    elif "huaweibrowser" in s:
        browser = "Huawei"
    elif "ucbrowser" in s:
        browser = "UC"
    elif "quark/" in s:
        browser = "Quark"
    elif "micromessenger" in s:
        browser = "WeChat"
    elif "qqbrowser" in s:
        browser = "QQ"
    elif re.search(r"\bline/[\d.]+", s):
        browser = "LINE"
    elif re.search(r"\bviber/[\d.]+", s):
        browser = "Viber"
    elif "kakaotalk" in s and "scrap" not in s:
        browser = "KakaoTalk"
    elif "crios/" in s:
        browser = "Chrome"
    elif "fxios/" in s or "firefox" in s:
        browser = "Firefox"
    elif "chrome/" in s:
        browser = "Chrome"
    elif "safari/" in s:
        browser = "Safari"

    if device and browser:
        return f"{device} {browser}"
    if device:
        return device
    if browser:
        return browser
    return "未识别"
