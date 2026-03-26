"""语音账户归属员工（admin_users）

Revision ID: 010
Revises: 009
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(conn, name: str) -> bool:
    return conn.dialect.has_table(conn, name)


def _has_column(conn, table: str, col: str) -> bool:
    if not conn.dialect.has_table(conn, table):
        return False
    insp = inspect(conn)
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()

    if _has_table(conn, "voice_accounts"):
        if not _has_column(conn, "voice_accounts", "sales_id"):
            op.add_column(
                "voice_accounts",
                sa.Column(
                    "sales_id",
                    sa.Integer(),
                    nullable=True,
                    comment="归属员工/销售（admin_users.id）",
                ),
            )
            try:
                op.create_foreign_key(
                    "fk_voice_accounts_sales",
                    "voice_accounts",
                    "admin_users",
                    ["sales_id"],
                    ["id"],
                )
            except Exception:
                pass
            try:
                op.create_index(
                    "ix_voice_accounts_sales_id",
                    "voice_accounts",
                    ["sales_id"],
                )
            except Exception:
                pass


def downgrade() -> None:
    conn = op.get_bind()
    if _has_table(conn, "voice_accounts") and _has_column(conn, "voice_accounts", "sales_id"):
        try:
            op.drop_index("ix_voice_accounts_sales_id", table_name="voice_accounts")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_voice_accounts_sales", "voice_accounts", type_="foreignkey")
        except Exception:
            pass
        op.drop_column("voice_accounts", "sales_id")
