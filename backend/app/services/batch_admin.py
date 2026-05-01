"""
批次管理服务（管理员任务管理页用）

四个核心动作：
  pause_batch          processing/pending → paused
  resume_batch         paused → processing；可选切换通道
  clear_batch_queue    paused → cancelled，未发 sms_logs.status='cancelled'
  switch_channel_for_unsent
                       通道切换 + 重新计费 + 余额调差（独立函数，被 resume 复用）

并发：每次状态修改用 SELECT ... FOR UPDATE 锁批次行，避免双管理员同时操作。
审计：每个动作返回的 detail 由调用方写入 admin_operation_log。
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sms.sms_batch import SmsBatch, BatchStatus
from app.modules.sms.sms_log import SMSLog
from app.modules.sms.channel import Channel
from app.modules.common.account import Account
from app.modules.common.balance_log import BalanceLog
from app.modules.sms.batch_utils import update_batch_progress
from app.utils.cache import get_cache_manager
from app.utils.errors import InsufficientBalanceError
from app.utils.logger import get_logger

logger = get_logger(__name__)


# 仍可干预的 sms_log.status（worker 还没把它送出去，可重新入队/改通道/取消）
_UNSENT_STATUSES = ("pending", "queued")


# ---------- internal helpers ----------

async def _lock_batch(db: AsyncSession, batch_id: int) -> Optional[SmsBatch]:
    return (await db.execute(
        select(SmsBatch).where(SmsBatch.id == int(batch_id)).with_for_update()
    )).scalar_one_or_none()


async def _count_unsent(db: AsyncSession, batch_id: int) -> int:
    from sqlalchemy import func
    return (await db.execute(
        select(func.count(SMSLog.id)).where(
            and_(SMSLog.batch_id == batch_id, SMSLog.status.in_(_UNSENT_STATUSES))
        )
    )).scalar() or 0


async def _select_unsent_logs(db: AsyncSession, batch_id: int) -> List[SMSLog]:
    return list((await db.execute(
        select(SMSLog).where(
            and_(SMSLog.batch_id == batch_id, SMSLog.status.in_(_UNSENT_STATUSES))
        )
    )).scalars().all())


async def _validate_channel_for_country(
    db: AsyncSession, channel_id: int, country_code: Optional[str]
) -> Tuple[Optional[Channel], Optional[str]]:
    """返回 (channel, error_msg)。channel 为 None 即校验失败。"""
    ch = (await db.execute(
        select(Channel).where(
            Channel.id == int(channel_id),
            Channel.is_deleted == False,  # noqa: E712
            Channel.status == "active",
        )
    )).scalar_one_or_none()
    if not ch:
        return None, f"通道 {channel_id} 不可用（不存在/已删/未启用）"
    # 路由规则覆盖检查（仅对有 country_code 的批次校验）
    if country_code:
        from app.core.router import RoutingEngine
        try:
            channels = await RoutingEngine(db)._get_available_channels(country_code)
        except Exception as e:
            return None, f"路由规则查询失败: {e}"
        if not any(c.id == ch.id for c in channels):
            return None, f"通道 {ch.channel_code} 未配置 country={country_code} 的路由规则"
    return ch, None


# ---------- pause ----------

async def pause_batch(db: AsyncSession, batch_id: int, admin_username: str) -> dict:
    batch = await _lock_batch(db, batch_id)
    if not batch:
        return {"success": False, "reason": "批次不存在"}
    if batch.status not in (BatchStatus.PROCESSING, BatchStatus.PENDING):
        return {"success": False, "reason": f"当前状态 {batch.status.value if hasattr(batch.status,'value') else batch.status} 不允许暂停"}
    unsent = await _count_unsent(db, batch_id)
    batch.status = BatchStatus.PAUSED
    await db.commit()
    logger.info(f"批次暂停: batch_id={batch_id} unsent={unsent} admin={admin_username}")
    return {
        "success": True,
        "batch_id": batch.id,
        "status": "paused",
        "unsent_count": unsent,
        "warning": "已重路由到 SMPP 队列的消息可能仍会被上游网关发出（暂停只对未到上游的消息有效）" if unsent else None,
    }


# ---------- clear queue ----------

async def clear_batch_queue(db: AsyncSession, batch_id: int, admin_username: str) -> dict:
    batch = await _lock_batch(db, batch_id)
    if not batch:
        return {"success": False, "reason": "批次不存在"}
    if batch.status != BatchStatus.PAUSED:
        return {"success": False, "reason": "仅 paused 状态可清空队列"}

    r = await db.execute(
        update(SMSLog)
        .where(and_(SMSLog.batch_id == batch_id, SMSLog.status.in_(_UNSENT_STATUSES)))
        .values(status="cancelled", error_message="管理员清空队列")
    )
    cancelled = r.rowcount or 0
    batch.status = BatchStatus.CANCELLED
    if not batch.error_message:
        batch.error_message = "管理员清空队列"
    await db.commit()
    try:
        await update_batch_progress(db, batch_id)
    except Exception as e:
        logger.warning(f"清空后刷新批次进度失败 batch={batch_id}: {e}")
    logger.info(f"批次清空: batch_id={batch_id} cancelled_logs={cancelled} admin={admin_username}")
    return {
        "success": True,
        "batch_id": batch_id,
        "cancelled_logs": cancelled,
        "status": "cancelled",
    }


# ---------- switch channel & re-price ----------

async def _compute_repricing(
    db: AsyncSession,
    logs: List[SMSLog],
    new_channel: Channel,
) -> Tuple[List[Tuple[SMSLog, Decimal, Decimal, Decimal]], Decimal]:
    """
    返回 (rows_with_prices, total_diff)
    rows_with_prices: [(log, new_cost, new_sell, diff_per_log), ...]
    total_diff: sum of (new_sell - old_sell)
    diff > 0 → 客户多支付（扣余额）；diff < 0 → 退回。
    """
    from app.core.pricing import PricingEngine
    pe = PricingEngine(db)
    out = []
    total_diff = Decimal("0")
    # 缓存通道 + 国家 单价（同 batch 多条记录通常落同一国家）
    price_cache: dict = {}
    cost_cache: dict = {}
    for log in logs:
        country = log.country_code or ""
        cache_key = (new_channel.id, country, log.account_id)
        if cache_key not in price_cache:
            price_info = await pe.get_price(new_channel.id, country, mnc=None, account_id=log.account_id)
            if not price_info:
                raise ValueError(f"新通道 {new_channel.channel_code} 缺少 country={country} 销售价（账户 {log.account_id}）")
            price_cache[cache_key] = Decimal(str(price_info["price"]))
        new_unit_sell = price_cache[cache_key]
        if (new_channel.id, country) not in cost_cache:
            cost_cache[(new_channel.id, country)] = await pe.resolve_base_cost_per_sms(
                new_channel.id, country, new_channel
            )
        new_unit_cost = cost_cache[(new_channel.id, country)]

        msg_count = int(log.message_count or 1)
        new_sell_total = new_unit_sell * msg_count
        new_cost_total = new_unit_cost * msg_count
        old_sell_total = Decimal(str(log.selling_price or 0))
        diff = new_sell_total - old_sell_total
        total_diff += diff
        out.append((log, new_cost_total, new_sell_total, diff))
    return out, total_diff


async def switch_channel_for_unsent(
    db: AsyncSession,
    batch_id: int,
    new_channel_id: int,
    admin_username: str,
    *,
    skip_lock: bool = False,
) -> dict:
    """
    通道切换 + 重新计费。原子性：
      预校验 → 计算调差 → 扣/退余额（原子）→ UPDATE sms_logs → 写 BalanceLog

    skip_lock=True 时不再 SELECT FOR UPDATE 批次（被 resume_batch 内部调用的场景）
    """
    if not skip_lock:
        batch = await _lock_batch(db, batch_id)
        if not batch:
            return {"success": False, "reason": "批次不存在"}
    else:
        batch = (await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))).scalar_one_or_none()
        if not batch:
            return {"success": False, "reason": "批次不存在"}

    # 取批次的 country_code（取首条未发的）
    country_sample = (await db.execute(
        select(SMSLog.country_code).where(
            and_(SMSLog.batch_id == batch_id, SMSLog.status.in_(_UNSENT_STATUSES))
        ).limit(1)
    )).scalar_one_or_none()

    new_channel, err = await _validate_channel_for_country(db, new_channel_id, country_sample)
    if err:
        return {"success": False, "reason": err}

    logs = await _select_unsent_logs(db, batch_id)
    if not logs:
        return {"success": False, "reason": "无未发条目可切换"}

    # 检查不与原通道相同（取多数）
    old_channel_ids = {log.channel_id for log in logs if log.channel_id}
    if len(old_channel_ids) == 1 and new_channel.id in old_channel_ids:
        return {"success": False, "reason": "新通道与当前通道相同"}

    try:
        rows_with_prices, total_diff = await _compute_repricing(db, logs, new_channel)
    except ValueError as e:
        return {"success": False, "reason": str(e)}

    # 原子扣/退余额
    account_id = batch.account_id
    bal_before = (await db.execute(select(Account.balance).where(Account.id == account_id))).scalar() or Decimal("0")
    if total_diff > 0:
        # 余额需 ≥ total_diff
        r = await db.execute(
            update(Account)
            .where(and_(Account.id == account_id, Account.balance >= total_diff))
            .values(balance=Account.balance - total_diff)
        )
        if r.rowcount == 0:
            raise InsufficientBalanceError(
                required=float(total_diff),
                available=float(bal_before),
            )
    elif total_diff < 0:
        await db.execute(
            update(Account).where(Account.id == account_id).values(balance=Account.balance + abs(total_diff))
        )

    bal_after = (await db.execute(select(Account.balance).where(Account.id == account_id))).scalar() or Decimal("0")

    # 批量更新 sms_logs（每条独立单价不同时只能逐条 UPDATE；用 case-when 也行但 ORM 简单点逐条）
    for log, new_cost, new_sell, _diff in rows_with_prices:
        await db.execute(
            update(SMSLog).where(SMSLog.id == log.id).values(
                channel_id=new_channel.id,
                cost_price=new_cost,
                selling_price=new_sell,
            )
        )

    # BalanceLog 调差记录（仅当真的发生扣/退）
    if total_diff != 0:
        chg_amount = -total_diff if total_diff > 0 else abs(total_diff)  # 与 charge 字段语义对齐
        change_type = "adjustment"
        db.add(BalanceLog(
            account_id=account_id,
            change_type=change_type,
            amount=chg_amount,
            balance_after=float(bal_after) if bal_after is not None else 0.0,
            description=(
                f"通道切换调差: batch={batch_id} 原通道→{new_channel.channel_code}(#{new_channel.id}) "
                f"未发条数={len(logs)} diff={total_diff}"
            )[:500],
        ))

    await db.commit()

    # 失效余额缓存
    try:
        cm = await get_cache_manager()
        await cm.set(f"account:{account_id}:balance", float(bal_after), ttl=60)
    except Exception as e:
        logger.warning(f"切换通道后余额缓存刷新失败 account={account_id}: {e}")

    logger.info(
        f"批次切换通道: batch={batch_id} new_channel={new_channel.channel_code} "
        f"unsent={len(logs)} diff={total_diff} admin={admin_username}"
    )
    return {
        "success": True,
        "batch_id": batch_id,
        "new_channel_id": new_channel.id,
        "new_channel_code": new_channel.channel_code,
        "unsent_count": len(logs),
        "total_diff": float(total_diff),
        "balance_before": float(bal_before),
        "balance_after": float(bal_after),
    }


# ---------- preview switch (read-only) ----------

async def preview_switch_channel(
    db: AsyncSession, batch_id: int, new_channel_id: int
) -> dict:
    """只读预览：返回未发条数、调差、余额变化预估。不动数据。"""
    batch = (await db.execute(select(SmsBatch).where(SmsBatch.id == batch_id))).scalar_one_or_none()
    if not batch:
        return {"success": False, "reason": "批次不存在"}

    country_sample = (await db.execute(
        select(SMSLog.country_code).where(
            and_(SMSLog.batch_id == batch_id, SMSLog.status.in_(_UNSENT_STATUSES))
        ).limit(1)
    )).scalar_one_or_none()

    new_channel, err = await _validate_channel_for_country(db, new_channel_id, country_sample)
    if err:
        return {"success": False, "reason": err}

    logs = await _select_unsent_logs(db, batch_id)
    if not logs:
        return {"success": False, "reason": "无未发条目可切换"}

    old_channel_ids = {log.channel_id for log in logs if log.channel_id}
    same_channel = (len(old_channel_ids) == 1 and new_channel.id in old_channel_ids)
    if same_channel:
        return {"success": False, "reason": "新通道与当前通道相同"}

    try:
        _, total_diff = await _compute_repricing(db, logs, new_channel)
    except ValueError as e:
        return {"success": False, "reason": str(e)}

    bal = (await db.execute(select(Account.balance).where(Account.id == batch.account_id))).scalar() or Decimal("0")
    enough_balance = (total_diff <= 0) or (Decimal(str(bal)) >= total_diff)

    return {
        "success": True,
        "batch_id": batch_id,
        "new_channel_id": new_channel.id,
        "new_channel_code": new_channel.channel_code,
        "unsent_count": len(logs),
        "total_diff": float(total_diff),
        "balance_before": float(bal),
        "balance_after_estimate": float(bal - total_diff),
        "balance_sufficient": bool(enough_balance),
    }


# ---------- resume ----------

async def resume_batch(
    db: AsyncSession,
    batch_id: int,
    admin_username: str,
    new_channel_id: Optional[int] = None,
) -> dict:
    """恢复发送。可选切换通道（若指定 new_channel_id）。"""
    batch = await _lock_batch(db, batch_id)
    if not batch:
        return {"success": False, "reason": "批次不存在"}
    if batch.status != BatchStatus.PAUSED:
        return {"success": False, "reason": "仅 paused 状态可恢复"}

    switch_result = None
    if new_channel_id:
        switch_result = await switch_channel_for_unsent(
            db, batch_id, new_channel_id, admin_username, skip_lock=True
        )
        if not switch_result.get("success"):
            return switch_result

    batch.status = BatchStatus.PROCESSING
    await db.commit()

    # 重新入队所有未发的 sms_logs（worker 在 _send_sms_async 入口看到 status=processing 会正常发送）
    from app.utils.queue import QueueManager
    logs = await _select_unsent_logs(db, batch_id)
    queued_ok, queued_fail = 0, 0
    for log in logs:
        if QueueManager.queue_sms(log.message_id):
            queued_ok += 1
        else:
            queued_fail += 1

    logger.info(
        f"批次恢复: batch_id={batch_id} unsent={len(logs)} ok={queued_ok} fail={queued_fail} "
        f"new_channel={new_channel_id} admin={admin_username}"
    )
    return {
        "success": True,
        "batch_id": batch_id,
        "status": "processing",
        "unsent_count": len(logs),
        "requeued_ok": queued_ok,
        "requeued_fail": queued_fail,
        "switch_channel": switch_result,
    }
