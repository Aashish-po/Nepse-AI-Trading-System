"""FRED client tests (offline via httpx.MockTransport)."""

from __future__ import annotations

from datetime import date

import httpx
from app.core.config import Settings
from app.services.external.fred import FredClient, _parse_value


def _cfg() -> Settings:
    return Settings(_env_file=None, FRED_ENABLED=True, FRED_API_KEY="testkey")  # type: ignore[call-arg]


def _client(handler) -> FredClient:
    transport = httpx.MockTransport(handler)
    return FredClient(_cfg(), client=httpx.Client(transport=transport))


def test_parse_value_handles_missing() -> None:
    assert _parse_value(".") is None
    assert _parse_value("") is None
    assert _parse_value(None) is None
    assert _parse_value("3.14") == 3.14
    assert _parse_value("notanumber") is None


def test_observations_normalized_and_sorted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": "2024-01-03", "value": "4.1"},
                    {"date": "2024-01-01", "value": "4.0"},
                    {"date": "2024-01-02", "value": "."},  # missing
                ]
            },
        )

    client = _client(handler)
    rows = client.get_observations("DGS10", today=date(2024, 12, 31))
    assert [r["date"] for r in rows] == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    assert rows[0]["value"] == 4.0
    assert rows[1]["value"] is None  # explicit missing, not dropped
    assert all(r["provider"] == "fred" for r in rows)


def test_future_dated_observations_dropped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": "2024-01-01", "value": "1.0"},
                    {"date": "2024-06-01", "value": "2.0"},  # after as-of -> leakage
                ]
            },
        )

    client = _client(handler)
    rows = client.get_observations("DGS10", today=date(2024, 1, 31))
    assert [r["date"] for r in rows] == [date(2024, 1, 1)]


def test_series_metadata_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "seriess": [{"title": "10-Year Treasury", "units": "Percent", "frequency": "Daily"}]
            },
        )

    client = _client(handler)
    meta = client.get_series_metadata("DGS10")
    assert meta["name"] == "10-Year Treasury"
    assert meta["units"] == "Percent"
    assert meta["frequency"] == "Daily"
