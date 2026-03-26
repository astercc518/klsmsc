"""自建语音：主叫号码池、外呼任务、挂机短信、DNC、CDR 日志及话单扩展

Revision ID: 005
Revises: 004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(conn, name: str) -> bool:
    return conn.dialect.has_table(conn, name)


def _has_column(conn, table: str, col: str) -> bool:
    if not _has_table(conn, table):
        return False
    insp = inspect(conn)
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()

    # 1) voice_caller_ids（须在 voice_accounts 增加 default_caller_id_id 之前创建）
    if not _has_table(conn, "voice_caller_ids"):
        op.create_table(
            "voice_caller_ids",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("voice_account_id", sa.Integer(), nullable=True),
            sa.Column("number_e164", sa.String(32), nullable=False),
            sa.Column("label", sa.String(128), nullable=True),
            sa.Column("trunk_ref", sa.String(64), nullable=True),
            sa.Column(
                "status",
                sa.Enum("active", "disabled", name="voice_caller_id_status_enum"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
            sa.ForeignKeyConstraint(["voice_account_id"], ["voice_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
        )

    if _has_table(conn, "voice_accounts"):
        if not _has_column(conn, "voice_accounts", "sip_username"):
            op.add_column(
                "voice_accounts",
                sa.Column("sip_username", sa.String(100), nullable=True, comment="SIP注册用户名"),
            )
        if not _has_column(conn, "voice_accounts", "default_caller_id_id"):
            op.add_column(
                "voice_accounts",
                sa.Column("default_caller_id_id", sa.Integer(), nullable=True),
            )
            try:
                op.create_foreign_key(
                    "fk_voice_accounts_default_caller",
                    "voice_accounts",
                    "voice_caller_ids",
                    ["default_caller_id_id"],
                    ["id"],
                )
            except Exception:
                pass

    # 2) 外呼任务与名单
    if not _has_table(conn, "voice_outbound_campaigns"):
        op.create_table(
            "voice_outbound_campaigns",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("voice_account_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "draft",
                    "running",
                    "paused",
                    "completed",
                    "cancelled",
                    name="voice_campaign_status_enum",
                ),
                nullable=True,
            ),
            sa.Column("timezone", sa.String(64), nullable=True),
            sa.Column("window_start", sa.String(8), nullable=True),
            sa.Column("window_end", sa.String(8), nullable=True),
            sa.Column("max_concurrent", sa.Integer(), nullable=True),
            sa.Column(
                "caller_id_mode",
                sa.Enum("fixed", "round_robin", "random", name="voice_campaign_caller_mode_enum"),
                nullable=True,
            ),
            sa.Column("fixed_caller_id_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
            sa.ForeignKeyConstraint(["voice_account_id"], ["voice_accounts.id"]),
            sa.ForeignKeyConstraint(["fixed_caller_id_id"], ["voice_caller_ids.id"]),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
        )

    if not _has_table(conn, "voice_outbound_contacts"):
        op.create_table(
            "voice_outbound_contacts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("campaign_id", sa.Integer(), nullable=False),
            sa.Column("phone_e164", sa.String(32), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "pending",
                    "dialing",
                    "completed",
                    "failed",
                    "skipped",
                    name="voice_contact_status_enum",
                ),
                nullable=True,
            ),
            sa.Column("attempt_count", sa.Integer(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["campaign_id"], ["voice_outbound_campaigns.id"]),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
        )
        op.create_index("ix_voice_outbound_contacts_campaign_id", "voice_outbound_contacts", ["campaign_id"])

    if not _has_table(conn, "voice_hangup_sms_rules"):
        op.create_table(
            "voice_hangup_sms_rules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=True),
            sa.Column("voice_account_id", sa.Integer(), nullable=True),
            sa.Column("campaign_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=True),
            sa.Column("match_answered_only", sa.Boolean(), nullable=True),
            sa.Column("template_body", sa.Text(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
            sa.ForeignKeyConstraint(["voice_account_id"], ["voice_accounts.id"]),
            sa.ForeignKeyConstraint(["campaign_id"], ["voice_outbound_campaigns.id"]),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
        )

    if not _has_table(conn, "voice_dnc_numbers"):
        op.create_table(
            "voice_dnc_numbers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("phone_e164", sa.String(32), nullable=False),
            sa.Column("source", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("account_id", "phone_e164", name="uq_voice_dnc_account_phone"),
            mysql_charset="utf8mb4",
        )

    if not _has_table(conn, "voice_cdr_webhook_logs"):
        op.create_table(
            "voice_cdr_webhook_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("call_id", sa.String(128), nullable=False),
            sa.Column("payload_hash", sa.String(64), nullable=True),
            sa.Column(
                "status",
                sa.Enum("received", "processed", "failed", name="voice_cdr_webhook_status_enum"),
                nullable=True,
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("call_id", name="uq_voice_cdr_webhook_call_id"),
            mysql_charset="utf8mb4",
        )

    # 3) voice_calls 扩展
    if _has_table(conn, "voice_calls"):
        cols = [
            ("provider_call_id", sa.String(128)),
            ("voice_account_id", sa.Integer()),
            ("outbound_campaign_id", sa.Integer()),
            ("direction", sa.String(16)),
            ("sip_extension", sa.String(32)),
            ("answer_time", sa.DateTime()),
            ("billsec", sa.Integer()),
            ("hangup_cause", sa.String(64)),
            ("recording_url", sa.String(512)),
            ("hangup_sms_message_id", sa.String(128)),
        ]
        for name, typ in cols:
            if not _has_column(conn, "voice_calls", name):
                op.add_column("voice_calls", sa.Column(name, typ, nullable=True))
        # FK（可选，失败则忽略）
        try:
            op.create_foreign_key(
                "fk_voice_calls_voice_account",
                "voice_calls",
                "voice_accounts",
                ["voice_account_id"],
                ["id"],
            )
        except Exception:
            pass
        try:
            op.create_foreign_key(
                "fk_voice_calls_campaign",
                "voice_calls",
                "voice_outbound_campaigns",
                ["outbound_campaign_id"],
                ["id"],
            )
        except Exception:
            pass


def downgrade() -> None:
    pass
