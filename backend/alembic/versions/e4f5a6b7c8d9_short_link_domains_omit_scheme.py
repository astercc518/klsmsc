"""short_link_domains 增加 omit_scheme 列；允许 base_path 为空字符串

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "short_link_domains"
_COL = "omit_scheme"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL not in cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _COL,
                sa.Boolean,
                nullable=False,
                server_default=sa.text("0"),
                comment="短链显示是否省略 https:// 前缀（用于绕过部分运营商 https 拦截 + 节省字符）",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL in cols:
        op.drop_column(_TABLE, _COL)
