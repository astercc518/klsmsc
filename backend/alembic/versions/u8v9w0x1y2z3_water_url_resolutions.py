"""water_url_resolutions

短链替换表：注水任务调度时，将 SMS 文本中的 CF 拦截短链替换为人工解析的真实落地页。

Revision ID: u8v9w0x1y2z3
Revises: e7eec478dee4
Create Date: 2026-04-29 00:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'u8v9w0x1y2z3'
down_revision: Union[str, None] = 'e7eec478dee4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'water_url_resolutions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('short_url', sa.String(500), nullable=False, comment='SMS 中出现的短链（带 scheme，如 https://shorturl.at/UdTAy）'),
        sa.Column('resolved_url', sa.String(2000), nullable=False, comment='人工浏览器解析得到的真实落地页 URL'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='0', comment='累计命中次数'),
        sa.Column('notes', sa.String(500), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('short_url', name='uk_short_url'),
    )


def downgrade() -> None:
    op.drop_table('water_url_resolutions')
