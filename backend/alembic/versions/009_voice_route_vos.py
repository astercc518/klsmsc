"""语音路由 VOS 对接字段

Revision ID: 009
Revises: 008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "009"
down_revision: Union[str, None] = "008"
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
        if not _has_column(conn, "voice_routes", "gateway_type"):
            op.add_column(
                "voice_routes",
                sa.Column(
                    "gateway_type",
                    sa.String(32),
                    nullable=False,
                    server_default="generic",
                    comment="出局类型：generic 通用 FS/Trunk；vos 对接 VOS 落地/网关名",
                ),
            )
        if not _has_column(conn, "voice_routes", "vos_gateway_name"):
            op.add_column(
                "voice_routes",
                sa.Column(
                    "vos_gateway_name",
                    sa.String(128),
                    nullable=True,
                    comment="VOS 侧网关/落地名称，与网关注册或对接配置一致",
                ),
            )


def downgrade() -> None:
    conn = op.get_bind()
    if _has_table(conn, "voice_routes"):
        if _has_column(conn, "voice_routes", "vos_gateway_name"):
            op.drop_column("voice_routes", "vos_gateway_name")
        if _has_column(conn, "voice_routes", "gateway_type"):
            op.drop_column("voice_routes", "gateway_type")
