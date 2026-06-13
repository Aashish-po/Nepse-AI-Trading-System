"""add signal provider/telegram tracking tables

Revision ID: 0008_add_signal_tracking_and_telegram_alerts
Revises: 0007_add_benchmark_and_trade_fields
Create Date: 2026-06-12

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "0008_add_signal_tracking_and_telegram_alerts"
down_revision = "0007_add_benchmark_and_trade_fields"
branch_labels = None
depends_on = None


def _get_inspector() -> Inspector:
    bind = op.get_bind()
    # Alembic's `op.get_bind()` is typed as `Connection`.
    # Pylance typing note: `Inspector.from_engine` expects an Engine; at runtime
    # the bind typically exposes `.engine`.
    engine = getattr(bind, "engine", bind)  # type: ignore[arg-type]
    return Inspector.from_engine(engine)  # type: ignore[arg-type]



def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = _get_inspector()
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _table_exists(table_name: str) -> bool:
    inspector = _get_inspector()
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = _get_inspector()
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}



def upgrade() -> None:
    if not _column_exists("signals", "provider"):
        op.add_column(
            "signals",
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="rules"),
        )
    if not _column_exists("signals", "model_source"):
        op.add_column(
            "signals",
            sa.Column("model_source", sa.String(length=32), nullable=True),
        )
    if not _column_exists("signals", "prompt_version"):
        op.add_column(
            "signals",
            sa.Column("prompt_version", sa.String(length=20), nullable=True),
        )
    if not _column_exists("signals", "inference_cost"):
        op.add_column(
            "signals",
            sa.Column("inference_cost", sa.Numeric(precision=10, scale=6), nullable=True),
        )
    if not _column_exists("signals", "token_count"):
        op.add_column(
            "signals",
            sa.Column("token_count", sa.Integer(), nullable=True),
        )
    if not _column_exists("signals", "rule_params"):
        op.add_column(
            "signals",
            sa.Column("rule_params", sa.Text(), nullable=True),
        )
    if not _column_exists("signals", "target_price"):
        op.add_column(
            "signals",
            sa.Column("target_price", sa.Numeric(precision=18, scale=4), nullable=True),
        )
    if not _column_exists("signals", "take_profit"):
        op.add_column(
            "signals",
            sa.Column("take_profit", sa.Numeric(precision=18, scale=4), nullable=True),
        )
    if not _column_exists("signals", "stop_loss"):
        op.add_column(
            "signals",
            sa.Column("stop_loss", sa.Numeric(precision=18, scale=4), nullable=True),
        )
    if not _column_exists("signals", "trailing_stop"):
        op.add_column(
            "signals",
            sa.Column("trailing_stop", sa.Numeric(precision=10, scale=6), nullable=True),
        )

    if not _table_exists("telegram_daily_alerts"):
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
    if not _index_exists("telegram_daily_alerts", "ix_telegram_daily_alerts_symbol_date"):
        op.create_index(
            "ix_telegram_daily_alerts_symbol_date",
            "telegram_daily_alerts",
            ["symbol", "alert_date"],
        )
    if not _index_exists("telegram_daily_alerts", "ix_telegram_daily_alerts_alert_date"):
        op.create_index(
            "ix_telegram_daily_alerts_alert_date",
            "telegram_daily_alerts",
            ["alert_date"],
        )


def downgrade() -> None:
    if _table_exists("telegram_daily_alerts"):
        if _index_exists("telegram_daily_alerts", "ix_telegram_daily_alerts_alert_date"):
            op.drop_index("ix_telegram_daily_alerts_alert_date", table_name="telegram_daily_alerts")
        if _index_exists("telegram_daily_alerts", "ix_telegram_daily_alerts_symbol_date"):
            op.drop_index("ix_telegram_daily_alerts_symbol_date", table_name="telegram_daily_alerts")
        op.drop_table("telegram_daily_alerts")
    for column_name in (
        "trailing_stop",
        "stop_loss",
        "take_profit",
        "target_price",
        "rule_params",
        "token_count",
        "inference_cost",
        "prompt_version",
        "model_source",
        "provider",
    ):
        if _column_exists("signals", column_name):
            op.drop_column("signals", column_name)
