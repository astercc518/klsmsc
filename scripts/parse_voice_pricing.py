#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从网关名称解析语音报价数据
格式: {供应商}{国家}{备注}{国码}-{价格}-{计费}
例: BE越南电力84-0.048-60+60
  -> 供应商: BE语音, 国家: 越南, 备注: 电力, 计费: 0.048U 60秒+60秒, 解读: 越南BE语音 0.048U 每分钟
"""

import re
import json
from pathlib import Path

# 国家中文名 -> ISO 代码 (dial 国码用于匹配)
COUNTRY_MAP = {
    "越南": "VN", "印度": "IN", "墨西哥": "MX", "加拿大": "CA", "巴西": "BR",
    "菲律宾": "PH", "印尼": "ID", "印度尼西亚": "ID", "巴基斯坦": "PK",
    "德国": "DE", "泰国": "TH", "新加坡": "SG", "瑞典": "SE", "缅甸": "MM",
    "智利": "CL", "比利时": "BE", "意大利": "IT", "文莱": "BN", "法国": "FR",
    "西班牙": "ES", "荷兰": "NL", "葡萄牙": "PT", "英国": "GB", "美国": "US",
    "埃及": "EG", "土耳其": "TR", "马来西亚": "MY", "阿根廷": "AR",
}

# 网关前缀(国码) -> ISO (用于无国家名时推断)
DIAL_TO_ISO = {
    "84": "VN", "91": "IN", "52": "MX", "1": "US", "55": "BR", "63": "PH",
    "62": "ID", "92": "PK", "49": "DE", "66": "TH", "65": "SG", "46": "SE",
    "95": "MM", "56": "CL", "32": "BE", "39": "IT", "673": "BN", "33": "FR",
    "34": "ES", "31": "NL", "351": "PT", "44": "GB", "20": "EG", "90": "TR",
    "60": "MY", "54": "AR", "41": "CH", "370": "LT", "353": "IE", "48": "PL",
    "420": "CZ", "43": "AT", "36": "HU", "30": "GR", "64": "NZ", "61": "AU",
    "81": "JP", "82": "KR", "86": "CN", "852": "HK", "886": "TW",
}

def parse_billing(interval: str) -> tuple[str, str]:
    """解析计费间隔，返回 (计费描述, 解读)"""
    if not interval:
        return "", ""
    # 60+60 -> 每分钟
    if interval == "60+60":
        return "60秒+60秒", "每分钟"
    # 1+1 -> 每秒
    if interval == "1+1":
        return "1秒+1秒", "按秒计费"
    # 6+1, 30+6 等
    m = re.match(r"(\d+)\+(\d+)", interval)
    if m:
        a, b = m.groups()
        return f"{a}秒+{b}秒", f"{a}秒起每{b}秒"
    return interval, interval

def parse_gateway(name: str, prefix: str = "") -> dict | None:
    """
    解析网关名称
    格式: [Supplier][Country][Remark][Code]-[Price]-[Interval]
    """
    # 匹配末尾的 -价格-间隔
    m = re.search(r"-(\d+\.?\d*)-(\d+\+\d+)$", name)
    if not m:
        # 尝试 0.0054-1+1 这种无前导-的
        m2 = re.search(r"(\d+\.?\d*)-(\d+\+\d+)$", name)
        if m2:
            price, interval = m2.groups()
            rest = name[:m2.start()].strip()
        else:
            return None
    else:
        price, interval = m.groups()
        rest = name[:m.start()].strip()

    # 提取供应商 (开头2-6个字母)
    supplier_match = re.match(r"^([A-Za-z]{2,6})", rest)
    if not supplier_match:
        return None
    supplier = supplier_match.group(1).upper()
    rest = rest[len(supplier):].lstrip("+")

    # 提取国家：优先匹配已知国家名（避免把"电力""快递""卡线"等并入国家）
    country = ""
    for cname in sorted(COUNTRY_MAP.keys(), key=len, reverse=True):
        if rest.startswith(cname) or rest.startswith("+" + cname):
            country = cname
            rest = rest[len(country):].lstrip("+")
            break
    if not country:
        # 回退：取第一个连续中文
        for i, c in enumerate(rest):
            if "\u4e00" <= c <= "\u9fff":
                country += c
            elif country:
                break
        if not country:
            return None
        rest = rest[len(country):].lstrip("+")

    # 备注 (国家后的中文，如 电力/快递/卡线) 和 国码 (数字)
    remark = ""
    code_in_name = ""
    # 剩余部分可能包含: 电力84, 快递84, +91, 84, 777 等
    code_match = re.search(r"[\+]?(\d{1,4})\s*$", rest)
    if code_match:
        code_in_name = code_match.group(1)
        rest = rest[:code_match.start()].strip("+- ")
    # 备注是剩余的中文部分
    for c in rest:
        if "\u4e00" <= c <= "\u9fff":
            remark += c
    remark = remark or None

    # 确定 country_code
    country_code = COUNTRY_MAP.get(country) or DIAL_TO_ISO.get(prefix or code_in_name, "")

    price_f = float(price)
    billing_desc, billing_read = parse_billing(interval)
    # 用户要求格式：越南BE语音 0.048U 每分钟（国家+供应商+价格+计费）
    supplier_display = f"{supplier}语音"
    if remark:
        full_read = f"{country}{supplier_display}({remark}) {price}U {billing_read}"
    else:
        full_read = f"{country}{supplier_display} {price}U {billing_read}"

    return {
        "gateway_name": name,
        "supplier": f"{supplier}语音",
        "channel_code": f"VOICE_{supplier}",
        "country": country,
        "country_code": country_code,
        "prefix": prefix or code_in_name,
        "cost_usd": price_f,
        "sale_usd": round(price_f * 1.3, 4),  # 默认加价30%
        "price_usd": round(price_f * 1.3, 4),
        "billing_model": interval,
        "billing_desc": f"{price}U {billing_desc}",
        "full_desc": full_read,
        "description": remark or None,
    }

# 从图片描述和OCR提取的原始数据 (网关名称, 网关前缀)
RAW_DATA = [
    # 图片1
    ("BE越南电力84-0.048-60+60", "84"),
    ("BO越南84-0.035-1+1", "84"),
    ("DL越南777-0.055-60+60", "84"),
    ("HB印度+91-0.035-60+60", "91"),
    ("HB越南快递84-0.028-60+60", "84"),
    ("KM加拿大0.0054-1+1", "1"),
    ("KM巴西+55-0.0086-30+6", "55"),
    ("NU越南快递-0.044-60+60", "84"),
    ("JT越南卡线84-0.046-6+1", "84"),
    # 图片2 - QK
    ("QK巴西00-0.008-30+6", "55"),
    ("QK德国49-0.0175-1+1", "49"),
    ("QK巴基斯坦00-0.055-1+1", "92"),
    ("QK越南+84-0.048-60+60", "84"),
    ("QK菲律宾+63-0.035-60+60", "63"),
    ("QK加拿大-0.0054-1+1", "1"),
    ("QK巴基斯坦92-0.058-1+1", "92"),
    # 图片2 - SK
    ("SK越南+84-0.046-60+60", "84"),
    ("SK印度+91-0.028-60+60", "91"),
    ("SK菲律宾+63-0.035-60+60", "63"),
    ("SK新加坡65-0.036-60+60", "65"),
    ("SK巴西+55-0.007-1+1", "55"),
    ("SK法国33-0.022-1+1", "33"),
    ("SK意大利+39-0.026-1+1", "39"),
    ("SK巴基斯坦92-0.04-1+1", "92"),
    ("SK巴西+55-0.006-30+6", "55"),
    ("SK美国1-0.006-1+1", "1"),
    # 图片2 - SY
    ("SY越南+84-0.048-60+60", "84"),
    ("SY印度+91-0.035-60+60", "91"),
    ("SY巴基斯坦92-0.04-1+1", "92"),
    ("SY巴西+55-0.006-30+6", "55"),
    ("SY美国1-0.006-1+1", "1"),
    ("SY印尼+62-0.059-1+1", "62"),
    ("SY菲律宾63-0.031-1+1", "63"),
    ("SY巴西+55-0.0078-30+6", "55"),
    # 图片2 - Ueasy
    ("Ueasy越南电力84-0.048-60+60", "84"),
    ("Ueasy越南+84-0.053-1+1", "84"),
    ("Ueasy印尼+62-0.031-1+1", "62"),
    ("Ueasy印度+91-0.028-60+60", "91"),
    ("Ueasy巴基斯坦92-0.058-1+1", "92"),
    ("Ueasy巴西+55-0.0078-30+6", "55"),
    ("Ueasy智利+56-0.00875-1+1", "56"),
    ("Ueasy泰国66-0.042-60+60", "66"),
    ("Ueasy新加坡65-0.027-1+1", "65"),
    ("Ueasy瑞典+46-0.028-1+1", "46"),
    ("Ueasy缅甸95-0.03-60+60", "95"),
    ("Ueasy墨西哥52-0.048-60+60", "52"),
    ("Ueasy墨西哥52-0.047-6+6", "52"),
]

def main():
    results = []
    seen = set()
    for name, prefix in RAW_DATA:
        row = parse_gateway(name, prefix)
        if row and row["gateway_name"] not in seen:
            seen.add(row["gateway_name"])
            results.append(row)

    # 按供应商、国家排序
    results.sort(key=lambda x: (x["supplier"], x["country"], x["gateway_name"]))

    # 构建 by_supplier (按供应商分组，每供应商下按 gateway_name 列表)
    by_supplier = {}
    for r in results:
        sup = r["supplier"]
        if sup not in by_supplier:
            by_supplier[sup] = {"channel_code": r["channel_code"], "items": []}
        by_supplier[sup]["items"].append({
            "type": "VOICE",
            "gateway_name": r["gateway_name"],
            "supplier": r["supplier"],
            "channel_code": r["channel_code"],
            "country": r["country"],
            "country_code": r["country_code"],
            "prefix": r["prefix"],
            "cost_usd": r["cost_usd"],
            "sale_usd": r["sale_usd"],
            "price_usd": r["price_usd"],
            "billing_model": r["billing_model"],
            "billing_desc": r["billing_desc"],
            "full_desc": r["full_desc"],
            "description": r["description"],
        })

    # flat_list 格式 (与 resource_pricing 兼容)
    flat_list = []
    for r in results:
        flat_list.append({
            "type": "VOICE",
            "gateway_name": r["gateway_name"],
            "supplier": r["supplier"],
            "channel_code": r["channel_code"],
            "country": r["country"],
            "country_code": r["country_code"],
            "prefix": r["prefix"],
            "cost_usd": r["cost_usd"],
            "sale_usd": r["sale_usd"],
            "price_usd": r["price_usd"],
            "billing_model": r["billing_model"],
            "billing_desc": r["billing_desc"],
            "full_desc": r["full_desc"],
            "description": r["description"],
        })

    out = {
        "generated_at": "2026-03-12",
        "source": "语音报价1.png, 语音报价2.png",
        "total_records": len(results),
        "supplier_count": len(by_supplier),
        "country_count": len(set(r["country_code"] for r in results if r["country_code"])),
        "currency": "USD",
        "by_supplier": by_supplier,
        "flat_list": flat_list,
    }

    out_path = Path(__file__).parent.parent / "data" / "resource_voice_pricing.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Generated {out_path} with {len(results)} records")

if __name__ == "__main__":
    main()
