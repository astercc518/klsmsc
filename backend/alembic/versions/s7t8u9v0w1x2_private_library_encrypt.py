"""私库加密：upload_tasks 加 export_password_hash；summaries 加 batch_name + export_password_hash

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s7t8u9v0w1x2"
down_revision: Union[str, None] = "r6s7t8u9v0w1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    tables = insp.get_table_names()

    if "private_library_upload_tasks" in tables:
        cols = {c["name"] for c in insp.get_columns("private_library_upload_tasks")}
        if "export_password_hash" not in cols:
            op.add_column(
                "private_library_upload_tasks",
                sa.Column(
                    "export_password_hash",
                    sa.String(128),
                    nullable=True,
                    comment="下载密码哈希（设置后导出需验证）",
                ),
            )

    if "private_library_summaries" in tables:
        cols = {c["name"] for c in insp.get_columns("private_library_summaries")}
        if "batch_name" not in cols:
            op.add_column(
                "private_library_summaries",
                sa.Column(
                    "batch_name",
                    sa.String(255),
                    nullable=True,
                    comment="数据包名称（来自上传文件名）",
                ),
            )
        if "export_password_hash" not in cols:
            op.add_column(
                "private_library_summaries",
                sa.Column(
                    "export_password_hash",
                    sa.String(128),
                    nullable=True,
                    comment="下载密码哈希（设置后导出需验证）",
                ),
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "private_library_upload_tasks" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("private_library_upload_tasks")}
        if "export_password_hash" in cols:
            op.drop_column("private_library_upload_tasks", "export_password_hash")

    if "private_library_summaries" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("private_library_summaries")}
        if "export_password_hash" in cols:
            op.drop_column("private_library_summaries", "export_password_hash")
        if "batch_name" in cols:
            op.drop_column("private_library_summaries", "batch_name")
