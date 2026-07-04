# FastAPI Metrics Monitoring System

[![GitHub](https://img.shields.io/badge/GitHub-jogashray%2Ffastapi--monitoring--apps-blue?logo=github)](https://github.com/jogashray/fastapi-monitoring-apps.git)

A production-ready FastAPI application that exposes **system-level** and **HTTP-level** Prometheus metrics, bundled with a complete observability stack — **Prometheus**, **Grafana**, and **Alertmanager** — wired together via Docker Compose. The application tracks CPU/memory/FD/GC/thread state, request volumes with method/endpoint/status labels, latency histograms, request and response sizes, and in-flight request counts, then surfaces everything through auto-provisioned Grafana dashboards and severity-routed alerts.

**Repository:** [https://github.com/jogashray/fastapi-monitoring-apps.git](https://github.com/jogashray/fastapi-monitoring-apps.git)

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Setup & Installation](#setup--installation)
6. [Configuration](#configuration)
7. [Available APIs and URLs](#available-apis-and-urls)
8. [Using the API](#using-the-api)
9. [Metrics Reference](#metrics-reference)
10. [Sample PromQL Queries](#sample-promql-queries)
11. [Grafana Dashboards](#grafana-dashboards)
12. [Alerting](#alerting)
13. [Running Tests](#running-tests)
14. [Limitations](#limitations)
15. [Troubleshooting](#troubleshooting)
16. [References](#references)

---

## Overview

This project implements comprehensive metrics monitoring for a FastAPI application:

- **System metrics**: CPU, memory, file descriptors, threads, GC, uptime
- **HTTP metrics**: request volume, latency percentiles, request/response sizes, in-flight requests
- **Prometheus**: scrape collection with alert rules for system & HTTP anomalies
- **Grafana**: auto-provisioned dashboards (FastAPI Overview + System Health)
- **Alertmanager**: severity-based routing with critical/warning/info receivers

### Architecture

```
        ┌──────────────────┐
        │  FastAPI App(s)  │  ← exposes /metrics
        └────────┬─────────┘
                 │ scraped every 5s
        ┌────────▼─────────┐
        │    Prometheus    │  ← stores TSDB, evaluates alerts
        └────────┬─────────┘
                 │
        ┌────────┴─────────┐
        │                  │
┌───────▼────────┐  ┌──────▼──────────┐
│   Grafana      │  │  Alertmanager   │
│  (dashboards)  │  │  (dedup/route)  │
└────────────────┘  └──────┬──────────┘
                           │ webhooks/slack
                     ┌─────▼──────┐
                     │ On-call    │
                     └────────────┘
```

---

## Features

- **System metrics** — CPU seconds (counter), CPU %, RSS, virtual memory, memory %, start time, uptime, open FDs, max FDs, thread count, CPU count, plus per-generation garbage-collection counts.
- **HTTP metrics** — `http_requests_total` counter labelled by `method`, `endpoint`, `status_code`; latency histogram (`http_request_duration_seconds`); request and response size histograms; in-flight request gauge.
- **FastAPI app** with five endpoints: `GET /`, `GET /health`, `GET /health/ready`, `POST /data`, `GET /data`, `GET /data/count`, plus `GET /metrics` for Prometheus exposition.
- **Custom middleware** (`PrometheusMetricsMiddleware`) that times requests, captures status, and uses route templates to keep label cardinality bounded.
- **Background async collector** that updates system gauges every `SYSTEM_METRICS_INTERVAL` seconds.
- **Docker Compose stack** with 4 services — FastAPI, Prometheus, Grafana, Alertmanager — sharing a `monitoring` network.
- **Prometheus alert rules** for high CPU, high memory, instance down, FD exhaustion, error rate, slow requests, traffic spikes.
- **Alertmanager** with severity-based routing (`critical`, `warning`, `info`), inhibition rules, and webhook receivers.
- **Grafana dashboards** auto-provisioned on startup: `FastAPI Overview` (22 panels) and `FastAPI System Health` (9 panels), with template variables for `endpoint`, `method`, `status_code`.
- **Smoke test script** (`scripts/smoke_test.sh`) for end-to-end verification.
- **Pytest suite** of 24 tests covering endpoints, HTTP metrics, and system metrics.

---

## Technology Stack

### Core (Application)

| Component | Version | Role |
|-----------|---------|------|
| Python | 3.8+ (tested on 3.10, 3.11) | Runtime |
| FastAPI | 0.115.6 | Async web framework |
| Uvicorn (standard) | 0.32.1 | ASGI server |
| Pydantic | 2.10.3 | Request/response validation |
| pydantic-settings | 2.7.0 | Environment-driven configuration |
| prometheus-client | 0.21.1 | Metric definitions + exposition format |
| psutil | 6.1.1 | Process-level CPU/memory/FD/thread stats |
| python-dotenv | 1.0.1 | `.env` file loading |

### Testing

| Component | Version | Role |
|-----------|---------|------|
| pytest | 8.3.4 | Test runner |
| pytest-asyncio | 0.25.0 | Async test support |
| httpx | 0.28.1 | ASGI in-process test transport |

### Monitoring Stack (Docker images)

| Service | Image | Version | Default Port |
|---------|-------|---------|--------------|
| Prometheus | `prom/prometheus` | v2.55.1 | 9090 |
| Alertmanager | `prom/alertmanager` | v0.27.0 | 9093 |
| Grafana | `grafana/grafana` | 11.3.0 | 3000 |
| FastAPI | Built from local `Dockerfile` (python:3.11-slim) | — | 8000 |

---

## Project Structure

```
fastapi-metrics-app/
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI entry point + lifespan + /metrics handler
│   ├── config.py                     # pydantic-settings configuration
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── system_metrics.py         # CPU/memory/FD/GC/thread gauges + custom GC collector
│   │   └── http_metrics.py           # http_requests_total, histograms, in-progress gauge
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── metrics_middleware.py     # Records metrics per request, captures route templates
│   ├── collectors/
│   │   ├── __init__.py
│   │   └── system_collector.py       # Async background task updating system metrics
│   └── routers/
│       ├── __init__.py
│       ├── health.py                 # /, /health, /health/ready
│       └── api.py                    # POST/GET /data, GET /data/count
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # Shared pytest fixtures (ASGI client)
│   ├── test_endpoints.py             # 10 tests — endpoint behavior
│   ├── test_http_metrics.py          # 8 tests  — HTTP metric collection
│   └── test_system_metrics.py        # 6 tests  — System metric values
│
├── prometheus/
│   ├── prometheus.yml                # Scrape + rule_files config
│   └── alerts/
│       ├── system_alerts.yml         # HighCPU, HighMemory, InstanceDown, FDs
│       └── http_alerts.yml           # HighErrorRate, SlowRequests, TrafficSpike
│
├── alertmanager/
│   ├── alertmanager.yml              # Severity-based routing + inhibition
│   └── templates/
│       └── default.tmpl              # Slack/email message templates
│
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/prometheus.yml    # Auto-provision Prometheus DS
│   │   └── dashboards/dashboard.yml      # Auto-load dashboards from disk
│   └── dashboards/
│       ├── fastapi-overview.json     # 22 panels — main dashboard
│       └── system-health.json        # 9 panels  — system-only dashboard
│
├── scripts/
│   └── smoke_test.sh                 # End-to-end stack check
│
├── docker-compose.yml                # 4-service stack on `monitoring` network
├── Dockerfile                        # python:3.11-slim, uvicorn entrypoint
├── Makefile                          # install / run / test / up / down / smoke
├── pytest.ini                        # asyncio_mode=auto
├── requirements.txt                  # Pinned dependencies
├── .env.example                      # Sample configuration
├── README.md                         # This file — comprehensive documentation
├── plan.md                           # Project plan (system design)
└── test_cases.md                     # Detailed test case specifications
```

---

## Setup & Installation

### Prerequisites

- **Python 3.8+** (recommended 3.10 or 3.11)
- **pip** (bundled with Python)
- **Docker** + **Docker Compose** (for the full stack)
- **curl** (for smoke tests)
- ~2 GB free disk space for Docker images

### Option 1: Local Python Installation

**Best for:** actively modifying the app, running tests, fast iteration without Docker overhead.

```bash
# 1. Clone the repository
git clone https://github.com/jogashray/fastapi-monitoring-apps.git
cd fastapi-monitoring-apps

# 2. (Recommended) Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Copy the example env file — defaults work out of the box
cp .env.example .env

# 5. Start the app
make run
# or: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The app is now available at `http://localhost:8000`. To run the test suite:

```bash
make test
# or: pytest -v
```

### Option 2: Full Docker Compose Stack

**Best for:** trying the complete monitoring stack (FastAPI + Prometheus + Grafana + Alertmanager) with zero manual setup.

```bash
# 1. Clone the repository
git clone https://github.com/jogashray/fastapi-monitoring-apps.git
cd fastapi-monitoring-apps

# 2. Build images and start all 4 services
#    Use whichever `compose` command is available on your device:
docker compose up -d --build       # Modern Docker (post-2020, v2 plugin)
# OR
docker-compose up -d --build       # Older Docker Toolbox / v1 binary

# 3. Check service health
docker compose ps                   # OR: docker-compose ps
```

> If neither command is found, install [Docker Desktop](https://www.docker.com/products/docker-desktop/) or the `docker-compose-plugin` package.

After ~30 seconds, the following URLs are live:

| Service | URL | Credentials |
|---------|-----|-------------|
| FastAPI | http://localhost:8000 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Alertmanager | http://localhost:9093 | — |

> If any of these host ports is already in use on your device (for example, a
> system-installed Grafana on `:3000`), set the matching variable in `.env`
> (e.g. `GRAFANA_PORT=3001`) **before** running `docker compose up`. See
> [Configuration](#configuration) for the full list of overridable ports.

The Grafana dashboards (`FastAPI Overview`, `FastAPI System Health`) and Prometheus datasource are auto-provisioned on startup.

To verify the stack is functioning end-to-end:

```bash
make smoke        # or: bash scripts/smoke_test.sh
```

To stop and clean up:

```bash
docker compose down               # OR: docker-compose down       — stop, keep volumes
docker compose down -v            # OR: docker-compose down -v    — stop, remove volumes
```

---

## Configuration

All settings are read from environment variables (or a `.env` file at startup) by `pydantic-settings`. See `app/config.py` and `.env.example`.

| Variable | Default | Used In | Description |
|----------|---------|---------|-------------|
| `APP_NAME` | `fastapi-metrics-app` | `app/config.py` | Application display name returned by `/` |
| `METRICS_ENDPOINT` | `/metrics` | `app/main.py`, `app/middleware/metrics_middleware.py` | Path that exposes Prometheus exposition |
| `SYSTEM_METRICS_INTERVAL` | `5.0` (seconds) | `app/collectors/system_collector.py` | How often the background task updates system gauges |
| `ENABLE_DEFAULT_METRICS` | `true` | `app/main.py` | If true, register `ProcessCollector`, `PlatformCollector`, `GCCollector` |
| `HTTP_HISTOGRAM_BUCKETS` | `0.005,0.01,0.025,0.05,0.1,0.25,0.5,1.0,2.5,5.0,10.0` | `app/metrics/http_metrics.py` | Latency histogram buckets (seconds) |
| `REQUEST_SIZE_BUCKETS` | `100,1024,10240,102400,1048576,10485760` | `app/metrics/http_metrics.py` | Request size histogram buckets (bytes) |
| `RESPONSE_SIZE_BUCKETS` | `100,1024,10240,102400,1048576,10485760` | `app/metrics/http_metrics.py` | Response size histogram buckets (bytes) |
| `MAX_DATA_ITEMS` | `1000` | `app/routers/api.py` | Capacity of the in-memory `/data` store (deque `maxlen`) |

### Custom bucket examples

```bash
# Stricter latency buckets (sub-100ms granularity)
export HTTP_HISTOGRAM_BUCKETS=0.001,0.005,0.01,0.025,0.05,0.1,0.25

# Disable default collectors (only custom metrics)
export ENABLE_DEFAULT_METRICS=false

# Slower system collector (10s) to reduce CPU on idle systems
export SYSTEM_METRICS_INTERVAL=10
```

### Docker Compose port overrides

The host-side port bindings for the full stack are overridable. Set any of these in `.env` before running `docker compose up` if a default port is already in use on your device:

| Variable | Default | Service |
|----------|---------|---------|
| `FASTAPI_PORT` | `8000` | FastAPI app |
| `PROMETHEUS_PORT` | `9090` | Prometheus |
| `ALERTMANAGER_PORT` | `9093` | Alertmanager |
| `GRAFANA_PORT` | `3000` | Grafana |

Example: if port 3000 is already in use (common when Grafana is installed system-wide), set `GRAFANA_PORT=3001` in `.env` and re-run `docker compose up -d`. Container-side ports stay fixed.

---

## Available APIs and URLs

### 1. FastAPI Application (port 8000)

The application's HTTP API. All endpoints return JSON unless noted.

| Method | URL | Purpose | Auth | Sample |
|--------|-----|---------|------|--------|
| GET | `/` | Application banner | None | `curl http://localhost:8000/` |
| GET | `/health` | Liveness probe | None | `curl http://localhost:8000/health` |
| GET | `/health/ready` | Readiness probe (503 until first metric snapshot) | None | `curl http://localhost:8000/health/ready` |
| POST | `/data` | Submit a JSON payload, returns an item ID | None | `curl -X POST http://localhost:8000/data -H 'Content-Type: application/json' -d '{"payload":{}}'` |
| GET | `/data` | List stored items; supports `?limit=` and `?offset=` | None | `curl http://localhost:8000/data?limit=10` |
| GET | `/data/count` | Current size and capacity of the in-memory store | None | `curl http://localhost:8000/data/count` |
| GET | `/metrics` | Prometheus exposition (text format) | None | `curl http://localhost:8000/metrics` |
| GET | `/docs` | Auto-generated OpenAPI / Swagger UI | None | Open in browser |
| GET | `/redoc` | Alternative API documentation | None | Open in browser |

### 2. Prometheus (port 9090)

| URL | Purpose |
|-----|---------|
| `http://localhost:9090/` | Query UI |
| `http://localhost:9090/targets` | Scrape target health (look for `app:8000`) |
| `http://localhost:9090/rules` | Loaded alert rules |
| `http://localhost:9090/alerts` | Currently firing / pending alerts |
| `http://localhost:9090/graph` | PromQL query editor with autocomplete |
| `http://localhost:9090/metrics` | Prometheus's own self-metrics |

### 3. Grafana (port 3000)

| URL | Credentials | Purpose |
|-----|-------------|---------|
| `http://localhost:3000/login` | admin / admin | Login page |
| `http://localhost:3000/dashboards` | admin | Dashboard list (auto-loaded: FastAPI Overview, FastAPI System Health) |
| `http://localhost:3000/explore` | admin | Ad-hoc query explorer |
| `http://localhost:3000/alerting/grafana` | admin | Grafana-side alert rules |
| `http://localhost:3000/datasources` | admin | Datasources (Prometheus auto-provisioned) |

### 4. Alertmanager (port 9093)

| URL | Purpose |
|-----|---------|
| `http://localhost:9093/` | Alert overview (silences, active alerts) |
| `http://localhost:9093/#/alerts` | Active alert list |
| `http://localhost:9093/#/silences` | Silence management |
| `http://localhost:9093/api/v1/alerts` | JSON API for active alerts |

---

## Using the API

All examples assume the app is at `http://localhost:8000`.

### `GET /` — Root banner

```bash
curl http://localhost:8000/
```

```json
{
  "message": "FastAPI Metrics Monitoring System",
  "app": "fastapi-metrics-app",
  "version": "1.0.0"
}
```

### `GET /health` — Liveness probe

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "timestamp": "2026-07-02T18:00:00.000000+00:00",
  "app": "fastapi-metrics-app"
}
```

Use this for Kubernetes liveness probes — it returns 200 as long as the process is alive and the event loop is responsive.

### `GET /health/ready` — Readiness probe

```bash
curl -i http://localhost:8000/health/ready
```

```
HTTP/1.1 200 OK
content-type: application/json
{"status":"ready"}
```

Returns `503 {"status":"not_ready"}` if the system collector has not run at least once. Use this for Kubernetes readiness probes.

### `POST /data` — Submit a payload

```bash
curl -X POST http://localhost:8000/data \
  -H "Content-Type: application/json" \
  -d '{"payload": {"name": "alice", "age": 30}, "note": "first user"}'
```

```json
{
  "id": "11111111-2222-3333-4444-555555555555",
  "received": {
    "payload": {"name": "alice", "age": 30},
    "note": "first user"
  },
  "size": 65,
  "created_at": "2026-07-02T18:00:00.000000+00:00"
}
```

**Validation rules:**
- Body must be valid JSON
- `payload` defaults to `{}` if omitted
- `note` must be a string if provided (or `null`)

Sending an invalid field type returns `422 Unprocessable Entity` with a JSON error body from FastAPI.

### `GET /data` — List items

```bash
# All items (up to default 100)
curl http://localhost:8000/data

# Paginated
curl "http://localhost:8000/data?limit=10&offset=20"
```

```json
[
  {
    "id": "11111111-...",
    "received": {"payload": {"k": "v"}, "note": null},
    "size": 22,
    "created_at": "2026-07-02T18:00:00.000000+00:00"
  }
]
```

Query parameters:
- `limit` (int, 1–1000, default 100) — max items to return
- `offset` (int, ≥0, default 0) — items to skip from the start

### `GET /data/count` — Store size

```bash
curl http://localhost:8000/data/count
```

```json
{"count": 42, "max": 1000}
```

### `GET /metrics` — Prometheus exposition

```bash
curl http://localhost:8000/metrics
```

The response is plain text in Prometheus exposition format with `Content-Type: text/plain; version=0.0.4; charset=utf-8`. Sample excerpt:

```
# HELP process_cpu_seconds_total Total CPU time consumed by the process (seconds).
# TYPE process_cpu_seconds_total counter
process_cpu_seconds_total 0.12

# HELP process_resident_memory_bytes Resident memory currently used by the process (RSS, bytes).
# TYPE process_resident_memory_bytes gauge
process_resident_memory_bytes 4.582e+07

# HELP http_requests_total Total HTTP requests processed, labelled by method, endpoint, and status code.
# TYPE http_requests_total counter
http_requests_total{endpoint="/health",method="GET",status_code="200"} 42.0
http_requests_total{endpoint="/data",method="POST",status_code="201"} 5.0

# HELP http_request_duration_seconds HTTP request duration in seconds, labelled by method, endpoint, status code.
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{endpoint="/health",method="GET",status_code="200",le="0.005"} 30.0
http_request_duration_seconds_bucket{endpoint="/health",method="GET",status_code="200",le="0.01"} 40.0
http_request_duration_seconds_bucket{endpoint="/health",method="GET",status_code="200",le="+Inf"} 42.0
http_request_duration_seconds_count{endpoint="/health",method="GET",status_code="200"} 42.0
http_request_duration_seconds_sum{endpoint="/health",method="GET",status_code="200"} 0.084
```

---

## Metrics Reference

### System Metrics

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `process_cpu_seconds_total` | Counter | — | Cumulative CPU time consumed by the process (seconds). Rate it with `rate(process_cpu_seconds_total[5m])`. |
| `process_cpu_utilization_percent` | Gauge | — | Approximate CPU utilization (0–100). |
| `process_resident_memory_bytes` | Gauge | — | Physical memory (RSS) currently used, in bytes. |
| `process_virtual_memory_bytes` | Gauge | — | Virtual memory allocated, in bytes. |
| `process_memory_utilization_percent` | Gauge | — | Process RSS as % of total system memory. |
| `process_start_time_seconds` | Gauge | — | Unix timestamp when the process started. |
| `process_uptime_seconds` | Gauge | — | Number of seconds the process has been running. |
| `process_open_fds` | Gauge | — | Number of open file descriptors. |
| `process_max_fds` | Gauge | — | Maximum file descriptors allowed. |
| `process_threads` | Gauge | — | Active thread count. |
| `process_num_cpu` | Gauge | — | Number of CPUs on the host. |
| `python_gc_collections_total` | Gauge | `generation` | Number of garbage-collection runs per generation. |
| `python_gc_objects_collected_total` | Gauge | `generation` | Objects collected per generation. |

### HTTP Metrics

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Total requests received, partitioned by method, route template, and status. |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint`, `status_code` | Request duration distribution. Use `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))` for p95. |
| `http_request_size_bytes` | Histogram | `method`, `endpoint` | Request body size distribution. |
| `http_response_size_bytes` | Histogram | `method`, `endpoint` | Response body size distribution. |
| `http_requests_in_progress` | Gauge | `method`, `endpoint` | Concurrent requests currently being processed. |

---

## Sample PromQL Queries

### CPU & Memory

```promql
# CPU rate (cores per second) over 5 minutes
rate(process_cpu_seconds_total[5m])

# CPU rate as percentage (one core = 100%)
rate(process_cpu_seconds_total[5m]) * 100

# Memory in megabytes
process_resident_memory_bytes / 1024 / 1024

# File-descriptor usage percentage
process_open_fds / process_max_fds * 100
```

### HTTP Traffic

```promql
# Total request rate
sum(rate(http_requests_total[5m]))

# Per-endpoint request rate
sum by (endpoint) (rate(http_requests_total[5m]))

# p95 latency by endpoint (the headline query)
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))

# p95 latency for a specific endpoint/method
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{endpoint="/data", method="GET"}[5m])) by (le))

# Error rate (5xx / total)
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
  /
sum(rate(http_requests_total[5m]))

# Average request duration
sum(rate(http_request_duration_seconds_sum[5m])) by (endpoint)
  /
sum(rate(http_request_duration_seconds_count[5m])) by (endpoint)
```

### Sizes

```promql
# p95 request body size by endpoint
histogram_quantile(0.95,
  sum(rate(http_request_size_bytes_bucket[5m])) by (le, endpoint))

# p95 response body size by endpoint
histogram_quantile(0.95,
  sum(rate(http_response_size_bytes_bucket[5m])) by (le, endpoint))
```

### Operational

```promql
# In-flight requests (currently being processed)
sum(http_requests_in_progress)

# Status code distribution (for the pie chart)
sum by (status_code) (rate(http_requests_total[5m]))

# Top 5 endpoints by traffic
topk(5, sum by (endpoint) (rate(http_requests_total[5m])))
```

---

## Grafana Dashboards

Open http://localhost:3000 (admin / admin). The dashboards are auto-loaded from `/var/lib/grafana/dashboards`:

- **FastAPI Overview** — main dashboard with system + HTTP panels, latency percentiles, error rates (22 panels)
- **FastAPI System Health** — dedicated system-metric view with GC and FD gauges (9 panels)

Both dashboards have **5-second refresh** and template variables for `endpoint`, `method`, and `status_code`.

### Navigating the dashboards

1. Open `http://localhost:3000` and log in (`admin` / `admin`).
2. Click the four-squares icon in the left sidebar → **Dashboards** → **FastAPI**.
3. Use the **template variables** at the top of each panel (`endpoint`, `method`, `status_code`) to filter.
4. Time range and refresh are in the top-right corner (default: last 1h, refresh 5s).

### Using the Prometheus UI

1. Open `http://localhost:9090`.
2. **Graph** tab → enter a PromQL expression → click **Execute** → switch to **Graph** tab.
3. **Alerts** tab shows rules and their state (`inactive`, `pending`, `firing`).
4. **Status → Targets** shows whether Prometheus can scrape `app:8000`.

---

## Alerting

### Alert rules

Defined in `prometheus/alerts/`:

- `system_alerts.yml` — `HighCPUUsage`, `HighMemoryUsage`, `InstanceDown`, `FileDescriptorExhaustion`, `ProcessThreadCountHigh`
- `http_alerts.yml` — `HighErrorRate`, `SlowRequests` (p95 > 1s), `HighTrafficSpike`, `NoTraffic`

- View loaded rules at: http://localhost:9090/rules
- View firing alerts at: http://localhost:9090/alerts

### Alertmanager routing

`alertmanager/alertmanager.yml` defines severity-based routing:

- **critical** → `critical-receiver` (1h repeat, immediate dispatch)
- **warning** → `warning-receiver` (4h repeat)
- **info** → `info-receiver` (24h repeat)

Inhibition rules silence warnings in the same category when a critical alert fires, and suppress HTTP alerts when an instance is down.

Webhooks default to a local listener at `http://localhost:5001/alerts` (no-op in dev). Replace with Slack/PagerDuty in production by uncommenting the configs and supplying real URLs.

### Using Alertmanager

1. Open `http://localhost:9093`.
2. Active alerts appear automatically when a rule transitions from `pending` to `firing`.
3. **Silences** → **New Silence** lets you mute an alert for a time window by label matchers (e.g., silence `severity=warning` for 1 hour).

---

## Running Tests

```bash
# All tests
make test
# or
pytest -v

# Specific test file
pytest tests/test_endpoints.py -v

# Single test
pytest tests/test_endpoints.py::test_root_endpoint -v
```

Tests are configured with `asyncio_mode = auto` in `pytest.ini`, so `async def` test functions are automatically awaited.

### Test Suite Organization

| File | Tests | What it Covers |
|------|-------|----------------|
| `tests/test_endpoints.py` | 10 | Status codes, payloads, validation, pagination, store CRUD |
| `tests/test_http_metrics.py` | 8 | `http_requests_total` counter, histograms, label correctness, `/metrics` self-exclusion |
| `tests/test_system_metrics.py` | 6 | Presence of all required system metrics, gauge values are positive, GC metrics exposed |

**Total: 24 tests, all passing.**

### Detailed Coverage

**Endpoint tests (`test_endpoints.py`):**
1. `test_root_endpoint` — `GET /` returns 200 with banner JSON
2. `test_health_endpoint` — `GET /health` returns 200 with timestamp
3. `test_health_ready_endpoint` — `GET /health/ready` returns 200 or 503 depending on collector state
4. `test_metrics_endpoint` — `GET /metrics` returns 200 with correct Content-Type
5. `test_post_data_valid` — `POST /data` with valid payload returns 201
6. `test_post_data_invalid` — Invalid type for `note` returns 422
7. `test_get_data_returns_list` — `GET /data` returns a JSON array
8. `test_data_round_trip` — POST then GET retrieves the same item
9. `test_data_pagination` — `limit` and `offset` are respected
10. `test_data_count` — `/data/count` returns current size

**HTTP metric tests (`test_http_metrics.py`):**
1. `test_http_requests_total_increments` — Counter values increase after traffic
2. `test_http_request_duration_histogram_records` — All histogram series present
3. `test_http_request_size_histogram_records` — Request size histogram observes payloads
4. `test_http_response_size_histogram_records` — Response size histogram observes bodies
5. `test_status_code_label_present` — `status_code="200"` appears
6. `test_endpoint_label_uses_route_template` — Labels are `/data`, `/health`, not raw URLs
7. `test_metrics_endpoint_not_recorded` — Scraping `/metrics` does not pollute the counter
8. `test_method_label_records_get_and_post` — Both `GET` and `POST` appear in labels

**System metric tests (`test_system_metrics.py`):**
1. `test_update_system_metrics_populates_gauges` — All required gauges present in `/metrics`
2. `test_gc_metrics_present` — `python_gc_collections_total` and `python_gc_objects_collected_total` present
3. `test_resident_memory_positive` — `process_resident_memory_bytes` > 0
4. `test_start_time_set` — `process_start_time_seconds` > 0
5. `test_num_cpu_positive` — `process_num_cpu` ≥ 1
6. `test_default_process_metrics_present` — Default `process_*` metrics exposed

### Smoke Test

The `scripts/smoke_test.sh` script performs a black-box end-to-end check against a running stack. It:

1. `curl /health` and asserts `"status":"healthy"`
2. `POST /data` and asserts an `id` is returned
3. `GET /data` and asserts the payload is listed
4. `GET /metrics` and asserts presence of `# HELP` lines and required metric names

Run with: `make smoke` (after `docker compose up -d` or `docker-compose up -d`).

---

## Limitations

This is a single-process monitoring example, **not a hardened production system**. The following limitations are honest acknowledgments of what this project does *not* provide.

### Application Limitations

- **In-memory `POST /data` store** — Uses a `collections.deque(maxlen=1000)` in the Python process. Data is **not persisted** and is lost on restart. Cannot be shared across multiple replicas. For production, use Redis, PostgreSQL, or another backing store.
- **No authentication / authorization** — All endpoints are open. The metrics endpoint in particular exposes process internals, which can aid attackers. Do not expose the app to the public internet without adding auth.
- **No rate limiting** — A client can flood `POST /data` and exhaust the store. Add `slowapi` or a reverse-proxy rate limit for production.
- **No CORS configuration** — Default FastAPI CORS applies (restrictive). Browsers from other origins cannot call the API without explicit configuration.
- **No request-ID / tracing** — When a request is slow or fails, there is no UUID to correlate logs and metrics. OpenTelemetry tracing is recommended for distributed systems.
- **No graceful shutdown beyond uvicorn defaults** — Long-running in-flight requests may be cut off on `SIGTERM`. Increase `--timeout-graceful-shutdown` for production.
- **Single-process worker model** — Default uvicorn runs one worker; for higher throughput, run with `--workers N` and aggregate metrics across pods via Prometheus service discovery.

### Monitoring Stack Limitations

- **Single Prometheus = single point of failure** — If Prometheus dies, all metrics collection stops, alerts stop firing, and Grafana has no data. For HA, run two Prometheus replicas scraping the same targets, or use Thanos / Mimir.
- **15-day retention** — Default Prometheus storage is short. Use Thanos sidecar + S3, Mimir, or a SaaS for long-term storage.
- **Alertmanager webhooks are no-op** — The default receivers point at `http://localhost:5001/alerts` which is not running. Replace with Slack/PagerDuty/Email in production by uncommenting the corresponding config blocks in `alertmanager/alertmanager.yml`.
- **No Prometheus authentication** — UI is open on port 9090. Bind to internal Docker network only; do not publish 9090 to the host in production.
- **Default Grafana admin password** — Hardcoded as `admin/admin` in `docker-compose.yml`. Replace with a secret and disable anonymous access for production.
- **No alert deduplication across Prometheus replicas** — If you scale to HA Prometheus, Alertmanager needs a `cluster.*` config to dedupe alerts.

### Test Limitations

- **No load tests** — `pytest` covers functional behavior but not throughput, p99 latency, or memory pressure. Use `k6`, `locust`, or `wrk` to validate performance.
- **No chaos tests** — There is no automated test for "what happens if the app dies mid-scrape" or "what happens if the alertmanager is down".
- **No security tests** — No fuzzing, no auth tests, no cardinality regression test (e.g., sending 1M unique URLs and verifying the metric series count is bounded).

### Configuration Limitations

- **No hot reload** — Settings are read once at startup. To change buckets or intervals, restart the service.
- **No secret manager integration** — Secrets are read from `.env` or environment variables. Use Docker secrets, Kubernetes secrets, or HashiCorp Vault for production.
- **Histogram buckets are not adaptive** — Fixed at startup. If your traffic has a very different latency profile, edit `HTTP_HISTOGRAM_BUCKETS` accordingly.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `bash: docker-compose: command not found` | Device only has Compose v2 (`docker compose`, no hyphen) | Use `docker compose ...` instead; or install the `docker-compose-plugin` |
| `curl /health` returns 502/connection refused | App container not started | `docker compose ps` (or `docker-compose ps`), check logs: `docker compose logs app` |
| `GET /metrics` is empty | Lifespan never started the collector | Restart the container; verify `SYSTEM_METRICS_INTERVAL` is valid |
| Grafana shows "No data" | Prometheus not scraping | Open `:9090/targets`, ensure `app:8000` is `UP` |
| Alert rules not in `/alerts` | Rule files not mounted | Check `docker-compose.yml` volumes; check Prometheus logs for `error parsing rule files` |
| `POST /data` returns 422 | Body missing `payload` field or wrong type | Send `{"payload": {...}}`; `note` must be a string if present |
| 500-series errors in `http_requests_total` | App exception in handler | Check app logs: `docker compose logs -f app` (or `docker-compose logs -f app`) |
| `ModuleNotFoundError: app` | Running tests from wrong directory | Run `pytest` from the project root |
| `bind: address already in use` for any of 8000 / 3000 / 9090 / 9093 | A previous run's leftover containers, or another system process holding the port | First: `docker compose down` to clean up. If still bound, find the culprit — `lsof -i :3000` (Linux/macOS) or `netstat -ano \| findstr :3000` (Windows). To remap without editing YAML: set the matching variable in `.env` (e.g. `GRAFANA_PORT=3001`) and re-run `docker compose up -d`. |
| Stack fails to start mid-way (some containers `Exit 1`) | One container can't bind its port; another service depends on it | `docker compose ps` shows which service failed; `docker compose logs <service>` for details. Then `docker compose down` and remap the conflicting port in `.env`. |
| `docker compose up` hangs on prometheus | Volume permission issue | `docker compose down -v && docker compose up -d` |
| `process_open_fds` missing on macOS | macOS has no `RLIMIT_NOFILE` | Expected; not a bug, but the metric is unavailable on macOS Docker Desktop |
| Test failures after `git pull` | Stale `__pycache__` | `find . -name __pycache__ -exec rm -rf {} +` |
| `pytest` complains about `event_loop` fixture deprecation | Newer pytest-asyncio | Use `pytest-asyncio` ≥ 0.23; remove the custom `event_loop` fixture from `conftest.py` |
| CardCount explosion in `/metrics` | Unmatched routes leaking raw paths | Already mitigated by middleware sanitization; verify by sending random UUIDs and checking series count |

---

## References

### Project Repository

- **GitHub:** [https://github.com/jogashray/fastapi-monitoring-apps.git](https://github.com/jogashray/fastapi-monitoring-apps.git)
- **Issues & feature requests:** [https://github.com/jogashray/fastapi-monitoring-apps/issues](https://github.com/jogashray/fastapi-monitoring-apps/issues)
- **Clone:** `git clone https://github.com/jogashray/fastapi-monitoring-apps.git`

### Project Files

- `requirements.md` — original project statement
- `plan.md` — system design and architectural plan
- `test_cases.md` — detailed test case specifications
- `README.md` — this comprehensive documentation
- `app/config.py` — configuration definition
- `app/metrics/` — Prometheus metric definitions
- `prometheus/prometheus.yml` — scrape and rule configuration
- `alertmanager/alertmanager.yml` — routing and receiver configuration
- `grafana/dashboards/` — dashboard JSON definitions

### Upstream Documentation

- **FastAPI** — https://fastapi.tiangolo.com
- **Uvicorn** — https://www.uvicorn.org
- **Pydantic / pydantic-settings** — https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- **prometheus-client (Python)** — https://github.com/prometheus/client_python
- **psutil** — https://psutil.readthedocs.io
- **Prometheus** — https://prometheus.io/docs/
- **Prometheus query language (PromQL)** — https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Alertmanager** — https://prometheus.io/docs/alerting/latest/alertmanager/
- **Grafana provisioning** — https://grafana.com/docs/grafana/latest/administration/provisioning/
- **Grafana dashboards** — https://grafana.com/docs/grafana/latest/dashboards/

### Related Concepts

- **RED method** (Rate, Errors, Duration) — https://www.weave.works/blog/the-red-method-key-metrics-for-microservices-architecture/
- **USE method** (Utilization, Saturation, Errors) — https://www.brendangregg.com/usemethod.html
- **Prometheus best practices on metric names** — https://prometheus.io/docs/practices/naming/

---

## License

This project is provided for educational and demonstration purposes.
