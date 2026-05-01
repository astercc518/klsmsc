"""SMPP 入站服务器：新增 smpp_inbound_submissions 与 smpp_pending_dlrs 表

Revision ID: a1b2c3d4e5f6
Revises: z9y8x7w6v5u4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "40c11d1f7e29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())

    if "smpp_inbound_submissions" not in existing:
        op.create_table(
            "smpp_inbound_submissions",
            sa.Column("message_id", sa.String(64), primary_key=True),
            sa.Column("account_id", sa.Integer, nullable=False),
            sa.Column("system_id", sa.String(20), nullable=False),
            sa.Column("source_addr", sa.String(20), nullable=True),
            sa.Column("dest_addr", sa.String(20), nullable=False),
            sa.Column(
                "created_at",
                sa.TIMESTAMP,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index(
            "idx_smpp_inb_sub_system_created",
            "smpp_inbound_submissions",
            ["system_id", "created_at"],
        )

    if "smpp_pending_dlrs" not in existing:
        op.create_table(
            "smpp_pending_dlrs",
            sa.Column(
                "id",
                sa.BigInteger,
                primary_key=True,
                autoincrement=True,
            ),
            sa.Column("system_id", sa.String(20), nullable=False),
            sa.Column("payload", sa.JSON, nullable=False),
            sa.Column(
                "created_at",
                sa.TIMESTAMP,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("expires_at", sa.TIMESTAMP, nullable=False),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
        op.create_index(
            "idx_smpp_pending_dlr_sys_exp",
            "smpp_pending_dlrs",
            ["system_id", "expires_at"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())
    if "smpp_pending_dlrs" in existing:
        op.drop_index("idx_smpp_pending_dlr_sys_exp", table_name="smpp_pending_dlrs")
        op.drop_table("smpp_pending_dlrs")
    if "smpp_inbound_submissions" in existing:
        op.drop_index(
            "idx_smpp_inb_sub_system_created",
            table_name="smpp_inbound_submissions",
        )
        op.drop_table("smpp_inbound_submissions")
