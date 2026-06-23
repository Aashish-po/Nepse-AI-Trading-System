"""Marketstack/Finnhub OHLCV ingestion + global feature tests (offline)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest
import sqlalchemy as sa
from app.core.config import Settings
from app.models.external_market import ExternalPrice, ExternalSymbol
from app.services.external.finnhub import FinnhubClient
from app.services.external.marketstack import MarketstackClient
from app.services.external.ohlcv import normalize_ohlcv_rows
from app.services.external_features import GlobalMarketFeatureBuilder
from app.services.external_market import MarketIngestionService


def _ms_cfg() -> Settings:
    return Settings(marketstack_enabled=True, marketstack_api_key="k")  # type: ignore[call-arg]


def _fh_cfg() -> Settings:
    return Settings(finnhub_enabled=True, finnhub_api_key="k")  # type: ignore[call-arg]


# ----- OHLCV validation (shared normaliser) --------------------------------


def test_normalize_rejects_bad_bounds_and_negative_volume() -> None:
    rows = [
        {
            "date": date(2024, 1, 1),
            "open": 5,
            "high": 4,
            "low": 3,
            "close": 4,
            "volume": 10,
        },  # high<open
        {
            "date": date(2024, 1, 2),
            "open": 4,
            "high": 6,
            "low": 3,
            "close": 5,
            "volume": -1,
        },  # neg vol
        {"date": date(2024, 1, 3), "open": 4, "high": 6, "low": 3, "close": 5, "volume": 10},  # ok
    ]
    out = normalize_ohlcv_rows("marketstack", "SPY", rows)
    assert len(out) == 1
    assert out[0]["date"] == date(2024, 1, 3)


def test_normalize_drops_future_dated() -> None:
    rows = [{"date": date(2024, 6, 10), "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1}]
    out = normalize_ohlcv_rows("marketstack", "SPY", rows, today=date(2024, 6, 1))
    assert out == []


# ----- Marketstack client ---------------------------------------------------


def test_marketstack_eod_normalizes(db_session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "date": "2024-01-02T00:00:00+0000",
                        "open": 10,
                        "high": 12,
                        "low": 9,
                        "close": 11,
                        "volume": 100,
                    },
                    {
                        "date": "2024-01-03T00:00:00+0000",
                        "open": 11,
                        "high": 13,
                        "low": 10,
                        "close": 12,
                        "volume": 120,
                    },
                ]
            },
        )

    client = MarketstackClient(
        _ms_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    rows = client.get_eod("SPY", today=date(2024, 12, 31))
    assert [r["date"] for r in rows] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert rows[0]["close"] == 11.0


# ----- Finnhub client -------------------------------------------------------


def test_finnhub_candles_status_not_ok_returns_empty(db_session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"s": "no_data"})

    client = FinnhubClient(_fh_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.get_candles("AAPL", from_ts=0, to_ts=1, today=date(2024, 12, 31)) == []


def test_finnhub_candles_unzip(db_session) -> None:
    ts1 = int(datetime(2024, 1, 2, tzinfo=UTC).timestamp())
    ts2 = int(datetime(2024, 1, 3, tzinfo=UTC).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "s": "ok",
                "o": [10, 11],
                "h": [12, 13],
                "l": [9, 10],
                "c": [11, 12],
                "v": [100, 120],
                "t": [ts1, ts2],
            },
        )

    client = FinnhubClient(_fh_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    rows = client.get_candles("AAPL", from_ts=0, to_ts=ts2, today=date(2024, 12, 31))
    assert len(rows) == 2
    assert rows[0]["date"] == date(2024, 1, 2)


# ----- Ingestion service ----------------------------------------------------


def test_disabled_provider_skips(db_session) -> None:
    svc = MarketIngestionService(
        "marketstack", Settings(marketstack_enabled=False), session=db_session
    )  # type: ignore[call-arg]
    result = svc.run(["SPY"])
    assert result["status"] == "skipped"


def test_unsupported_provider_raises() -> None:
    with pytest.raises(ValueError):
        MarketIngestionService("nonsense")


def test_ingest_is_idempotent(db_session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "date": "2024-01-02T00:00:00+0000",
                        "open": 10,
                        "high": 12,
                        "low": 9,
                        "close": 11,
                        "volume": 100,
                    },
                ]
            },
        )

    client = MarketstackClient(
        _ms_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    svc = MarketIngestionService("marketstack", _ms_cfg(), session=db_session, client=client)
    r1 = svc.run(["SPY"], today=date(2024, 12, 31))
    assert r1["inserted"] == 1
    assert db_session.scalar(
        sa.select(ExternalSymbol).where(ExternalSymbol.external_symbol == "SPY")
    )

    client2 = MarketstackClient(
        _ms_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    svc2 = MarketIngestionService("marketstack", _ms_cfg(), session=db_session, client=client2)
    r2 = svc2.run(["SPY"], today=date(2024, 12, 31))
    assert r2["inserted"] == 0
    assert db_session.scalar(sa.select(sa.func.count()).select_from(ExternalPrice)) == 1


# ----- Global feature builder ----------------------------------------------


def _seed_prices(db_session, n: int) -> None:
    for i in range(n):
        db_session.add(
            ExternalPrice(
                provider="marketstack",
                external_symbol="SPY",
                date=date(2024, 1, 1) + __import__("datetime").timedelta(days=i),
                open=100.0 + i,
                high=100.0 + i,
                low=100.0 + i,
                close=100.0 + i,
                volume=10,
            )
        )
    db_session.commit()


def test_global_feature_builder_returns(db_session) -> None:
    _seed_prices(db_session, 30)  # closes 100..129 ascending by date
    builder = GlobalMarketFeatureBuilder("marketstack", "SPY", session=db_session)
    feats = builder.build_features(date(2024, 1, 30))  # latest close = 129
    # 5d return: 129 / 124 - 1 (builder rounds to 6 dp).
    assert feats["values"]["global_equity_return_5d"] == pytest.approx(129 / 124 - 1, abs=1e-5)
    assert feats["values"]["global_equity_return_20d"] == pytest.approx(129 / 109 - 1, abs=1e-5)


def test_global_feature_builder_insufficient_history_is_none(db_session) -> None:
    _seed_prices(db_session, 3)
    builder = GlobalMarketFeatureBuilder("marketstack", "SPY", session=db_session)
    feats = builder.build_features(date(2024, 1, 3))
    assert feats["values"]["global_equity_return_5d"] is None
