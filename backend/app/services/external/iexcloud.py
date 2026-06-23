"""IEX Cloud client — optional US equities/fundamentals provider.

Minimal adapter; disabled by default. Added in Phase 5 rollout.
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

PROVIDER = "iexcloud"


class IEXCloudClient(ExternalApiClient):
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
            base_url="https://cloud.iexapis.com",
            api_key=cfg.iexcloud_api_key,
            auth_query_param="token",
            rate_limit_per_minute=30,
            client=client,
            **kwargs,
        )

    def get_historical(
        self,
        symbol: str,
        *,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        data = self.get_json(
            f"/stable/stock/{symbol}/chart/max",
        )
        raw_rows = []
        for item in data or []:
            try:
                obs_date = date.fromisoformat(str(item.get("date") or "")[:10])
            except Exception:
                continue
            raw_rows.append(
                {
                    "external_symbol": symbol,
                    "date": obs_date,
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "volume": item.get("volume"),
                    "currency": None,
                    "raw": item,
                }
            )
        return normalize_ohlcv_rows(PROVIDER, symbol, raw_rows, today=today)
