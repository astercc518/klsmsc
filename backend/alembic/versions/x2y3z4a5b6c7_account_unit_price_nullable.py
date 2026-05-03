"""accounts.unit_price 改为可为 NULL，移除 0.05 sentinel 语义

Revision ID: x2y3z4a5b6c7
Revises: w1x2y3z4a5b6
Create Date: 2026-05-02 16:00:00.000000

背景：
- 旧 pricing.py 把 unit_price=0.05 当作"未设置"sentinel，会 fall-through 到
  account_pricing / country_pricing。
- 真实定价 0.05/条的客户被静默覆盖；ORM 默认 0.0500 与 schema 默认 0.0100 漂移。

修复策略：
- column 改为 nullable，新默认 NULL（明确表达"未设置"）
- 把当前 unit_price=0.05 的账号统一置 NULL，保持原有 fall-through 行为不变
- 0.0100 / 0 / 其他自定义值原样保留（它们都是字面价格，业务方手设）
- 配套 pricing.py:271 改用 `unit_price IS NOT NULL` 判定（在另一次提交里改）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'x2y3z4a5b6c7'
down_revision: Union[str, None] = 'w1x2y3z4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 把当前依赖 sentinel 的 0.05 账号置 NULL，保留 fall-through 行为
    op.execute("UPDATE accounts SET unit_price=NULL WHERE unit_price=0.05")

    # 2. 修改列定义：默认 NULL，nullable
    op.alter_column(
        'accounts', 'unit_price',
        existing_type=sa.DECIMAL(10, 4),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    # 还原默认值与 sentinel；NULL 行回写 0.05 表示"未设置"
    op.execute("UPDATE accounts SET unit_price=0.05 WHERE unit_price IS NULL")
    op.alter_column(
        'accounts', 'unit_price',
        existing_type=sa.DECIMAL(10, 4),
        nullable=True,  # 列原本就是 nullable，这里只回滚 default
        server_default=sa.text('0.0100'),
    )
