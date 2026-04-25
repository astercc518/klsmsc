"""add_sms_landing_tests_table

Revision ID: 40c11d1f7e29
Revises: z9y8x7w6v5u4
Create Date: 2026-04-25 09:01:14.376484
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '40c11d1f7e29'
down_revision: Union[str, None] = 'z9y8x7w6v5u4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sms_landing_tests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('requester_tg_id', sa.BigInteger(), nullable=False, comment='发起员工 TG ID'),
        sa.Column('requester_name', sa.String(length=100), nullable=True, comment='发起员工姓名'),
        sa.Column('supplier_id', sa.Integer(), nullable=False, comment='供应商ID'),
        sa.Column('supplier_name', sa.String(length=100), nullable=True, comment='供应商名称（冗余）'),
        sa.Column('supplier_tg_group_id', sa.String(length=50), nullable=False, comment='供应商 TG 群 ID（冗余）'),
        sa.Column('country', sa.String(length=100), nullable=False, comment='测试国家'),
        sa.Column('sms_content', sa.Text(), nullable=False, comment='测试短信文案（不含中文）'),
        sa.Column(
            'status',
            sa.Enum('pending', 'forwarded', 'completed', 'cancelled', name='sms_landing_test_status_enum'),
            nullable=True,
            comment='状态'
        ),
        sa.Column('forwarded_message_id', sa.Integer(), nullable=True, comment='转发至供应商群的 TG 消息 ID'),
        sa.Column('forwarded_at', sa.DateTime(), nullable=True, comment='转发时间'),
        sa.Column('result_photo_file_ids', sa.Text(), nullable=True, comment='供应商回传截图 file_id（JSON 数组）'),
        sa.Column('result_note', sa.Text(), nullable=True, comment='供应商回复备注'),
        sa.Column('completed_at', sa.DateTime(), nullable=True, comment='完成时间'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_sms_landing_tests_requester_tg_id'),
        'sms_landing_tests',
        ['requester_tg_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_sms_landing_tests_requester_tg_id'), table_name='sms_landing_tests')
    op.drop_table('sms_landing_tests')
    op.execute("DROP TYPE IF EXISTS sms_landing_test_status_enum")
