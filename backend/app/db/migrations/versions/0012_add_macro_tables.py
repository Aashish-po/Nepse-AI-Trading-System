"""Add macro_series and macro_observations tables

Revision ID: 0012_add_macro_tables
Revises: 0011_add_is_trading_day
Create Date: 2026-06-22

"""

import sqlalchemy as sa
from alembic import op

revision = "0012_add_macro_tables"
down_revision = "0011_add_is_trading_day"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "macro_series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("series_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("units", sa.String(length=100), nullable=True),
        sa.Column("frequency", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("provider", "series_id", name="uq_macro_series_provider_series"),
    )

    op.create_table(
        "macro_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "macro_series_id",
            sa.Integer(),
            sa.ForeignKey("macro_series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("macro_series_id", "date", name="uq_macro_obs_series_date"),
    )
    op.create_index("ix_macro_observations_date", "macro_observations", ["date"])
    op.create_index(
        "ix_macro_obs_series_date", "macro_observations", ["macro_series_id", "date"]
    )


def downgrade() -> None:
    op.drop_index("ix_macro_obs_series_date", table_name="macro_observations")
    op.drop_index("ix_macro_observations_date", table_name="macro_observations")
    op.drop_table("macro_observations")
    op.drop_table("macro_series")
