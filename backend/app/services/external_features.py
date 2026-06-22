"""Point-in-time-safe external feature builders.

Macro features are market-wide (not per-stock), so rather than writing rows to
the per-stock ``features`` table we expose a builder that returns a feature dict
for an as-of date. Callers merge this into each stock's feature vector.

Point-in-time safety rule: a feature for date ``T`` may only use observations
whose ``date <= T`` (i.e. data available at or before ``T``). The latest such
observation per series is used.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import sqlalchemy as sa
from app.db.session import SessionLocal
from app.models.macro import MacroObservation, MacroSeries
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

FRED_PROVIDER = "fred"

# Map feature name -> FRED series id.
FRED_FEATURE_SERIES: dict[str, str] = {
    "fred_dgs10": "DGS10",
    "fred_dgs2": "DGS2",
    "fred_dff": "DFF",
    "fred_cpi": "CPIAUCSL",
    "fred_unrate": "UNRATE",
}


class MacroFeatureBuilder:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def _get_session(self) -> Session:
        return self._session if self._session is not None else SessionLocal()

    def build_features(self, as_of: date) -> dict[str, Any]:
        """Return ``{values: {...}, meta: {...}}`` for macro features as of a date.

        Missing series resolve to ``None`` in ``values`` (explicitly missing,
        never fabricated). ``meta`` records the observation date used per feature
        for provenance/leakage auditing.
        """
        session = self._get_session()
        owns_session = self._session is None
        try:
            values: dict[str, float | None] = {}
            provenance: dict[str, str | None] = {}
            for feature_name, series_id in FRED_FEATURE_SERIES.items():
                obs = self._latest_observation(session, series_id, as_of)
                if obs is None:
                    values[feature_name] = None
                    provenance[feature_name] = None
                else:
                    values[feature_name] = obs.value
                    provenance[feature_name] = obs.date.isoformat()
            return {
                "values": values,
                "meta": {
                    "macro_provider": FRED_PROVIDER,
                    "macro_as_of": as_of.isoformat(),
                    "macro_observation_dates": provenance,
                },
            }
        finally:
            if owns_session:
                session.close()

    def _latest_observation(
        self,
        session: Session,
        series_id: str,
        as_of: date,
    ) -> MacroObservation | None:
        return session.scalar(
            sa.select(MacroObservation)
            .join(MacroSeries, MacroObservation.macro_series_id == MacroSeries.id)
            .where(
                MacroSeries.provider == FRED_PROVIDER,
                MacroSeries.series_id == series_id,
                MacroObservation.date <= as_of,
                MacroObservation.value.isnot(None),
            )
            .order_by(MacroObservation.date.desc())
            .limit(1)
        )
