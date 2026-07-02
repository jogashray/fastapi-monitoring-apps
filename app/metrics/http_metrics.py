"""HTTP application-level Prometheus metrics.

These metrics are exposed on a dedicated `http_registry` separate from the
system registry. The middleware (`app.middleware.metrics_middleware`) calls
the helper functions below for every request.
"""

from __future__ import annotations

from typing import Iterable, List

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.config import settings


# ---------------------------------------------------------------------------
# Dedicated registry for HTTP metrics
# ---------------------------------------------------------------------------
http_registry = CollectorRegistry(auto_describe=True)


# ---------------------------------------------------------------------------
# Request volume: counter labelled by method, endpoint, status_code
# ---------------------------------------------------------------------------
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests processed, labelled by method, endpoint, and status code.",
    labelnames=("method", "endpoint", "status_code"),
    registry=http_registry,
)


# ---------------------------------------------------------------------------
# Request performance: histogram of durations
# ---------------------------------------------------------------------------
_http_duration_buckets: List[float] = settings.http_histogram_buckets_list
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, labelled by method, endpoint, status code.",
    labelnames=("method", "endpoint", "status_code"),
    buckets=_http_duration_buckets,
    registry=http_registry,
)


# ---------------------------------------------------------------------------
# Request and response size histograms
# ---------------------------------------------------------------------------
_request_size_buckets: List[float] = settings.request_size_buckets_list
http_request_size_bytes = Histogram(
    "http_request_size_bytes",
    "HTTP request body size in bytes, labelled by method and endpoint.",
    labelnames=("method", "endpoint"),
    buckets=_request_size_buckets,
    registry=http_registry,
)

_response_size_buckets: List[float] = settings.response_size_buckets_list
http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response body size in bytes, labelled by method and endpoint.",
    labelnames=("method", "endpoint"),
    buckets=_response_size_buckets,
    registry=http_registry,
)


# ---------------------------------------------------------------------------
# In-flight requests gauge
# ---------------------------------------------------------------------------
http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed, labelled by method and endpoint.",
    labelnames=("method", "endpoint"),
    registry=http_registry,
)


# ---------------------------------------------------------------------------
# Helper API used by the middleware
# ---------------------------------------------------------------------------
def record_request(method: str, endpoint: str, status_code: int | str) -> None:
    """Increment the request counter for the given label set."""
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).inc()


def observe_duration(method: str, endpoint: str, status_code: int | str, duration: float) -> None:
    """Record a request-duration observation."""
    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).observe(duration)


def observe_request_size(method: str, endpoint: str, size: int | float) -> None:
    """Record a request-size observation."""
    http_request_size_bytes.labels(method=method, endpoint=endpoint).observe(max(0, int(size)))


def observe_response_size(method: str, endpoint: str, size: int | float) -> None:
    """Record a response-size observation."""
    http_response_size_bytes.labels(method=method, endpoint=endpoint).observe(max(0, int(size)))


def in_progress_inc(method: str, endpoint: str) -> None:
    http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()


def in_progress_dec(method: str, endpoint: str) -> None:
    http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()


def iter_metrics() -> Iterable[bytes]:
    """Yield Prometheus exposition bytes for the HTTP registry."""
    from prometheus_client import generate_latest
    from prometheus_client.exposition import CONTENT_TYPE_LATEST

    return generate_latest(http_registry)