from __future__ import annotations

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
from app.api.routes.auth import router as auth_router
from app.api.routes.data_quality import router as data_quality_router
from app.api.routes.features import router as features_router
from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.api.routes.signals import router as signals_router
from app.api.routes.strategies import router as strategies_router
from app.core.logging import configure_logging
from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()

    app = FastAPI(
        title="NEPSE AI Trading System",
        description="Quantitative trading research platform for Nepal Stock Exchange",
        version="2.0.0",
    )

    # Register core routers immediately
    app.include_router(auth_router)
    app.include_router(data_quality_router)
    app.include_router(features_router)
    app.include_router(health_router)
    app.include_router(market_router)
    app.include_router(signals_router)
    app.include_router(strategies_router)

    # LAZY-LOAD ml_router to avoid circular imports
    # Only import ml module when app is created and routers are added
    try:
        from app.api.routes.ml import router as ml_router

        app.include_router(ml_router)
    except ImportError as e:
        # ML module optional - log but don't fail app startup
        from app.core.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(f"ML router import failed (optional): {e}")

    return app


app = create_app()
