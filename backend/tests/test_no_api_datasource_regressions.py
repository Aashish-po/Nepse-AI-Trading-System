import sqlalchemy as sa


def test_provider_seed_creates_no_api_types(db_session):
    """Regression test: seeding providers must not create DataSource rows with type 'api'.

    This prevents accidental regressions that reintroduce the legacy 'api' value
    which is disallowed by the DB check constraint enforced by migrations.
    """
    from app.services.external.providers import ensure_all_data_sources
    from app.models.data_source import DataSource

    # Run the idempotent seeding helper (it will commit internally).
    ensure_all_data_sources(db_session)

    # Assert there are no DataSource rows with the legacy 'api' type.
    api_rows = db_session.scalars(sa.select(DataSource).where(DataSource.type == "api")).all()
    assert api_rows == []
