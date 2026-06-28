"""add sms_batches.scheduled_at (定时发送落库根治)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-26

定时发送原走 process_batch_chunk.apply_async(eta=...) 反模式：任务挂 worker 内存
unacked，eta 距投递 >30min 必撞 RabbitMQ consumer_timeout 崩 worker；且计划时间
不落库、无 beat 兜底，崩了无法恢复。改为：定时批次落 scheduled_at + 负载持久化到文件，
status=PENDING，到点由 beat 任务 dispatch_scheduled_batches 当下入队（无 eta）。

本迁移加 scheduled_at 列 + (status, scheduled_at) 复合索引供 beat 扫描 due 批次。
幂等守门：存在才加。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IDX_SCHEDULED = "idx_sms_batches_status_scheduled"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_batches" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("sms_batches")}
    if "scheduled_at" not in cols:
        op.add_column(
            "sms_batches",
            sa.Column(
                "scheduled_at",
                sa.TIMESTAMP(),
                nullable=True,
                comment="定时发送时间(NULL=立即);到点由 beat dispatch_scheduled_batches 派发",
            ),
        )
    idx = {ix["name"] for ix in insp.get_indexes("sms_batches")}
    if IDX_SCHEDULED not in idx:
        # beat 扫描 WHERE status=PENDING AND scheduled_at<=now 的支撑索引
        op.create_index(IDX_SCHEDULED, "sms_batches", ["status", "scheduled_at"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_batches" not in insp.get_table_names():
        return
    idx = {ix["name"] for ix in insp.get_indexes("sms_batches")}
    if IDX_SCHEDULED in idx:
        op.drop_index(IDX_SCHEDULED, table_name="sms_batches")
    cols = {c["name"] for c in insp.get_columns("sms_batches")}
    if "scheduled_at" in cols:
        op.drop_column("sms_batches", "scheduled_at")
