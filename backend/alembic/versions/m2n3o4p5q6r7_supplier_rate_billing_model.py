"""supplier_rates 增加 billing_model / line_desc 列（语音计费模式）

Revision ID: m2n3o4p5q6r7
Revises: l1m2n3o4p5q6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m2n3o4p5q6r7"
down_revision: Union[str, None] = "l1m2n3o4p5q6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "supplier_rates" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("supplier_rates")}

    if "billing_model" not in cols:
        op.add_column(
            "supplier_rates",
            sa.Column(
                "billing_model",
                sa.String(20),
                nullable=True,
                comment="语音计费模式：1+1/6+6/30+6/60+1/60+60",
            ),
        )

    if "line_desc" not in cols:
        op.add_column(
            "supplier_rates",
            sa.Column(
                "line_desc",
                sa.String(100),
                nullable=True,
                comment="语音线路描述（如：电力/快递/卡线）",
            ),
        )

    # 将现有语音费率的 resource_type（存的是计费模式）迁移到 billing_model
    op.execute(
        sa.text(
            "UPDATE supplier_rates "
            "SET billing_model = resource_type "
            "WHERE business_type = 'voice' "
            "AND resource_type REGEXP '^[0-9]+\\\\+[0-9]+$' "
            "AND (billing_model IS NULL OR billing_model = '')"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "supplier_rates" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("supplier_rates")}
        if "line_desc" in cols:
            op.drop_column("supplier_rates", "line_desc")
        if "billing_model" in cols:
            op.drop_column("supplier_rates", "billing_model")
