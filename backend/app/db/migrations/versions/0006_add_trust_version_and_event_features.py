"""add trust_version to data_trust and features, event_overrides, source_correlations

Revision ID: 0006_add_trust_version_and_event_features
Revises: 0005_add_trust_score_to_features
Create Date: 2026-06-06

"""

import sqlalchemy as sa
from alembic import op

revision = "0006_add_trust_version_and_event_features"
down_revision = "0005_add_trust_score_to_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_trust",
        sa.Column("trust_version", sa.String(length=20), nullable=False, server_default="v1"),
    )
    op.add_column(
        "features",
        sa.Column("trust_version", sa.String(length=20), nullable=True),
    )
    op.create_table(
        "source_correlations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_a_id", sa.Integer(), nullable=False),
        sa.Column("source_b_id", sa.Integer(), nullable=False),
        sa.Column("correlation_score", sa.Float(), nullable=False),
        sa.Column("last_sync_detected", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detection_count", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "correlation_score >= 0.0 AND correlation_score <= 1.0",
            name="ck_correlation_score_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "event_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("sensitivity_multiplier", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "sensitivity_multiplier > 0",
            name="ck_sensitivity_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("event_overrides")
    op.drop_table("source_correlations")
    op.drop_column("features", "trust_version")
    op.drop_column("data_trust", "trust_version")