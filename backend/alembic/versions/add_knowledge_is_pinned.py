"""添加知识库置顶字段

Revision ID: 001
Revises: 
Create Date: 2025-03-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 检查 knowledge_articles 表是否存在
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "knowledge_articles"):
        op.add_column("knowledge_articles", sa.Column("is_pinned", sa.Integer(), nullable=True, server_default=sa.text("0")))


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "knowledge_articles"):
        op.drop_column("knowledge_articles", "is_pinned")
