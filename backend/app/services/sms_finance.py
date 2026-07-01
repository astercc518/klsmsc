"""SMS 退款净额聚合口径（退补充值治本，2026-07）。

退补充值：管理员审核确认「发送失败」的短信可退款后，写入 sms_logs.refunded_at
并把 selling_price 退回客户余额（见 services/sms_refund.py）。商业口径上该条发送
等于未发生 —— 成本/收入/利润都应剔除；但发送数/失败数/成功率仍应保留（短信确实
提交过且失败），因此只对金额列做条件求和，不动计数。

关键前提：refunded_at 只可能出现在 status='failed' 的行（退款资格强制 failed），
所以已按 status='delivered' 过滤的聚合（如销售佣金）天然免疫，无需套用本口径。

用法：把 func.sum(SMSLog.cost_price).label("x") 换成 net_cost("x")，收入/利润同理。
"""
from __future__ import annotations

from sqlalchemy import func, case

from app.modules.sms.sms_log import SMSLog

# refunded_at IS NULL 才计入金额，已退补充值（failed+已退）计 0
_NOT_REFUNDED = SMSLog.refunded_at.is_(None)


def _net_sum(col, label):
    expr = func.sum(case((_NOT_REFUNDED, col), else_=0))
    return expr.label(label) if label else expr


def net_cost(label: str | None = "total_cost"):
    """净成本：剔除已退补充值行的 cost_price。label=None 返回无标签表达式。"""
    return _net_sum(SMSLog.cost_price, label)


def net_revenue(label: str | None = "total_revenue"):
    """净收入：剔除已退补充值行的 selling_price。label=None 返回无标签表达式。"""
    return _net_sum(SMSLog.selling_price, label)


def net_profit(label: str | None = "total_profit"):
    """净利润：剔除已退补充值行的 profit（生成列 = selling - cost）。"""
    return _net_sum(SMSLog.profit, label)
