#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将所有开户模板的默认售价调整为成本价

从 data/resource_pricing.json 读取成本价，按 template_code (SMS_{country}_{channel})
匹配并更新 account_templates.default_price

用法:
  docker compose run --rm -v $(pwd):/workspace -w /workspace api python scripts/update_templates_default_price_to_cost.py
"""
import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)

PRICING_JSON = os.path.join(_ROOT, 'data', 'resource_pricing.json')


def main():
    if not os.path.exists(PRICING_JSON):
        print(f"错误: 文件不存在 {PRICING_JSON}")
        sys.exit(1)

    with open(PRICING_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 构建 (channel_code, country_code) -> cost_usd 映射（仅 SMS）
    cost_map = {}
    for supplier_name, supplier_data in data.get('by_supplier', {}).items():
        channel_code = supplier_data.get('channel_code', '')
        for country_code, country_data in supplier_data.get('countries', {}).items():
            if (country_data.get('type') or '').upper() != 'SMS':
                continue
            cost = country_data.get('cost_usd')
            if cost is not None and cost > 0:
                cost_map[(channel_code, country_code)] = round(cost, 4)

    print(f"从报价表加载 {len(cost_map)} 条短信成本价")

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

    updated = 0
    skipped = 0

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT id, template_code, template_name, default_price FROM account_templates WHERE business_type = 'sms'"
            )
            templates = cur.fetchall()

            for t in templates:
                code = (t['template_code'] or '').strip()
                # template_code 格式: SMS_{country}_{channel} 如 SMS_AU_SUP_YIZHENG
                parts = code.split('_')
                if len(parts) < 3:
                    skipped += 1
                    continue
                country_code = parts[1]
                channel_code = '_'.join(parts[2:])

                key = (channel_code, country_code)
                cost = cost_map.get(key)
                if cost is None:
                    skipped += 1
                    continue

                cur.execute(
                    "UPDATE account_templates SET default_price = %s, updated_at = NOW() WHERE id = %s",
                    (str(cost), t['id'])
                )
                updated += 1
                print(f"  更新: {t['template_name']} ({country_code}) ${t['default_price']} -> ${cost}")

        conn.commit()
    finally:
        conn.close()

    print(f"\n完成: 更新 {updated} 条，跳过 {skipped} 条")


if __name__ == '__main__':
    main()
