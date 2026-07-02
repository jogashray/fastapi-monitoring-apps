"""HTTP metrics middleware.

Intercepts every request, records timing, sizes, status, and labels, and
updates the Prometheus HTTP metrics. Skips the metrics endpoint itself to
avoid recursive noise.
"""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.metrics import http_metrics

logger = logging.getLogger(__name__)


def _safe_endpoint_label(request: Request) -> str:
    """Return a stable endpoint label for the request.

    Uses the matched route template (`/data`, `/health`, etc.) so cardinality
    stays bounded. Falls back to the literal path if the request did not
    match any route (e.g. 404) and finally to "unknown" to prevent an
    attacker from creating a unique series per URL.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    raw = request.url.path
    if not raw:
        return "unknown"
    # Sanitize: any path that doesn't match simple alphanumeric/dash/underscore
    # segments is bucketed as "unknown" to cap cardinality.
    return raw if raw.replace("/", "").replace("-", "").replace("_", "").isalnum() else "unknown"


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Records Prometheus HTTP metrics for every request handled by FastAPI.

    The route template is captured AFTER `call_next` returns, because at
    dispatch time the router has not yet matched the request — so we
    inspect `request.scope["route"]` after the inner app has processed it.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path

        # Skip the metrics endpoint to avoid self-instrumentation
        if path == settings.metrics_endpoint:
            return await call_next(request)

        # Skip FastAPI's auto-generated docs/openapi pages — they would
        # otherwise inflate label cardinality and add noise to metrics.
        if path in ("/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        method = request.method
        start = time.perf_counter()

        # Read request body size (header or 0)
        request_size = 0
        cl = request.headers.get("content-length")
        if cl:
            try:
                request_size = int(cl)
            except ValueError:
                request_size = 0

        status_code = 500
        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            logger.exception("Request failed: %s %s", method, path)
            raise
        finally:
            # After the inner app runs, the router has populated scope["route"].
            endpoint_label = _safe_endpoint_label(request)
            duration = time.perf_counter() - start

            # Response size
            response_size = 0
            if response is not None:
                rcl = response.headers.get("content-length")
                if rcl:
                    try:
                        response_size = int(rcl)
                    except ValueError:
                        response_size = 0
                else:
                    body = getattr(response, "body", None)
                    if body is not None and hasattr(body, "__len__"):
                        response_size = len(body)

            try:
                http_metrics.in_progress_inc(method, endpoint_label)
                http_metrics.observe_request_size(method, endpoint_label, request_size)
                http_metrics.observe_response_size(method, endpoint_label, response_size)
                http_metrics.observe_duration(method, endpoint_label, status_code, duration)
                http_metrics.record_request(method, endpoint_label, status_code)
            finally:
                http_metrics.in_progress_dec(method, endpoint_label)