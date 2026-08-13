"""channels.protocol 收回 RCS：RCS 归入 HTTP，靠 config_json.rcs.vendor 区分上游

RCS 走的就是 HTTP API，不该占一个协议枚举 —— 否则每接一家 RCS 供应商
（叮咚 BoltTel / 节点 nodesms / …）都要动一次 DB 枚举。改为：

    protocol = 'HTTP'  +  config_json.rcs.vendor = 'bolttel' | 'node' | ...

已有 RCS 通道先补写 vendor 标记再转 HTTP，保证判别依据不丢。

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-10 13:20:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENUM_WITH_RCS = "ENUM('SMPP','HTTP','VIRTUAL','RCS')"
_ENUM_NO_RCS = "ENUM('SMPP','HTTP','VIRTUAL')"

# JSON_SET 无法创建中间路径($.rcs 不存在时写 $.rcs.vendor 不生效)，故分两步。
# JSON_VALID 守卫：config_json 是 Text 列，历史行可能存了非法 JSON，
# 直接喂给 JSON_EXTRACT 会整条语句报错。
_ENSURE_RCS_OBJ = """
UPDATE channels
   SET config_json = JSON_SET(
           CASE WHEN config_json IS NULL OR config_json = '' OR JSON_VALID(config_json) = 0
                THEN '{}' ELSE config_json END,
           '$.rcs', JSON_OBJECT())
 WHERE protocol = 'RCS'
   AND (config_json IS NULL OR config_json = '' OR JSON_VALID(config_json) = 0
        OR JSON_EXTRACT(config_json, '$.rcs') IS NULL)
"""

_ENSURE_VENDOR = """
UPDATE channels
   SET config_json = JSON_SET(config_json, '$.rcs.vendor', 'bolttel')
 WHERE protocol = 'RCS'
   AND JSON_VALID(config_json) = 1
   AND JSON_EXTRACT(config_json, '$.rcs.vendor') IS NULL
"""


def upgrade() -> None:
    # 1) 先给存量 RCS 通道补上 vendor 标记（转 HTTP 后这是唯一的判别依据）
    op.execute(_ENSURE_RCS_OBJ)
    op.execute(_ENSURE_VENDOR)
    # 2) 转为 HTTP
    op.execute("UPDATE channels SET protocol = 'HTTP' WHERE protocol = 'RCS'")
    # 3) 收窄枚举
    op.execute(
        f"ALTER TABLE channels MODIFY COLUMN protocol {_ENUM_NO_RCS} NOT NULL COMMENT '协议类型'"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE channels MODIFY COLUMN protocol {_ENUM_WITH_RCS} NOT NULL COMMENT '协议类型'"
    )
    # 带 rcs.vendor 标记的 HTTP 通道还原为 RCS 协议
    op.execute(
        """
        UPDATE channels
           SET protocol = 'RCS'
         WHERE protocol = 'HTTP'
           AND config_json IS NOT NULL AND config_json <> ''
           AND JSON_VALID(config_json) = 1
           AND JSON_EXTRACT(config_json, '$.rcs.vendor') IS NOT NULL
        """
    )
