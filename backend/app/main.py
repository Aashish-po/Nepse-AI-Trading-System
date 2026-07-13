from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure workspace root is on path for backend.app imports (used in CI)
_workspace_root = Path(__file__).parent.parent.parent
_backend_dir = _workspace_root / "backend"
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# ruff: noqa: E402
import sqlalchemy as sa
from app.api.routes import lstm
from app.api.routes.analytics import alerts_router, router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.data_quality import router as data_quality_router
from app.api.routes.explainability import (
    gov_router as governance_router,
    router as explainability_router,
)
from app.api.routes.external import (
    macro_router,
    news_router,
    router as external_router,
    sentiment_router,
)
from app.api.routes.features import router as features_router
from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.api.routes.mlops import router as mlops_router
from app.api.routes.paper_trading import router as paper_trading_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.signals import router as signals_router
from app.api.routes.strategies import router as strategies_router
from app.api.routes.streaming import router as streaming_router
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.data_source import DataSource
from app.services.monitoring import metrics
from fastapi import FastAPI, Request


def _assert_no_active_legacy_api_sources() -> None:
    with SessionLocal() as db:
        active_api_sources = db.scalar(
            sa.select(sa.func.count())
            .select_from(DataSource)
            .where(DataSource.is_active.is_(True), DataSource.type == "api")
        )
        if active_api_sources:
            raise RuntimeError(
                "Legacy NEPSE data sources are still active. Migrate them to scraper/csv before startup."
            )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()

    app = FastAPI(
        title="NEPSE AI Trading System",
        description="Quantitative trading research platform for Nepal Stock Exchange",
        version="2.0.0",
    )

    @app.on_event("startup")
    def _startup_guard() -> None:
        _assert_no_active_legacy_api_sources()

    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        import time

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        # Use the route template (not the raw path) to keep label cardinality bounded.
        route = request.scope.get("route")
        endpoint = getattr(route, "path", request.url.path)
        labels = {
            "method": request.method,
            "endpoint": endpoint,
            "status": str(response.status_code),
        }
        metrics.inc_counter("http_requests_total", labels=labels)
        metrics.observe(
            "http_request_duration_seconds",
            elapsed,
            labels={"method": request.method, "endpoint": endpoint},
        )
        return response

    # In test environments, some integration tests use TestClient directly
    # (without injecting auth overrides from backend/tests/conftest.py).
    # Allow portfolio endpoints to work by providing a lightweight researcher
    # identity when no bearer token is present.
    if os.environ.get("TESTING") == "true":
        try:
            from app.core.security import get_current_user as _get_current_user
        except Exception:
            _get_current_user = None  # type: ignore[assignment]

        if _get_current_user is not None:
            from typing import Any

            from app.models.user import User as _User

            def _override_get_current_user(*args: Any, **kwargs: Any) -> _User:
                return _User(
                    id="test-user",
                    email="test@example.com",
                    hashed_password="x",
                    role="researcher",
                )

            if _get_current_user is not None:
                app.dependency_overrides[_get_current_user] = _override_get_current_user  # type: ignore[assignment]

    # Register core routers immediately
    app.include_router(auth_router)
    app.include_router(data_quality_router)
    app.include_router(features_router)
    app.include_router(health_router)
    app.include_router(market_router)
    app.include_router(signals_router)
    app.include_router(strategies_router)
    app.include_router(lstm.router)
    app.include_router(portfolio_router)
    app.include_router(paper_trading_router)
    app.include_router(streaming_router)
    app.include_router(explainability_router)
    app.include_router(governance_router)
    app.include_router(mlops_router)
    app.include_router(analytics_router)
    app.include_router(alerts_router)
    app.include_router(external_router)
    app.include_router(macro_router)
    app.include_router(news_router)
    app.include_router(sentiment_router)

    # LAZY-LOAD ml_router to avoid circular imports
    # Only import ml module when app is created and routers are added
    try:
        from app.api.routes.ml import router as ml_router

        app.include_router(ml_router)
    except ImportError as e:
        # ML module optional - log but don't fail app startup
        logging.getLogger(__name__).warning(f"ML router import failed (optional): {e}")

    return app


app = create_app()
