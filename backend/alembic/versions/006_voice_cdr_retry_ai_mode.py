"""CDR Webhook 原始报文与重试计数；外呼任务 ai_mode

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "006"
down_revision: Union[str, None] = "005"
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
    if _has_table(conn, "voice_cdr_webhook_logs"):
        if not _has_column(conn, "voice_cdr_webhook_logs", "raw_payload"):
            op.add_column("voice_cdr_webhook_logs", sa.Column("raw_payload", sa.Text(), nullable=True))
        if not _has_column(conn, "voice_cdr_webhook_logs", "retry_count"):
            op.add_column(
                "voice_cdr_webhook_logs",
                sa.Column("retry_count", sa.Integer(), nullable=True, server_default="0"),
            )
    if _has_table(conn, "voice_outbound_campaigns"):
        if not _has_column(conn, "voice_outbound_campaigns", "ai_mode"):
            op.add_column(
                "voice_outbound_campaigns",
                sa.Column("ai_mode", sa.String(16), nullable=True, server_default="ivr"),
            )


def downgrade() -> None:
    pass
