"""CoinGecko client — crypto asset prices for regime context.

Uses the free public /coins/{id}/market_chart endpoint (no API key required).
Disabled by default; added in Phase 5 rollout. For advisory context only.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient

logger = logging.getLogger(__name__)

PROVIDER = "coingecko"


class CoinGeckoClient(ExternalApiClient):
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
            base_url="https://api.coingecko.com/api/v3",
            api_key=None,  # free tier no auth
            rate_limit_per_minute=30,
            client=client,
            **kwargs,
        )

    def get_market_chart(
        self,
        coin_id: str,
        *,
        days: int = 90,
        vs_currency: str = "usd",
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        data = self.get_json(
            f"/coins/{coin_id}/market_chart",
            params={"vs_currency": vs_currency, "days": str(days)},
        )
        rows: list[dict[str, Any]] = []
        for ts_ms, value in data.get("prices") or []:
            try:
                obs_date = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).date()
            except Exception:
                continue
            if today is not None and obs_date > today:
                continue
            rows.append(
                {
                    "provider": PROVIDER,
                    "coin_id": coin_id,
                    "date": obs_date,
                    "price": value,
                    "currency": vs_currency,
                }
            )
        rows.sort(key=lambda r: r["date"])
        return rows
