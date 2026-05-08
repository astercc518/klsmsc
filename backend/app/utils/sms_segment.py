"""
短信分段条数计算（GSM-7 / UCS-2），与前端 utils/smsParts 及运营展示对齐。

在判断编码前对正文做轻量规范化，避免 NBSP、零宽字符、弯引号等导致
「肉眼为英文」却整段被判为 UCS-2、条数虚高。

另：识别短链占位符 {{TRACK_URL=target|base}}，按实际发送时的短链长度计费，
避免「占位符 94 字符算 2 条 / 实发 70 字符 1 条」的多扣费问题。
"""
import re
import unicodedata
from typing import Final

_GSM7_CHARS: Final = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)


def normalize_for_sms_segment_count(text: str) -> str:
    """分段计费前的规范化（不改变用户存储的正文，仅用于条数与编码判断）。"""
    if not text:
        return text
    t = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    for c in t:
        if c == "\u00a0":
            out.append(" ")
        elif c in "\u200b\u200c\u200d\ufeff":
            continue
        elif c in "\u2018\u2019":
            out.append("'")
        elif c in "\u201c\u201d":
            out.append('"')
        elif c == "\u2013":
            out.append("-")
        elif c == "\u2014":
            out.append("-")
        elif c == "\u2026":
            out.append("...")
        else:
            out.append(c)
    return "".join(out)


def is_gsm7_message(message: str) -> bool:
    norm = normalize_for_sms_segment_count(message)
    return all(c in _GSM7_CHARS for c in norm)


# 短链占位符识别：{{TRACK_URL}}、{{TRACK_URL=target}}、{{TRACK_URL=target|base}}
_TRACK_URL_RE = re.compile(r"\{\{TRACK_URL(?:=([^}]*))?\}\}")
# 平均 token 长度（实际为 6-8 位 Base62，取 7 位）+ 1 位斜杠
_TRACK_TOKEN_OVERHEAD = 8


def substitute_track_url_for_count(message: str) -> str:
    """
    把 {{TRACK_URL=target|base}} 占位符替换为「实际发送形态」的字符串，仅用于分段/字符数计算。

    - 有 base：替换为 ``{base}/Ab3Xz7q``（base 取 placeholder 内的真实值）
    - 无 base：用兜底域名长度估算，与设置里 SHORT_LINK_BASE_URL 长度近似
    - 多个占位符：全部替换
    - 占位符内含特殊 SMS 字符（如 GSM-7 不支持的）会改变编码判定，与实际发送一致
    """
    if not message or "{{TRACK_URL" not in message:
        return message

    def _repl(m: 're.Match[str]') -> str:
        inner = m.group(1) or ""
        base = "klsms.com"
        if inner:
            parts = inner.split("|", 1)
            if len(parts) >= 2 and parts[1].strip():
                base = parts[1].strip()
        # 去掉两端可能出现的协议前缀（不影响字符数大头）和尾斜杠
        clean_base = base.rstrip("/")
        return f"{clean_base}/Ab3Xz7q"

    return _TRACK_URL_RE.sub(_repl, message)


def count_sms_parts(message: str) -> int:
    """与历史 PricingEngine._count_sms_parts 语义一致，增加规范化步骤。

    若文案含短链占位符 {{TRACK_URL=...}}，按实际短链长度计算（避免按占位符长度多扣费）。
    """
    if message and "{{TRACK_URL" in message:
        message = substitute_track_url_for_count(message)
    norm = normalize_for_sms_segment_count(message)
    length = len(norm)
    if length == 0:
        return 0
    if all(c in _GSM7_CHARS for c in norm):
        if length <= 160:
            return 1
        return (length + 152) // 153
    if length <= 70:
        return 1
    return (length + 66) // 67
