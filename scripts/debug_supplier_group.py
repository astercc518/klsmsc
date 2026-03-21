#!/usr/bin/env python3
"""
供应商群解析诊断脚本 - 模拟 Bot 的 _resolve_supplier_group_for_account 逻辑
用法: 
  cd /var/smsc && docker compose exec api python /app/../scripts/debug_supplier_group.py 17
  cd /var/smsc && docker compose exec api python /app/../scripts/debug_supplier_group.py --tg-id 6650783812

或通过 API (需管理员 Token):
  curl "http://localhost:8000/api/v1/admin/debug/supplier-group?account_id=17" -H "Authorization: Bearer <token>"
  curl "http://localhost:8000/api/v1/admin/debug/supplier-group?tg_id=6650783812" -H "Authorization: Bearer <token>"
"""
import os
import sys
import asyncio

# 添加 backend 到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

async def main():
    account_id = None
    tg_id = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == '--tg-id' and i + 2 < len(sys.argv):
            tg_id = int(sys.argv[i + 2])
            break
        elif arg.isdigit():
            account_id = int(arg)
            break

    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if tg_id and not account_id:
            # 按 TG ID 查 account_id
            r = await db.execute(
                text("SELECT account_id FROM telegram_bindings WHERE tg_id=:tid AND is_active=1"),
                {"tid": tg_id}
            )
            row = r.first()
            if not row:
                print(f"❌ TG 用户 {tg_id} 未绑定账户")
                return
            account_id = row[0]
            print(f"TG 用户 {tg_id} -> 账户 ID {account_id}")

        if not account_id:
            print("用法: python debug_supplier_group.py <account_id>")
            print("  或: python debug_supplier_group.py --tg-id <telegram_user_id>")
            return

        print(f"\n=== 诊断账户 {account_id} 的供应商群解析 ===\n")

        # 1. 账户绑定的通道
        r = await db.execute(
            text("SELECT channel_id, priority FROM account_channels WHERE account_id=:aid ORDER BY priority DESC"),
            {"aid": account_id}
        )
        bound = r.all()
        channel_ids = [row[0] for row in bound]
        print(f"1. 账户绑定通道: {bound if bound else '无'}")
        if not channel_ids:
            r2 = await db.execute(text("""
                SELECT id FROM channels WHERE status='active' AND is_deleted=0 ORDER BY priority DESC
            """))
            channel_ids = [row[0] for row in r2.all()]
            print(f"   (无绑定，使用全部通道: {channel_ids})")

        if not channel_ids:
            print("\n❌ 无可用通道")
            return

        # 2. 查 supplier_channels + suppliers
        placeholders = ",".join([str(c) for c in channel_ids])
        r3 = await db.execute(text(f"""
            SELECT sc.channel_id, s.id as supplier_id, s.supplier_name, s.telegram_group_id
            FROM supplier_channels sc
            JOIN suppliers s ON sc.supplier_id = s.id
            WHERE sc.channel_id IN ({placeholders})
              AND sc.status = 'active'
              AND s.is_deleted = 0
        """))
        rows = r3.all()
        print(f"\n2. 通道-供应商关联:")
        for row in rows:
            tg = row[3] or "(空)"
            print(f"   channel_id={row[0]} supplier={row[2]} (id={row[1]}) telegram_group_id={tg}")

        # 3. 解析结果
        resolved = None
        for row in rows:
            if row[3] and str(row[3]).strip():
                resolved = str(row[3]).strip()
                print(f"\n✅ 解析到: telegram_group_id = {resolved} (来自 {row[2]})")
                break
        if not resolved:
            print("\n❌ 未找到配置了 telegram_group_id 的供应商")
            print("   请在「供应商管理」中为通道关联的供应商配置「Telegram 群组 ID」")

if __name__ == '__main__':
    asyncio.run(main())
