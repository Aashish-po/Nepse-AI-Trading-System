"""add trust_score to features table

Revision ID: 0005_add_trust_score_to_features
Revises: 0004_add_data_quality_tables
Create Date: 2026-06-05

"""

import sqlalchemy as sa
from alembic import op

revision = "0005_add_trust_score_to_features"
down_revision = "0004_add_data_quality_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("features", sa.Column("trust_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("features", "trust_score")