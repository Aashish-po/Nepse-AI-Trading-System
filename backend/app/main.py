from fastapi import FastAPI

from backend.app.api.routes.health import router as health_router
from backend.app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Research-only NEPSE AI trading decision-support platform.",
    )
    app.include_router(health_router)
    return app


app = create_app()

