"""add trust_score to features and accuracy_score to sources

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
    op.add_column(
        "data_sources",
        sa.Column("accuracy_score", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.create_table(
        "system_mode_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("unsafe_ratio", sa.Float(), nullable=False),
        sa.Column("total_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "mode IN ('NORMAL', 'DEGRADED', 'SAFE_MODE')",
            name="ck_system_mode",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("system_mode_history")
    op.drop_column("data_sources", "accuracy_score")
    op.drop_column("features", "trust_score")