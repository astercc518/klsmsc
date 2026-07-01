"""
数据库运维定时任务（审计 P0-8 / P0-10）。

设计原则：只做安全、幂等、低频的运维动作；对不可逆/重写型操作(如非空 p_future 的大改写)
一律降级为告警交人工在维护窗口处理，绝不在 beat 里静默执行重活。
"""
import os
import re
from datetime import datetime, timedelta

from sqlalchemy import text

from app.workers.celery_app import celery_app
from app.workers.sms_worker import _make_session, _run_async
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 分区键 UNIX_TIMESTAMP(submit_time) 的边界须与既有分区口径一致。既有边界按会话 +08:00 生成
# （容器/MySQL/datetime.now() 全是北京时间，enable_utc=False），故本任务统一 SET +08:00 后再算。
_PARTITION_TZ = "+08:00"


def _month_add(year: int, month: int, delta: int):
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


@celery_app.task(name="ensure_sms_logs_partitions")
def ensure_sms_logs_partitions():
    """每月自动扩展 sms_logs 未来月分区，杜绝 p_future 积压导致分区裁剪失效（审计 P0-8）。

    生产 sms_logs 已按月分区且未来分区已预建若干月，但无自动扩展机制——预建的未来分区一旦
    用尽，新数据会全部落入 p_future，分区裁剪失效、报表退化为全表扫描。本任务保证任意时刻都
    至少预留 PARTITION_KEEP_AHEAD_MONTHS 个空的未来月分区。

    安全性：新增分区通过 REORGANIZE **空的** p_future 实现，纯元数据操作、瞬时无数据搬迁。
    若 p_future 意外非空(缓冲已失守)，超过阈值则不擅自大改写，仅记 CRITICAL 交人工窗口处理。
    """
    return _run_async(_do_ensure_partitions())


async def _do_ensure_partitions():
    keep_ahead = int(os.getenv("PARTITION_KEEP_AHEAD_MONTHS", "6"))
    pfuture_alert = int(os.getenv("PARTITION_PFUTURE_ALERT_ROWS", "500000"))

    eng, Session = _make_session()
    try:
        async with Session() as db:
            await db.execute(text(f"SET SESSION time_zone = '{_PARTITION_TZ}'"))

            rows = (await db.execute(text(
                "SELECT PARTITION_NAME, TABLE_ROWS FROM information_schema.PARTITIONS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sms_logs' "
                "AND PARTITION_NAME IS NOT NULL"
            ))).all()
            if not rows:
                logger.warning("ensure_partitions: sms_logs 无分区信息(未分区表?)，跳过")
                return {"skipped": "not_partitioned"}

            month_parts = {}
            pfuture_rows = 0
            for name, trows in rows:
                if name == "p_future":
                    pfuture_rows = int(trows or 0)
                    continue
                m = re.match(r"^p(\d{4})(\d{2})$", name or "")
                if m:
                    month_parts[(int(m.group(1)), int(m.group(2)))] = int(trows or 0)

            if not month_parts:
                logger.warning("ensure_partitions: 未识别到月分区(pYYYYMM)，跳过以免误操作")
                return {"skipped": "no_month_partitions"}

            # p_future 非空 = 未来分区曾用尽、缓冲失守。分裂它会重写这些行(可能数 GB)，不在 beat 里做。
            if pfuture_rows > pfuture_alert:
                logger.critical(
                    f"ensure_partitions: p_future 已积压 {pfuture_rows} 行(>{pfuture_alert})，"
                    f"分区裁剪已失效！需人工在维护窗口 REORGANIZE 抢救，本任务不擅自大改写。"
                )
                return {"alert": "p_future_backlog", "p_future_rows": pfuture_rows}

            latest = max(month_parts.keys())
            now = datetime.now()
            target = _month_add(now.year, now.month, keep_ahead)

            # 逐月补齐 (latest, target]
            to_add = []
            cur = latest
            while cur < target:
                cur = _month_add(cur[0], cur[1], 1)
                if cur > target:
                    break
                if cur not in month_parts:
                    to_add.append(cur)

            if not to_add:
                logger.info(
                    f"ensure_partitions: 无需新增，最新月分区 p{latest[0]:04d}{latest[1]:02d}，"
                    f"已覆盖至 now+{keep_ahead} 月; p_future_rows={pfuture_rows}"
                )
                return {"added": 0, "latest": f"p{latest[0]:04d}{latest[1]:02d}",
                        "p_future_rows": pfuture_rows}

            defs = []
            for (y, mth) in to_add:
                ny, nm = _month_add(y, mth, 1)  # 分区上界 = 次月 1 日
                defs.append(
                    f"PARTITION p{y:04d}{mth:02d} VALUES LESS THAN "
                    f"(UNIX_TIMESTAMP('{ny:04d}-{nm:02d}-01'))"
                )
            defs.append("PARTITION p_future VALUES LESS THAN MAXVALUE")
            alter = (
                "ALTER TABLE sms_logs REORGANIZE PARTITION p_future INTO ("
                + ", ".join(defs) + ")"
            )
            await db.execute(text(alter))
            await db.commit()
            names = [f"p{y:04d}{m:02d}" for (y, m) in to_add]
            logger.info(f"ensure_partitions: 新增 {len(names)} 个未来月分区 {names}")
            return {"added": len(names), "partitions": names}
    except Exception as e:
        logger.error(f"ensure_partitions 失败(忽略,下轮重试): {e}", exc_info=e)
        return {"error": str(e)}
    finally:
        await eng.dispose()


@celery_app.task(name="assert_fund_conservation")
def assert_fund_conservation():
    """每日资金守恒断言（审计 P0-10）——只读校验，异常记 WARNING/CRITICAL，供告警接入。

    校验项：
      ① 负余额账户：预付费扣费本应原子 CAS 防超扣(pricing.py)，出现 balance<0 说明有绕过 CAS 的
         扣费/调账路径（审计 C3）。
      ② 重复退款检测：同一 message_id 在 balance_logs(change_type='refund') 被贷记多次，即 P0-3
         并发重复退款的特征。（注：退款台账含 per-message 与批次聚合两类不同账层，故不做总额守恒，
         只按 message_id 去重判重，避免误报。）
    """
    return _run_async(_do_assert_fund_conservation())


async def _do_assert_fund_conservation():
    eng, Session = _make_session()
    try:
        async with Session() as db:
            # ① 负余额账户（预付费 CAS 本应防超扣，出现负余额=有绕过 CAS 的扣费/调账路径）
            neg = (await db.execute(text(
                "SELECT id, account_name, balance FROM accounts "
                "WHERE balance < 0 AND is_deleted = 0 ORDER BY balance ASC LIMIT 50"
            ))).all()
            if neg:
                logger.warning(
                    f"资金守恒[负余额]: {len(neg)} 个账户余额为负(疑超扣): "
                    + ", ".join(f"#{r[0]}({r[1]})={r[2]}" for r in neg[:20])
                )

            # ② 重复退款检测（P0-3 特征）：同一 message_id 在 refund 台账被贷记多次即重复退款。
            #    仅 per-message 退款(描述含 message_id=)可判重；批次聚合退款无 message_id，天然跳过。
            dup = int((await db.execute(text(
                "SELECT COALESCE(SUM(c-1),0) FROM ("
                "  SELECT REGEXP_SUBSTR(description,'message_id=[^ ]+') mid, COUNT(*) c "
                "  FROM balance_logs WHERE change_type='refund' AND description LIKE '%message_id=%' "
                "  GROUP BY mid HAVING c>1"
                ") x"
            ))).scalar() or 0)
            if dup > 0:
                logger.critical(
                    f"资金守恒[重复退款]: 检测到 {dup} 笔重复退款贷记(同一 message_id 多次 refund)，"
                    f"疑并发重复退款(P0-3)，请核账"
                )
            else:
                logger.info("资金守恒[重复退款]: 无同一 message_id 多次退款")

            return {
                "negative_balance_accounts": len(neg),
                "duplicate_refund_credits": dup,
            }
    except Exception as e:
        logger.error(f"assert_fund_conservation 失败(忽略): {e}", exc_info=e)
        return {"error": str(e)}
    finally:
        await eng.dispose()
