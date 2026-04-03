"""私库卡片汇总表 private_library_summaries + 历史数据回填

Revision ID: h8a9b0c1d2e3
Revises: g2h3i4j5k6l7
Create Date: 2026-04-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "h8a9b0c1d2e3"
down_revision: Union[str, None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS private_library_summaries"))
    op.create_table(
        "private_library_summaries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("purpose", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("batch_id", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("carrier", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("library_origin", sa.String(length=20), nullable=False, comment="manual=手工私库 purchased=购入"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("first_at", sa.DateTime(), nullable=True),
        sa.Column("last_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint(
            "account_id",
            "country_code",
            "source",
            "purpose",
            "batch_id",
            "carrier",
            "library_origin",
            name="uq_pls_account_dims",
        ),
    )
    op.create_index("idx_pls_account", "private_library_summaries", ["account_id"], unique=False)
    op.create_index("idx_pls_account_last", "private_library_summaries", ["account_id", "last_at"], unique=False)

    if conn.dialect.name != "mysql":
        return

    # 手工私库分表
    op.execute(
        sa.text(
            """
            INSERT INTO private_library_summaries
            (account_id, country_code, source, purpose, batch_id, carrier, library_origin,
             total_count, used_count, remarks, first_at, last_at, created_at, updated_at)
            SELECT
                account_id,
                IFNULL(NULLIF(TRIM(country_code), ''), '') AS c_code,
                IFNULL(source, '') AS c_source,
                IFNULL(purpose, '') AS c_purpose,
                IFNULL(batch_id, '') AS c_batch_id,
                IFNULL(carrier, '') AS c_carrier,
                'manual',
                COUNT(*),
                SUM(CASE WHEN use_count > 0 THEN 1 ELSE 0 END),
                SUBSTRING(MAX(CONCAT(LPAD(CHAR_LENGTH(IFNULL(remarks,'')), 6, '0'), IFNULL(remarks,''))), 7),
                MIN(created_at),
                MAX(created_at),
                NOW(6),
                NOW(6)
            FROM private_library_numbers
            GROUP BY account_id, c_code, c_source, c_purpose, c_batch_id, c_carrier
            """
        )
    )
    # 公海购入绑定
    op.execute(
        sa.text(
            """
            INSERT INTO private_library_summaries
            (account_id, country_code, source, purpose, batch_id, carrier, library_origin,
             total_count, used_count, remarks, first_at, last_at, created_at, updated_at)
            SELECT
                account_id,
                IFNULL(NULLIF(TRIM(country_code), ''), '') AS c_code,
                IFNULL(source, '') AS c_source,
                IFNULL(purpose, '') AS c_purpose,
                IFNULL(batch_id, '') AS c_batch_id,
                IFNULL(carrier, '') AS c_carrier,
                'purchased',
                COUNT(*),
                SUM(CASE WHEN use_count > 0 THEN 1 ELSE 0 END),
                SUBSTRING(MAX(CONCAT(LPAD(CHAR_LENGTH(IFNULL(remarks,'')), 6, '0'), IFNULL(remarks,''))), 7),
                MIN(created_at),
                MAX(created_at),
                NOW(6),
                NOW(6)
            FROM data_numbers
            WHERE account_id IS NOT NULL
            GROUP BY account_id, c_code, c_source, c_purpose, c_batch_id, c_carrier
            """
        )
    )


def downgrade() -> None:
    op.drop_index("idx_pls_account_last", table_name="private_library_summaries")
    op.drop_index("idx_pls_account", table_name="private_library_summaries")
    op.drop_table("private_library_summaries")
