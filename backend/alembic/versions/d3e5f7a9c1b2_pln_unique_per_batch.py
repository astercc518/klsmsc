"""private_library_numbers 唯一键加入 batch_id：数据包彼此独立

Revision ID: d3e5f7a9c1b2
Revises: a2c4e6f8b0d1
Create Date: 2026-08-03

客户分包上传时，同一号码出现在多个数据包里是正常的，各包应各自计数。
旧唯一键 (account_id, phone_number) 是全账户级去重，上传遇到重号不新增而是把
老行的 batch_id 改挂到新包并清零 use_count，导致：
  - 老数据包凭空缩水，卡片总数与客户上传的文件条数对不上
  - 已发过的号被搬走后变回"未使用"，已用/未用两边都不准

改为 (account_id, phone_number, batch_id)：同号可在不同包各存一份。
唯一键前缀仍是 (account_id, phone_number)，按号码查找的既有查询照常走索引。

存量数据不动（历史包归属已无法还原），只影响此后的上传。
迁移幂等（信息架构判存）。
"""
from alembic import op


revision = "d3e5f7a9c1b2"
down_revision = "a2c4e6f8b0d1"
branch_labels = None
depends_on = None

TABLE = "private_library_numbers"
OLD_IDX = "uq_pln_account_phone"
NEW_IDX = "uq_pln_account_phone_batch"


def _index_exists(conn, table: str, index: str) -> bool:
    return bool(conn.exec_driver_sql(
        "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = %s AND INDEX_NAME = %s LIMIT 1",
        (table, index),
    ).fetchone())


def upgrade() -> None:
    conn = op.get_bind()

    # 先建新唯一键再删旧的：中途失败也不会留下"无唯一约束"的窗口。
    # batch_id 全表非空（无 NULL/空串），扩三列不会放宽为"多 NULL 可重复"。
    if not _index_exists(conn, TABLE, NEW_IDX):
        conn.exec_driver_sql(
            f"ALTER TABLE {TABLE} "
            f"ADD UNIQUE INDEX {NEW_IDX} (account_id, phone_number, batch_id), "
            f"ALGORITHM=INPLACE, LOCK=NONE"
        )

    if _index_exists(conn, TABLE, OLD_IDX):
        conn.exec_driver_sql(
            f"ALTER TABLE {TABLE} DROP INDEX {OLD_IDX}, ALGORITHM=INPLACE, LOCK=NONE"
        )


def downgrade() -> None:
    conn = op.get_bind()

    # 回滚需要账户内号码唯一。分包独立上线后若已产生跨包重号，这一步会失败，
    # 必须先人工决定保留哪一份再回滚——不在迁移里静默删数据。
    if not _index_exists(conn, TABLE, OLD_IDX):
        conn.exec_driver_sql(
            f"ALTER TABLE {TABLE} "
            f"ADD UNIQUE INDEX {OLD_IDX} (account_id, phone_number), "
            f"ALGORITHM=INPLACE, LOCK=NONE"
        )

    if _index_exists(conn, TABLE, NEW_IDX):
        conn.exec_driver_sql(
            f"ALTER TABLE {TABLE} DROP INDEX {NEW_IDX}, ALGORITHM=INPLACE, LOCK=NONE"
        )
