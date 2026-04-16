"""
电话号码工具函数
"""
from typing import Any, Optional


def strip_leading_plus_enabled(config: Optional[dict[str, Any]]) -> bool:
    """
    从通道扩展 JSON（channels.config_json）解析是否去掉号码前导「+」。
    缺省为 True，与历史行为一致；仅当 strip_leading_plus 显式为假值时保留「+」。
    """
    if not config:
        return True
    v = config.get("strip_leading_plus")
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("false", "0", "no", "off", ""):
            return False
        return True
    return True


def format_sms_dest_phone(phone: str | None, *, strip_leading_plus: bool) -> str:
    """按通道策略格式化提交给上游的目的号码（是否去掉前导 +）。"""
    if phone is None:
        return ""
    s = str(phone).strip()
    if strip_leading_plus and s.startswith("+"):
        return s[1:]
    return s


def e164_without_plus(phone: str | None) -> str:
    """
    提交给短信上游时去掉前导「+」。
    库表与校验仍可使用带 + 的 E.164；仅外发 payload / SMPP 目的地址使用本函数。
    等价于通道未关闭 strip 时的默认行为。
    """
    return format_sms_dest_phone(phone, strip_leading_plus=True)


def export_phone_plain_digits(raw) -> str:
    """导出文件用号码：仅保留数字，无 +、空格、横线等（纯号码）"""
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        s = raw.decode("utf-8", errors="ignore")
    elif isinstance(raw, memoryview):
        s = raw.tobytes().decode("utf-8", errors="ignore")
    else:
        s = str(raw)
    s = s.strip().strip("\ufeff")
    if not s:
        return ""
    # 去掉全角加号等后再抽数字（半角 + 已由 isdigit 过滤）
    s = s.replace("\uff0b", "").replace("\ufe62", "").replace("\u207a", "")
    return "".join(c for c in s if c.isdigit())


# ISO 3166-1 alpha-2 → ITU-T E.164 国家区号
_COUNTRY_DIAL_MAP = {
    "PH": "63", "VN": "84", "ID": "62", "TH": "66", "MY": "60",
    "SG": "65", "MM": "95", "KH": "855", "LA": "856", "BN": "673",
    "CN": "86", "HK": "852", "TW": "886", "MO": "853",
    "JP": "81", "KR": "82", "IN": "91", "BD": "880", "PK": "92",
    "US": "1", "CA": "1", "GB": "44", "AU": "61", "NZ": "64",
    "DE": "49", "FR": "33", "IT": "39", "ES": "34", "BR": "55",
    "MX": "52", "RU": "7", "ZA": "27", "NG": "234", "KE": "254",
    "EG": "20", "SA": "966", "AE": "971", "TR": "90", "IL": "972",
}

# 电话区号 → ISO 国家码（路由规则支持两种格式）
_DIAL_TO_ISO = {v: k for k, v in _COUNTRY_DIAL_MAP.items()}


def country_to_dial_code(country_code: str) -> str:
    """将国家二字码（如 PH）转换为电话区号（如 63），找不到则原样返回"""
    return _COUNTRY_DIAL_MAP.get(country_code.upper(), country_code)


def dial_to_country_code(dial: str) -> str:
    """将电话区号（如 63）转换为国家二字码（如 PH），找不到则原样返回"""
    return _DIAL_TO_ISO.get(str(dial), str(dial))
