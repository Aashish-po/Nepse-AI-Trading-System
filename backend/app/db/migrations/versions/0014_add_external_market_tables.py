"""Add external_symbols, external_prices tables

Revision ID: 0014_add_external_market_tables
Revises: 0013_add_news_sentiment_tables
Create Date: 2026-06-22

"""

import sqlalchemy as sa
from alembic import op

revision = "0014_add_external_market_tables"
down_revision = "0013_add_news_sentiment_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_symbols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("external_symbol", sa.String(length=50), nullable=False),
        sa.Column("asset_class", sa.String(length=30), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=True),
        sa.Column("exchange", sa.String(length=50), nullable=True),
        sa.Column("timezone", sa.String(length=50), nullable=True),
        sa.Column("mapped_nepse_symbol", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "provider", "external_symbol", name="uq_external_symbols_provider_symbol"
        ),
    )

    op.create_table(
        "external_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("external_symbol", sa.String(length=50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "provider", "external_symbol", "date", name="uq_external_prices_provider_symbol_date"
        ),
    )
    op.create_index(
        "ix_external_prices_provider_symbol_date",
        "external_prices",
        ["provider", "external_symbol", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_external_prices_provider_symbol_date", table_name="external_prices")
    op.drop_table("external_prices")
    op.drop_table("external_symbols")
