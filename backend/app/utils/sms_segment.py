"""
短信分段条数计算（GSM-7 / UCS-2），与前端 utils/smsParts 及运营展示对齐。

在判断编码前对正文做轻量规范化，避免 NBSP、零宽字符、弯引号等导致
「肉眼为英文」却整段被判为 UCS-2、条数虚高。

另：识别短链占位符 {{TRACK_URL=target|base}}，按实际发送时的短链长度计费，
避免「占位符 94 字符算 2 条 / 实发 70 字符 1 条」的多扣费问题。
"""
import re
from typing import Final

_GSM7_CHARS: Final = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# GSM-7 扩展表（escape 表）字符：仍是 GSM-7 编码，但每个需转义符前缀、占 2 个 septet。
# 漏掉它们会导致含 [ ] { } \ ^ ~ | € 的纯英文短信被误判为 UCS-2、条数虚高、多扣费。
_GSM7_EXT_CHARS: Final = frozenset("\f^{}\\[~]|€")


def gsm7_septet_count(norm: str) -> "int | None":
    """返回按 GSM-7 编码所需的 septet 数；若含任何非 GSM-7 字符返回 None。

    基本表字符各占 1 个 septet，扩展表字符（escape）各占 2 个。
    """
    total = 0
    for c in norm:
        if c in _GSM7_CHARS:
            total += 1
        elif c in _GSM7_EXT_CHARS:
            total += 2
        else:
            return None
    return total


def utf16_code_unit_count(text: str) -> int:
    """Return the number of 16-bit code units used by SMS Unicode encoding.

    SMS providers commonly call the encoding UCS-2, but supplementary Unicode
    characters (emoji, some historic scripts) are carried as UTF-16 surrogate
    pairs and therefore consume two 16-bit units. Python ``len`` counts those as
    one code point, so it cannot be used for billing boundaries.
    """
    return sum(2 if ord(c) > 0xFFFF else 1 for c in text)


def normalize_for_sms_segment_count(text: str) -> str:
    """分段计费前的规范化（不改变用户存储的正文，仅用于条数与编码判断）。

    不做整段 NFKC：NFKC 的兼容性分解会把 Thai SARA AM (ำ U+0E33→U+0E4D+U+0E32)、
    ㍿/Ⓐ/① 等单 UCS-2 码点拆成多码点或改变 GSM-7 命中，造成条数虚高
    （70 char 误判 71 → 多扣 1 条）。实际 SMS UCS-2 传输时这些都是 1 个 16-bit
    单元，无需任何规范化。仅做白名单字符替换：NBSP、零宽、弯引号、长破折、省略号 ——
    这些才是真正会让「肉眼英文」被误判 UCS-2 的元凶。
    """
    if not text:
        return text
    out: list[str] = []
    for c in text:
        if c == " ":
            out.append(" ")
        elif c in "​‌‍﻿":
            continue
        elif c in "‘’":
            out.append("'")
        elif c in "“”":
            out.append('"')
        elif c == "–":
            out.append("-")
        elif c == "—":
            out.append("-")
        elif c == "…":
            out.append("...")
        else:
            out.append(c)
    return "".join(out)


def is_gsm7_message(message: str) -> bool:
    norm = normalize_for_sms_segment_count(message)
    return gsm7_septet_count(norm) is not None


def sanitize_sms_text_for_wire(message: str) -> str:
    """上行发送前对正文做与「分段计费」完全相同的白名单规范化。

    与 normalize_for_sms_segment_count 共用同一实现——这是关键：计费按此规范化
    后判定编码/条数，若发送时不做同样处理，就会出现「计费按 GSM-7 算 1 条、上游
    按 UCS-2 算 2 条」的口径错位（en-dash「–」U+2013、em-dash、省略号、弯引号、
    NBSP、零宽字符都会触发），中间差价由平台自担。让上行正文走同一函数，
    「实际发出的编码 ≡ 计费口径」由构造保证，二者永不漂移。

    仅做安全的等价替换（–/—→-、…→...、弯引号→直引号、NBSP→空格、零宽→删除），
    对真正的非 GSM-7 内容（中文/泰文/emoji 等）不改动，仍按 UCS-2 正确多段计费。
    幂等：重复调用结果不变。
    """
    if not message:
        return message
    return normalize_for_sms_segment_count(message)


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
    if len(norm) == 0:
        return 0
    septets = gsm7_septet_count(norm)
    if septets is not None:
        # GSM-7：单段 160 septet，拼接长短信每段 153 septet
        if septets <= 160:
            return 1
        return (septets + 152) // 153
    # SMS Unicode（习惯称 UCS-2，实际需兼容 UTF-16 代理对）：
    # 单段 70 个 16-bit 码元；6-byte UDH 拼接每段 67 码元。
    units = utf16_code_unit_count(norm)
    if units <= 70:
        return 1
    return (units + 66) // 67
