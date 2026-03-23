"""添加通道连接状态字段

Revision ID: 002
Revises: 001
Create Date: 2025-03-23

通道状态列改为展示实际连接状态(正常/异常)，由状态检测接口更新
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "channels"):
        op.add_column(
            "channels",
            sa.Column("connection_status", sa.String(20), nullable=True, comment="连接状态：online=正常 offline=异常 unknown=未检测"),
        )
        op.add_column(
            "channels",
            sa.Column("connection_checked_at", sa.TIMESTAMP, nullable=True, comment="最后检测时间"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "channels"):
        op.drop_column("channels", "connection_checked_at")
        op.drop_column("channels", "connection_status")
