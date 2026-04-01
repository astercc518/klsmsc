"""
短信分段条数计算（GSM-7 / UCS-2），与前端 utils/smsParts 及运营展示对齐。

在判断编码前对正文做轻量规范化，避免 NBSP、零宽字符、弯引号等导致
「肉眼为英文」却整段被判为 UCS-2、条数虚高。
"""
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


def count_sms_parts(message: str) -> int:
    """与历史 PricingEngine._count_sms_parts 语义一致，增加规范化步骤。"""
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
