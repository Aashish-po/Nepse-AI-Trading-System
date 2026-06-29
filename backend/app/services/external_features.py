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
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from app.core.config import Settings, settings as default_settings
from app.db.session import session_scope
from app.models.external_market import ExternalPrice
from app.models.macro import MacroObservation, MacroSeries
from app.services.external.base import ExternalApiClient
from app.services.external.finnhub import FinnhubClient
from app.services.external.marketstack import MarketstackClient
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

    def build_features(self, as_of: date) -> dict[str, Any]:
        """Return ``{values: {...}, meta: {...}}`` for macro features as of a date.

        Missing series resolve to ``None`` in ``values`` (explicitly missing,
        never fabricated). ``meta`` records the observation date used per feature
        for provenance/leakage auditing.
        """
        with session_scope(self._session) as session:
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


class NewsSentimentFeatureBuilder:
    """Per-stock trailing-window news-sentiment features, point-in-time safe.

    Delegates aggregation to ``external_sentiment.aggregate_symbol_sentiment`` so
    feature generation and the ``/news/sentiment/run`` endpoint share one
    confidence-gated definition. A feature for date ``T`` uses only articles
    published at or before ``T``.
    """

    def __init__(
        self,
        session: Session | None = None,
        *,
        window_days: int = 7,
    ) -> None:
        self._session = session
        self._window_days = window_days

    def build_features(self, symbol: str, as_of: date) -> dict[str, Any]:
        """Return ``{values: {...}, meta: {...}}`` for one stock's news features."""
        # Imported here to avoid a circular import at module load
        # (external_sentiment imports ml.sentiment, which is heavier).
        from app.services.external_sentiment import aggregate_symbol_sentiment

        with session_scope(self._session) as session:
            agg = aggregate_symbol_sentiment(session, symbol, as_of, window_days=self._window_days)
            return {
                "values": {
                    "news_sentiment_score_7d": agg["score"],
                    "news_sentiment_confidence_7d": agg["confidence"],
                    "news_article_count_7d": float(agg["count"]),
                },
                "meta": {
                    "news_provider": "newsapi",
                    "news_as_of": as_of.isoformat(),
                    "news_window_days": self._window_days,
                    "news_backend": agg["backend"],
                },
            }


class GlobalMarketFeatureBuilder:
    """Trailing benchmark-return features from external OHLCV, point-in-time safe.

    Returns ``global_equity_return_5d`` / ``_20d`` for a mapped benchmark symbol
    (e.g. an index ETF ingested via Marketstack/Finnhub). A return for date ``T``
    uses only closes dated at or before ``T``: the most recent close vs. the close
    ``N`` trading rows earlier. Missing data resolves to ``None`` (never fabricated).
    """

    def __init__(
        self,
        provider: str,
        benchmark_symbol: str,
        session: Session | None = None,
        cfg: Settings | None = None,
    ) -> None:
        self._provider = provider
        self._benchmark = benchmark_symbol.upper()
        self._session = session
        self._cfg = cfg or default_settings

    def build_features(self, as_of: date) -> dict[str, Any]:
        with session_scope(self._session) as session:
            # Closes at or before as_of, most recent first.
            closes = list(
                session.scalars(
                    sa.select(ExternalPrice.close)
                    .where(
                        ExternalPrice.provider == self._provider,
                        ExternalPrice.external_symbol == self._benchmark,
                        ExternalPrice.date <= as_of,
                        ExternalPrice.close.isnot(None),
                    )
                    .order_by(ExternalPrice.date.desc())
                ).all()
            )
            return {
                "values": {
                    "global_equity_return_5d": self._trailing_return(closes, 5),
                    "global_equity_return_20d": self._trailing_return(closes, 20),
                },
                "meta": {
                    "global_provider": self._provider,
                    "global_benchmark": self._benchmark,
                    "global_as_of": as_of.isoformat(),
                    "global_rows_available": len(closes),
                },
            }

    @staticmethod
    def _trailing_return(closes_desc: Sequence[float | None], lookback: int) -> float | None:
        """Return (latest / close `lookback` rows earlier) - 1, or None if short."""
        if len(closes_desc) <= lookback:
            return None
        latest = closes_desc[0]
        prior = closes_desc[lookback]
        if latest is None or prior is None or prior == 0:
            return None
        return round(latest / prior - 1.0, 6)

    def ingest_benchmark(self, symbol: str, today: date) -> dict[str, Any]:
        """Fetch + persist OHLCV rows for the benchmark symbol (for feature generation)."""
        client: ExternalApiClient
        if self._provider == "marketstack":
            client = MarketstackClient(cfg=self._cfg)
        elif self._provider == "finnhub":
            client = FinnhubClient(cfg=self._cfg)
        else:
            raise ValueError(f"Unsupported provider: {self._provider}")
        try:
            with session_scope(self._session) as session:
                try:
                    return self._ingest_one(session, client, symbol.upper(), today)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s ingest for %s failed: %s", self._provider, symbol, exc)
                    session.rollback()
                    return {"status": "failed", "error": str(exc), "fetched": 0, "inserted": 0}
        finally:
            client.close()

    def ingest_benchmark_from_client(
        self, client: ExternalApiClient, symbol: str, today: date
    ) -> dict[str, Any]:
        """Variant of ingest_benchmark that accepts an existing client (e.g. for testing)."""
        with session_scope(self._session) as session:
            try:
                return self._ingest_one(session, client, symbol.upper(), today)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s ingest for %s failed: %s", self._provider, symbol, exc)
                session.rollback()
                return {"status": "failed", "error": str(exc), "fetched": 0, "inserted": 0}

    def ingest_benchmark_from_client_and_session(
        self, client: ExternalApiClient, session: Session, symbol: str, today: date
    ) -> dict[str, Any]:
        """Variant of ingest_benchmark that accepts existing client and session (e.g. for testing)."""
        try:
            return self._ingest_one(session, client, symbol.upper(), today)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s ingest for %s failed: %s", self._provider, symbol, exc)
            session.rollback()
            return {"status": "failed", "error": str(exc), "fetched": 0, "inserted": 0}

    def _ingest_one(
        self, session: Session, client: ExternalApiClient, symbol: str, today: date
    ) -> dict[str, Any]:
        """Ingest OHLCV for one benchmark symbol into `external_prices`.

        This method exists to keep `GlobalMarketFeatureBuilder` self-contained
        while reusing the same DB upsert contract as `MarketIngestionService`.
        """
        # Import locally to avoid import cycles at module load time.
        from app.services.external_market import MarketIngestionService

        service = MarketIngestionService(
            self._provider,
            cfg=self._cfg,
            session=session,
            client=client,
        )
        return service._ingest_one(session, client, symbol, today)
