"""sms_logs 增加 upstream_message_id 索引；message_id 已有 UNIQUE 等效索引

Revision ID: z9y8x7w6v5u4
Revises: s7t8u9v0w1x2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z9y8x7w6v5u4"
down_revision: Union[str, None] = "s7t8u9v0w1x2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# DLR 更新: WHERE upstream_message_id = ? AND status='sent'；千万级表必须走索引
IDX_UPSTREAM = "idx_sms_logs_upstream_message_id"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_UPSTREAM not in existing:
        op.create_index(
            IDX_UPSTREAM,
            "sms_logs",
            ["upstream_message_id"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_UPSTREAM in existing:
        op.drop_index(IDX_UPSTREAM, table_name="sms_logs")
