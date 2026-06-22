"""Tests for the DataSource seed helper (Commit 0)."""

from __future__ import annotations

import sqlalchemy as sa
from app.models.data_source import DataSource
from app.services.external.providers import PROVIDERS, ensure_all_data_sources


def test_seed_creates_one_data_source_per_provider(db_session) -> None:
    created = ensure_all_data_sources(db_session)
    assert created == len(PROVIDERS)
    names = set(db_session.scalars(sa.select(DataSource.name)).all())
    for spec in PROVIDERS:
        assert spec.name in names


def test_seed_is_idempotent(db_session) -> None:
    ensure_all_data_sources(db_session)
    created_again = ensure_all_data_sources(db_session)
    assert created_again == 0
    count = db_session.scalar(sa.select(sa.func.count()).select_from(DataSource))
    assert count == len(PROVIDERS)
