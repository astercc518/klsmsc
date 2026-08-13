"""业务类型增加 rcs：account_templates.business_type + accounts.business_type

RCS 作为独立业务（与短信/语音/数据并列）参与开户模板、开户邀请、客户归类与报表，
其单价与短信量级差异很大，混进 sms 会污染业绩/成本口径。

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-07 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TPL_NEW = "ENUM('sms','voice','data','rcs')"
_TPL_OLD = "ENUM('sms','voice','data')"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE account_templates MODIFY COLUMN business_type {_TPL_NEW} "
        f"NOT NULL DEFAULT 'sms' COMMENT '业务类型'"
    )
    op.execute(
        f"ALTER TABLE accounts MODIFY COLUMN business_type {_TPL_NEW} "
        f"NOT NULL DEFAULT 'sms' COMMENT '业务类型'"
    )


def downgrade() -> None:
    # 防御：回滚前把 rcs 归并回 sms，避免 ENUM 收窄直接报错丢数据
    op.execute("UPDATE account_templates SET business_type='sms' WHERE business_type='rcs'")
    op.execute("UPDATE accounts SET business_type='sms' WHERE business_type='rcs'")
    op.execute(
        f"ALTER TABLE account_templates MODIFY COLUMN business_type {_TPL_OLD} "
        f"NOT NULL DEFAULT 'sms' COMMENT '业务类型'"
    )
    op.execute(
        f"ALTER TABLE accounts MODIFY COLUMN business_type {_TPL_OLD} "
        f"NOT NULL DEFAULT 'sms' COMMENT '业务类型'"
    )
