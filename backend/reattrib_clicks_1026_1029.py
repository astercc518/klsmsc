"""历史再归因：对 batch 1026/1029 已 status='success' 的注水点击任务，
调用生产归因函数 _attribute_short_link_click 补记短链点击(幂等)。
原因：修复前 web_click_task 成功不归因，计数只靠外域 66c.eu 回流(~15%)。
这些点击任务是已落 water_injection_logs 的真实 headless 访问，此处补上漏记的归因。
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text
from app.workers.batch_worker import _make_fresh_session
from app.workers.web_worker import _attribute_short_link_click
from app.modules.common.admin_user import AdminUser  # noqa: F401  ORM 注册
from app.modules.common.account import Account  # noqa: F401

BATCHES = (1026, 1029)
DRY_RUN = os.getenv("DRY_RUN", "1") == "1"


async def main():
    eng, factory = _make_fresh_session()
    # 取每个成功点击任务(按 sms_log 去重，取一条带 proxy_ip/ua)
    async with factory() as db:
        recs = (await db.execute(text(
            """
            SELECT w.sms_log_id, MIN(w.proxy_ip) ip, MIN(w.user_agent) ua
            FROM water_injection_logs w
            WHERE w.batch_id IN :bids AND w.action='click' AND w.status='success'
            GROUP BY w.sms_log_id
            """.replace(":bids", str(BATCHES))
        ))).all()
    print(f"成功点击任务(去重 sms_log): {len(recs)}")
    if DRY_RUN:
        print(">> DRY_RUN：不写库")
        await eng.dispose()
        return

    attributed = 0
    skipped = 0
    for sms_log_id, ip, ua in recs:
        ok = await _attribute_short_link_click(factory, sms_log_id, client_ip=ip, user_agent=ua)
        if ok:
            attributed += 1
        else:
            skipped += 1
    print(f"再归因完成：新增点击 {attributed}，跳过(已记/无短链) {skipped}")
    await eng.dispose()


asyncio.run(main())
