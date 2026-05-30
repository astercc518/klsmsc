#!/usr/bin/env python3
"""
一次性回填：把现有所有通道价格(country_pricing)倒灌进资源报价(supplier_rates)。

逐 (channel_id, country_code) 取**最新生效**的一条价格，复用 admin._sync_supplier_rate
执行同步——逻辑与"保存通道价格自动联动"完全一致：
  - 通道未关联供应商(channels.supplier_id 为空) → 跳过；
  - 命中已有报价行 → 更新 cost_price、标 price_source='channel'，sell_price 不动；
  - 无 → 新建(cost=sell=price，resource_type 取该供应商众数)。

幂等：重复运行只会把 cost 刷成同值。

用法(api 容器内，工作目录 /app)：
  docker compose exec -w /app -e PYTHONPATH=/app api python scripts/backfill_supplier_rates_from_pricing.py
  # 加 --dry-run 只统计、不写库
"""
import asyncio
import sys

import app.main  # noqa: F401  触发全部 ORM 模型注册
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.api.v1.admin import _sync_supplier_rate
from app.modules.sms.country_pricing import CountryPricing
from app.modules.sms.channel import Channel


async def main(dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        # 有 supplier_id 的通道集合（无则 _sync 内部会跳过，这里只为统计）
        ch_rows = (await db.execute(
            select(Channel.id, Channel.supplier_id)
        )).all()
        sup_map = {cid: sid for cid, sid in ch_rows}

        # 每 (channel_id, country_code) 取最新 effective_date、再取最大 id 的一条
        latest = (await db.execute(
            select(
                CountryPricing.channel_id,
                CountryPricing.country_code,
                func.max(CountryPricing.effective_date).label("eff"),
            ).group_by(CountryPricing.channel_id, CountryPricing.country_code)
        )).all()

        affected = 0            # 受影响的 supplier_rates 行数
        synced_pairs = 0        # 实际触发同步的 (通道,国家) 组数
        skipped_no_supplier = 0 # 通道无供应商被跳过的组数
        seen_channels_skipped = set()

        for channel_id, country_code, eff in latest:
            if not sup_map.get(channel_id):
                skipped_no_supplier += 1
                seen_channels_skipped.add(channel_id)
                continue

            # 取该 (通道,国家,最新生效日) 下 id 最大的价格行
            row = (await db.execute(
                select(CountryPricing)
                .where(
                    CountryPricing.channel_id == channel_id,
                    CountryPricing.country_code == country_code,
                    CountryPricing.effective_date == eff,
                )
                .order_by(CountryPricing.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            if row is None:
                continue

            if dry_run:
                synced_pairs += 1
                continue

            n = await _sync_supplier_rate(
                db, row.channel_id, row.country_code, row.price_per_sms,
                country_name=row.country_name, currency=row.currency or "USD",
            )
            affected += n
            if n:
                synced_pairs += 1

        if not dry_run:
            await db.commit()

    tag = "[dry-run] " if dry_run else ""
    print(f"{tag}country_pricing 去重后 {len(latest)} 组 (通道,国家)")
    print(f"{tag}已同步 {synced_pairs} 组，受影响 supplier_rates {affected} 行")
    print(f"{tag}因通道未关联供应商跳过 {skipped_no_supplier} 组"
          f"（涉及 {len(seen_channels_skipped)} 个通道）")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
