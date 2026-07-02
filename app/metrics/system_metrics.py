"""System-level Prometheus metrics: CPU, memory, file descriptors, GC, threads.

These metrics are exposed on a dedicated `system_registry`. The background
collector (`app.collectors.system_collector`) periodically updates the gauges,
while the GC collector is invoked every scrape via `collect()`.
"""

from __future__ import annotations

import gc
import logging
import os
import time
from typing import Iterable

import psutil
from prometheus_client import CollectorRegistry, Counter, Gauge
from prometheus_client.core import GaugeMetricFamily

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dedicated registry for system metrics
# ---------------------------------------------------------------------------
system_registry = CollectorRegistry(auto_describe=True)


# ---------------------------------------------------------------------------
# CPU metrics
# ---------------------------------------------------------------------------
process_cpu_seconds_total = Counter(
    "process_cpu_seconds_total",
    "Total CPU time consumed by the process (seconds).",
    registry=system_registry,
)
process_cpu_utilization_percent = Gauge(
    "process_cpu_utilization_percent",
    "Approximate CPU utilization of the process (0-100).",
    registry=system_registry,
)


# ---------------------------------------------------------------------------
# Memory metrics
# ---------------------------------------------------------------------------
process_resident_memory_bytes = Gauge(
    "process_resident_memory_bytes",
    "Resident memory currently used by the process (RSS, bytes).",
    registry=system_registry,
)
process_virtual_memory_bytes = Gauge(
    "process_virtual_memory_bytes",
    "Virtual memory currently allocated by the process (bytes).",
    registry=system_registry,
)
process_memory_utilization_percent = Gauge(
    "process_memory_utilization_percent",
    "Approximate share of total system memory used by the process (0-100).",
    registry=system_registry,
)


# ---------------------------------------------------------------------------
# Process metadata / runtime
# ---------------------------------------------------------------------------
process_start_time_seconds = Gauge(
    "process_start_time_seconds",
    "Unix timestamp (seconds) when the process started.",
    registry=system_registry,
)
process_uptime_seconds = Gauge(
    "process_uptime_seconds",
    "Number of seconds the process has been running.",
    registry=system_registry,
)


# ---------------------------------------------------------------------------
# File descriptor metrics
# ---------------------------------------------------------------------------
process_open_fds = Gauge(
    "process_open_fds",
    "Number of open file descriptors.",
    registry=system_registry,
)
process_max_fds = Gauge(
    "process_max_fds",
    "Maximum number of file descriptors allowed.",
    registry=system_registry,
)


# ---------------------------------------------------------------------------
# Threads / CPU count
# ---------------------------------------------------------------------------
process_threads = Gauge(
    "process_threads",
    "Number of threads currently active in the process.",
    registry=system_registry,
)
process_num_cpu = Gauge(
    "process_num_cpu",
    "Number of CPUs available on the host.",
    registry=system_registry,
)


# ---------------------------------------------------------------------------
# Garbage collection custom collector
# ---------------------------------------------------------------------------
class PythonGCCollector:
    """Exposes Python garbage-collection statistics as Prometheus metrics."""

    def collect(self) -> Iterable[GaugeMetricFamily]:
        # gc.get_stats() returns per-generation counters; fall back to empty
        # if the interpreter does not support it.
        try:
            stats = gc.get_stats()
        except Exception:
            stats = [{"collected": 0, "uncollectable": 0, "collections": 0} for _ in range(3)]

        collected = GaugeMetricFamily(
            "python_gc_objects_collected_total",
            "Number of Python objects collected by the garbage collector, per generation.",
            labels=["generation"],
        )
        collections = GaugeMetricFamily(
            "python_gc_collections_total",
            "Number of times the garbage collector has run, per generation.",
            labels=["generation"],
        )

        for gen, entry in enumerate(stats):
            collected.add_metric([str(gen)], float(entry.get("collected", 0)))
            collections.add_metric([str(gen)], float(entry.get("collections", 0)))

        return [collected, collections]


# Register the GC collector so its metrics appear in scrape output
system_registry.register(PythonGCCollector())


# ---------------------------------------------------------------------------
# Collector helper — invoked by the background async task
# ---------------------------------------------------------------------------
_process_handle: psutil.Process | None = None
_start_time: float = time.time()


def _get_process() -> psutil.Process:
    """Cache a psutil.Process handle for the current PID."""
    global _process_handle
    if _process_handle is None or not _process_handle.is_running():
        _process_handle = psutil.Process(os.getpid())
    return _process_handle


def update_system_metrics() -> None:
    """Snapshot current system metrics and update all gauges.

    Designed to be called periodically by the background collector. Catches
    and logs exceptions so a transient psutil error does not crash the loop.
    """
    try:
        proc = _get_process()

        # CPU
        try:
            cpu_times = proc.cpu_times()
            total_cpu = float(cpu_times.user + cpu_times.system)
            # Counter is monotonic — only increment when value goes up
            current = process_cpu_seconds_total._value.get()
            if total_cpu > current:
                process_cpu_seconds_total.inc(total_cpu - current)
        except (psutil.AccessDenied, AttributeError):
            pass

        try:
            process_cpu_utilization_percent.set(proc.cpu_percent(interval=None))
        except (psutil.AccessDenied, AttributeError):
            pass

        # Memory
        try:
            mem = proc.memory_info()
            process_resident_memory_bytes.set(float(mem.rss))
            process_virtual_memory_bytes.set(float(mem.vms))
        except (psutil.AccessDenied, AttributeError):
            pass

        try:
            total_mem = psutil.virtual_memory().total or 1
            process_memory_utilization_percent.set(
                100.0 * proc.memory_info().rss / total_mem
            )
        except (psutil.AccessDenied, AttributeError):
            pass

        # Start time / uptime
        try:
            start = proc.create_time()
            process_start_time_seconds.set(float(start))
            process_uptime_seconds.set(max(0.0, time.time() - _start_time))
        except (psutil.AccessDenied, AttributeError):
            pass

        # File descriptors
        try:
            process_open_fds.set(float(proc.num_fds()))
        except (psutil.AccessDenied, AttributeError, NotImplementedError):
            process_open_fds.set(0.0)

        try:
            import resource

            soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            process_max_fds.set(float(soft))
        except (ImportError, ValueError, OSError):
            process_max_fds.set(0.0)

        # Threads
        try:
            process_threads.set(float(proc.num_threads()))
        except (psutil.AccessDenied, AttributeError):
            pass

        # CPU count (relatively static — set on first call)
        try:
            if process_num_cpu._value.get() == 0:
                process_num_cpu.set(float(psutil.cpu_count() or os.cpu_count() or 1))
        except Exception:  # noqa: BLE001
            process_num_cpu.set(1.0)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to update system metrics: %s", exc)


# Initial population so /metrics has data before the first interval tick
update_system_metrics()