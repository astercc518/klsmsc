"""sms_logs add refund tracking columns

为 P0-1「系统问题导致提交失败可退款」功能新增字段：
  refunded_at          NULL → 未退款；非 NULL → 已退款时间戳
  refunded_by          管理员用户名
  refunded_amount      实际退回金额（与 selling_price 通常一致；保留独立字段以适配部分退款）

Revision ID: v0w1x2y3z4a5
Revises: u8v9w0x1y2z3
Create Date: 2026-05-01 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'v0w1x2y3z4a5'
down_revision: Union[str, None] = 'u8v9w0x1y2z3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sms_logs',
        sa.Column('refunded_at', sa.DateTime(), nullable=True, comment='退款时间；NULL 表示未退款'),
    )
    op.add_column(
        'sms_logs',
        sa.Column('refunded_by', sa.String(100), nullable=True, comment='执行退款的管理员用户名'),
    )
    op.add_column(
        'sms_logs',
        sa.Column('refunded_amount', sa.Numeric(18, 6), nullable=True, comment='实际退款金额'),
    )
    # 列出未退款的 failed 候选时按 status + refunded_at 高频过滤
    op.create_index(
        'ix_sms_logs_status_refunded_at',
        'sms_logs',
        ['status', 'refunded_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_sms_logs_status_refunded_at', table_name='sms_logs')
    op.drop_column('sms_logs', 'refunded_amount')
    op.drop_column('sms_logs', 'refunded_by')
    op.drop_column('sms_logs', 'refunded_at')
