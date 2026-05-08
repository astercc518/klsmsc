"""add short_link_domains table

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "short_link_domains"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE in insp.get_table_names():
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("domain", sa.String(255), nullable=False, unique=True,
                  comment="域名主体"),
        sa.Column("base_path", sa.String(64), nullable=False,
                  server_default="/s", comment="路径前缀"),
        sa.Column("scheme", sa.String(8), nullable=False,
                  server_default="https", comment="协议"),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="short_link_domain_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE in insp.get_table_names():
        op.drop_table(_TABLE)
