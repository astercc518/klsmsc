"""account_channels 增加 country_code：支持"每账户每国家独立指定通道"

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1

代理商批发场景：一个 SMPP 客户账户可对多个国家分别指定上游通道。
account_channels.country_code 为空(NULL)=该账户全国家默认通道（向后兼容旧绑定）；
指定 ISO2(如 US)=仅该国家走此通道。配合 core/router.py 的账户+国家二维路由。
销售价仍走 account_pricing(account_id, country_code, price)。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v7w8x9y0z1a2"
down_revision: Union[str, None] = "u6v7w8x9y0z1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "account_channels"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if TABLE not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(TABLE)}
    if "country_code" not in cols:
        op.add_column(
            TABLE,
            sa.Column(
                "country_code",
                sa.String(length=10),
                nullable=True,
                comment="国家代码(ISO2)；空=全国默认，指定=该国家专用通道",
            ),
        )
    idx_names = {ix["name"] for ix in insp.get_indexes(TABLE)}
    if "idx_acc_chan_account_country" not in idx_names:
        op.create_index(
            "idx_acc_chan_account_country",
            TABLE,
            ["account_id", "country_code"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if TABLE not in insp.get_table_names():
        return
    idx_names = {ix["name"] for ix in insp.get_indexes(TABLE)}
    if "idx_acc_chan_account_country" in idx_names:
        op.drop_index("idx_acc_chan_account_country", table_name=TABLE)
    cols = {c["name"] for c in insp.get_columns(TABLE)}
    if "country_code" in cols:
        op.drop_column(TABLE, "country_code")
