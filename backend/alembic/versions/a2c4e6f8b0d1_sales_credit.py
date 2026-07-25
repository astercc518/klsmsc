"""sales credit: admin_users credit columns + balance_logs sales_credit type + sales_credit_logs

Revision ID: a2c4e6f8b0d1
Revises: f1a2b3c4d5e6
Create Date: 2026-07-25

管理员给销售(role=sales)授信额度，销售用该额度自行给名下客户充值：
  - admin_users 增加 credit_limit / credit_used（循环信用额度，默认 0）
  - balance_logs.change_type 枚举增加 sales_credit（授信充值，报表可与现金区分）
  - 新增 sales_credit_logs 授信账本（含唯一 idempotency_key 防重复扣款）
迁移幂等（信息架构判存）。"""
from alembic import op


revision = "a2c4e6f8b0d1"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _col_exists(conn, table: str, column: str) -> bool:
    return bool(conn.exec_driver_sql(
        "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1",
        (table, column),
    ).fetchone())


def _table_exists(conn, table: str) -> bool:
    return bool(conn.exec_driver_sql(
        "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = %s LIMIT 1",
        (table,),
    ).fetchone())


def _enum_has(conn, table: str, column: str, value: str) -> bool:
    row = conn.exec_driver_sql(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1",
        (table, column),
    ).fetchone()
    return bool(row) and (f"'{value}'" in row[0])


BALANCE_ENUM_WITH = (
    "ENUM('charge','refund','deposit','withdraw','adjustment','refund_recharge','sales_credit')"
)
BALANCE_ENUM_WITHOUT = (
    "ENUM('charge','refund','deposit','withdraw','adjustment','refund_recharge')"
)


def upgrade() -> None:
    conn = op.get_bind()

    if not _col_exists(conn, "admin_users", "credit_limit"):
        op.execute(
            "ALTER TABLE admin_users ADD COLUMN credit_limit DECIMAL(12,4) NOT NULL DEFAULT 0 "
            "COMMENT '授信额度上限'"
        )
    if not _col_exists(conn, "admin_users", "credit_used"):
        op.execute(
            "ALTER TABLE admin_users ADD COLUMN credit_used DECIMAL(12,4) NOT NULL DEFAULT 0 "
            "COMMENT '已用授信'"
        )

    if not _enum_has(conn, "balance_logs", "change_type", "sales_credit"):
        op.execute(
            f"ALTER TABLE balance_logs MODIFY COLUMN change_type {BALANCE_ENUM_WITH} NOT NULL "
            "COMMENT '变动类型: refund_recharge=退补充值; sales_credit=销售授信充值'"
        )

    if not _table_exists(conn, "sales_credit_logs"):
        op.execute(
            """
            CREATE TABLE sales_credit_logs (
                id BIGINT NOT NULL AUTO_INCREMENT,
                sales_id INT NOT NULL,
                change_type ENUM('limit_change','recharge','settlement') NOT NULL
                    COMMENT 'limit_change=调额/recharge=授信充值/settlement=结算冲销',
                amount DECIMAL(12,4) NOT NULL COMMENT '本次变动金额(正数)',
                credit_limit_after DECIMAL(12,4) NOT NULL COMMENT '变动后额度上限',
                credit_used_after DECIMAL(12,4) NOT NULL COMMENT '变动后已用授信',
                account_id INT NULL COMMENT '关联客户账户ID(recharge)',
                related_balance_log_id BIGINT NULL COMMENT '关联客户余额流水ID(recharge)',
                operator_id INT NULL COMMENT '操作人ID',
                operator_name VARCHAR(50) NULL COMMENT '操作人用户名快照',
                idempotency_key VARCHAR(64) NULL COMMENT '幂等键(防重复充值)',
                description TEXT NULL COMMENT '备注',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                PRIMARY KEY (id),
                UNIQUE KEY uq_sales_credit_idem (idempotency_key),
                KEY idx_sales_credit_sales (sales_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销售授信流水账本'
            """
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "sales_credit_logs"):
        op.execute("DROP TABLE sales_credit_logs")
    if _enum_has(conn, "balance_logs", "change_type", "sales_credit"):
        # 回退前需确保无 sales_credit 存量行，否则 MODIFY 会失败
        op.execute(
            f"ALTER TABLE balance_logs MODIFY COLUMN change_type {BALANCE_ENUM_WITHOUT} NOT NULL "
            "COMMENT '变动类型: refund_recharge=退补充值(不计算业绩/成本)'"
        )
    if _col_exists(conn, "admin_users", "credit_used"):
        op.execute("ALTER TABLE admin_users DROP COLUMN credit_used")
    if _col_exists(conn, "admin_users", "credit_limit"):
        op.execute("ALTER TABLE admin_users DROP COLUMN credit_limit")
