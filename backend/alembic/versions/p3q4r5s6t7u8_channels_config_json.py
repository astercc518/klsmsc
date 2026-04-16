"""channels 表增加 config_json（通道扩展 JSON）

Revision ID: p3q4r5s6t7u8
Revises: o1p2q3r4s5t6
Create Date: 2026-04-13

用于 strip_leading_plus、payload_template 等与协议无关的网关选项。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "p3q4r5s6t7u8"
down_revision: Union[str, None] = "o1p2q3r4s5t6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    if not conn.dialect.has_table(conn, table_name):
        return False
    insp = inspect(conn)
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, "channels"):
        return
    if not _has_column(conn, "channels", "config_json"):
        op.add_column(
            "channels",
            sa.Column(
                "config_json",
                sa.Text(),
                nullable=True,
                comment="HTTP/SMPP 扩展 JSON：strip_leading_plus、payload_template 等",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, "channels"):
        return
    if _has_column(conn, "channels", "config_json"):
        op.drop_column("channels", "config_json")
