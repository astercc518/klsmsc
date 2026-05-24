"""admin_users 增加 token_version 列：JWT 旋转失效机制

Revision ID: p9q0r1s2t3u4
Revises: o7p8q9r0s1t2

每次 /admin/auth/refresh 或主动注销时 token_version += 1，
旧 refresh token 的 payload.tv 不再匹配，自动失效。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p9q0r1s2t3u4"
down_revision: Union[str, None] = "o7p8q9r0s1t2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "admin_users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("admin_users")}
    if "token_version" in cols:
        return
    op.add_column(
        "admin_users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="JWT 刷新版本；refresh token 的 tv 必须等于此值",
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "admin_users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("admin_users")}
    if "token_version" not in cols:
        return
    op.drop_column("admin_users", "token_version")
