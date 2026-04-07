"""private_library_summaries 增加 is_deleted 列（客户软删标记）

Revision ID: l1m2n3o4p5q6
Revises: k9m0n1p2q3r4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "k9m0n1p2q3r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "private_library_summaries" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("private_library_summaries")}
    if "is_deleted" not in cols:
        op.add_column(
            "private_library_summaries",
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default="0",
                comment="客户侧软删后标记为 True，管理端仍可查阅",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "private_library_summaries" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("private_library_summaries")}
        if "is_deleted" in cols:
            op.drop_column("private_library_summaries", "is_deleted")
