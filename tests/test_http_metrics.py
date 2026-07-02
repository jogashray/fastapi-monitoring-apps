"""Tests for HTTP-level Prometheus metrics."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_http_requests_total_increments(client):
    before = await client.get("/metrics")
    initial_count = _count_lines(before.text, "http_requests_total")
    assert initial_count is not None

    await client.get("/health")
    await client.get("/health")

    after = await client.get("/metrics")
    new_count = _count_lines(after.text, "http_requests_total")
    assert new_count is not None
    # Counter values should have increased
    assert new_count > initial_count


@pytest.mark.asyncio
async def test_http_request_duration_histogram_records(client):
    await client.get("/health")
    metrics = (await client.get("/metrics")).text
    assert "http_request_duration_seconds_bucket" in metrics
    assert "http_request_duration_seconds_count" in metrics
    assert "http_request_duration_seconds_sum" in metrics


@pytest.mark.asyncio
async def test_http_request_size_histogram_records(client):
    # POST with a body to record non-zero request size
    await client.post("/data", json={"payload": {"hello": "world"}})
    metrics = (await client.get("/metrics")).text
    assert "http_request_size_bytes" in metrics


@pytest.mark.asyncio
async def test_http_response_size_histogram_records(client):
    await client.get("/health")
    metrics = (await client.get("/metrics")).text
    assert "http_response_size_bytes" in metrics


@pytest.mark.asyncio
async def test_status_code_label_present(client):
    await client.get("/health")
    metrics = (await client.get("/metrics")).text
    # Look for any status_code label value in http_requests_total
    assert 'status_code="200"' in metrics


@pytest.mark.asyncio
async def test_endpoint_label_uses_route_template(client):
    await client.get("/health")
    await client.get("/data")
    metrics = (await client.get("/metrics")).text
    assert 'endpoint="/health"' in metrics
    assert 'endpoint="/data"' in metrics


@pytest.mark.asyncio
async def test_metrics_endpoint_not_recorded(client):
    """Scraping /metrics should not pollute http_requests_total."""
    before = await client.get("/metrics")
    await client.get("/metrics")
    await client.get("/metrics")
    after = await client.get("/metrics")

    # No new sample should appear for endpoint="/metrics"
    assert 'endpoint="/metrics"' not in after.text


@pytest.mark.asyncio
async def test_method_label_records_get_and_post(client):
    await client.get("/health")
    await client.post("/data", json={"payload": {"x": 1}})
    metrics = (await client.get("/metrics")).text
    assert 'method="GET"' in metrics
    assert 'method="POST"' in metrics


def _count_lines(text: str, prefix: str) -> int | None:
    """Sum the numeric values of all metric samples with the given prefix."""
    total = 0.0
    found = False
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line.startswith(prefix + "{") or line.startswith(prefix + " "):
            found = True
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                try:
                    total += float(parts[1])
                except ValueError:
                    pass
    return int(total) if found else None
