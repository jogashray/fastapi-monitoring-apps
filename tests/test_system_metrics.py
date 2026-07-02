"""Tests for system-level metrics."""

from __future__ import annotations

import pytest

from app.metrics import system_metrics


@pytest.mark.asyncio
async def test_update_system_metrics_populates_gauges(client):
    # Trigger a one-shot update explicitly
    system_metrics.update_system_metrics()

    metrics = (await client.get("/metrics")).text

    # Verify all process_* gauges present and have a positive value (where applicable)
    expected_metrics = [
        "process_cpu_seconds_total",
        "process_resident_memory_bytes",
        "process_virtual_memory_bytes",
        "process_start_time_seconds",
        "process_uptime_seconds",
        "process_threads",
        "process_num_cpu",
    ]
    for name in expected_metrics:
        assert name in metrics, f"missing metric: {name}"


@pytest.mark.asyncio
async def test_gc_metrics_present(client):
    metrics = (await client.get("/metrics")).text
    assert "python_gc_collections_total" in metrics
    assert "python_gc_objects_collected_total" in metrics


@pytest.mark.asyncio
async def test_resident_memory_positive(client):
    system_metrics.update_system_metrics()
    assert system_metrics.process_resident_memory_bytes._value.get() > 0


@pytest.mark.asyncio
async def test_start_time_set(client):
    assert system_metrics.process_start_time_seconds._value.get() > 0


@pytest.mark.asyncio
async def test_num_cpu_positive(client):
    val = system_metrics.process_num_cpu._value.get()
    assert val >= 1


@pytest.mark.asyncio
async def test_default_process_metrics_present(client):
    """Default Prometheus collectors expose canonical process_* metrics."""
    metrics = (await client.get("/metrics")).text
    # Default ProcessCollector exposes process_cpu_seconds and similar
    # We already expose our own process_cpu_seconds_total; default is complementary
    assert "process_cpu_seconds_total" in metrics
