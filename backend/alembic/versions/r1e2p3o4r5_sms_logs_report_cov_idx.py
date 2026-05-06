"""sms_logs add covering index for business reports

Revision ID: r1e2p3o4r5
Revises: a4b5c6d7e8f9
Create Date: 2026-05-06

业务报表在 sms_logs 上对 last_month 等大区间做按客户/渠道/国家维度的聚合，
原查询走全分区扫描 + JOIN，单次 ~30s。该覆盖索引让 GROUP BY account_id
路径只扫索引，避免回表。"""
from alembic import op


revision = "r1e2p3o4r5"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 检查索引是否已存在（生产已通过 ALTER 直接加，迁移做幂等）
    conn = op.get_bind()
    existing = conn.exec_driver_sql(
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'sms_logs' AND INDEX_NAME = 'idx_sms_report_cov' LIMIT 1"
    ).fetchone()
    if existing:
        return
    op.execute(
        "ALTER TABLE sms_logs ADD INDEX idx_sms_report_cov "
        "(account_id, submit_time, status, selling_price, cost_price), "
        "ALGORITHM=INPLACE, LOCK=NONE"
    )


def downgrade() -> None:
    conn = op.get_bind()
    existing = conn.exec_driver_sql(
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'sms_logs' AND INDEX_NAME = 'idx_sms_report_cov' LIMIT 1"
    ).fetchone()
    if existing:
        op.execute("ALTER TABLE sms_logs DROP INDEX idx_sms_report_cov")
