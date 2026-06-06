"""water_injection_logs 加 device_info / user_agent（点击设备信息）

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0

注水点击/注册已升级为 Playwright 真浏览器+设备模拟，记录本次使用的设备指纹：
- device_info：友好摘要，前端列表直接展示（如「移动端 · iPhone · 390×844」）。
- user_agent：实际下发的 User-Agent 全文，供详情/排查。

均为可空加列，online DDL，不阻塞业务。幂等：列已存在则跳过。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u6v7w8x9y0z1"
down_revision: Union[str, None] = "t5u6v7w8x9y0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "water_injection_logs" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("water_injection_logs")}
    if "device_info" not in cols:
        op.add_column(
            "water_injection_logs",
            sa.Column("device_info", sa.String(255), nullable=True, comment="点击设备信息(友好摘要)"),
        )
    if "user_agent" not in cols:
        op.add_column(
            "water_injection_logs",
            sa.Column("user_agent", sa.String(512), nullable=True, comment="实际使用的 User-Agent 全文"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "water_injection_logs" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("water_injection_logs")}
    if "user_agent" in cols:
        op.drop_column("water_injection_logs", "user_agent")
    if "device_info" in cols:
        op.drop_column("water_injection_logs", "device_info")
