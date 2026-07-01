"""add sms_logs idx_sms_report_cov2 (含 channel_id 的报表覆盖索引)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-01

背景：发送统计/业务报表按月聚合(≈900万行)时，"虚拟通道剔除"加的
WHERE channel_id NOT IN(虚拟) 过滤引用 channel_id，而旧覆盖索引
idx_sms_report_cov(account_id,cost_price,selling_price,status,submit_time)
不含 channel_id → 逐行回表取 channel_id，月维度聚合退化到 ~157s，
超过前端 120s 超时导致「按员工」等视图一直转圈。

本索引 (submit_time, account_id, channel_id, status, cost_price, selling_price)：
- 前导 submit_time → 各区间(今日/本月)都能 range-seek，不整表扫；
- 覆盖 account_id(分组/关联员工)、channel_id(虚拟过滤)、status(送达/失败 case)、
  cost_price/selling_price(SUM/AVG) → index-only，无回表。
预期月维度从 157s 降到 ~15-20s，业务报表同口径受益。

幂等守门：存在才建。在线 ALGORITHM=INPLACE, LOCK=NONE（9M 行约 1-3 分钟，不锁发送）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IDX_NAME = "idx_sms_report_cov2"
IDX_COLS = "(submit_time, account_id, channel_id, status, cost_price, selling_price)"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_NAME not in existing:
        op.execute(
            f"ALTER TABLE sms_logs ADD INDEX {IDX_NAME} {IDX_COLS}, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_NAME in existing:
        op.execute(
            f"ALTER TABLE sms_logs DROP INDEX {IDX_NAME}, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        )
