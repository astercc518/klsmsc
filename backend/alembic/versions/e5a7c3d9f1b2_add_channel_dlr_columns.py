"""channels 表增加 SMPP DLR 偏好列

Revision ID: e5a7c3d9f1b2
Revises: d1e2f3a4b5c6
Create Date: 2026-04-02

将启动时自动 ALTER 逻辑收归 Alembic 管理。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "e5a7c3d9f1b2"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    """列已存在时跳过，兼容此前启动时自动补齐或手工 ALTER 的环境。"""
    if not conn.dialect.has_table(conn, table_name):
        return False
    insp = inspect(conn)
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, "channels"):
        return

    if not _has_column(conn, "channels", "smpp_dlr_socket_hold_seconds"):
        op.add_column(
            "channels",
            sa.Column(
                "smpp_dlr_socket_hold_seconds",
                sa.Integer,
                nullable=True,
                comment="SMPP发送成功后保持TCP秒数以接收deliver_sm",
            ),
        )

    if not _has_column(conn, "channels", "dlr_sent_timeout_hours"):
        op.add_column(
            "channels",
            sa.Column(
                "dlr_sent_timeout_hours",
                sa.Integer,
                nullable=True,
                comment="sent状态最长等待终态DLR小时数",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, "channels"):
        return

    if _has_column(conn, "channels", "dlr_sent_timeout_hours"):
        op.drop_column("channels", "dlr_sent_timeout_hours")
    if _has_column(conn, "channels", "smpp_dlr_socket_hold_seconds"):
        op.drop_column("channels", "smpp_dlr_socket_hold_seconds")
