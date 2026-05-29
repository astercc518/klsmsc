"""sms_logs 增加 (submit_time, id) 联合索引，消除发送记录分页 filesort

Revision ID: r3s4t5u6v7w8
Revises: q1r2s3t4u5v6

发送记录页(GET /sms/records)管理员视角默认 30 天窗口下 ~168 万行，分页查询
ORDER BY submit_time DESC, id DESC 现有 idx_submit_status_price(submit_time,...)
无 id 列，二级排序触发 filesort 1.68M 行，实测 LIMIT 20 也要 7+ 秒。

新增覆盖 (submit_time, id) 即可让分页 LIMIT 20 直接取前 20 条索引项，
无需 filesort。预期降至 50ms 级。

实施:
- ALGORITHM=INPLACE, LOCK=NONE: MySQL 8 onine DDL，期间业务读写不阻塞
- 6M 行表预估构建时间 2-5 分钟、磁盘 ~200MB
- 与 sms_logs 现有按月分区配合(分区裁剪先做，再走索引)

DESC 显式声明: MySQL 8 支持 descending index；查询 ORDER BY DESC DESC 命中
无需反向扫描。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r3s4t5u6v7w8"
down_revision: Union[str, None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if "idx_submit_id_desc" in existing:
        return
    # 直接 SQL，确保 DESC + ALGORITHM/LOCK 指定生效（SQLAlchemy create_index 不能传 ALGORITHM）
    op.execute(
        "ALTER TABLE sms_logs "
        "ADD INDEX idx_submit_id_desc (submit_time DESC, id DESC), "
        "ALGORITHM=INPLACE, LOCK=NONE"
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if "idx_submit_id_desc" not in existing:
        return
    op.execute("ALTER TABLE sms_logs DROP INDEX idx_submit_id_desc")
