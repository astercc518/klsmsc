"""account_channels 唯一约束加入 country_code：允许同账户同通道按国家多行

Revision ID: w8x9y0z1a2b3
Revises: v7w8x9y0z1a2

原唯一键 uk_account_channel=(account_id, channel_id) 阻止了"同账户同通道既做全国默认、
又做某国家专用"。改为 (account_id, channel_id, country_code)，MySQL 视 NULL 互不相同，
故全国默认(country_code=NULL) 与按国家(country_code=ISO2) 可共存同一通道。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w8x9y0z1a2b3"
down_revision: Union[str, None] = "v7w8x9y0z1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "account_channels"
UK = "uk_account_channel"


def _unique_cols() -> set:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    for uc in insp.get_unique_constraints(TABLE):
        if uc["name"] == UK:
            return set(uc["column_names"])
    # 某些 MySQL 反射把唯一键当索引返回
    for ix in insp.get_indexes(TABLE):
        if ix["name"] == UK and ix.get("unique"):
            return set(ix["column_names"])
    return set()


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if TABLE not in insp.get_table_names():
        return
    cols = _unique_cols()
    if cols and "country_code" in cols:
        return  # 已是含 country_code 的唯一键
    if cols:
        op.drop_index(UK, table_name=TABLE)
    op.create_unique_constraint(UK, TABLE, ["account_id", "channel_id", "country_code"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if TABLE not in insp.get_table_names():
        return
    cols = _unique_cols()
    if cols == {"account_id", "channel_id"}:
        return
    if cols:
        op.drop_index(UK, table_name=TABLE)
    op.create_unique_constraint(UK, TABLE, ["account_id", "channel_id"])
