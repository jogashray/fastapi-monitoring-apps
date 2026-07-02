"""Health-check and root endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app import __version__
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/", summary="Root endpoint")
async def root() -> dict:
    """Return basic application info."""
    return {
        "message": "FastAPI Metrics Monitoring System",
        "app": settings.app_name,
        "version": __version__,
    }


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Lightweight liveness check — process is alive and event loop responsive."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app": settings.app_name,
    }


@router.get("/health/ready", summary="Readiness probe")
async def health_ready(response: Response) -> dict:
    """Readiness check — collectors have run, metrics are populated."""
    from app.metrics.system_metrics import process_start_time_seconds

    ready = process_start_time_seconds._value.get() > 0
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "not_ready"}