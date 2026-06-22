"""Macro ingestion + feature builder tests (offline)."""

from __future__ import annotations

from datetime import date

import httpx
import sqlalchemy as sa
from app.core.config import Settings
from app.models.data_source import IngestionLog
from app.models.macro import MacroObservation, MacroSeries
from app.services.external.fred import FredClient
from app.services.external_features import MacroFeatureBuilder
from app.services.external_macro import MacroIngestionService


def _enabled_cfg() -> Settings:
    return Settings(  # type: ignore[call-arg]
        fred_enabled=True,
        fred_api_key="testkey",
        fred_default_series="DGS10",
    )


def _fred_handler(values: list[tuple[str, str]]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/series"):
            return httpx.Response(
                200,
                json={"seriess": [{"title": "10Y", "units": "Percent", "frequency": "Daily"}]},
            )
        return httpx.Response(
            200,
            json={"observations": [{"date": d, "value": v} for d, v in values]},
        )

    return handler


def _client(handler) -> FredClient:
    return FredClient(_enabled_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_disabled_provider_skips_without_calls(db_session) -> None:
    # Default settings: FRED disabled -> must not error and must not call network.
    svc = MacroIngestionService(Settings(fred_enabled=False), session=db_session)  # type: ignore[call-arg]
    result = svc.run()
    assert result["status"] == "skipped"
    assert result["reason"] == "provider_disabled"


def test_ingest_inserts_observations_and_logs(db_session) -> None:
    handler = _fred_handler([("2024-01-01", "4.0"), ("2024-01-02", "4.1")])
    svc = MacroIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    result = svc.run(["DGS10"], today=date(2024, 12, 31))

    assert result["status"] == "success"
    assert result["inserted"] == 2
    series = db_session.scalar(sa.select(MacroSeries).where(MacroSeries.series_id == "DGS10"))
    assert series is not None and series.units == "Percent"
    obs = db_session.scalars(sa.select(MacroObservation)).all()
    assert len(obs) == 2
    log = db_session.scalar(sa.select(IngestionLog).where(IngestionLog.source == "fred"))
    assert log is not None and log.status == "success"


def test_ingest_is_idempotent(db_session) -> None:
    handler = _fred_handler([("2024-01-01", "4.0"), ("2024-01-02", "4.1")])
    svc = MacroIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    svc.run(["DGS10"], today=date(2024, 12, 31))
    # Second run with the same data inserts nothing new.
    handler2 = _fred_handler([("2024-01-01", "4.0"), ("2024-01-02", "4.2")])  # value updated
    svc2 = MacroIngestionService(_enabled_cfg(), session=db_session, client=_client(handler2))
    result = svc2.run(["DGS10"], today=date(2024, 12, 31))
    assert result["inserted"] == 0
    count = db_session.scalar(sa.select(sa.func.count()).select_from(MacroObservation))
    assert count == 2
    # Existing observation value was updated in place.
    latest = db_session.scalar(
        sa.select(MacroObservation).where(MacroObservation.date == date(2024, 1, 2))
    )
    assert latest is not None and latest.value == 4.2


def test_macro_feature_builder_point_in_time(db_session) -> None:
    handler = _fred_handler([("2024-01-01", "4.0"), ("2024-02-01", "4.5")])
    svc = MacroIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    svc.run(["DGS10"], today=date(2024, 12, 31))

    builder = MacroFeatureBuilder(session=db_session)
    # As of mid-January, only the Jan 1 observation is available.
    feats = builder.build_features(date(2024, 1, 15))
    assert feats["values"]["fred_dgs10"] == 4.0
    assert feats["meta"]["macro_observation_dates"]["fred_dgs10"] == "2024-01-01"
    # Series not ingested -> explicitly None, not fabricated.
    assert feats["values"]["fred_cpi"] is None

    # As of March, the later observation is the most recent available.
    feats2 = builder.build_features(date(2024, 3, 1))
    assert feats2["values"]["fred_dgs10"] == 4.5


def test_macro_feature_builder_no_future_leakage(db_session) -> None:
    handler = _fred_handler([("2024-06-01", "9.9")])
    svc = MacroIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    svc.run(["DGS10"], today=date(2024, 12, 31))
    builder = MacroFeatureBuilder(session=db_session)
    # As-of date BEFORE the only observation -> no value leaks back.
    feats = builder.build_features(date(2024, 1, 1))
    assert feats["values"]["fred_dgs10"] is None
