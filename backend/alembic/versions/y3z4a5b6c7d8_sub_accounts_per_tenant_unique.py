"""sub_accounts.username 改为租户内唯一（parent_account_id, username）

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7
Create Date: 2026-05-02 17:00:00.000000

旧设计：username 全局 UNIQUE → 客户 A 用了"admin" 阻止客户 B 用同名
新设计：(parent_account_id, username) 联合唯一，租户内唯一即可
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'y3z4a5b6c7d8'
down_revision: Union[str, None] = 'x2y3z4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 删除旧的全局唯一约束
    op.drop_constraint('username', 'sub_accounts', type_='unique')
    # 2. 添加 (parent_account_id, username) 联合唯一
    op.create_unique_constraint(
        'uq_sub_accounts_parent_username',
        'sub_accounts',
        ['parent_account_id', 'username'],
    )
    # idx_username 普通索引保留（用于 username LIKE 查询）


def downgrade() -> None:
    op.drop_constraint('uq_sub_accounts_parent_username', 'sub_accounts', type_='unique')
    op.create_unique_constraint('username', 'sub_accounts', ['username'])
