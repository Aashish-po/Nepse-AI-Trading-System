from __future__ import annotations

import pytest
from app.models.data_source import DataSource
from sqlalchemy.exc import IntegrityError


def test_legacy_api_data_source_type_is_rejected(db_session) -> None:
    db_session.add(DataSource(name="LEGACY", type="api", is_active=True))

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_scraper_and_csv_source_types_are_allowed(db_session) -> None:
    db_session.add_all(
        [
            DataSource(name="SCRAPER", type="scraper", is_active=True),
            DataSource(name="CSV", type="csv", is_active=False),
        ]
    )
    db_session.commit()

    rows = db_session.query(DataSource).order_by(DataSource.name).all()
    assert [row.type for row in rows] == ["csv", "scraper"]
