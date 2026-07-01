"""SMS 报表金额聚合口径（成本/收入/利润）。

历史（2026-07 上旬）：曾把成本/收入/利润改成 SUM(CASE WHEN refunded_at IS NULL ...)
以「剔除已退款短信」。后来确认两件事，故已回退为原始 SUM：

  1. 业务上的「退补充值」= balance_logs.change_type='refund_recharge'（管理员按售价
     把钱补回客户余额），与 sms_logs.refunded_at 无关，且明确「不计业绩和成本」。
     所以报表的成本/收入/利润应取 sms_logs 原始值，退补充值另行独立列示
     （见 reports_service._fetch_refund_recharge 与 admin.get_send_statistics）。

  2. 性能陷阱：refunded_at 不在覆盖索引 idx_sms_report_cov(account_id, cost_price,
     selling_price, status, submit_time) 内。一旦 SUM 里引用 refunded_at，原本的
     索引只读扫描会退化成对数百万行逐行回表——月维度聚合从秒级劣化到 80s+，
     发送统计/业务报表直接转圈卡死。

结论：这里必须是纯 SUM(cost_price/selling_price/profit)，勿再包 CASE(refunded_at)。
函数名保留 net_*，避免大面积改动调用点；语义即「报表金额聚合」。
"""
from __future__ import annotations

from sqlalchemy import func

from app.modules.sms.sms_log import SMSLog


def _sum(col, label):
    expr = func.sum(col)
    return expr.label(label) if label else expr


def net_cost(label: str | None = "total_cost"):
    """成本聚合：SUM(cost_price)。label=None 返回无标签表达式（用于 coalesce 等）。"""
    return _sum(SMSLog.cost_price, label)


def net_revenue(label: str | None = "total_revenue"):
    """收入聚合：SUM(selling_price)。"""
    return _sum(SMSLog.selling_price, label)


def net_profit(label: str | None = "total_profit"):
    """利润聚合：SUM(profit)（profit 为生成列 = selling - cost）。"""
    return _sum(SMSLog.profit, label)
