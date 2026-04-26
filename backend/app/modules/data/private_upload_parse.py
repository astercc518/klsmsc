"""私库上传：号码解析与运营商识别（纯函数，供 API 与异步任务共用）"""
import csv
import io
import re
from typing import Dict, List, Optional, Tuple

_NON_DIGIT_PHONE = re.compile(r"[^\d+]")

# 快速路径表：ISO2 -> (dial_prefix, min_total_digits, max_total_digits)
# total_digits = 含国家区号的完整数字位数（不含 +）
_FAST_REGION_MAP: Dict[str, Tuple[str, int, int]] = {
    "BD": ("880", 12, 13),
    "IN": ("91",  12, 12),
    "PK": ("92",  12, 12),
    "TH": ("66",  11, 11),
    "PH": ("63",  11, 12),
    "ID": ("62",  11, 13),
    "VN": ("84",  11, 12),
    "MY": ("60",  11, 11),
    "CN": ("86",  13, 13),
    "KH": ("855", 11, 12),
    "MM": ("95",  11, 12),
    "LK": ("94",  11, 11),
    "NG": ("234", 13, 13),
    "GH": ("233", 12, 12),
    "KE": ("254", 12, 12),
    "TZ": ("255", 12, 12),
    "UG": ("256", 12, 12),
    "ET": ("251", 12, 12),
    "SN": ("221", 11, 11),
    "CM": ("237", 11, 11),
    "BJ": ("229", 11, 11),
    "EG": ("20",  11, 12),
    "ZA": ("27",  11, 11),
    "MA": ("212", 12, 12),
    "AE": ("971", 12, 12),
    "SA": ("966", 12, 12),
    "TR": ("90",  12, 12),
    "SG": ("65",  10, 11),
    "JP": ("81",  12, 12),
    "KR": ("82",  11, 12),
    "BR": ("55",  12, 13),
    "MX": ("52",  12, 12),
    "AR": ("54",  13, 13),
    "CO": ("57",  12, 12),
}


def _fast_parse_e164(digits: str, region: str) -> Optional[str]:
    """
    快速路径：对已知 region 仅做前缀+长度校验，避免调用 phonenumbers.parse()。
    速度比 phonenumbers 快 100-500x。
    """
    info = _FAST_REGION_MAP.get(region)
    if not info:
        return None
    prefix, min_len, max_len = info
    d = digits
    if d.startswith("00"):
        d = d[2:]
    if not d.startswith(prefix):
        d = prefix + d
    if min_len <= len(d) <= max_len:
        return "+" + d
    return None


def decode_my_numbers_upload_bytes(content: bytes) -> str:
    """尝试多种编码解码私库上传文件（避免 GBK 误用 UTF-8 导致整文件无效）"""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_line_to_e164(line: str, default_region: Optional[str]) -> Optional[str]:
    """将一行文本解析为 E.164（含 +）。对已知 region 走快速路径跳过 phonenumbers。"""
    import phonenumbers

    s = line.strip().strip("﻿").strip("​").strip('"').strip("'")
    if not s:
        return None
    s = _NON_DIGIT_PHONE.sub("", s)
    if not s:
        return None
    digits = s.lstrip("+")
    if len(digits) < 7 or len(digits) > 20:
        return None

    region = (default_region or "").strip().upper() or None

    # 快速路径：已知 region 直接校验前缀+长度，不调用 phonenumbers
    if region:
        result = _fast_parse_e164(digits, region)
        if result:
            return result

    # Fallback：phonenumbers 完整校验（未知 region 或快速路径未匹配）
    attempts: List[str] = []
    if s.startswith("+"):
        attempts.append(s)
    elif s.startswith("00"):
        attempts.append("+" + s[2:])
    else:
        if default_region:
            attempts.append(s)
        attempts.append("+" + s)

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
