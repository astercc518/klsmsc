"""语音话单列表/导出：按日期范围过滤（入库时间或通话开始时间）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional, Tuple

# 与 MySQL 存库一致，使用 naive 日期边界（与服务器时区一致，一般为 UTC）


def parse_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    将 YYYY-MM-DD 转为 [start 当日 0 点, end 日次日 0 点)，半开区间。
    """
    start_dt: Optional[datetime] = None
    end_exclusive: Optional[datetime] = None
    if start_date and str(start_date).strip():
        try:
            start_dt = datetime.strptime(str(start_date).strip()[:10], "%Y-%m-%d")
        except ValueError:
            pass
    if end_date and str(end_date).strip():
        try:
            day = datetime.strptime(str(end_date).strip()[:10], "%Y-%m-%d")
            end_exclusive = day + timedelta(days=1)
        except ValueError:
            pass
    return start_dt, end_exclusive


# 兼容旧名
parse_created_at_range = parse_date_range


def apply_date_range_on_column(
    query: Any,
    column: Any,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Any:
    s, e = parse_date_range(start_date, end_date)
    if s is not None:
        query = query.where(column >= s)
    if e is not None:
        query = query.where(column < e)
    return query


def apply_created_at_range(
    query: Any,
    created_at_column: Any,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Any:
    """兼容：仅按 created_at。"""
    return apply_date_range_on_column(query, created_at_column, start_date, end_date)


def apply_voice_call_date_filter(
    query: Any,
    voice_call_model: Any,
    start_date: Optional[str],
    end_date: Optional[str],
    date_basis: str = "created_at",
) -> Any:
    """
    date_basis:
      - created_at：话单入库时间（默认）
      - start_time：通话开始时间（排除 start_time 为空的行）
    """
    if not start_date and not end_date:
        return query
    basis = (date_basis or "created_at").strip().lower()
    if basis == "start_time":
        query = query.where(voice_call_model.start_time.isnot(None))
        col = voice_call_model.start_time
    else:
        col = voice_call_model.created_at
    return apply_date_range_on_column(query, col, start_date, end_date)


def voice_call_order_column(voice_call_model: Any, date_basis: str = "created_at") -> Any:
    """列表/导出排序用列。"""
    basis = (date_basis or "created_at").strip().lower()
    if basis == "start_time":
        return voice_call_model.start_time
    return voice_call_model.created_at
