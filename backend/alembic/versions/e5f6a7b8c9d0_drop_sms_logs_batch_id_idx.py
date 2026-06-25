"""drop redundant sms_logs idx_sms_logs_batch_id (索引瘦身)

Revision ID: e5f6a7b8c9d0
Revises: d4f5a6b7c8d9
Create Date: 2026-06-25

索引治理续：单列 idx_sms_logs_batch_id(batch_id) 被复合索引
idx_sms_logs_batch_status(batch_id, status) 的左前缀完全覆盖。
IGNORE INDEX 模拟删除后 EXPLAIN 实测：所有 batch_id 前导查询
(WHERE batch_id=? 计数 / IN..GROUP BY batch_id,status / batch_id=?+status IN)
全部回落到 batch_status，plan 相同或更优(同 ref、key_len=5、仍 Using index 覆盖;
带 status 的还升 range)。usage stats：本索引仅 ~2万读 vs 复合索引 ~1.1亿读。

幂等守门：存在才删/重建。在线 ALGORITHM=INPLACE, LOCK=NONE(秒级、不锁表)。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 被 idx_sms_logs_batch_status 左前缀覆盖的冗余单列索引
IDX_BATCH_ID = "idx_sms_logs_batch_id"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_BATCH_ID in existing:
        # 在线删除：千万级表必须 INPLACE + LOCK=NONE,避免锁住并发发送
        op.execute(
            f"ALTER TABLE sms_logs DROP INDEX {IDX_BATCH_ID}, "
            "ALGORITHM=INPLACE, LOCK=NONE"
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_BATCH_ID not in existing:
        op.execute(
            f"ALTER TABLE sms_logs ADD INDEX {IDX_BATCH_ID} (batch_id), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        )
