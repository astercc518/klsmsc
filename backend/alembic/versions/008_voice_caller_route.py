"""主叫号码池可选绑定语音路由 voice_route_id

Revision ID: 008
Revises: 007
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "008"
down_revision: Union[str, None] = "007"
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
    if _has_table(conn, "voice_caller_ids"):
        if not _has_column(conn, "voice_caller_ids", "voice_route_id"):
            op.add_column(
                "voice_caller_ids",
                sa.Column(
                    "voice_route_id",
                    sa.Integer(),
                    nullable=True,
                    comment="可选绑定出局/批价路由",
                ),
            )
            try:
                op.create_foreign_key(
                    "fk_voice_caller_ids_voice_route",
                    "voice_caller_ids",
                    "voice_routes",
                    ["voice_route_id"],
                    ["id"],
                )
            except Exception:
                pass


def downgrade() -> None:
    pass
