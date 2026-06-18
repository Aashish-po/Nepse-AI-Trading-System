from __future__ import annotations

import logging

from app.core.config import settings
from app.db.session import engine
from app.services.monitoring import metrics
from fastapi import APIRouter, Response
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "version": settings.app_version,
        "scope": "research-only",
    }


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Liveness probe: process is up and serving. No external dependencies."""
    return {"status": "alive"}


@router.get("/health/ready")
def readiness(response: Response) -> dict[str, object]:
    """Readiness probe: verify the database is reachable before taking traffic."""
    checks: dict[str, str] = {}
    ready = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised when DB is down
        logger.warning("Readiness DB check failed: %s", exc)
        checks["database"] = "unavailable"
        ready = False

    if not ready:
        response.status_code = 503
    return {"status": "ready" if ready else "not_ready", "checks": checks}


@router.get("/metrics")
def prometheus_metrics() -> Response:
    """Expose collected metrics in Prometheus text exposition format."""
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")
