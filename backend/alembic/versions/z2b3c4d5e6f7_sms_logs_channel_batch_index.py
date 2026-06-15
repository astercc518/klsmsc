"""sms_logs 增加 (channel_id, batch_id) 覆盖索引：加速全局批次按通道筛选

Revision ID: z2b3c4d5e6f7
Revises: z1a2b3c4d5e6

全局短信任务页按通道查询走 `SELECT DISTINCT batch_id FROM sms_logs WHERE channel_id=X`，
原 idx_channel_id_submit 不含 batch_id，需回表读数百万行 + 临时表去重（实测 ~12s）。
新建 (channel_id, batch_id) 覆盖索引后变松散索引扫描、index-only，子秒返回。

8.8M 行分区表，用 InnoDB ONLINE DDL（ALGORITHM=INPLACE, LOCK=NONE）建索引，不阻塞读写。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "z2b3c4d5e6f7"
down_revision: Union[str, None] = "z1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "sms_logs"
INDEX = "idx_channel_id_batch"


def _has_index() -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if TABLE not in insp.get_table_names():
        return True  # 表不存在则跳过（全新部署由 ORM 建表时已含该索引）
    return any(ix["name"] == INDEX for ix in insp.get_indexes(TABLE))


def upgrade() -> None:
    if _has_index():
        return
    # ONLINE DDL，避免锁大表；asyncmy/MySQL 8 支持
    op.execute(
        f"ALTER TABLE {TABLE} ADD INDEX {INDEX} (channel_id, batch_id), "
        f"ALGORITHM=INPLACE, LOCK=NONE"
    )


def downgrade() -> None:
    if not _has_index():
        return
    op.execute(f"ALTER TABLE {TABLE} DROP INDEX {INDEX}")
