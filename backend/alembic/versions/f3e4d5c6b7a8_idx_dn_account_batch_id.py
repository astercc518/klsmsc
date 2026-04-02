"""私库按 batch_id 聚合索引 data_numbers(account_id, batch_id)

Revision ID: f3e4d5c6b7a8
Revises: e5a7c3d9f1b2
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f3e4d5c6b7a8"
down_revision: Union[str, None] = "e5a7c3d9f1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_numbers"):
        op.create_index(
            "idx_dn_account_batch_id",
            "data_numbers",
            ["account_id", "batch_id"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_numbers"):
        op.drop_index("idx_dn_account_batch_id", table_name="data_numbers")
