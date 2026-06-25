"""drop sms_logs ix_sms_logs_status_refunded_at (索引瘦身)

Revision ID: d4f5a6b7c8d9
Revises: z2b3c4d5e6f7
Create Date: 2026-06-25

索引治理：v0w1x2y3z4a5 建的 (status, refunded_at) 复合索引在退款候选查询里
EXPLAIN rows_selected=0（优化器走 idx_status 即可），属冗余/死锁磁铁，
生产已手工 DROP。此迁移补记该 DROP，消除全新部署的 schema drift。

幂等：生产已手工 DROP，stamp 即可（不重复执行 DDL）；
全新部署正常 upgrade，会真正把 v0w1x2y3z4a5 建出的索引删掉。
两种情形都靠 information_schema 守门，存在才删。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4f5a6b7c8d9"
down_revision: Union[str, None] = "z2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# v0w1x2y3z4a5 建的退款候选过滤索引；实测冗余，已下线
IDX_STATUS_REFUNDED = "ix_sms_logs_status_refunded_at"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_STATUS_REFUNDED in existing:
        op.drop_index(IDX_STATUS_REFUNDED, table_name="sms_logs")


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "sms_logs" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("sms_logs")}
    if IDX_STATUS_REFUNDED not in existing:
        op.create_index(
            IDX_STATUS_REFUNDED,
            "sms_logs",
            ["status", "refunded_at"],
        )
