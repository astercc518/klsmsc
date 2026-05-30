"""channels 加 supplier_id 外键；supplier_rates 加 price_source

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8

资源报价(supplier_rates)单一数据源治理第 1 步——建立通道↔供应商硬主键：

- channels.supplier_id：可空外键 -> suppliers.id (ON DELETE SET NULL)。
  通道与供应商此前只能靠名字模糊对齐(KMI直连/KM_888_zhilian/KMI通信)，
  本列把对应关系落成主键。回填由 scripts/backfill_channel_supplier.py
  按 channel_code->supplier_name 显式映射执行(可空，未匹配通道留 NULL)。
- supplier_rates.price_source：'excel'(默认，人工成本表导入) / 'channel'
  (通道价格保存自动同步)。两个写入源各管各的：Excel 导入不覆盖 channel 行。

均为可空/带默认的加列，online DDL，不阻塞业务。幂等：列已存在则跳过。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "s4t5u6v7w8x9"
down_revision: Union[str, None] = "r3s4t5u6v7w8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "channels" in tables:
        ch_cols = {c["name"] for c in insp.get_columns("channels")}
        if "supplier_id" not in ch_cols:
            op.add_column(
                "channels",
                sa.Column("supplier_id", sa.Integer(), nullable=True, comment="关联供应商ID"),
            )
            op.create_index("idx_channels_supplier", "channels", ["supplier_id"])
            # suppliers 存在时才建外键，避免环境缺表导致迁移中断
            if "suppliers" in tables:
                op.create_foreign_key(
                    "fk_channels_supplier", "channels", "suppliers",
                    ["supplier_id"], ["id"], ondelete="SET NULL",
                )

    if "supplier_rates" in tables:
        sr_cols = {c["name"] for c in insp.get_columns("supplier_rates")}
        if "price_source" not in sr_cols:
            op.add_column(
                "supplier_rates",
                sa.Column(
                    "price_source", sa.String(length=20),
                    nullable=False, server_default="excel",
                    comment="成本来源：excel=人工导入 channel=通道价格同步",
                ),
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "supplier_rates" in tables:
        sr_cols = {c["name"] for c in insp.get_columns("supplier_rates")}
        if "price_source" in sr_cols:
            op.drop_column("supplier_rates", "price_source")

    if "channels" in tables:
        ch_cols = {c["name"] for c in insp.get_columns("channels")}
        if "supplier_id" in ch_cols:
            fks = {fk["name"] for fk in insp.get_foreign_keys("channels")}
            if "fk_channels_supplier" in fks:
                op.drop_constraint("fk_channels_supplier", "channels", type_="foreignkey")
            idx = {i["name"] for i in insp.get_indexes("channels")}
            if "idx_channels_supplier" in idx:
                op.drop_index("idx_channels_supplier", "channels")
            op.drop_column("channels", "supplier_id")
