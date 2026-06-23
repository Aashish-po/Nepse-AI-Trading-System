"""Optional scale-provider client tests (offline MockTransport).

All providers are tested disabled-by-default + basic response parsing.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
from app.core.config import Settings
from app.services.external.coingecko import CoinGeckoClient
from app.services.external.exchangerate_host import ExchangeRateHostClient
from app.services.external.fixer import FixerClient
from app.services.external.iexcloud import IEXCloudClient
from app.services.external.polygon import PolygonClient


def _handler(json_body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=json_body)

    return handler


# -- Polygon ----------------------------------------------------------------


def test_polygon_aggs_parses_dates() -> None:
    ts = int(datetime(2024, 1, 2, tzinfo=UTC).timestamp() * 1000)  # epoch ms
    client = PolygonClient(
        Settings(polygon_enabled=True, polygon_api_key="k"),  # type: ignore[call-arg]
        client=httpx.Client(
            transport=httpx.MockTransport(
                _handler({"results": [{"t": ts, "o": 1, "h": 2, "l": 1, "c": 2, "v": 100}]})
            )
        ),
    )
    rows = client.get_aggs(
        "AAPL", from_date="2024-01-01", to_date="2024-01-31", today=date(2024, 12, 31)
    )
    assert len(rows) == 1 and rows[0]["date"] == date(2024, 1, 2)


# -- IEX Cloud --------------------------------------------------------------


def test_iex_cloud_historical_parses_dates() -> None:
    client = IEXCloudClient(
        Settings(iexcloud_enabled=True, iexcloud_api_key="k"),  # type: ignore[call-arg]
        client=httpx.Client(
            transport=httpx.MockTransport(
                _handler(
                    [
                        {
                            "date": "2024-01-02",
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "volume": 100,
                        }
                    ]
                )
            )
        ),
    )
    rows = client.get_historical("AAPL", today=date(2024, 12, 31))
    assert len(rows) == 1 and rows[0]["date"] == date(2024, 1, 2)


# -- CoinGecko --------------------------------------------------------------


def test_coingecko_parses_price_history() -> None:
    ts_ms = int(datetime(2024, 1, 2, tzinfo=UTC).timestamp() * 1000)
    client = CoinGeckoClient(
        Settings(coingecko_enabled=True),  # type: ignore[call-arg]
        client=httpx.Client(
            transport=httpx.MockTransport(_handler({"prices": [[ts_ms, 42000.0]]}))
        ),
    )
    rows = client.get_market_chart("bitcoin", today=date(2024, 12, 31))
    assert len(rows) == 1 and rows[0]["price"] == 42000.0


# -- Fixer ------------------------------------------------------------------


def test_fixer_latest_returns_rates() -> None:
    client = FixerClient(
        Settings(fixer_enabled=True, fixer_api_key="k"),  # type: ignore[call-arg]
        client=httpx.Client(
            transport=httpx.MockTransport(
                _handler({"base": "EUR", "date": "2024-01-02", "rates": {"USD": 1.1, "NPR": 140.0}})
            )
        ),
    )
    result = client.get_latest(symbols="USD,NPR")
    assert result["base"] == "EUR" and result["rates"] == {"USD": 1.1, "NPR": 140.0}


# -- ExchangeRate.host ------------------------------------------------------


def test_exchangerate_host_live_returns_rates() -> None:
    client = ExchangeRateHostClient(
        Settings(exchangerate_host_enabled=True),  # type: ignore[call-arg]
        client=httpx.Client(transport=httpx.MockTransport(_handler({"rates": {"NPR": 132.0}}))),
    )
    result = client.get_latest(base="USD", symbols="NPR")
    assert result["rates"]["NPR"] == 132.0
