"""sms_batches.status 增加 paused 值（管理员任务管理）

Revision ID: w1x2y3z4a5b6
Revises: v0w1x2y3z4a5
Create Date: 2026-05-01 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'w1x2y3z4a5b6'
down_revision: Union[str, None] = 'v0w1x2y3z4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_ENUM = "ENUM('pending','processing','paused','completed','failed','cancelled')"
_OLD_ENUM = "ENUM('pending','processing','completed','failed','cancelled')"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE sms_batches MODIFY COLUMN status {_NEW_ENUM} NOT NULL"
    )


def downgrade() -> None:
    # 防御：回滚前若有 paused 值，先转 cancelled，避免 ENUM 收窄报错
    op.execute("UPDATE sms_batches SET status='cancelled' WHERE status='paused'")
    op.execute(
        f"ALTER TABLE sms_batches MODIFY COLUMN status {_OLD_ENUM} NOT NULL"
    )
