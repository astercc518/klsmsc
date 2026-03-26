"""语音路由 FS/Trunk 对齐字段；账户外呼配额；话单记录批价路由

Revision ID: 007
Revises: 006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "007"
down_revision: Union[str, None] = "006"
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

    if _has_table(conn, "voice_routes"):
        if not _has_column(conn, "voice_routes", "trunk_profile"):
            op.add_column(
                "voice_routes",
                sa.Column(
                    "trunk_profile",
                    sa.String(128),
                    nullable=True,
                    comment="FS/网关侧出局 profile 或网关名，供运维与网关对齐",
                ),
            )
        if not _has_column(conn, "voice_routes", "dial_prefix"):
            op.add_column(
                "voice_routes",
                sa.Column("dial_prefix", sa.String(32), nullable=True, comment="出局拨号前缀"),
            )
        if not _has_column(conn, "voice_routes", "notes"):
            op.add_column(
                "voice_routes",
                sa.Column("notes", sa.Text(), nullable=True),
            )

    if _has_table(conn, "voice_accounts"):
        if not _has_column(conn, "voice_accounts", "max_concurrent_calls"):
            op.add_column(
                "voice_accounts",
                sa.Column(
                    "max_concurrent_calls",
                    sa.Integer(),
                    nullable=True,
                    server_default="0",
                    comment="账户级最大并发外呼路数，0 表示不限制",
                ),
            )
        if not _has_column(conn, "voice_accounts", "daily_outbound_limit"):
            op.add_column(
                "voice_accounts",
                sa.Column(
                    "daily_outbound_limit",
                    sa.Integer(),
                    nullable=True,
                    server_default="0",
                    comment="账户每日外呼尝试上限，0 表示不限制",
                ),
            )

    if _has_table(conn, "voice_calls"):
        if not _has_column(conn, "voice_calls", "voice_route_id"):
            op.add_column(
                "voice_calls",
                sa.Column("voice_route_id", sa.Integer(), nullable=True, comment="批价所用路由"),
            )
            try:
                op.create_foreign_key(
                    "fk_voice_calls_voice_route",
                    "voice_calls",
                    "voice_routes",
                    ["voice_route_id"],
                    ["id"],
                )
            except Exception:
                pass


def downgrade() -> None:
    pass
