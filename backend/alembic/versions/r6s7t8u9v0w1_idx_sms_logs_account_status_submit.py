"""sms_logs 增加 (account_id, status, submit_time) 索引，加速销售本月业绩 SUM 与 verify-user 聚合

Revision ID: r6s7t8u9v0w1
Revises: p3q4r5s6t7u8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r6s7t8u9v0w1"
down_revision: Union[str, None] = "p3q4r5s6t7u8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "idx_sms_logs_account_status_submit"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if INDEX_NAME in existing:
        return
    op.create_index(
        INDEX_NAME,
        "sms_logs",
        ["account_id", "status", "submit_time"],
        unique=False,
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if INDEX_NAME not in existing:
        return
    op.drop_index(INDEX_NAME, table_name="sms_logs")
