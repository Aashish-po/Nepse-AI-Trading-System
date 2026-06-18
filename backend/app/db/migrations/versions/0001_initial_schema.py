"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stocks_symbol", "stocks", ["symbol"], unique=True)

    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("metadata", json_type, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("metrics", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("config", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("high", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("low", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("close", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id", "date", name="uq_prices_stock_id_date"),
    )
    op.create_index("ix_prices_date", "prices", ["date"], unique=False)
    op.create_index(
        "ix_prices_stock_id_date_desc",
        "prices",
        ["stock_id", sa.text("date DESC")],
        unique=False,
    )

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("feature_version", sa.String(length=50), nullable=False),
        sa.Column("values", json_type, nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stock_id",
            "date",
            "feature_version",
            name="uq_features_stock_date_version",
        ),
    )
    op.create_index("ix_features_stock_id_date", "features", ["stock_id", "date"], unique=False)

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_stock_id_date", "signals", ["stock_id", "date"], unique=False)

    op.create_table(
        "backtests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("config", json_type, nullable=False),
        sa.Column("metrics", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("backtest_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cash", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("positions", json_type, nullable=False),
        sa.ForeignKeyConstraint(["backtest_id"], ["backtests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("backtest_id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["backtest_id"], ["backtests.id"]),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_table("portfolio_snapshots")
    op.drop_table("backtests")
    op.drop_index("ix_signals_stock_id_date", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_features_stock_id_date", table_name="features")
    op.drop_table("features")
    op.drop_index("ix_prices_stock_id_date_desc", table_name="prices")
    op.drop_index("ix_prices_date", table_name="prices")
    op.drop_table("prices")
    op.drop_table("strategies")
    op.drop_table("models")
    op.drop_table("datasets")
    op.drop_index("ix_stocks_symbol", table_name="stocks")
    op.drop_table("stocks")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
