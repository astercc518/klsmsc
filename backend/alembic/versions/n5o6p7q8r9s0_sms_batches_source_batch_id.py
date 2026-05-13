"""sms_batches add source_batch_id (failure retry → new batch lineage)

Revision ID: n5o6p7q8r9s0
Revises: e4f5a6b7c8d9
Create Date: 2026-05-13 16:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sms_batches",
        sa.Column(
            "source_batch_id",
            sa.Integer(),
            nullable=True,
            comment="重发来源批次ID（失败重发生成的新批次回指原批次）",
        ),
    )
    op.create_index(
        "ix_sms_batches_source_batch_id",
        "sms_batches",
        ["source_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sms_batches_source_batch_id", table_name="sms_batches")
    op.drop_column("sms_batches", "source_batch_id")
