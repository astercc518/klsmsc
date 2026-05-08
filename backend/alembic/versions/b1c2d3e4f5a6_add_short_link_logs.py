"""add short_link_logs table for per-number click tracking

Revision ID: b1c2d3e4f5a6
Revises: z9y8x7w6v5u4
Branch Labels: None
Depends On: None
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
# 同时合并两个并行分支头：r1e2p3o4r5（生产当前 head）+ z9y8x7w6v5u4（旧链残留）
down_revision: Union[str, tuple, None] = ("r1e2p3o4r5", "z9y8x7w6v5u4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "short_link_logs"
_IDX_SMSLOG = "idx_short_link_sms_log_id"
_IDX_CREATED = "idx_short_link_created_at"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE in insp.get_table_names():
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # 7 位 Base62；留 1 位余量以防将来扩位
        sa.Column("token", sa.String(8), nullable=False, unique=True,
                  comment="Base62短链token"),
        sa.Column("sms_log_id", sa.BigInteger, nullable=False,
                  comment="关联sms_logs.id"),
        sa.Column("original_url", sa.Text, nullable=False,
                  comment="重定向目标URL"),
        sa.Column("click_count", sa.Integer, nullable=False,
                  server_default="0", comment="点击次数"),
        sa.Column("last_click_at", sa.TIMESTAMP, nullable=True,
                  comment="最近点击时间"),
        sa.Column("created_at", sa.TIMESTAMP, nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    # 按 sms_log_id 快查「该条短信对应的 token/点击数」
    op.create_index(_IDX_SMSLOG, _TABLE, ["sms_log_id"])
    # 按时间范围查点击统计（运营报表）
    op.create_index(_IDX_CREATED, _TABLE, ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _TABLE not in insp.get_table_names():
        return
    op.drop_index(_IDX_CREATED, table_name=_TABLE)
    op.drop_index(_IDX_SMSLOG, table_name=_TABLE)
    op.drop_table(_TABLE)
