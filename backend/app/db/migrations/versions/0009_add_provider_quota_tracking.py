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


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = _get_inspector()
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


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
    else:
        columns = {column["name"] for column in _get_inspector().get_columns("provider_quota_usage")}
        for name, column in [
            ("request_count", sa.Column("request_count", sa.Integer(), nullable=False, server_default="0")),
            ("signal_count", sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0")),
            ("updated_count", sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0")),
            ("success_count", sa.Column("success_count", sa.Integer(), nullable=False, server_default="0")),
            ("failure_count", sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0")),
            ("skipped_count", sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0")),
            ("token_count", sa.Column("token_count", sa.Integer(), nullable=False, server_default="0")),
            ("cost", sa.Column("cost", sa.Float(), nullable=False, server_default="0")),
            ("metadata_json", sa.Column("metadata_json", JSON().with_variant(JSONB, "postgresql"), nullable=True)),
            (
                "updated_at",
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            ),
        ]:
            if name not in columns:
                op.add_column("provider_quota_usage", column)

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
