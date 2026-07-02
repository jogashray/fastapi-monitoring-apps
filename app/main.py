"""FastAPI application entry point.

Wires together routers, middleware, the background system-metrics collector,
and the Prometheus `/metrics` endpoint which exposes both the HTTP and
system metric registries plus the default process/platform/GC collectors.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    GCCollector,
    PlatformCollector,
    generate_latest,
)
from prometheus_client.exposition import REGISTRY as DEFAULT_REGISTRY

from app import __version__
from app.collectors.system_collector import lifespan_collector
from app.config import settings
from app.metrics.http_metrics import http_registry
from app.metrics.system_metrics import system_registry
from app.middleware.metrics_middleware import PrometheusMetricsMiddleware
from app.routers import api as api_router
from app.routers import health as health_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default metrics registry (process, platform, GC) — separate so it can be
# enabled/disabled from configuration without touching the HTTP metrics.
# ---------------------------------------------------------------------------
default_metrics_registry = CollectorRegistry(auto_describe=True)


def _register_default_collectors() -> None:
    """Register platform + GC default collectors.

    Note: We deliberately do NOT register ``ProcessCollector`` here because
    ``app.metrics.system_metrics`` already exposes the same ``process_*``
    metrics on its own registry. Registering both causes duplicate series
    in the Prometheus exposition.
    """
    if not settings.enable_default_metrics:
        return
    try:
        default_metrics_registry.register(PlatformCollector(registry=default_metrics_registry))
    except ValueError:
        pass  # Already registered
    try:
        default_metrics_registry.register(GCCollector(registry=default_metrics_registry))
    except ValueError:
        pass


def _is_already_registered() -> bool:
    """Some prometheus_client versions auto-register on default REGISTRY;
    our custom registries avoid that — this is a defensive check."""
    try:
        for _collector in list(DEFAULT_REGISTRY._collector_to_names.keys()):  # type: ignore[attr-defined]
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the background system-metrics collector on startup."""
    _register_default_collectors()
    async with lifespan_collector():
        logger.info(
            "Application %s v%s started",
            settings.app_name,
            __version__,
        )
        yield


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Production-ready FastAPI app with Prometheus metrics, Grafana dashboards, and Alertmanager routing.",
    lifespan=lifespan,
)

# Order matters: middleware is applied in reverse — the first added becomes
# the outermost. Metrics middleware must wrap everything to capture the
# final response status even when an exception bubbles up.
app.add_middleware(PrometheusMetricsMiddleware)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health_router.router)
app.include_router(api_router.router)


# ---------------------------------------------------------------------------
# /metrics endpoint — merges all registries into a single Prometheus exposition
# ---------------------------------------------------------------------------
@app.get(settings.metrics_endpoint, include_in_schema=False)
async def metrics() -> Response:
    """Expose Prometheus metrics in the standard text exposition format."""
    output = generate_latest(system_registry) + generate_latest(http_registry)
    if settings.enable_default_metrics:
        output += generate_latest(default_metrics_registry)
    return Response(content=output, media_type=CONTENT_TYPE_LATEST)