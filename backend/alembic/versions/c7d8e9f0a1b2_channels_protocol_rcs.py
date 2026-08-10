"""channels.protocol 增加 RCS 值（对接叮咚 BoltTel RCS 供应商）

Revision ID: c7d8e9f0a1b2
Revises: d3e5f7a9c1b2
Create Date: 2026-08-07 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "d3e5f7a9c1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_ENUM = "ENUM('SMPP','HTTP','VIRTUAL','RCS')"
_OLD_ENUM = "ENUM('SMPP','HTTP','VIRTUAL')"


def upgrade() -> None:
    op.execute(f"ALTER TABLE channels MODIFY COLUMN protocol {_NEW_ENUM} NOT NULL COMMENT '协议类型'")


def downgrade() -> None:
    # 防御：回滚前若已有 RCS 通道，先停用并转为 HTTP，避免 ENUM 收窄直接报错丢数据
    op.execute("UPDATE channels SET status='inactive', protocol='HTTP' WHERE protocol='RCS'")
    op.execute(f"ALTER TABLE channels MODIFY COLUMN protocol {_OLD_ENUM} NOT NULL COMMENT '协议类型'")
