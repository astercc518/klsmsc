"""私有库独立表 private_library_numbers（与公海 data_numbers 分表）

Revision ID: g2h3i4j5k6l7
Revises: f3e4d5c6b7a8
Create Date: 2026-04-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, None] = "f3e4d5c6b7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "private_library_numbers"):
        return
    op.create_table(
        "private_library_numbers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("phone_number", sa.String(length=30), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("carrier", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("purpose", sa.String(length=50), nullable=True),
        sa.Column("batch_id", sa.String(length=50), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_pln_account_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "phone_number", name="uq_pln_account_phone"),
    )
    op.create_index("idx_pln_account_batch", "private_library_numbers", ["account_id", "batch_id"], unique=False)
    op.create_index("idx_pln_account_created", "private_library_numbers", ["account_id", "created_at"], unique=False)
    op.create_index(
        "idx_pln_account_summary_dims",
        "private_library_numbers",
        ["account_id", "country_code", "source", "purpose", "batch_id"],
        unique=False,
    )
    op.create_index("ix_private_library_numbers_account_id", "private_library_numbers", ["account_id"], unique=False)
    op.create_index("ix_private_library_numbers_country_code", "private_library_numbers", ["country_code"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "private_library_numbers"):
        op.drop_table("private_library_numbers")
