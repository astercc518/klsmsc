"""删除结算管理相关数据表（供应商结算、客户账单、销售佣金结算、利润报表）

Revision ID: k9m0n1p2q3r4
Revises: j2k3l4m5n6o7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k9m0n1p2q3r4"
down_revision: Union[str, None] = "j2k3l4m5n6o7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 子表优先删除（外键依赖）
_DROP_ORDER = (
    "settlement_details",
    "settlement_logs",
    "settlements",
    "customer_bill_details",
    "customer_bills",
    "sales_commission_details",
    "sales_commission_settlements",
    "profit_reports",
)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())
    for t in _DROP_ORDER:
        if t in existing:
            op.drop_table(t)


def downgrade() -> None:
    # 结算模块已从代码移除，不回建表
    pass
