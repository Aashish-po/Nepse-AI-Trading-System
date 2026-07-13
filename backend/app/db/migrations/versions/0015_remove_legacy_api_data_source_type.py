"""remove_legacy_api_data_source_type

Revision ID: 0015_remove_legacy_api_data_source_type
Revises: 0014_add_external_market_tables
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_remove_legacy_api_data_source_type"
down_revision = "0014_add_external_market_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE data_sources SET type = 'csv' WHERE type = 'api'"))
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=sa.String(length=20),
            server_default="csv",
            existing_nullable=False,
        )
        batch_op.drop_constraint("ck_data_sources_type", type_="check")
        batch_op.create_check_constraint("ck_data_sources_type", "type IN ('scraper', 'csv')")

def downgrade() -> None:
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_constraint("ck_data_sources_type", type_="check")
        batch_op.alter_column(
            "type",
            existing_type=sa.String(length=20),
            server_default="api",
            existing_nullable=False,
        )
        batch_op.create_check_constraint("ck_data_sources_type", "type IN ('api', 'scraper', 'csv')")