"""Polygon.io client — optional alternative market-data provider.

Provides minimal OHLCV coverage as an alternative to Marketstack/Finnhub.
Disabled by default; added in Phase 5 rollout. Uses the shared OHLCV normaliser
for validation.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient
from app.services.external.ohlcv import normalize_ohlcv_rows

logger = logging.getLogger(__name__)

PROVIDER = "polygon"


class PolygonClient(ExternalApiClient):
    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> None:
        cfg = cfg or default_settings
        super().__init__(
            provider=PROVIDER,
            base_url="https://api.polygon.io",
            api_key=cfg.polygon_api_key,
            auth_query_param="apiKey",
            rate_limit_per_minute=5,
            client=client,
            **kwargs,
        )

    def get_aggs(
        self,
        symbol: str,
        *,
        from_date: str,
        to_date: str,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        data = self.get_json(
            f"/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}",
            params={"adjusted": "true", "limit": 5000},
        )
        raw_rows = []
        for item in data.get("results") or []:
            try:
                obs_date = date.fromtimestamp(item["t"] / 1000.0)
            except Exception:
                continue
            raw_rows.append(
                {
                    "external_symbol": symbol,
                    "date": obs_date,
                    "open": item.get("o"),
                    "high": item.get("h"),
                    "low": item.get("l"),
                    "close": item.get("c"),
                    "volume": item.get("v"),
                    "currency": None,
                    "raw": item,
                }
            )
        return normalize_ohlcv_rows(PROVIDER, symbol, raw_rows, today=today)
