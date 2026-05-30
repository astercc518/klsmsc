#!/usr/bin/env python3
"""
回填 channels.supplier_id —— 建立通道↔供应商硬主键。

按 channel_code -> supplier_name 的显式映射(已人工评审)执行，
不做运行时模糊匹配。幂等：仅回填 supplier_id 仍为 NULL 的通道，
不覆盖人工已设的值。运行后打印「已映射 / 已跳过 / 未匹配」对账清单。

用法(在 api 容器内，工作目录 /app)：
  docker compose exec api python scripts/backfill_channel_supplier.py
  # 加 --dry-run 只看清单不写库
"""
import asyncio
import sys

from sqlalchemy import text

from app.database import AsyncSessionLocal

# channel_code -> supplier_name(suppliers.supplier_name，精确匹配 is_deleted=0)
CHANNEL_TO_SUPPLIER = {
    "TS_zhilian": "TS通信",
    "Ue_zhilian": "ueasy通信",
    "KM_kafa": "KMI通信",
    "KM_888_zhilian": "KMI通信",
    "KM_meiguo_52": "KMI通信",
    "TS_feilvbin": "TS通信",
    "YZ_kafa": "一正通信",
    "YZ_zhilian": "一正通信",
    "YZ_OTP": "一正通信",
    "woId_kafa": "WOID通信",
    "KF_zhilian": "葵芳通信",
    "YX_kafa": "粤讯通信",
    "YX_zhilian": "粤讯通信",
    "YX_OTP": "粤讯通信",
    "CY_TH_zhilian": "创优通信",
    "CY_PH_zhilian": "创优通信",
    "HJ_888_kafa": "汇聚通信",
    "BO_zhilian": "BO通信",
    "BW_55_ZL": "百悟通信",
    "LCY_zhilian": "乐橙通信",
    "LCY_234_ZL": "乐橙通信",
    "TSD_TH_zhilian": "TSD通信",
    "WC_880_KF": "WC通信",
    "KL_888_GJ": "KL通信",
    "YK_066_Kafa": "云客通信",
    "JD_GP_BL_kafa": "节点通信",
    "JD_robi_kafa": "节点通信",
    "TA_880_zhilian": "塔兰加通信",
    "HY_888_zhilian": "浩域通信",
    "UE_066_BC": "ueasy通信",
    "XW_888_zhilian": "玄武通信",
    "TH_063_zhilian": "TH通信",
    "TS_066_zhilian": "TS通信",
}


async def main(dry_run: bool) -> None:
    mapped, skipped, no_channel, no_supplier = [], [], [], []
    async with AsyncSessionLocal() as db:
        # 供应商名 -> id
        rows = (await db.execute(text(
            "SELECT id, supplier_name FROM suppliers WHERE is_deleted=0"
        ))).fetchall()
        name_to_id = {}
        for sid, name in rows:
            name_to_id.setdefault((name or "").strip(), sid)

        for code, sup_name in CHANNEL_TO_SUPPLIER.items():
            ch = (await db.execute(text(
                "SELECT id, supplier_id FROM channels WHERE channel_code=:c AND is_deleted=0"
            ), {"c": code})).fetchone()
            if ch is None:
                no_channel.append(code)
                continue
            ch_id, cur_sup = ch
            sup_id = name_to_id.get(sup_name)
            if sup_id is None:
                no_supplier.append((code, sup_name))
                continue
            if cur_sup is not None:
                skipped.append((code, cur_sup))
                continue
            if not dry_run:
                await db.execute(text(
                    "UPDATE channels SET supplier_id=:s WHERE id=:i AND supplier_id IS NULL"
                ), {"s": sup_id, "i": ch_id})
            mapped.append((code, sup_name, sup_id))

        if not dry_run:
            await db.commit()

    tag = "[dry-run] " if dry_run else ""
    print(f"{tag}已映射 {len(mapped)} 个通道:")
    for code, name, sid in mapped:
        print(f"  {code:18s} -> {name}(id={sid})")
    if skipped:
        print(f"\n已跳过(supplier_id 已存在) {len(skipped)} 个: " +
              ", ".join(f"{c}(={s})" for c, s in skipped))
    if no_channel:
        print(f"\n⚠ 映射表里有、库中无此 active 通道 {len(no_channel)} 个: " + ", ".join(no_channel))
    if no_supplier:
        print(f"\n⚠ 找不到对应供应商 {len(no_supplier)} 个: " +
              ", ".join(f"{c}->{n}" for c, n in no_supplier))


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
