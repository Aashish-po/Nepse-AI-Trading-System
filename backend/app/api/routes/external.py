"""External provider management & inspection endpoints.

Manual/on-demand sync (no scheduler) plus read-only inspection of ingested
macro data. All mutating routes require authentication. No secrets are exposed.
"""

from __future__ import annotations

import logging
from datetime import date

import sqlalchemy as sa
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.macro import MacroObservation, MacroSeries
from app.models.news import NewsArticle, SentimentRun
from app.models.user import User
from app.services.external.providers import provider_status
from app.services.external_macro import MacroIngestionService
from app.services.external_news import NewsIngestionService
from app.services.external_sentiment import SentimentRunService
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/external", tags=["external"])
macro_router = APIRouter(prefix="/macro", tags=["macro"])
news_router = APIRouter(prefix="/news", tags=["news"])
sentiment_router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("/health")
def external_health() -> dict[str, object]:
    """Provider availability summary (no network call, no secrets)."""
    providers = provider_status()
    return {
        "providers": providers,
        "usable_count": sum(1 for p in providers if p["usable"]),
    }


@router.get("/providers")
def list_providers() -> list[dict[str, object]]:
    return provider_status()


@router.post("/sync/{provider}")
def sync_provider(
    provider: str,
    query_by_symbol: dict[str, str] | None = Body(
        default=None,
        description="newsapi only: map of symbol -> search query, e.g. {'NABIL': 'Nabil Bank'}",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Trigger an on-demand ingestion for a provider.

    Returns a summary; a disabled provider returns ``status="skipped"`` rather
    than erroring, so callers can probe safely.
    """
    key = provider.lower()
    if key == "fred":
        result = MacroIngestionService(session=db).run()
        logger.info("user %s triggered fred sync: %s", user.id, result.get("status"))
        return result
    if key == "newsapi":
        if not query_by_symbol:
            raise HTTPException(
                status_code=422,
                detail="newsapi sync requires a JSON body mapping symbol -> search query",
            )
        result = NewsIngestionService(session=db).run(query_by_symbol)
        logger.info("user %s triggered newsapi sync: %s", user.id, result.get("status"))
        return result
    raise HTTPException(
        status_code=404, detail=f"Unknown or not-yet-supported provider: {provider}"
    )


@macro_router.get("/series")
def list_macro_series(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(sa.select(MacroSeries).order_by(MacroSeries.series_id)).all()
    return [
        {
            "id": s.id,
            "provider": s.provider,
            "series_id": s.series_id,
            "name": s.name,
            "units": s.units,
            "frequency": s.frequency,
            "is_active": s.is_active,
        }
        for s in rows
    ]


@macro_router.get("/observations")
def list_macro_observations(
    series_id: str = Query(..., description="Provider series id, e.g. DGS10"),
    provider: str = Query("fred"),
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(500, le=5000),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    series = db.scalar(
        sa.select(MacroSeries).where(
            MacroSeries.provider == provider, MacroSeries.series_id == series_id
        )
    )
    if series is None:
        raise HTTPException(status_code=404, detail=f"Unknown series: {provider}/{series_id}")
    stmt = sa.select(MacroObservation).where(MacroObservation.macro_series_id == series.id)
    if start is not None:
        stmt = stmt.where(MacroObservation.date >= start)
    if end is not None:
        stmt = stmt.where(MacroObservation.date <= end)
    stmt = stmt.order_by(MacroObservation.date.desc()).limit(limit)
    return [{"date": o.date.isoformat(), "value": o.value} for o in db.scalars(stmt).all()]


@news_router.get("/articles")
def list_news_articles(
    symbol: str | None = Query(None, description="Filter to articles mentioning this symbol"),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    stmt = sa.select(NewsArticle)
    if symbol is not None:
        from app.models.news import NewsMention

        stmt = stmt.join(NewsMention, NewsMention.article_id == NewsArticle.id).where(
            NewsMention.symbol == symbol.upper()
        )
    stmt = stmt.order_by(NewsArticle.published_date.desc().nullslast()).limit(limit)
    return [
        {
            "id": a.id,
            "provider": a.provider,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "published_date": a.published_date.isoformat() if a.published_date else None,
        }
        for a in db.scalars(stmt).all()
    ]


@news_router.post("/sentiment/run")
def run_news_sentiment(
    symbols: list[str] = Body(..., embed=True, description="Symbols to aggregate sentiment for"),
    as_of: date | None = Body(None, embed=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Aggregate trailing-window news sentiment per symbol and persist to sentiment_runs."""
    result = SentimentRunService(session=db).run(symbols, as_of=as_of)
    logger.info("user %s ran news sentiment for %d symbols", user.id, len(symbols))
    return result


@sentiment_router.get("/features")
def list_sentiment_features(
    symbol: str = Query(..., description="Stock symbol"),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Inspect persisted per-symbol/date sentiment runs (feature provenance)."""
    rows = db.scalars(
        sa.select(SentimentRun)
        .where(SentimentRun.symbol == symbol.upper())
        .order_by(SentimentRun.date.desc())
        .limit(limit)
    ).all()
    return [
        {
            "date": r.date.isoformat(),
            "score": r.score,
            "confidence": r.confidence,
            "count": r.count,
            "model": r.model,
        }
        for r in rows
    ]
