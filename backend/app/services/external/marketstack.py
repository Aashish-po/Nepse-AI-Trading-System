"""Marketstack client — global end-of-day OHLCV / benchmark context.

Normalises to the OHLCV contract used by the ingestion layer:

    {provider, external_symbol, date (date), open, high, low, close,
     volume (int|None), currency, raw}

Rows failing OHLCV invariants (low<=open/close<=high, volume>=0) are dropped
with a warning rather than stored. Future-dated rows (relative to ``today``) are
rejected to prevent look-ahead leakage. Marketstack is for global/benchmark
context only — it is NOT assumed to cover NEPSE symbols.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient
from app.services.external.ohlcv import normalize_ohlcv_rows

logger = logging.getLogger(__name__)

PROVIDER = "marketstack"


class MarketstackClient(ExternalApiClient):
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
            base_url=cfg.marketstack_base_url,
            api_key=cfg.marketstack_api_key,
            auth_query_param="access_key",
            rate_limit_per_minute=cfg.marketstack_rate_limit_per_minute,
            client=client,
            **kwargs,
        )

    def get_eod(
        self,
        symbol: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch end-of-day OHLCV for ``symbol`` and normalise + validate."""
        params: dict[str, Any] = {"symbols": symbol, "limit": limit}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        data = self.get_json("/v1/eod", params=params)
        raw_rows = [self._to_contract(symbol, item) for item in (data.get("data") or [])]
        return normalize_ohlcv_rows(PROVIDER, symbol, raw_rows, today=today)

    @staticmethod
    def _to_contract(symbol: str, item: dict[str, Any]) -> dict[str, Any]:
        raw_date = item.get("date")
        parsed: date | None = None
        if raw_date:
            try:
                # Marketstack dates are ISO-8601 timestamps (e.g. 2024-01-02T00:00:00+0000).
                parsed = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    parsed = date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    parsed = None
        return {
            "external_symbol": symbol,
            "date": parsed,
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "volume": item.get("volume"),
            "currency": None,
            "raw": item,
        }
