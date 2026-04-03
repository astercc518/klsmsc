"""private_library_numbers 增加客户软删字段 is_deleted

Revision ID: j2k3l4m5n6o7
Revises: i1j2k3l4m5n6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j2k3l4m5n6o7"
down_revision: Union[str, None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("private_library_numbers")]
    if "is_deleted" not in cols:
        op.add_column(
            "private_library_numbers",
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="客户软删标记"),
        )
        op.create_index("ix_private_library_numbers_is_deleted", "private_library_numbers", ["is_deleted"], unique=False)
        op.create_index(
            "idx_pln_account_not_deleted",
            "private_library_numbers",
            ["account_id", "is_deleted"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("private_library_numbers")]
    if "is_deleted" in cols:
        op.drop_index("idx_pln_account_not_deleted", table_name="private_library_numbers")
        op.drop_index("ix_private_library_numbers_is_deleted", table_name="private_library_numbers")
        op.drop_column("private_library_numbers", "is_deleted")
