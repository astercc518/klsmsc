"""私库汇总查询复合索引 data_numbers(account_id, country_code, source, purpose, batch_id)

Revision ID: c8f9e2a1b3d4
Revises: 5cd1450f675e
Create Date: 2026-04-02

说明：与模型 DataNumber.idx_dn_account_summary_dims 一致，加速按账号分组的聚合统计。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c8f9e2a1b3d4"
down_revision: Union[str, None] = "5cd1450f675e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_numbers"):
        op.create_index(
            "idx_dn_account_summary_dims",
            "data_numbers",
            ["account_id", "country_code", "source", "purpose", "batch_id"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_numbers"):
        op.drop_index("idx_dn_account_summary_dims", table_name="data_numbers")
