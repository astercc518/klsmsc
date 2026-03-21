#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据短信资源报价 (data/resource_pricing.json) 生成开户模板

规则:
- 模板名称: 供应商名称 + 国家名称 (如: 一正通信澳大利亚)
- 默认售价: 与报价表成本价一致 (cost_usd)
- 仅处理 type=SMS 的报价

用法:
  cd /var/smsc && python scripts/generate_account_templates_from_pricing.py

或在 api 容器中:
  docker compose run --rm -v $(pwd):/workspace -w /workspace api python scripts/generate_account_templates_from_pricing.py
"""
import json
import os
import sys
from decimal import Decimal

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
_BACKEND = os.path.join(_ROOT, 'backend')
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# 数据文件路径
PRICING_JSON = os.path.join(_ROOT, 'data', 'resource_pricing.json')


def main():
    if not os.path.exists(PRICING_JSON):
        print(f"错误: 文件不存在 {PRICING_JSON}")
        sys.exit(1)

    with open(PRICING_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    by_supplier = data.get('by_supplier', {})
    if not by_supplier:
        print("错误: resource_pricing.json 中无 by_supplier 数据")
        sys.exit(1)

    # 收集所有 SMS 报价条目
    templates_to_create = []
    for supplier_name, supplier_data in by_supplier.items():
        channel_code = supplier_data.get('channel_code', 'SUP_UNKNOWN')
        countries = supplier_data.get('countries', {})
        for country_code, country_data in countries.items():
            if (country_data.get('type') or '').upper() != 'SMS':
                continue
            country_name = country_data.get('country', '')
            price = country_data.get('cost_usd') or 0
            if not country_name or price <= 0:
                continue
            template_name = f"{supplier_name}{country_name}"
            templates_to_create.append({
                'template_name': template_name,
                'template_code': f"SMS_{country_code}_{channel_code}",
                'business_type': 'sms',
                'country_code': country_code,
                'country_name': country_name,
                'default_price': Decimal(str(round(price, 4))),
            })

    print(f"从报价表解析到 {len(templates_to_create)} 条短信开户模板")

    try:
        import pymysql
    except ImportError:
        print("请确保在 api 容器中运行（含 pymysql）")
        sys.exit(1)

    host = os.environ.get('DATABASE_HOST', 'localhost')
    port = int(os.environ.get('DATABASE_PORT', 3306))
    user = os.environ.get('DATABASE_USER', 'smsuser')
    pwd = os.environ.get('DATABASE_PASSWORD', 'smspass123')
    db_name = os.environ.get('DATABASE_NAME', 'sms_system')

    conn = pymysql.connect(
        host=host, port=port, user=user, password=pwd, db=db_name, charset='utf8mb4'
    )

    inserted = 0
    skipped = 0

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            for t in templates_to_create:
                # 检查是否已存在（按 template_code 或 template_name）
                cur.execute(
                    "SELECT id FROM account_templates WHERE template_code = %s OR template_name = %s",
                    (t['template_code'], t['template_name'])
                )
                if cur.fetchone():
                    skipped += 1
                    continue

                cur.execute(
                    """INSERT INTO account_templates
                       (template_code, template_name, business_type, country_code, country_name,
                        default_price, status, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW(), NOW())""",
                    (
                        t['template_code'],
                        t['template_name'],
                        t['business_type'],
                        t['country_code'],
                        t['country_name'],
                        str(t['default_price']),
                    )
                )
                inserted += 1
                print(f"  新增: {t['template_name']} ({t['country_code']}) ${t['default_price']}")

        conn.commit()
    finally:
        conn.close()

    print(f"\n完成: 新增 {inserted} 条，跳过已存在 {skipped} 条")


if __name__ == '__main__':
    main()
