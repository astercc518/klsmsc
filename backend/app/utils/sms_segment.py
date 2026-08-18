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


# 零宽字符：不可见、不占字形，但会实打实占用 UCS-2 码元，且被计费口径删掉。
_ZERO_WIDTH: Final = frozenset("\u200b\u200c\u200d\ufeff")


def _normalize_length_only(text: str) -> str:
    """只做「会改变码元数」的清理，不碰任何等长的字形替换。

    给 UCS-2 正文（泰文/中文/阿拉伯文等）用：它们无论清洗与否都按 UCS-2 计费，
    条数只取决于长度。删零宽、把省略号展开成三点，长度就与计费口径严格一致；
    而 en-dash/em-dash/弯引号/NBSP 都是 1↔1 的等长替换，对条数毫无影响，
    保持原样才不会破坏上游按模板逐字节加白的精确匹配。
    """
    out: list[str] = []
    for c in text:
        if c in _ZERO_WIDTH:
            continue
        elif c == "…":
            out.append("...")
        else:
            out.append(c)
    return "".join(out)


def sanitize_sms_text_for_wire(message: str) -> str:
    """上行发送前规范化正文，保证「实际发出的编码/条数 ≡ 计费口径」。

    清洗的唯一收益，是把「肉眼英文却含 en-dash「–」U+2013、em-dash、省略号、弯引号、
    NBSP」的正文拉回 GSM-7，避免计费按 GSM-7 算 1 条、上游按 UCS-2 收 2 条的口径错位
    （差价由平台自担）。所以只在清洗确实能落回 GSM-7 时，才整段替换。

    正文本身就是 UCS-2（泰文/中文/emoji 等）时，等长字形替换一条也省不下来——实测
    「699–6,999」与「699-6,999」同为 UCS-2、同为 1 条——却会改写实际发出的字节。对按
    模板逐字节加白的上游（如 TS_066_zhilian 泰国直连）这是致命的：报备的是 en-dash 原
    文、发出去的是 hyphen，模板校验不过，整批回 SMPP status=1 且不写回执、不自动退费。
    故此路径只做零宽删除与省略号展开这类「改变码元数」的清理，字形一律原样发出。

    两条路径的输出长度恒等（normalize 里唯二改变长度的规则就是这两条），因此无论走哪
    条，UCS-2 码元数都与 count_sms_parts 的计费口径一致。幂等：重复调用结果不变。
    """
    if not message:
        return message
    normalized = normalize_for_sms_segment_count(message)
    if gsm7_septet_count(normalized) is not None:
        return normalized
    return _normalize_length_only(message)


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
