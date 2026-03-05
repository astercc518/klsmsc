"""
电话号码工具函数
"""

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


def country_to_dial_code(country_code: str) -> str:
    """将国家二字码（如 PH）转换为电话区号（如 63），找不到则原样返回"""
    return _COUNTRY_DIAL_MAP.get(country_code.upper(), country_code)
