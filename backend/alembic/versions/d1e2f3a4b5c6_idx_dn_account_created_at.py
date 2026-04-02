"""私库最近批次扫描索引 data_numbers(account_id, created_at)

Revision ID: d1e2f3a4b5c6
Revises: c8f9e2a1b3d4
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c8f9e2a1b3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_numbers"):
        op.create_index(
            "idx_dn_account_created_at",
            "data_numbers",
            ["account_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_numbers"):
        op.drop_index("idx_dn_account_created_at", table_name="data_numbers")
