"""add_data_quality_tables

Revision ID: 0004_add_data_quality_tables
Revises: 0003_update_ingestion_logs_add_source_id_and_duration
Create Date: 2026-06-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_add_data_quality_tables"
down_revision = "0003_update_ingestion_logs_add_source_id_and_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holiday_calendar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "is_trading_holiday",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uq_holiday_calendar_date"),
    )
    op.create_table(
        "data_trust",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("trust_score", sa.Float(), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=True),
        sa.Column("volume_anomaly_detected", sa.Boolean(), nullable=True),
        sa.Column("missing_dates_count", sa.Integer(), nullable=True),
        sa.Column("rejected_count", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "trust_score >= 0.0 AND trust_score <= 1.0",
            name="ck_trust_score_range",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id", "date", name="uq_data_trust_stock_id_date"),
    )
    op.create_table(
        "data_quality_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("total_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_trust_score", sa.Float(), nullable=True),
        sa.Column("total_rejected_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_missing_dates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_volume_anomalies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_date", name="uq_data_quality_reports_report_date"),
    )
    op.create_table(
        "data_quality_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('critical', 'warning', 'info')", name="ck_alert_severity"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_trust_stock_id_date", "data_trust", ["stock_id", "date"], unique=False)
    op.create_index("ix_alerts_report_id", "data_quality_alerts", ["report_id"])
    op.create_index("ix_alerts_symbol_date", "data_quality_alerts", ["symbol", "date"])


def downgrade() -> None:
    op.drop_index("ix_alerts_symbol_date", table_name="data_quality_alerts")
    op.drop_index("ix_alerts_report_id", table_name="data_quality_alerts")
    op.drop_table("data_quality_alerts")
    op.drop_index("ix_data_trust_stock_id_date", table_name="data_trust")
    op.drop_table("data_quality_reports")
    op.drop_table("data_trust")
    op.drop_table("holiday_calendar")
