"""Add is_trading_day column to holiday_calendar

Revision ID: 0011_add_is_trading_day
Revises: 0010_add_provider_quota_updated_count
Create Date: 2026-06-17

"""

from alembic import op

revision = "0011_add_is_trading_day"
down_revision = "0010_add_provider_quota_updated_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("ALTER TABLE holiday_calendar ADD COLUMN is_trading_day BOOLEAN DEFAULT false NOT NULL")


def downgrade() -> None:
    pass