"""
RCS 文案与号码校验

叮咚(BoltTel) RCS OpenAPI 对单批请求有硬性限制，任一不满足即「整批拒绝」：
  - 文案 ≤ 160 个 Unicode 字符（按字符数不是字节数）
  - 文案禁止 emoji
  - 号码须为 E.164（带 +）且与 isoCode 归属一致

这些限制必须在「提交入口」就拦下来，不能等发到上游才失败：
批量发送时上游是整批拒绝，一条带 emoji 的文案会连累同批其他号码。
"""
import re
from typing import Optional, Tuple

# 单条 RCS 文案最大 Unicode 字符数（上游硬限制）
RCS_MAX_CONTENT_CHARS = 160

# 单次 API 请求最大号码数（上游硬限制，本仓当前逐条提交，保留常量供批量提交复用）
RCS_MAX_PHONES_PER_REQUEST = 1000


# Emoji 码点集合。取 Unicode Extended_Pictographic 中「确定会被当作表情」的区段，
# 刻意不整块吞掉 U+2190–U+21FF / U+2300–U+23FF：普通箭头「→」、⌘ 等在正文里是合法字符，
# 误拦会让上游本可接受的文案在我们这里先被拒。
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # 麻将/牌/emoji 主区（含表情、手势、旗帜、交通、符号扩展）
    "☀-⛿"           # 杂项符号 ☀ ☎ ★ ♠ ♥ ⚡ ⛽
    "✀-➿"           # 装饰符号 ✂ ✅ ✈ ❤ ❗ ➡
    "⬀-⯿"           # ⬅ ⬆ ⭐ ⭕
    "↔-↙↩↪"  # ↔ ↕ ↖ ↗ ↘ ↙ ↩ ↪（Extended_Pictographic 箭头）
    "⌚⌛⌨⏏"   # ⌚ ⌛ ⌨ ⏏
    "⏩-⏳⏸-⏺"  # ⏩ ⏰ ⏳ ⏸ ⏺
    "Ⓜ▪▫▶◀◻-◾"
    "⤴⤵⬅-⬇"
    "〰〽㊗㊙"
    "‼⁉"            # ‼ ⁉
    "️"                  # 变体选择符-16（emoji 呈现，如 ❤️ 的第二个码点）
    "‍"                  # 零宽连接符（👨‍👩‍👧 组合 emoji）
    "⃣"                  # 键帽组合符（1️⃣）
    "]"
)


def find_emoji(text: Optional[str]) -> Optional[str]:
    """返回文案中第一个 emoji 字符，没有则返回 None。"""
    if not text:
        return None
    m = _EMOJI_PATTERN.search(text)
    return m.group(0) if m else None


def count_rcs_chars(text: Optional[str]) -> int:
    """按 Unicode 字符数计（与上游 CONTENT_TOO_LONG 判定口径一致）。"""
    return len(text or "")


def validate_rcs_content(text: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    校验 RCS 文案。

    Returns:
        (是否合法, 错误码, 中文错误说明)  —— 错误码与上游 errorCode 同名，便于日志对齐
    """
    body = text or ""
    if not body.strip():
        return False, "CONTENT_EMPTY", "RCS 文案不能为空"

    emoji = find_emoji(body)
    if emoji:
        return False, "CONTENT_EMOJI_FORBIDDEN", f"RCS 文案不支持 emoji（检测到 {emoji!r}），请删除表情符号"

    length = count_rcs_chars(body)
    if length > RCS_MAX_CONTENT_CHARS:
        return (
            False,
            "CONTENT_TOO_LONG",
            f"RCS 文案最长 {RCS_MAX_CONTENT_CHARS} 个字符（当前 {length} 个），请缩短后重试",
        )

    return True, None, None


def rcs_phone_e164(phone: Optional[str]) -> str:
    """
    归一为上游要求的 E.164（必须带前导 +）。

    RCS 与短信不同：上游按 `+` 开头的国际号码解析归属国，
    因此这里不走通道的 strip_leading_plus 配置，一律补 +。
    """
    s = str(phone or "").strip().replace(" ", "").replace("-", "")
    if not s:
        return ""
    if s.startswith("+"):
        return s
    return "+" + s.lstrip("+")
