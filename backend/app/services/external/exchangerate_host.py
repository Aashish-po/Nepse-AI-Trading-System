"""ExchangeRate.host client — free FX conversion fallback.

No API key required; used as a secondary source when Fixer is unavailable or
the user prefers a free-tier option.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient

logger = logging.getLogger(__name__)

PROVIDER = "exchangerate_host"


class ExchangeRateHostClient(ExternalApiClient):
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
            base_url="https://api.exchangerate.host",
            api_key=None,  # free, no auth
            rate_limit_per_minute=30,
            client=client,
            **kwargs,
        )

    def get_latest(self, base: str = "USD", symbols: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"base": base}
        if symbols:
            params["symbols"] = symbols
        data = self.get_json("/live", params=params)
        return {
            "base": base,
            "date": None,
            "rates": data.get("rates") or {},
            "provider": PROVIDER,
        }
