"""sms_logs 增加 (batch_id, status) 索引，加速批次进度 GROUP BY 与待发探测

Revision ID: o1p2q3r4s5t6
Revises: m2n3o4p5q6r7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o1p2q3r4s5t6"
down_revision: Union[str, None] = "m2n3o4p5q6r7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "idx_sms_logs_batch_status"


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
        ["batch_id", "status"],
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
