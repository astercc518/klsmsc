"""channels & country_pricing 增加 remark 列：通用备注

Revision ID: q1r2s3t4u5v6
Revises: p9q0r1s2t3u4

通道配置 / 价格配置新增「备注」字段，便于记录供应商、用途、调价原因等。
VARCHAR(255) NULL，无需默认值。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, None] = "p9q0r1s2t3u4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_remark_if_missing(table: str) -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if "remark" in cols:
        return
    op.add_column(
        table,
        sa.Column("remark", sa.String(length=255), nullable=True, comment="备注"),
    )


def _drop_remark_if_present(table: str) -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if "remark" not in cols:
        return
    op.drop_column(table, "remark")


def upgrade() -> None:
    _add_remark_if_missing("channels")
    _add_remark_if_missing("country_pricing")


def downgrade() -> None:
    _drop_remark_if_present("country_pricing")
    _drop_remark_if_present("channels")
