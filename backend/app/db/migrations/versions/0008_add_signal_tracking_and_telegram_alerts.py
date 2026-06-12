"""add signal provider/telegram tracking tables

Revision ID: 0008_add_signal_tracking_and_telegram_alerts
Revises: 0007_add_benchmark_and_trade_fields
Create Date: 2026-06-12

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_add_signal_tracking_and_telegram_alerts"
down_revision = "0007_add_benchmark_and_trade_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="rules"),
    )
    op.add_column(
        "signals",
        sa.Column("model_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("inference_cost", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("token_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("rule_params", sa.Text(), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("target_price", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("take_profit", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("stop_loss", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("trailing_stop", sa.Numeric(precision=10, scale=6), nullable=True),
    )

    op.create_table(
        "telegram_daily_alerts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("alert_date", sa.Date(), nullable=False),
        sa.Column("telegram_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("delivery_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("alert_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "alert_date", name="uq_telegram_daily_alert"),
        sa.CheckConstraint(
            "delivery_status IN ('pending','sent','failed','skipped')",
            name="ck_telegram_delivery_status",
        ),
    )
    op.create_index(
        "ix_telegram_daily_alerts_symbol_date",
        "telegram_daily_alerts",
        ["symbol", "alert_date"],
    )
    op.create_index(
        "ix_telegram_daily_alerts_alert_date",
        "telegram_daily_alerts",
        ["alert_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_daily_alerts_alert_date", table_name="telegram_daily_alerts")
    op.drop_index("ix_telegram_daily_alerts_symbol_date", table_name="telegram_daily_alerts")
    op.drop_table("telegram_daily_alerts")
    op.drop_column("signals", "trailing_stop")
    op.drop_column("signals", "stop_loss")
    op.drop_column("signals", "take_profit")
    op.drop_column("signals", "target_price")
    op.drop_column("signals", "rule_params")
    op.drop_column("signals", "token_count")
    op.drop_column("signals", "inference_cost")
    op.drop_column("signals", "prompt_version")
    op.drop_column("signals", "model_source")
    op.drop_column("signals", "provider")
