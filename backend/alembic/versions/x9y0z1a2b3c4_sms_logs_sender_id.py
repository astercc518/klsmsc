"""sms_logs 增加 sender_id：支持发送时按通道+国家自选 SID（每条落库实际使用的 SID）

Revision ID: x9y0z1a2b3c4
Revises: w8x9y0z1a2b3

业务需求：客户在网页控制台发送时可从该通道+目的国家已审批(active)的 SID 中自选一个
（每批次一个）。worker/适配器按 sms_logs.sender_id 发送，空则回退 channel.default_sender_id。
MySQL 8 末尾加可空列为 INSTANT，对大分区表无锁瞬时完成。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "x9y0z1a2b3c4"
down_revision: Union[str, None] = "w8x9y0z1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "sms_logs"
COL = "sender_id"


def _has_col() -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if TABLE not in insp.get_table_names():
        return True  # 表不存在则跳过（全新部署由 ORM 建表时已含该列）
    return any(c["name"] == COL for c in insp.get_columns(TABLE))


def upgrade() -> None:
    if _has_col():
        return
    op.add_column(
        TABLE,
        sa.Column(COL, sa.String(32), nullable=True, comment="本条实际使用的发送方ID(SID);空则用通道默认"),
    )


def downgrade() -> None:
    if not _has_col():
        return
    op.drop_column(TABLE, COL)
