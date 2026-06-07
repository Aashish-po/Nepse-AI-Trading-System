"""add benchmark tables and update trades for transaction tracking

Revision ID: 0007_add_benchmark_and_trade_fields
Revises: 0006_add_trust_version_and_event_features
Create Date: 2026-06-07

"""

import sqlalchemy as sa
from alembic import op

revision = "0007_add_benchmark_and_trade_fields"
down_revision = "0006_add_trust_version_and_event_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("transaction_cost", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("fill_rate", sa.Numeric(precision=6, scale=4), nullable=True),
    )
    op.create_table(
        "nepse_index",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uq_nepse_date"),
    )
    op.create_index("ix_nepse_date", "nepse_index", ["date"])
    op.create_table(
        "sector_indices",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sector", "date", name="uq_sector_date"),
    )
    op.create_index("ix_sector_sector_date", "sector_indices", ["sector", "date"])


def downgrade() -> None:
    op.drop_index("ix_sector_sector_date", table_name="sector_indices")
    op.drop_table("sector_indices")
    op.drop_index("ix_nepse_date", table_name="nepse_index")
    op.drop_table("nepse_index")
    op.drop_column("trades", "fill_rate")
    op.drop_column("trades", "transaction_cost")