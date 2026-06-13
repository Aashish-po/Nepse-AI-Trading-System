"""add missing provider quota updated_count column

Revision ID: 0010_add_provider_quota_updated_count
Revises: 0009_add_provider_quota_tracking
Create Date: 2026-06-13

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.reflection import Inspector


revision = "0010_add_provider_quota_updated_count"
down_revision = "0009_add_provider_quota_tracking"
branch_labels = None
depends_on = None


def _get_engine() -> Engine:
    bind = op.get_bind()
    if isinstance(bind, Engine):
        return bind
    if isinstance(bind, Connection):
        return bind.engine
    # Fallback for unexpected bind types; still helps keep Alembic runtime behavior.
    maybe_engine = getattr(bind, "engine", None)
    if isinstance(maybe_engine, Engine):
        return maybe_engine
    raise TypeError(f"Unsupported Alembic bind type: {type(bind)!r}")


def _table_exists(table_name: str) -> bool:
    engine = _get_engine()
    return table_name in Inspector.from_engine(engine).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    engine = _get_engine()
    columns = Inspector.from_engine(engine).get_columns(table_name)
    return column_name in {column["name"] for column in columns}



def upgrade() -> None:
    if _table_exists("provider_quota_usage") and not _column_exists(
        "provider_quota_usage", "updated_count"
    ):
        op.add_column(
            "provider_quota_usage",
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _table_exists("provider_quota_usage") and _column_exists(
        "provider_quota_usage", "updated_count"
    ):
        op.drop_column("provider_quota_usage", "updated_count")
