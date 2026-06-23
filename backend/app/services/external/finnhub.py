"""Finnhub client — stock candles (OHLCV) and company profile.

Normalises candles to the shared OHLCV contract. Finnhub's ``/stock/candle``
returns parallel arrays with a status field ``s``; a non-``ok`` status yields an
empty result (no rows). Timestamps ``t`` are epoch seconds mapped to dates, and
missing volume arrays are tolerated. For global/benchmark context only — NEPSE
coverage is not assumed.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient
from app.services.external.ohlcv import normalize_ohlcv_rows

logger = logging.getLogger(__name__)

PROVIDER = "finnhub"


class FinnhubClient(ExternalApiClient):
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
            base_url=cfg.finnhub_base_url,
            api_key=cfg.finnhub_api_key,
            auth_query_param="token",
            rate_limit_per_minute=cfg.finnhub_rate_limit_per_minute,
            client=client,
            **kwargs,
        )

    def get_candles(
        self,
        symbol: str,
        *,
        resolution: str = "D",
        from_ts: int,
        to_ts: int,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch daily candles and normalise + validate to OHLCV rows."""
        data = self.get_json(
            "/api/v1/stock/candle",
            params={"symbol": symbol, "resolution": resolution, "from": from_ts, "to": to_ts},
        )
        if data.get("s") != "ok":
            logger.info("finnhub: no candle data for %s (status=%s)", symbol, data.get("s"))
            return []
        return normalize_ohlcv_rows(PROVIDER, symbol, self._unzip(symbol, data), today=today)

    def get_profile(self, symbol: str) -> dict[str, Any]:
        """Return company metadata for ``symbol`` (may be empty for unknown tickers)."""
        data = self.get_json("/api/v1/stock/profile2", params={"symbol": symbol})
        return {
            "external_symbol": symbol,
            "name": data.get("name"),
            "currency": data.get("currency"),
            "country": data.get("country"),
            "exchange": data.get("exchange"),
        }

    @staticmethod
    def _unzip(symbol: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        opens = data.get("o") or []
        highs = data.get("h") or []
        lows = data.get("l") or []
        closes = data.get("c") or []
        vols = data.get("v") or []
        times = data.get("t") or []
        rows: list[dict[str, Any]] = []
        for i, ts in enumerate(times):
            try:
                obs_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
            except (TypeError, ValueError, OSError):
                continue
            rows.append(
                {
                    "external_symbol": symbol,
                    "date": obs_date,
                    "open": opens[i] if i < len(opens) else None,
                    "high": highs[i] if i < len(highs) else None,
                    "low": lows[i] if i < len(lows) else None,
                    "close": closes[i] if i < len(closes) else None,
                    "volume": vols[i] if i < len(vols) else None,
                    "currency": None,
                    "raw": {"t": ts},
                }
            )
        return rows
