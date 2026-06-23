"""Fixer client — foreign exchange rates.

Returns a single latest rate for a base/quote pair. Uses the Fixer API with
a plan-required key; disabled by default.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient

logger = logging.getLogger(__name__)

PROVIDER = "fixer"


class FixerClient(ExternalApiClient):
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
            base_url="https://data.fixer.io/api",
            api_key=cfg.fixer_api_key,
            auth_query_param="access_key",
            rate_limit_per_minute=30,
            client=client,
            **kwargs,
        )

    def get_latest(self, base: str = "EUR", symbols: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"base": base}
        if symbols:
            params["symbols"] = symbols
        data = self.get_json("/latest", params=params)
        return {
            "base": data.get("base"),
            "date": data.get("date"),
            "rates": data.get("rates") or {},
            "provider": PROVIDER,
        }
