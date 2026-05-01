"""add_smpp_max_binds_to_accounts

Revision ID: e7eec478dee4
Revises: a1b2c3d4e5f6
Create Date: 2026-04-28 17:04:48.035167
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e7eec478dee4'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'accounts',
        sa.Column('smpp_max_binds', sa.Integer(), nullable=True,
                  server_default='5', comment='SMPP 最大并发绑定数'),
    )


def downgrade() -> None:
    op.drop_column('accounts', 'smpp_max_binds')
