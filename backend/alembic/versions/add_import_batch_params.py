"""添加导入批次参数字段（用于重试）

Revision ID: 003
Revises: 002
Create Date: 2025-03-23

存储 purpose/data_date 等参数，支持 pending/failed 任务重新投递
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_import_batches"):
        op.add_column(
            "data_import_batches",
            sa.Column("purpose", sa.String(100), nullable=True, comment="用途（重试时需）"),
        )
        op.add_column(
            "data_import_batches",
            sa.Column("data_date_str", sa.String(20), nullable=True, comment="采集日期 YYYY-MM-DD"),
        )
        op.add_column(
            "data_import_batches",
            sa.Column("pricing_template_id", sa.Integer, nullable=True, comment="定价模板ID"),
        )
        op.add_column(
            "data_import_batches",
            sa.Column("default_tags_json", sa.Text, nullable=True, comment="默认标签 JSON 数组"),
        )
        op.add_column(
            "data_import_batches",
            sa.Column("country_code", sa.String(10), nullable=True, comment="国家代码"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "data_import_batches"):
        op.drop_column("data_import_batches", "country_code")
        op.drop_column("data_import_batches", "default_tags_json")
        op.drop_column("data_import_batches", "pricing_template_id")
        op.drop_column("data_import_batches", "data_date_str")
        op.drop_column("data_import_batches", "purpose")
