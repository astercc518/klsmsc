"""
短信文本 URL 提取工具
"""
import re
from typing import List

# 匹配 HTTP/HTTPS 链接的正则
_URL_PATTERN = re.compile(
    r'https?://[^\s<>"\'，。！？、；：）】}\]]+',
    re.IGNORECASE
)

# 常见短链域名（用于无协议前缀匹配和短链判断）
_SHORT_DOMAINS = {
    'bit.ly', 't.co', 'tinyurl.com', 'goo.gl', 'is.gd', 'v.gd',
    'ow.ly', 'rebrand.ly', 'cutt.ly', 'rb.gy', 'shorturl.at',
    'tiny.cc', 'bc.vc', 'lnk.to', 'surl.li', 'short.io',
    'did.li', 'jdykalnwl.icu', 'cutt.ly', 'bit.ly', 'shorturl.at',
}

# 匹配无协议前缀的短链域名（如 cutt.ly/htFIS3ZQ）
_BARE_SHORT_PATTERN = re.compile(
    r'(?<!\w)(?:' +
    '|'.join(re.escape(d) for d in sorted(_SHORT_DOMAINS, key=len, reverse=True)) +
    r')/[^\s<>"\'，。！？、；：）】}\]]+',
    re.IGNORECASE
)


def extract_urls(text: str) -> List[str]:
    """从短信文本中提取所有链接（含无协议前缀的短链），返回去重列表"""
    if not text:
        return []

    urls = _URL_PATTERN.findall(text)

    # 提取无协议前缀的可能域名（格式如 domain.tld/path）
    # 匹配规则：字母数字开头，包含点，跟随 2-6 位后缀，后面必须接 / 和路径字符
    _GENERIC_BARE_PATTERN = re.compile(
        r'(?<![a-zA-Z0-9])([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-z]{2,6}/[^\s<>"\'，。！？、；：）】}\]]+)',
        re.IGNORECASE
    )
    for m in _GENERIC_BARE_PATTERN.finditer(text):
        bare = m.group(1)
        # 排除包含连续点的（可能是版本号或IP片段）
        if '..' in bare:
            continue
        full = f"https://{bare}"
        if full not in urls:
            urls.append(full)

    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?)')
        if url and len(url) > 8: # 稍微放宽长度
            cleaned.append(url)
    return list(dict.fromkeys(cleaned))


def is_short_url(url: str) -> bool:
    """判断是否为短链"""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        return domain in _SHORT_DOMAINS
    except Exception:
        return False
