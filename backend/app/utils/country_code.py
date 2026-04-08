"""
国家代码规范化工具：中文名 / 国际区号 / ISO2 互转。

所有入库的 country_code 应统一为 ISO2 大写（如 TH、BR）。
计费引擎查询时使用 get_country_variants() 获取同一国家的全部等价写法。
"""
from typing import Dict, List, Optional, Set, Tuple

_COUNTRY_DATA: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    # (ISO2, 区号, (中文别名...))
    ("TH", "66", ("泰国",)),
    ("BR", "55", ("巴西",)),
    ("BD", "880", ("孟加拉", "孟加拉国")),
    ("ID", "62", ("印度尼西亚", "印尼")),
    ("MY", "60", ("马来西亚", "马来")),
    ("VN", "84", ("越南",)),
    ("PH", "63", ("菲律宾",)),
    ("SG", "65", ("新加坡",)),
    ("JP", "81", ("日本",)),
    ("KR", "82", ("韩国",)),
    ("IN", "91", ("印度",)),
    ("PK", "92", ("巴基斯坦",)),
    ("MX", "52", ("墨西哥",)),
    ("AR", "54", ("阿根廷",)),
    ("CO", "57", ("哥伦比亚",)),
    ("CL", "56", ("智利",)),
    ("PE", "51", ("秘鲁",)),
    ("EG", "20", ("埃及",)),
    ("NG", "234", ("尼日利亚",)),
    ("KE", "254", ("肯尼亚",)),
    ("ZA", "27", ("南非",)),
    ("AE", "971", ("阿联酋",)),
    ("SA", "966", ("沙特", "沙特阿拉伯")),
    ("TR", "90", ("土耳其",)),
    ("RU", "7", ("俄罗斯",)),
    ("UA", "380", ("乌克兰",)),
    ("GB", "44", ("英国",)),
    ("DE", "49", ("德国",)),
    ("FR", "33", ("法国",)),
    ("ES", "34", ("西班牙",)),
    ("IT", "39", ("意大利",)),
    ("AU", "61", ("澳大利亚", "澳洲")),
    ("NZ", "64", ("新西兰",)),
    ("US", "1", ("美国",)),
    ("CA", "1CA", ("加拿大",)),
    ("KH", "855", ("柬埔寨",)),
    ("LB", "961", ("黎巴嫩",)),
    ("BJ", "229", ("贝宁",)),
    ("MM", "95", ("缅甸",)),
    ("LK", "94", ("斯里兰卡",)),
    ("GH", "233", ("加纳",)),
    ("UG", "256", ("乌干达",)),
    ("TZ", "255", ("坦桑尼亚",)),
    ("ET", "251", ("埃塞俄比亚",)),
    ("CM", "237", ("喀麦隆",)),
    ("SN", "221", ("塞内加尔",)),
    ("VE", "58", ("委内瑞拉",)),
    ("EC", "593", ("厄瓜多尔",)),
    ("BO", "591", ("玻利维亚",)),
    ("IL", "972", ("以色列",)),
    ("JO", "962", ("约旦",)),
    ("KW", "965", ("科威特",)),
    ("QA", "974", ("卡塔尔",)),
    ("MA", "212", ("摩洛哥",)),
    ("DK", "45", ("丹麦",)),
    ("FI", "358", ("芬兰",)),
    ("NL", "31", ("荷兰",)),
    ("BE", "32", ("比利时",)),
    ("PL", "48", ("波兰",)),
    ("RO", "40", ("罗马尼亚",)),
    ("IE", "353", ("爱尔兰",)),
    ("PT", "351", ("葡萄牙",)),
    ("KZ", "7KZ", ("哈萨克斯坦",)),
    ("ZM", "260", ("赞比亚",)),
)

# 索引：任意写法 -> ISO2
_TO_ISO: Dict[str, str] = {}
# 索引：ISO2 -> 全部等价写法
_ISO_VARIANTS: Dict[str, Set[str]] = {}

for _iso, _dial, _cn_names in _COUNTRY_DATA:
    all_keys = {_iso, _dial} | set(_cn_names)
    _ISO_VARIANTS[_iso] = all_keys
    for k in all_keys:
        _TO_ISO[k] = _iso
        _TO_ISO[k.upper()] = _iso
        _TO_ISO[k.lower()] = _iso


def normalize_country_code(raw: Optional[str]) -> Optional[str]:
    """
    将任意格式的国家代码规范化为 ISO2 大写。
    输入可以是 ISO2（TH）、区号（66）、中文名（泰国）。
    无法识别时返回原值的 strip().upper()。
    """
    if not raw:
        return raw
    s = str(raw).strip()
    if not s:
        return None
    iso = _TO_ISO.get(s) or _TO_ISO.get(s.upper())
    if iso:
        return iso
    return s.upper()


def get_country_variants(country_code: Optional[str]) -> List[str]:
    """
    返回同一国家的全部等价写法列表，用于 SQL IN 查询。
    输入可以是 ISO2/区号/中文名。
    """
    if not country_code:
        return []
    s = str(country_code).strip()
    iso = _TO_ISO.get(s) or _TO_ISO.get(s.upper())
    if iso:
        return list(_ISO_VARIANTS[iso])
    return [s, s.upper()]
