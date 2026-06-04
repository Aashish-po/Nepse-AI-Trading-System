from fastapi import APIRouter

from backend.app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "version": settings.app_version,
        "scope": "research-only",
    }

