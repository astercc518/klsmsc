"""accounts add private_library_auto_dedup (私有库自动去重开关)

Revision ID: g3h4i5j6k7l8
Revises: f0a1b2c3d4e5
Create Date: 2026-08-18

客户上传多份数据包(A/B/C)之间常有重复号码。数据包彼此独立时，同一号码在每个
包里各存一份、各自计 use_count，发完 A 包再发 B 包会把重号再发一次。
新增账户级开关：开启后发送取号按号码全局去重——号码只要在本账户任一数据包里
已被使用过就不再取；关闭(默认，向后兼容存量账户)维持原来的分包独立行为。
迁移做幂等（信息架构判存），便于生产已手工 ALTER 的情况。"""
from alembic import op


revision = "g3h4i5j6k7l8"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def _column_exists(conn, column: str) -> bool:
    row = conn.exec_driver_sql(
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'accounts' AND COLUMN_NAME = %s LIMIT 1",
        (column,),
    ).fetchone()
    return bool(row)


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "private_library_auto_dedup"):
        op.execute(
            "ALTER TABLE accounts ADD COLUMN private_library_auto_dedup TINYINT(1) "
            "NOT NULL DEFAULT 0 "
            "COMMENT '私有库自动去重(发送取号跳过其它数据包已使用过的同号)'"
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "private_library_auto_dedup"):
        op.execute("ALTER TABLE accounts DROP COLUMN private_library_auto_dedup")
