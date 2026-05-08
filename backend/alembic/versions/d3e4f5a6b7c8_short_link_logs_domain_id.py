"""short_link_logs 增加 domain_id 列与复合索引（per-domain 统计）

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "short_link_logs"
_COL = "domain_id"
_IDX = "idx_short_link_domain_created"  # (domain_id, created_at) 支撑 GROUP BY + MAX(created_at)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL not in cols:
        op.add_column(
            _TABLE,
            sa.Column(_COL, sa.BigInteger, nullable=True, comment="关联short_link_domains.id"),
        )

    existing_idx = {ix["name"] for ix in insp.get_indexes(_TABLE)}
    if _IDX not in existing_idx:
        op.create_index(_IDX, _TABLE, [_COL, "created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE not in insp.get_table_names():
        return

    existing_idx = {ix["name"] for ix in insp.get_indexes(_TABLE)}
    if _IDX in existing_idx:
        op.drop_index(_IDX, table_name=_TABLE)

    cols = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL in cols:
        op.drop_column(_TABLE, _COL)
