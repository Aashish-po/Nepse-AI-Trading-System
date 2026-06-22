"""News-sentiment aggregation and run persistence.

Aggregates stored articles (per symbol, over a trailing window) into a single
sentiment score using ``ml.sentiment.SentimentAnalyzer`` — the same analyzer the
signal-fusion engine consumes — and optionally persists the result to
``sentiment_runs`` for audit/inspection.

Point-in-time safety: aggregation for an as-of date ``T`` only considers articles
with ``published_date <= T`` within the trailing window. Articles with a NULL
published date are excluded (their availability date is unknown, so including
them could leak future information).

Defaults to the deterministic lexicon backend so ingestion stays offline and
reproducible; callers may inject any analyzer (e.g. HF-enriched in Phase 3).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from app.db.session import SessionLocal
from app.models.news import NewsArticle, NewsMention, SentimentRun
from sqlalchemy.orm import Session

from ml.sentiment import SentimentAnalyzer

logger = logging.getLogger(__name__)

PROVIDER = "newsapi"
DEFAULT_WINDOW_DAYS = 7

# Below this aggregate confidence the day's news is treated as non-informative:
# the score collapses to neutral (0.5) so weak signals never tilt fusion.
DEFAULT_MIN_CONFIDENCE = 0.15

NEUTRAL_SCORE = 0.5


def aggregate_symbol_sentiment(
    session: Session,
    symbol: str,
    as_of: date,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    analyzer: SentimentAnalyzer | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> dict[str, Any]:
    """Aggregate trailing-window news sentiment for one symbol as of a date.

    Returns ``{score, confidence, count, backend}``. With no qualifying articles
    the result is neutral with zero confidence/count. Below ``min_confidence`` the
    score is forced to neutral (confidence preserved for transparency).
    """
    analyzer = analyzer or SentimentAnalyzer(backend="lexicon")
    window_start = as_of - timedelta(days=window_days)

    titles = session.scalars(
        sa.select(NewsArticle.title)
        .join(NewsMention, NewsMention.article_id == NewsArticle.id)
        .where(
            NewsMention.symbol == symbol.upper(),
            NewsArticle.published_date.isnot(None),
            NewsArticle.published_date <= as_of,
            NewsArticle.published_date > window_start,
            NewsArticle.title.isnot(None),
        )
    ).all()

    texts = [t for t in titles if t]
    if not texts:
        return {
            "score": NEUTRAL_SCORE,
            "confidence": 0.0,
            "count": 0,
            "backend": analyzer._active_backend().backend_name,
        }

    agg = analyzer.aggregate(texts)
    confidence = float(agg["confidence"])
    score = float(agg["score"]) if confidence >= min_confidence else NEUTRAL_SCORE
    return {
        "score": score,
        "confidence": confidence,
        "count": int(agg["count"]),
        "backend": agg["backend"],
    }


class SentimentRunService:
    """Compute and persist per-symbol/date sentiment aggregates."""

    def __init__(
        self,
        *,
        session: Session | None = None,
        analyzer: SentimentAnalyzer | None = None,
        window_days: int = DEFAULT_WINDOW_DAYS,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        self._session = session
        self._analyzer = analyzer
        self._window_days = window_days
        self._min_confidence = min_confidence

    def _get_session(self) -> Session:
        return self._session if self._session is not None else SessionLocal()

    def run(
        self,
        symbols: list[str],
        *,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """Aggregate + persist sentiment for each symbol as of ``as_of`` (today UTC default)."""
        as_of = as_of or datetime.now(UTC).date()
        session = self._get_session()
        owns_session = self._session is None
        analyzer = self._analyzer or SentimentAnalyzer(backend="lexicon")
        results: dict[str, Any] = {}
        try:
            for symbol in symbols:
                agg = aggregate_symbol_sentiment(
                    session,
                    symbol,
                    as_of,
                    window_days=self._window_days,
                    analyzer=analyzer,
                    min_confidence=self._min_confidence,
                )
                self._upsert_run(session, symbol.upper(), as_of, agg)
                results[symbol] = agg
            session.commit()
            return {"status": "success", "as_of": as_of.isoformat(), "symbols": results}
        except Exception as exc:  # noqa: BLE001 — never propagate into callers
            session.rollback()
            logger.exception("sentiment run failed")
            return {"status": "failed", "error": str(exc), "symbols": results}
        finally:
            if owns_session:
                session.close()

    def _upsert_run(self, session: Session, symbol: str, as_of: date, agg: dict[str, Any]) -> None:
        existing = session.scalar(
            sa.select(SentimentRun).where(
                SentimentRun.provider == PROVIDER,
                SentimentRun.symbol == symbol,
                SentimentRun.date == as_of,
            )
        )
        if existing is None:
            session.add(
                SentimentRun(
                    provider=PROVIDER,
                    model=agg.get("backend"),
                    symbol=symbol,
                    date=as_of,
                    score=agg["score"],
                    confidence=agg["confidence"],
                    count=agg["count"],
                    features_json={"window_days": self._window_days},
                )
            )
        else:
            existing.model = agg.get("backend")
            existing.score = agg["score"]
            existing.confidence = agg["confidence"]
            existing.count = agg["count"]
