"""add provider quota tracking table

Revision ID: 0009_add_provider_quota_tracking
Revises: 0008_add_signal_tracking_and_telegram_alerts
Create Date: 2026-06-12

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.types import JSON

# revision identifiers, used by Alembic.
revision = "0009_add_provider_quota_tracking"
down_revision = "0008_add_signal_tracking_and_telegram_alerts"
branch_labels = None
depends_on = None


def _get_inspector() -> Inspector:
    bind = op.get_bind()
    engine = getattr(bind, "engine", bind)  # type: ignore[arg-type]
    return Inspector.from_engine(engine)  # type: ignore[arg-type]



def _table_exists(table_name: str) -> bool:
    inspector = _get_inspector()
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = _get_inspector()
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}



def upgrade() -> None:
    if not _table_exists("provider_quota_usage"):
        op.create_table(
            "provider_quota_usage",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("quota_date", sa.Date(), nullable=False),
            sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
            sa.Column("metadata_json", JSON().with_variant(JSONB, "postgresql"), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "provider", "quota_date", name="uq_provider_quota_usage_provider_date"
            ),
        )
    if not _index_exists("provider_quota_usage", "ix_provider_quota_usage_provider_date"):
        op.create_index(
            "ix_provider_quota_usage_provider_date",
            "provider_quota_usage",
            ["provider", "quota_date"],
        )


def downgrade() -> None:
    if _table_exists("provider_quota_usage"):
        if _index_exists("provider_quota_usage", "ix_provider_quota_usage_provider_date"):
            op.drop_index("ix_provider_quota_usage_provider_date", table_name="provider_quota_usage")
        op.drop_table("provider_quota_usage")
