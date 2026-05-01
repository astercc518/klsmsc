"""
短信退款服务（P0-1：系统问题导致提交失败时由管理员手动审核退款）

策略：
- 仅 status='failed' 且 refunded_at IS NULL 且 cost_price > 0 才可退
- upstream_message_id IS NULL 是必要条件（拿到上游 ID 即视为已提交）
- 通过 error_message 排除已知"已提交到上游"的失败模式（来自上游 SubmitSMResp）
- 最终需要管理员人工 review 列表中的每一条再批准
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select, update, and_, or_, func, true as sql_true
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sms.sms_log import SMSLog
from app.modules.common.account import Account
from app.modules.common.balance_log import BalanceLog
from app.utils.cache import get_cache_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


# 已提交到上游的失败模式（不退款）
# - "SMPP Error: N"：来自 connector.go:455 SubmitSMResp 非零状态，意味着 PDU 已被上游处理
# - "SMPP DLR: stat=..."：DLR 已收到，意味着上游接收并尝试投递
# - "DLR 超时" / "SubmitSMResp丢失"：进入 expired 不进 failed，理论上不会出现，列为防御
_SUBMITTED_PATTERNS = re.compile(
    r"SMPP Error:\s*\d+|SMPP DLR:|DLR 超时|SubmitSMResp丢失",
    re.IGNORECASE,
)


def _looks_submitted_to_upstream(sms_log: SMSLog) -> bool:
    """根据现有上下文猜测是否已提交到上游；保守判断（true=不可退）"""
    if sms_log.upstream_message_id:
        return True
    err = (sms_log.error_message or "").strip()
    if err and _SUBMITTED_PATTERNS.search(err):
        return True
    return False


@dataclass
class RefundCandidate:
    sms_log: SMSLog
    eligible: bool
    reason: str  # 不合格时的原因；合格时是简短分类（如"通道不可用"/"队列失败"/"未知"）


def classify_refund_candidate(sms_log: SMSLog) -> RefundCandidate:
    """对单条 sms_log 做退款资格判定。"""
    if sms_log.status != "failed":
        return RefundCandidate(sms_log, False, f"状态非 failed（{sms_log.status}）")
    if sms_log.refunded_at is not None:
        return RefundCandidate(sms_log, False, "已退款")
    if sms_log.cost_price is None or float(sms_log.cost_price) <= 0:
        return RefundCandidate(sms_log, False, "无销售价/已是零费用")
    if _looks_submitted_to_upstream(sms_log):
        return RefundCandidate(sms_log, False, "看起来已提交到上游，需上游确认未发出")

    err = (sms_log.error_message or "").strip()
    # 合格 → 给一个简短分类便于管理员判断
    if not err:
        category = "未知系统错误（无错误信息）"
    elif any(k in err for k in ["No available channel", "无可用通道"]):
        category = "通道不可用/路由失败"
    elif any(k in err for k in ["黑名单", "blacklist"]):
        category = "黑名单拦截"
    elif any(k in err for k in ["批次已取消", "cancelled"]):
        category = "批次已取消"
    elif any(k in err for k in ["队列", "queue", "RabbitMQ"]):
        category = "入队失败"
    elif any(k in err for k in ["RBINDFAIL", "Bind Failed", "未绑定"]):
        category = "通道未 bind 成功"
    else:
        category = "其它系统错误"
    return RefundCandidate(sms_log, True, category)


async def list_refundable(
    db: AsyncSession,
    account_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[int, List[RefundCandidate]]:
    """列出退款候选（仅返回 eligible=True 的项）"""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 50), 200))

    base_where = [
        SMSLog.status == "failed",
        SMSLog.refunded_at.is_(None),
        SMSLog.cost_price > 0,
        SMSLog.upstream_message_id.is_(None),
    ]
    # 排除已知"已到上游"的错误码模式
    base_where.append(
        or_(
            SMSLog.error_message.is_(None),
            and_(
                ~SMSLog.error_message.like("%SMPP Error:%"),
                ~SMSLog.error_message.like("%SMPP DLR:%"),
            ),
        )
    )
    if account_id:
        base_where.append(SMSLog.account_id == int(account_id))
    if batch_id:
        base_where.append(SMSLog.batch_id == int(batch_id))
    if channel_id:
        base_where.append(SMSLog.channel_id == int(channel_id))
    if keyword:
        kw = f"%{keyword.strip()}%"
        base_where.append(
            or_(
                SMSLog.message_id.like(kw),
                SMSLog.phone_number.like(kw),
                SMSLog.error_message.like(kw),
            )
        )

    total = (await db.execute(
        select(func.count(SMSLog.id)).where(and_(*base_where))
    )).scalar() or 0

    rows = (await db.execute(
        select(SMSLog)
        .where(and_(*base_where))
        .order_by(SMSLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    candidates = [classify_refund_candidate(r) for r in rows]
    # 二次过滤（基础 SQL 过滤可能有边缘漏网；以分类器结果为准）
    return total, [c for c in candidates if c.eligible]


async def get_refund_preview(db: AsyncSession, sms_log_id: int) -> RefundCandidate | None:
    """单条退款资格预览（不实际操作）。"""
    row = (await db.execute(select(SMSLog).where(SMSLog.id == int(sms_log_id)))).scalar_one_or_none()
    if not row:
        return None
    return classify_refund_candidate(row)


async def execute_refund(
    db: AsyncSession,
    sms_log_id: int,
    admin_username: str,
    note: Optional[str] = None,
) -> dict:
    """
    执行退款。原子操作：
      1. SELECT ... FOR UPDATE 锁住 sms_log，二次确认资格
      2. UPDATE accounts.balance += amount
      3. INSERT balance_logs (change_type='refund')
      4. UPDATE sms_logs.refunded_at/by/amount
      5. 失效余额缓存

    返回结构：{"success": bool, "reason"?, "amount"?, "balance_after"?, "message_id"?}
    """
    # 1. 锁住 sms_log
    row = (await db.execute(
        select(SMSLog).where(SMSLog.id == int(sms_log_id)).with_for_update()
    )).scalar_one_or_none()
    if not row:
        return {"success": False, "reason": "not_found"}

    cand = classify_refund_candidate(row)
    if not cand.eligible:
        return {"success": False, "reason": cand.reason, "message_id": row.message_id}

    amount = Decimal(str(row.selling_price or 0))
    if amount <= 0:
        return {"success": False, "reason": "金额非正", "message_id": row.message_id}

    # 2. 加回账户余额
    await db.execute(
        update(Account).where(Account.id == row.account_id).values(balance=Account.balance + amount)
    )
    bal = (await db.execute(select(Account.balance).where(Account.id == row.account_id))).scalar()
    bal_f = float(bal) if bal is not None else 0.0

    # 3. 记账
    desc = f"SMS退款: message_id={row.message_id} reason={cand.reason}"
    if note:
        desc += f" note={note[:200]}"
    db.add(
        BalanceLog(
            account_id=row.account_id,
            change_type="refund",
            amount=amount,
            balance_after=bal_f,
            description=desc[:500],
        )
    )

    # 4. 写回 sms_logs
    from datetime import datetime as _dt
    await db.execute(
        update(SMSLog)
        .where(SMSLog.id == row.id, SMSLog.refunded_at.is_(None))  # 再次幂等保护
        .values(
            refunded_at=_dt.now(),
            refunded_by=admin_username[:100],
            refunded_amount=amount,
        )
    )

    await db.commit()

    # 5. 失效余额缓存
    try:
        cm = await get_cache_manager()
        await cm.set(f"account:{row.account_id}:balance", bal_f, ttl=60)
    except Exception as e:
        logger.warning(f"refund 余额缓存刷新失败 account={row.account_id}: {e}")

    logger.info(
        f"SMS退款成功 sms_log_id={row.id} message_id={row.message_id} "
        f"amount={amount} account_id={row.account_id} admin={admin_username} reason={cand.reason}"
    )
    return {
        "success": True,
        "amount": float(amount),
        "balance_after": bal_f,
        "message_id": row.message_id,
        "account_id": row.account_id,
        "category": cand.reason,
    }


async def execute_refund_batch(
    db: AsyncSession,
    sms_log_ids: List[int],
    admin_username: str,
    note: Optional[str] = None,
) -> dict:
    """批量退款（每条独立事务保证幂等）。"""
    ok, fail, total_amount = 0, 0, Decimal("0")
    failures: List[dict] = []
    for lid in sms_log_ids:
        try:
            r = await execute_refund(db, lid, admin_username, note)
            if r.get("success"):
                ok += 1
                total_amount += Decimal(str(r.get("amount") or 0))
            else:
                fail += 1
                failures.append({"sms_log_id": lid, "reason": r.get("reason")})
        except Exception as e:
            fail += 1
            failures.append({"sms_log_id": lid, "reason": f"exception: {e}"})
            try:
                await db.rollback()
            except Exception:
                pass
    return {
        "ok": ok,
        "failed": fail,
        "total_amount": float(total_amount),
        "failures": failures[:50],
    }
