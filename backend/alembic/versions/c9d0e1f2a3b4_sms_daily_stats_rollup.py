"""add sms_daily_stats rollup tables

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "sms_daily_stats" not in tables:
        op.create_table(
            "sms_daily_stats",
            sa.Column("stat_date", sa.Date(), nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("channel_id", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("country_code", sa.String(3), nullable=False, server_default=""),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("submit_total", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("priced_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("total_cost", sa.Numeric(24, 6), nullable=False, server_default="0"),
            sa.Column("total_revenue", sa.Numeric(24, 6), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint(
                "stat_date", "account_id", "channel_id", "country_code", "status",
                name="pk_sms_daily_stats",
            ),
        )
        op.create_index(
            "idx_sms_daily_stats_channel", "sms_daily_stats", ["stat_date", "channel_id"]
        )
        op.create_index(
            "idx_sms_daily_stats_country", "sms_daily_stats", ["stat_date", "country_code"]
        )

    if "sms_daily_stats_coverage" not in tables:
        op.create_table(
            "sms_daily_stats_coverage",
            sa.Column("stat_date", sa.Date(), nullable=False),
            sa.Column("refreshed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("stat_date", name="pk_sms_daily_stats_coverage"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "sms_daily_stats_coverage" in tables:
        op.drop_table("sms_daily_stats_coverage")
    if "sms_daily_stats" in tables:
        op.drop_table("sms_daily_stats")
