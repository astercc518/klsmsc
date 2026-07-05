"""water_task_configs 加 register_handler(注册脚本手动选择)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-04

注水注册原本纯靠落地页自动识别路由(tk688/sp111/onewin/api/通用)。轮换马甲域或
内容指纹漏判时会走错路径。本列让管理员在「注水配置」里按账户**手动指定**注册用哪个
脚本/handler,覆盖自动识别。空串=自动(默认,行为不变)。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "water_task_configs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("water_task_configs")}
    if "register_handler" not in cols:
        op.add_column(
            "water_task_configs",
            sa.Column(
                "register_handler",
                sa.String(32),
                nullable=False,
                server_default="",
                comment="注册脚本/handler:''=自动识别 / tk688 / sp111 / onewin / api / generic",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "water_task_configs" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("water_task_configs")}
        if "register_handler" in cols:
            op.drop_column("water_task_configs", "register_handler")
