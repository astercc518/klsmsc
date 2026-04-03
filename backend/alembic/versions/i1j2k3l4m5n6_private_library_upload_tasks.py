"""私库异步上传任务表 private_library_upload_tasks

Revision ID: i1j2k3l4m5n6
Revises: h8a9b0c1d2e3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, None] = "h8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "private_library_upload_tasks"):
        return
    op.create_table(
        "private_library_upload_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("country_code", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("purpose", sa.String(length=100), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("detect_carrier", sa.Boolean(), nullable=True, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(length=50), nullable=True, server_default=""),
        sa.Column("progress_percent", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("total_unique", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("inserted", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("result_batch_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("task_id", name="uq_pl_upload_task_id"),
    )
    op.create_index("idx_pl_upload_account_created", "private_library_upload_tasks", ["account_id", "created_at"], unique=False)
    op.create_index("ix_pl_upload_task_id", "private_library_upload_tasks", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pl_upload_task_id", table_name="private_library_upload_tasks")
    op.drop_index("idx_pl_upload_account_created", table_name="private_library_upload_tasks")
    op.drop_table("private_library_upload_tasks")
