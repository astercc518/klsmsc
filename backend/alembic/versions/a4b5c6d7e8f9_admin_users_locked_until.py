"""admin_users 增加 locked_until 字段：5 次密码错误临时锁 15 分钟

Revision ID: a4b5c6d7e8f9
Revises: y3z4a5b6c7d8
Create Date: 2026-05-05 13:00:00.000000

旧设计：5 次错密 → status='locked' 永久锁 → 需 super_admin 手动解
新设计：5 次错密 → locked_until = NOW() + 15min（自愈），
        到期自动恢复；status='locked' 仍保留作 super_admin 手动永久封锁
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = 'y3z4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'admin_users',
        sa.Column('locked_until', sa.DateTime(), nullable=True,
                  comment='临时锁定到期时间；NULL=未锁；5 次错密自动设为 NOW+15min')
    )


def downgrade() -> None:
    op.drop_column('admin_users', 'locked_until')
