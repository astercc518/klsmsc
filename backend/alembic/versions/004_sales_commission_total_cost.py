"""员工结算：增加客户成本汇总字段（毛利计佣）

Revision ID: 004
Revises: 003
Create Date: 2026-03-26

sales_commission_settlements / sales_commission_details 增加 total_cost，
佣金按 max(0, 营收-成本)*比例 计提，成本仅统计该销售名下客户。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    """列已存在时跳过 ADD，避免与启动时自动补齐或手工 ALTER 冲突。"""
    if not conn.dialect.has_table(conn, table_name):
        return False
    insp = inspect(conn)
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "sales_commission_settlements"):
        if not _has_column(conn, "sales_commission_settlements", "total_cost"):
            op.add_column(
                "sales_commission_settlements",
                sa.Column(
                    "total_cost",
                    sa.Numeric(14, 4),
                    nullable=False,
                    server_default=sa.text("0"),
                    comment="名下客户短信成本汇总",
                ),
            )
    if conn.dialect.has_table(conn, "sales_commission_details"):
        if not _has_column(conn, "sales_commission_details", "total_cost"):
            op.add_column(
                "sales_commission_details",
                sa.Column(
                    "total_cost",
                    sa.Numeric(14, 4),
                    nullable=False,
                    server_default=sa.text("0"),
                    comment="该客户周期内成本",
                ),
            )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "sales_commission_details"):
        if _has_column(conn, "sales_commission_details", "total_cost"):
            op.drop_column("sales_commission_details", "total_cost")
    if conn.dialect.has_table(conn, "sales_commission_settlements"):
        if _has_column(conn, "sales_commission_settlements", "total_cost"):
            op.drop_column("sales_commission_settlements", "total_cost")
