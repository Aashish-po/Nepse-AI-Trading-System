"""REST API routes for dashboard analytics and alerts (Phase 13)."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.alerts import AlertEngine
from app.services.analytics import AnalyticsService
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class MarketOverviewResponse(BaseModel):
    total_stocks: int
    active_stocks: int
    latest_date: str | None
    top_gainers: list[dict[str, Any]]
    top_losers: list[dict[str, Any]]


class SignalExplorerResponse(BaseModel):
    signals: list[dict[str, Any]]
    summary: dict[str, Any]


class PortfolioAnalyticsRequest(BaseModel):
    equity_curve: list[float]


class PortfolioAnalyticsResponse(BaseModel):
    total_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    n_periods: int


@router.get("/market-overview", response_model=MarketOverviewResponse)
def market_overview(
    session: DbSession,
    top_n: int = Query(default=5, ge=1, le=50),
) -> MarketOverviewResponse:
    service = AnalyticsService(session)
    return MarketOverviewResponse(**service.market_overview(top_n=top_n))


@router.get("/signals", response_model=SignalExplorerResponse)
def explore_signals(
    session: DbSession,
    symbol: str | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> SignalExplorerResponse:
    service = AnalyticsService(session)
    result = service.explore_signals(
        symbol=symbol,
        signal_type=signal_type,
        provider=provider,
        min_confidence=min_confidence,
        limit=limit,
    )
    return SignalExplorerResponse(**result)


@router.post("/portfolio", response_model=PortfolioAnalyticsResponse)
def portfolio_analytics(
    request: PortfolioAnalyticsRequest,
    session: DbSession,
) -> PortfolioAnalyticsResponse:
    service = AnalyticsService(session)
    return PortfolioAnalyticsResponse(**service.portfolio_analytics(request.equity_curve))


# ------------------------------------------------------------------------- alerts
alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertRulesRequest(BaseModel):
    """A list of declarative alert rules to evaluate."""

    rules: list[dict[str, Any]]


class AlertsResponse(BaseModel):
    count: int
    alerts: list[dict[str, Any]]


@alerts_router.post("/evaluate", response_model=AlertsResponse)
def evaluate_alerts(
    request: AlertRulesRequest,
    user: CurrentUser,
    session: DbSession,
) -> AlertsResponse:
    """Evaluate alert rules against current market/signal data."""
    engine = AlertEngine(session)
    alerts = engine.evaluate_rules(request.rules)
    return AlertsResponse(count=len(alerts), alerts=[a.to_dict() for a in alerts])
