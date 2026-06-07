"""telegram_bindings 增加 is_closed：解绑/换绑后置 True，bot 解析只取未关闭绑定

Revision ID: y0z1a2b3c4d5
Revises: x9y0z1a2b3c4

修复：原解绑只置 is_active=False，但 get_user_bindings 不过滤状态，导致旧 TG 仍能看到账户。
引入 is_closed 区分"已解绑/失效"，与 is_active(当前选中) 正交。末尾加可空列为 INSTANT。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "y0z1a2b3c4d5"
down_revision: Union[str, None] = "x9y0z1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "telegram_bindings"
COL = "is_closed"


def _has_col() -> bool:
    insp = sa.inspect(op.get_bind())
    if TABLE not in insp.get_table_names():
        return True
    return any(c["name"] == COL for c in insp.get_columns(TABLE))


def upgrade() -> None:
    if _has_col():
        return
    op.add_column(TABLE, sa.Column(COL, sa.Boolean(), nullable=False,
                                   server_default=sa.text("0"),
                                   comment="是否已解绑/失效"))


def downgrade() -> None:
    if not _has_col():
        return
    op.drop_column(TABLE, COL)
