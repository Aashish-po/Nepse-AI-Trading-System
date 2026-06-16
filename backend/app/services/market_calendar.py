"""Market calendar backed by the Calendarific Global Holidays API.

Determines whether a given date is a Nepali public holiday and therefore
whether the NEPSE market is closed.

NEPSE trades Sunday–Friday and is closed on Saturday plus public holidays.

Holidays are fetched and cached **per year** (a single API call returns the
whole year), so repeated lookups never re-hit the network. If the API is
unavailable or no API key is configured, the service degrades gracefully to
weekend-only logic and logs a warning.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from collections.abc import Iterable, Mapping
from typing import Any

import requests
from app.core.config import settings

logger = logging.getLogger(__name__)

CALENDARIFIC_URL = "https://calendarific.com/api/v2/holidays"
# Python weekday(): Monday=0 ... Saturday=5, Sunday=6.
# NEPSE only closes weekly on Saturday (Sunday is a trading day).
DEFAULT_CLOSED_WEEKDAYS: frozenset[int] = frozenset({5})
DEFAULT_TIMEOUT = 10.0


def _as_date(value: dt.date | dt.datetime) -> dt.date:
    return value.date() if isinstance(value, dt.datetime) else value


def _is_national_holiday(holiday: Mapping[str, Any]) -> bool:
    """True if a Calendarific holiday entry is a national/public holiday."""
    types = holiday.get("type") or []
    tokens = [str(t).lower() for t in types if isinstance(t, str)]
    tokens.append(str(holiday.get("primary_type", "")).lower())
    blob = " ".join(tokens)
    return "national" in blob or "public" in blob


def _parse_holiday_date(holiday: Mapping[str, Any]) -> dt.date | None:
    """Extract the calendar date from a Calendarific holiday entry."""
    date_field = holiday.get("date") or {}
    iso = date_field.get("iso")
    if isinstance(iso, str) and len(iso) >= 10:
        try:
            return dt.date.fromisoformat(iso[:10])
        except ValueError:
            pass
    parts = date_field.get("datetime") or {}
    try:
        return dt.date(int(parts["year"]), int(parts["month"]), int(parts["day"]))
    except (KeyError, TypeError, ValueError):
        return None


class MarketCalendar:
    """Resolve NEPSE trading days using the Calendarific holiday API.

    The HTTP client is injectable (``http``) so tests can supply a stub; it only
    needs a ``get(url, params=..., timeout=...)`` method returning an object with
    ``raise_for_status()`` and ``json()`` (the ``requests`` contract).
    """

    def __init__(
        self,
        api_key: str | None = None,
        country: str | None = None,
        *,
        base_url: str = CALENDARIFIC_URL,
        national_only: bool | None = None,
        closed_weekdays: Iterable[int] = DEFAULT_CLOSED_WEEKDAYS,
        http: Any | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = settings.calendarific_api_key if api_key is None else api_key
        self._country = country or settings.calendarific_country
        self._base_url = base_url
        self._national_only = (
            settings.calendarific_national_only if national_only is None else national_only
        )
        self._closed_weekdays = frozenset(closed_weekdays)
        self._http = http if http is not None else requests
        self._timeout = timeout
        self._cache: dict[int, set[dt.date]] = {}
        self._lock = threading.Lock()

    def _fetch_year(self, year: int) -> set[dt.date]:
        """Fetch every holiday for ``year`` in a single Calendarific call."""
        if not self._api_key:
            raise RuntimeError("CALENDARIFIC_API_KEY is not configured")

        params = {"api_key": self._api_key, "country": self._country, "year": year}
        response = self._http.get(self._base_url, params=params, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()

        holidays = (payload.get("response") or {}).get("holidays") or []
        dates: set[dt.date] = set()
        for holiday in holidays:
            if self._national_only and not _is_national_holiday(holiday):
                continue
            parsed = _parse_holiday_date(holiday)
            if parsed is not None:
                dates.add(parsed)
        return dates

    def _holiday_dates_for_year(self, year: int) -> set[dt.date] | None:
        """Return cached holiday dates for ``year`` or ``None`` if unavailable.

        ``None`` signals that the API could not be consulted (missing key or
        request failure); callers fall back to weekend-only logic. Failures are
        never cached, so a transient outage is retried on the next lookup.
        """
        with self._lock:
            cached = self._cache.get(year)
        if cached is not None:
            return cached

        try:
            dates = self._fetch_year(year)
        except Exception as exc:  # noqa: BLE001 - any failure degrades to fallback
            logger.warning("Calendarific holiday lookup failed for year %s: %s", year, exc)
            return None

        with self._lock:
            self._cache[year] = dates
        return dates

    def is_holiday(self, date: dt.date | dt.datetime) -> bool:
        """True if ``date`` is a Nepali public holiday.

        Returns ``False`` when the API is unavailable (fail-open), so the market
        is assumed open unless a holiday is positively confirmed.
        """
        day = _as_date(date)
        dates = self._holiday_dates_for_year(day.year)
        if dates is None:
            return False
        return day in dates

    def is_market_open(self, date: dt.date | dt.datetime) -> bool:
        """True if NEPSE is open on ``date`` (weekday and not a holiday)."""
        day = _as_date(date)
        if day.weekday() in self._closed_weekdays:
            return False
        return not self.is_holiday(day)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()


# Shared default instance for module-level convenience helpers.
_default_calendar = MarketCalendar()


def is_holiday(date: dt.date | dt.datetime) -> bool:
    """Module-level helper using the default :class:`MarketCalendar`."""
    return _default_calendar.is_holiday(date)


def is_market_open(date: dt.date | dt.datetime) -> bool:
    """Module-level helper using the default :class:`MarketCalendar`."""
    return _default_calendar.is_market_open(date)
