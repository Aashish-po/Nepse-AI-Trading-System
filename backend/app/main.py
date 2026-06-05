from fastapi import FastAPI

from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.data_quality import router as data_quality_router
from backend.app.api.routes.features import router as features_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.market import router as market_router
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Research-only NEPSE AI trading decision-support platform.",
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(market_router)
    app.include_router(data_quality_router)
    app.include_router(features_router)
    return app


app = create_app()
