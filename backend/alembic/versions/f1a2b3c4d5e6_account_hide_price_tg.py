"""accounts add hide_price / hide_tg (customer portal display control)

Revision ID: f1a2b3c4d5e6
Revises: c9d0e1f2a3b4
Create Date: 2026-07-25

部分销售要求对其客户在客户门户隐藏单价/剩余条数估算与 TG 信息。
新增两个布尔开关列（默认 0=照常展示，向后兼容存量账户）。仅影响客户门户显示，
不影响计费/路由。迁移做幂等（信息架构判存），便于生产已手工 ALTER 的情况。"""
from alembic import op


revision = "f1a2b3c4d5e6"
down_revision = "c9d0e1f2a3b4"
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
    if not _column_exists(conn, "hide_price"):
        op.execute(
            "ALTER TABLE accounts ADD COLUMN hide_price TINYINT(1) NOT NULL DEFAULT 0 "
            "COMMENT '客户门户隐藏价格(单价/剩余条数估算)'"
        )
    if not _column_exists(conn, "hide_tg"):
        op.execute(
            "ALTER TABLE accounts ADD COLUMN hide_tg TINYINT(1) NOT NULL DEFAULT 0 "
            "COMMENT '客户门户隐藏TG(自绑TG卡片+归属商务联系TG)'"
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "hide_tg"):
        op.execute("ALTER TABLE accounts DROP COLUMN hide_tg")
    if _column_exists(conn, "hide_price"):
        op.execute("ALTER TABLE accounts DROP COLUMN hide_price")
