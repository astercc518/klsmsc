"""私库上传：号码解析与运营商识别（纯函数，供 API 与异步任务共用）"""
import csv
import io
import re
from typing import Dict, List, Optional

_NON_DIGIT_PHONE = re.compile(r"[^\d+]")


def decode_my_numbers_upload_bytes(content: bytes) -> str:
    """尝试多种编码解码私库上传文件（避免 GBK 误用 UTF-8 导致整文件无效）"""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_line_to_e164(line: str, default_region: Optional[str]) -> Optional[str]:
    """将一行文本解析为 E.164（含 +）"""
    import phonenumbers

    s = line.strip().strip("\ufeff").strip("\u200b").strip('"').strip("'")
    if not s:
        return None
    s = _NON_DIGIT_PHONE.sub("", s)
    if not s:
        return None
    digits = s.lstrip("+")
    if len(digits) < 7 or len(digits) > 20:
        return None

    attempts: List[str] = []
    if s.startswith("+"):
        attempts.append(s)
    elif s.startswith("00"):
        attempts.append("+" + s[2:])
    else:
        if default_region:
            attempts.append(s)
        attempts.append("+" + s)

    region = (default_region or "").strip().upper() or None
    for attempt in attempts:
        try:
            pn = phonenumbers.parse(attempt, region)
            if phonenumbers.is_valid_number(pn):
                return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            continue
    return None


def extract_phone_numbers_from_upload_text(
    filename: str, text_content: str, default_region: Optional[str] = None
) -> List[str]:
    """从上传文本中解析号码为 E.164（同步，可在线程池中执行）"""
    numbers_to_add: List[str] = []
    lower_name = (filename or "").lower()
    if lower_name.endswith(".csv"):
        f = io.StringIO(text_content)
        reader = csv.reader(f)
        for row in reader:
            if not row or not str(row[0]).strip():
                continue
            line = str(row[0]).strip()
            e164 = parse_line_to_e164(line, default_region)
            if e164:
                numbers_to_add.append(e164)
    else:
        for line in text_content.splitlines():
            e164 = parse_line_to_e164(line, default_region)
            if e164:
                numbers_to_add.append(e164)
    return numbers_to_add


def phone_db_lookup_keys(e164: str) -> List[str]:
    """库中可能存 +66… 或 66…，查询时一并匹配"""
    s = (e164 or "").strip()
    d = s.lstrip("+")
    keys = [s, d]
    if d:
        keys.append("+" + d)
    seen = set()
    out: List[str] = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def batch_lookup_carriers(nums: List[str]) -> Dict[str, Optional[str]]:
    """批量运营商识别（在线程中执行，避免阻塞事件循环）"""
    import phonenumbers
    from phonenumbers import carrier as pn_carrier

    out: Dict[str, Optional[str]] = {}
    for num in nums:
        try:
            phone_with_plus = num if num.startswith("+") else "+" + num
            parse_obj = phonenumbers.parse(phone_with_plus, None)
            name = pn_carrier.name_for_number(parse_obj, "en")
            name = (name or "").strip() if name else ""
            out[num] = name if name else None
        except Exception:
            out[num] = None
    return out
