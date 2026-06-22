"""FRED (Federal Reserve Economic Data) client.

Fetches macro series metadata and observations. Normalises to the macro
contract used by the ingestion layer:

    {provider, series_id, date (YYYY-MM-DD), value (float|None),
     units, frequency, source_name, raw}

FRED encodes missing observations as the string ``"."`` — these are normalised
to ``None`` (explicitly missing), never dropped silently. Observations dated in
the future relative to ``today`` are rejected to prevent look-ahead leakage.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient

logger = logging.getLogger(__name__)

PROVIDER = "fred"


class FredClient(ExternalApiClient):
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
            base_url=cfg.fred_base_url,
            api_key=cfg.fred_api_key,
            auth_query_param="api_key",
            rate_limit_per_minute=cfg.fred_rate_limit_per_minute,
            client=client,
            **kwargs,
        )

    def get_series_metadata(self, series_id: str) -> dict[str, Any]:
        """Return ``{series_id, name, units, frequency}`` for a series."""
        data = self.get_json(
            "/fred/series",
            params={"series_id": series_id, "file_type": "json"},
        )
        seriess = data.get("seriess") or []
        if not seriess:
            return {"series_id": series_id, "name": None, "units": None, "frequency": None}
        s = seriess[0]
        return {
            "series_id": series_id,
            "name": s.get("title"),
            "units": s.get("units"),
            "frequency": s.get("frequency"),
        }

    def get_observations(
        self,
        series_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return normalised observations for ``series_id``.

        ``today`` (defaults to the largest observation date if not supplied is
        NOT done — caller passes the as-of date) bounds future leakage; rows
        dated after it are dropped with a warning.
        """
        params: dict[str, Any] = {"series_id": series_id, "file_type": "json"}
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date
        data = self.get_json("/fred/series/observations", params=params)
        return self._normalize_observations(series_id, data, today=today)

    @staticmethod
    def _normalize_observations(
        series_id: str,
        data: dict[str, Any],
        *,
        today: date | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for obs in data.get("observations") or []:
            raw_date = obs.get("date")
            if not raw_date:
                continue
            try:
                obs_date = date.fromisoformat(raw_date)
            except (TypeError, ValueError):
                logger.warning("fred: unparseable date %r for %s", raw_date, series_id)
                continue
            if today is not None and obs_date > today:
                logger.warning(
                    "fred: dropping future-dated observation %s for %s", raw_date, series_id
                )
                continue
            rows.append(
                {
                    "provider": PROVIDER,
                    "series_id": series_id,
                    "date": obs_date,
                    "value": _parse_value(obs.get("value")),
                    "raw": obs,
                }
            )
        rows.sort(key=lambda r: r["date"])
        return rows


def _parse_value(raw: Any) -> float | None:
    """FRED uses ``"."`` for missing; anything non-numeric -> None (missing)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text in ("", "."):
        return None
    try:
        return float(text)
    except ValueError:
        return None
