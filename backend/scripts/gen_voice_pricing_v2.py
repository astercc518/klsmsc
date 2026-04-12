#!/usr/bin/env python3
"""从截图数据生成 resource_voice_pricing.json（v2）"""
import json, re
from datetime import date
from pathlib import Path

# 国家名 → 国家代码 + 电话前缀
COUNTRY_MAP = {
    "印尼": ("ID", "62"), "印度": ("IN", "91"), "墨西哥": ("MX", "52"),
    "泰国": ("TH", "66"), "美国": ("US", "1"),  "菲律宾": ("PH", "63"),
    "越南": ("VN", "84"), "马来西亚": ("MY", "60"), "马来": ("MY", "60"),
    "加拿大": ("CA", "1"), "巴西": ("BR", "55"), "巴基斯坦": ("PK", "92"),
    "德国": ("DE", "49"), "日本": ("JP", "81"), "英国": ("GB", "44"),
    "土耳其": ("TR", "90"), "意大利": ("IT", "39"), "比利时": ("BE", "32"),
    "荷兰": ("NL", "31"), "尼日利亚": ("NG", "234"), "南非": ("ZA", "27"),
    "哥伦比亚": ("CO", "57"), "埃及": ("EG", "20"), "孟加拉": ("BD", "880"),
    "瑞典": ("SE", "46"), "澳大利亚": ("AU", "61"), "沙特": ("SA", "966"),
    "俄罗斯": ("RU", "7"), "韩国": ("KR", "82"), "法国": ("FR", "33"),
    "新加坡": ("SG", "65"), "新西兰": ("NZ", "64"), "捷克": ("CZ", "420"),
    "文莱": ("BN", "673"), "智利": ("CL", "56"), "波兰": ("PL", "48"),
    "爱尔兰": ("IE", "353"), "瑞士": ("CH", "41"), "科威特": ("KW", "965"),
    "秘鲁": ("PE", "51"), "立陶宛": ("LT", "370"), "缅甸": ("MM", "95"),
    "罗马尼亚": ("RO", "40"), "芬兰": ("FI", "358"), "西班牙": ("ES", "34"),
    "阿联酋": ("AE", "971"), "挪威": ("NO", "47"), "埃塞俄比亚": ("ET", "251"),
    "莫塞俄比亚": ("ET", "251"), "哈萨克斯坦": ("KZ", "7"),
    "葡萄牙": ("PT", "351"),
}

# 售价 = 成本 × 1.3（30% 加价）
MARKUP = 1.3

# ─── 截图原始数据：(网关名称, 前缀) ───
RAW = """
AT印尼过滤+62-0.031-1+1,62
AT印度91-0.017-60+60,91
AT印度包口91-0.017-60+60,91
AT墨西哥-透传-0.0045-1+1,52
AT泰国+66-0.03-60+60,66
AT美国+1-0.03-60+60,1
AT菲律宾63-0.05-1+1,63
AT越南股票84-0.029-1+1,84
BE越南电力84-0.048-60+60,84
BO越南84-0.035-1+1,84
DL越南111-0.048-60+60,84
DL越南222-0.043-60+60,84
DL越南333-0.025-60+60,84
DL越南666-0.03-1+1,84
DL越南777-0.055-60+60,84
DR越南快递84-0.03-60+60,84
HB印度+91-0.035-60+60,91
HB土耳其90-0.3-1+1,90
HB墨西哥52-0.0045-60+60,52
HB尼日利亚234-0.135-1+1,234
HB意大利39-0.016-1+1,39
HB日本81-0.18-1+1,81
HB比利时32-0.035-1+1,32
HB泰国66-0.05-60+60,66
HB英国44-0.06-1+1,44
HB荷兰31-0.02-1+1,31
HB越南02国活-0.03-1+1,84
HB越南CK-0.028-60+60,84
HB越南卡线84-0.048-60+60,84
HB越南快递84-0.028-60+60,84
HJ越南84-0.048-60+60,84
HS印度+91-0.0185-60+60,91
HS墨西哥+52-0.0032-60+60,52
HS日本+81-0.033-1+1,81
HS马来+60-0.013-1+1,60
JT印尼62-0.033-1+1,62
JT印度91-0.022-60+60,91
JT巴基斯坦92-0.054-1+1,92
JT菲律宾63-0.06-1+1,63
JT越南卡线84-0.046-6+1,84
JT马来西亚60-0.02-60+60,60
KM加拿大0.0054-1+1,1
KM南非27-0.041-1+1,27
KM印尼+62-0.041-1+1,62
KM哥伦比亚+57-0.0035-1+1,57
KM土耳其90-0.23-1+1,90
KM埃及+20-0.058-1+1,20
KM墨西哥+52-0.006-60+60,52
KM孟加拉00-0.0138-1+1,880
KM尼日利亚234-0.056-1+1,234
KM巴西+55-0.0086-30+6,55
KM德国+49-0.0236-1+1,49
KM意大利+39-0.0191-1+1,39
KM日本81-0.06-1+1,81
KM比利时32-0.037-1+1,32
KM沙特966-0.15-1+1,966
KM瑞典46-0.024-1+1,46
KM澳大利亚61-0.0263-1+1,61
KM秘鲁51-0.0036-1+1,51
KM美国0.0503-60+60,1
KM英国+44-0.0419-1+1,44
KM荷兰0.0218-1+1,31
KM菲律宾-63-0.108-1+1,63
KM葡萄牙351-0.032-1+1,351
KM西班牙+34-0.0156-1+1,34
KM新加坡+65-0.1645-60+1,65
KM韩国-82-0.036-60+60,82
NU墨西哥52-0.0036-60+60,52
NU巴西55-0.007-30+6,55
NU越南常规-0.036-1+1,84
NU越南快递-0.042-60+60,84
NU越南电力-0.045-60+60,84
QK俄罗斯+7-0.25-1+1,7
QK南非+27-0.048-1+1,27
QK印尼-透传-0.065-60+1,62
QK哥伦比亚+57-0.006-1+1,57
QK莫塞俄比亚0.189-1+1,251
QK墨西哥+52-0.0045-60+60,52
QK孟加拉-00-0.012-1+1,880
QK尼日利亚234-0.109-1+1,234
QK巴基斯坦00-0.055-1+1,92
QK巴西00-0.008-30+6,55
QK德国49-0.0175-1+1,49
QK意大利+39-0.025-1+1,39
QK捷克420-0.048-1+1,420
QK文莱+673-0.35-60+1,673
QK新加坡65-0.14-60+1,65
QK新西兰64-0.066-60+1,64
QK日本-国际显-0.055-1+1,81
QK日本050-0.12-60+1,81
QK智利+56-0.009-1+1,56
QK比利时32-0.035-1+1,32
QK沙特+000-0.125-1+1,966
QK法国+33-0.02-1+1,33
QK波兰-0.017-1+1,48
QK泰国66-0.065-60+60,66
QK澳大利亚61-0.046-1+1,61
QK爱尔兰353-0.035-1+1,353
QK瑞典46-0.022-1+1,46
QK瑞士41-0.085-1+1,41
QK科威特965-0.039-1+1,965
QK秘鲁-0.003-1+1,51
QK立陶宛370-0.2-1+1,370
QK缅甸+00-0.28-60+60,95
QK罗马尼亚40-0.012-1+1,40
QK芬兰-358-0.055-1+1,358
QK英国+44-0.063-1+1,44
QK菲律宾-63-0.06-1+1,63
QK西班牙透传-0.02-1+1,34
QK阿联酋-000-0.185-1+1,971
QK韩国02-0.043-60+1,82
QK马来西亚+60-0.012-60+1,60
SKY巴基斯坦92-0.058-1+1,92
SK哥伦比亚-57-0.0045-1+1,57
SK墨西哥-透传-0.0038-60+60,52
SK巴西+55-0.0066-30+6,55
SK意大利透传+39-0.017-1+1,39
SK新加坡-65-0.038-60+60,65
SK智利56-0.007-1+1,56
SK法国33-0.022-1+1,33
SK菲律宾63-0.06-1+1,63
SK西班牙透传-34-0.018-1+1,34
SK马来西亚+60-0.0145-1+1,60
SY印尼-手机-0.028-1+1,62
""".strip()

def parse_gateway(line: str):
    """解析网关名称行：提取供应商、国家、描述、价格、计费模式"""
    parts = line.split(",")
    if len(parts) != 2:
        return None
    gw_name = parts[0].strip()
    prefix = parts[1].strip()

    # 提取供应商代码（名称开头的英文字母）
    m = re.match(r'^([A-Z]+)', gw_name)
    if not m:
        return None
    supplier_code = m.group(1)

    # 提取计费模式（末尾的 X+Y 模式）
    bm = re.search(r'-(\d+\+\d+)$', gw_name)
    if not bm:
        return None
    billing_model = bm.group(1)

    # 去掉计费模式部分
    rest = gw_name[:bm.start()]

    # 提取成本（最后一个 -数字 部分）
    cm = re.search(r'-?(0\.\d+)$', rest)
    if not cm:
        return None
    cost = float(cm.group(1))
    rest = rest[:cm.start()]

    # 去掉末尾的 -
    rest = rest.rstrip('-')

    # 去掉供应商代码
    rest = rest[len(supplier_code):]

    # 识别国家：遍历国家名，找到最长匹配
    country_name = None
    country_code = None
    country_prefix = prefix
    for cn, (cc, cp) in sorted(COUNTRY_MAP.items(), key=lambda x: -len(x[0])):
        if cn in rest:
            country_name = cn
            country_code = cc
            country_prefix = cp
            break

    if not country_code:
        # 无法识别国家，用前缀推断
        for cn, (cc, cp) in COUNTRY_MAP.items():
            if cp == prefix:
                country_name = cn
                country_code = cc
                country_prefix = cp
                break

    if not country_code:
        return None

    # 提取描述（国家名之后的中文/字母部分，去掉数字和符号）
    desc = ""
    if country_name and country_name in rest:
        after = rest.split(country_name, 1)[1]
        after = re.sub(r'^[\d+\-]+', '', after)   # 去掉开头的数字/+/-
        after = re.sub(r'[\d+\-]+$', '', after)   # 去掉末尾的数字/+/-
        after = after.strip()
        if after and not after.replace('.', '').isdigit():
            desc = after

    sale = round(cost * MARKUP, 6)
    supplier_name = supplier_code + "语音"

    return {
        "type": "VOICE",
        "gateway_name": gw_name,
        "supplier": supplier_name,
        "channel_code": f"VOICE_{supplier_code}",
        "country": country_name,
        "country_code": country_code,
        "prefix": country_prefix,
        "cost_usd": cost,
        "sale_usd": sale,
        "price_usd": sale,
        "billing_model": billing_model,
        "billing_desc": f"{cost}U {billing_model}",
        "full_desc": gw_name,
        "description": desc or None,
    }


def main():
    by_supplier: dict = {}
    flat_list = []
    suppliers = set()
    countries = set()

    for line in RAW.split("\n"):
        line = line.strip()
        if not line:
            continue
        item = parse_gateway(line)
        if not item:
            print(f"SKIP: {line}")
            continue

        sn = item["supplier"]
        suppliers.add(sn)
        countries.add(item["country_code"])

        if sn not in by_supplier:
            by_supplier[sn] = {
                "channel_code": item["channel_code"],
                "items": [],
            }
        by_supplier[sn]["items"].append(item)
        flat_list.append(item)

    data = {
        "generated_at": str(date.today()),
        "source": "语音报价截图 2026-04",
        "total_records": len(flat_list),
        "supplier_count": len(suppliers),
        "country_count": len(countries),
        "currency": "USD",
        "by_supplier": by_supplier,
        "flat_list": flat_list,
    }

    out = Path(__file__).resolve().parent.parent / "data" / "resource_voice_pricing.json"
    out = Path("/var/smsc/data/resource_voice_pricing.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"生成完成: {len(flat_list)} 条报价, {len(suppliers)} 个供应商, {len(countries)} 个国家")
    print(f"输出文件: {out}")

    # 按供应商统计
    for sn, info in sorted(by_supplier.items()):
        items = info["items"]
        ccs = set(i["country_code"] for i in items)
        print(f"  {sn}: {len(items)} 条, 覆盖 {len(ccs)} 个国家")


if __name__ == "__main__":
    main()
