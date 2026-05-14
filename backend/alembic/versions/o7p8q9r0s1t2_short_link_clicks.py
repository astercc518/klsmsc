"""短链点击明细表 short_link_clicks（区分真人/机器扫描）

Revision ID: o7p8q9r0s1t2
Revises: n5o6p7q8r9s0
Create Date: 2026-05-14 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "o7p8q9r0s1t2"
down_revision: Union[str, None] = "n5o6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "short_link_clicks" in insp.get_table_names():
        return
    op.create_table(
        "short_link_clicks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("token", sa.String(8), nullable=False, comment="短链 token"),
        sa.Column("short_link_log_id", sa.BigInteger, nullable=True,
                  comment="冗余 short_link_logs.id，便于直接 JOIN"),
        sa.Column("clicked_at", sa.TIMESTAMP, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("is_bot", sa.Boolean, nullable=False, server_default=sa.text("0"),
                  comment="是否判定为机器/扫描点击"),
        sa.Column("bot_reason", sa.String(64), nullable=True,
                  comment="机器判定命中的规则名（empty_ua / curl / preview_bot / ...）"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "idx_short_link_clicks_log_time",
        "short_link_clicks",
        ["short_link_log_id", "clicked_at"],
        unique=False,
    )
    op.create_index(
        "idx_short_link_clicks_token_time",
        "short_link_clicks",
        ["token", "clicked_at"],
        unique=False,
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "short_link_clicks" not in insp.get_table_names():
        return
    op.drop_index("idx_short_link_clicks_token_time", table_name="short_link_clicks")
    op.drop_index("idx_short_link_clicks_log_time", table_name="short_link_clicks")
    op.drop_table("short_link_clicks")
