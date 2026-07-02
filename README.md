# FastAPI Metrics Monitoring System

[![GitHub](https://img.shields.io/badge/GitHub-jogashray%2Ffastapi--monitoring--apps-blue?logo=github)](https://github.com/jogashray/fastapi-monitoring-apps.git)

A production-ready FastAPI application exposing **system-level** and **HTTP-level** Prometheus metrics, with a complete monitoring stack — **Prometheus**, **Grafana**, and **Alertmanager** — wired together via Docker Compose.

**Repository:** [https://github.com/jogashray/fastapi-monitoring-apps.git](https://github.com/jogashray/fastapi-monitoring-apps.git)

## Overview

This project implements comprehensive metrics monitoring for a FastAPI application:

- **System metrics**: CPU, memory, file descriptors, threads, GC, uptime
- **HTTP metrics**: request volume, latency percentiles, request/response sizes, in-flight requests
- **Prometheus**: scrape collection with alert rules for system & HTTP anomalies
- **Grafana**: auto-provisioned dashboards (FastAPI Overview + System Health)
- **Alertmanager**: severity-based routing with critical/warning/info receivers

## Architecture

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

## Quick Start

### Option 1: Docker Compose (full stack)

```bash
docker-compose up -d
```

Services come up on:

| Service | URL | Credentials |
|---------|-----|-------------|
| FastAPI app | http://localhost:8000 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Alertmanager | http://localhost:9093 | — |

The Grafana dashboards (`FastAPI Overview`, `FastAPI System Health`) and Prometheus datasource are auto-provisioned on startup.

### Option 2: Local development

```bash
pip install -r requirements.txt
make run
# or:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Then `curl http://localhost:8000/metrics` to see Prometheus exposition output.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Application info |
| GET | `/health` | Liveness probe |
| GET | `/health/ready` | Readiness probe (returns 503 until metrics are initialized) |
| GET | `/metrics` | Prometheus exposition (Content-Type: `text/plain; version=0.0.4`) |
| POST | `/data` | Submit a JSON payload (`{"payload": {...}, "note": "..."}`) |
| GET | `/data` | List stored items (supports `?limit=` and `?offset=`) |
| GET | `/data/count` | Current size of in-memory store |

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

## Sample PromQL Queries

### CPU & Memory

```promql
# CPU rate (cores per second)
rate(process_cpu_seconds_total[5m])

# Memory usage growth
process_resident_memory_bytes / 1024 / 1024  # MB

# File descriptor saturation
process_open_fds / process_max_fds * 100
```

### HTTP Traffic

```promql
# Total request rate
sum(rate(http_requests_total[5m]))

# Per-endpoint request rate
sum by (endpoint) (rate(http_requests_total[5m]))

# p95 latency (matches requirements example)
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{endpoint="/data",method="GET"}[5m])) by (le))

# Error rate (5xx / total)
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
  /
sum(rate(http_requests_total[5m]))
```

### Sizing

```promql
# p95 request size
histogram_quantile(0.95, sum(rate(http_request_size_bytes_bucket[5m])) by (le, endpoint))

# p95 response size
histogram_quantile(0.95, sum(rate(http_response_size_bytes_bucket[5m])) by (le, endpoint))
```

## Grafana

Open http://localhost:3000 (admin / admin). The dashboards are auto-loaded from `/var/lib/grafana/dashboards`:

- **FastAPI Overview** — main dashboard with system + HTTP panels, latency percentiles, error rates
- **FastAPI System Health** — dedicated system-metric view with GC and FD gauges

Both dashboards have **5-second refresh** and template variables for `endpoint`, `method`, and `status_code`.

## Alerting

### Alert rules

Defined in `prometheus/alerts/`:

- `system_alerts.yml` — `HighCPUUsage`, `HighMemoryUsage`, `InstanceDown`, `FileDescriptorExhaustion`, `ProcessThreadCountHigh`
- `http_alerts.yml` — `HighErrorRate`, `SlowRequests` (p95 > 1s), `HighTrafficSpike`, `NoTraffic`

View loaded rules at: http://localhost:9090/rules
View firing alerts at: http://localhost:9090/alerts

### Alertmanager routing

`alertmanager/alertmanager.yml` defines severity-based routing:

- **critical** → `critical-receiver` (1h repeat, immediate dispatch)
- **warning** → `warning-receiver` (4h repeat)
- **info** → `info-receiver` (24h repeat)

Inhibition rules silence warnings in the same category when a critical alert fires, and suppress HTTP alerts when an instance is down.

Webhooks default to a local listener at `http://localhost:5001/alerts` (no-op in dev). Replace with Slack/PagerDuty in production by uncommenting the configs and supplying real URLs.

## Configuration

All settings are tunable via environment variables (or a `.env` file). See `.env.example`:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `fastapi-metrics-app` | App display name |
| `METRICS_ENDPOINT` | `/metrics` | Prometheus exposition path |
| `SYSTEM_METRICS_INTERVAL` | `5` | Seconds between system-metric snapshots |
| `ENABLE_DEFAULT_METRICS` | `true` | Register default process/platform/GC collectors |
| `HTTP_HISTOGRAM_BUCKETS` | `0.005,0.01,0.025,...,10.0` | Latency histogram buckets (seconds) |
| `REQUEST_SIZE_BUCKETS` | `100,1024,10240,...` | Request size histogram buckets (bytes) |
| `RESPONSE_SIZE_BUCKETS` | `100,1024,10240,...` | Response size histogram buckets (bytes) |
| `MAX_DATA_ITEMS` | `1000` | Capacity of in-memory `/data` store |

## Running Tests

```bash
pytest -v
```

Tests cover endpoint behavior, HTTP metric collection, system metric values, and exposition format.

## Project Structure

```
.
├── app/
│   ├── main.py                 # FastAPI entry point + lifespan + /metrics handler
│   ├── config.py               # pydantic-settings configuration
│   ├── metrics/
│   │   ├── system_metrics.py   # CPU, memory, GC, FD, threads
│   │   └── http_metrics.py     # HTTP counters, histograms, gauges
│   ├── middleware/
│   │   └── metrics_middleware.py
│   ├── collectors/
│   │   └── system_collector.py # Async background updater
│   └── routers/
│       ├── health.py           # /, /health, /health/ready
│       └── api.py              # POST/GET /data
├── prometheus/
│   ├── prometheus.yml          # Scrape + rule_files
│   └── alerts/                 # system_alerts.yml, http_alerts.yml
├── alertmanager/
│   └── alertmanager.yml        # Routing + receivers + inhibition
├── grafana/
│   ├── provisioning/           # Datasource + dashboard provider
│   └── dashboards/             # fastapi-overview.json, system-health.json
├── tests/                      # pytest suite
├── scripts/smoke_test.sh       # End-to-end stack check
├── docker-compose.yml          # 4-service stack
├── Dockerfile
├── Makefile
└── requirements.txt
```

## Smoke Test

After `docker-compose up -d`, verify the stack:

```bash
bash scripts/smoke_test.sh
```

This curl-asserts:
- `/health` returns healthy
- `POST /data` creates an item
- `GET /data` returns it
- `/metrics` exposes `# HELP` lines and required metric names

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `/metrics` returns empty | Lifespan never started | Check uvicorn started cleanly; restart |
| Grafana shows "No data" | Prometheus not scraping | Open `:9090/targets`, ensure `app:8000` is `UP` |
| Alerts not firing | Rules not loaded | Open `:9090/rules`, verify alert files mounted |
| 422 from `POST /data` | Missing `payload` field | Send `{"payload": {...}}` body |
| CardCount explodes | Unmatched routes leaking raw paths | Already mitigated; check middleware `_safe_endpoint_label` |
| `docker-compose up` fails on port 8000 | Port conflict | Edit `docker-compose.yml` ports |

## License

This project is provided for educational and demonstration purposes.