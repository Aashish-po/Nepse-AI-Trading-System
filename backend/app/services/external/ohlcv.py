"""Shared OHLCV normalisation + validation for external price providers.

Enforces the data-quality invariants from the integration plan so malformed
provider rows never reach the database:

* a parseable date that is not in the future (no look-ahead leakage),
* ``low <= open <= high`` and ``low <= close <= high``,
* non-negative volume (missing volume is allowed -> ``None``).

Returns rows sorted ascending by date. Rejected rows are logged and dropped.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_ohlcv_rows(
    provider: str,
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Validate + normalise a provider's contract rows into storable OHLCV rows."""
    valid: list[dict[str, Any]] = []
    for row in rows:
        obs_date = row.get("date")
        if not isinstance(obs_date, date):
            logger.warning("%s: dropping %s row with unparseable date", provider, symbol)
            continue
        if today is not None and obs_date > today:
            logger.warning("%s: dropping future-dated row %s for %s", provider, obs_date, symbol)
            continue

        o, h, low, c = (_num(row.get(k)) for k in ("open", "high", "low", "close"))
        if None in (o, h, low, c):
            logger.warning("%s: dropping %s %s row with missing OHLC", provider, symbol, obs_date)
            continue
        # mypy: the None check above guarantees these are floats.
        assert o is not None and h is not None and low is not None and c is not None
        if not (low <= o <= h and low <= c <= h):
            logger.warning(
                "%s: dropping %s %s row violating OHLC bounds", provider, symbol, obs_date
            )
            continue

        volume = _num(row.get("volume"))
        if volume is not None and volume < 0:
            logger.warning(
                "%s: dropping %s %s row with negative volume", provider, symbol, obs_date
            )
            continue

        valid.append(
            {
                "provider": provider,
                "external_symbol": symbol,
                "date": obs_date,
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": int(volume) if volume is not None else None,
                "currency": row.get("currency"),
                "raw": row.get("raw"),
            }
        )

    valid.sort(key=lambda r: r["date"])
    return valid
