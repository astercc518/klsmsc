"""supplier_rates 加 channel_id（记录设此成本的通道，展示用）

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9

资源报价行新增 channel_id：当成本由通道价格保存自动同步时(price_source='channel')，
记录是哪个通道触发的，供前端「通道」列精确展示。Excel 导入的行留 NULL。

不加外键约束(channels.id 为 int unsigned，避免签名不匹配；此列仅作展示引用)。
可空加列，online DDL。幂等：列已存在则跳过。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t5u6v7w8x9y0"
down_revision: Union[str, None] = "s4t5u6v7w8x9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "supplier_rates" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("supplier_rates")}
    if "channel_id" not in cols:
        op.add_column(
            "supplier_rates",
            sa.Column("channel_id", sa.Integer(), nullable=True, comment="设此成本的通道ID(展示用)"),
        )
        op.create_index("idx_supplier_rates_channel", "supplier_rates", ["channel_id"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "supplier_rates" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("supplier_rates")}
    if "channel_id" in cols:
        idx = {i["name"] for i in insp.get_indexes("supplier_rates")}
        if "idx_supplier_rates_channel" in idx:
            op.drop_index("idx_supplier_rates_channel", "supplier_rates")
        op.drop_column("supplier_rates", "channel_id")
