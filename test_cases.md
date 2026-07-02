# FastAPI Metrics Monitoring System - Test Cases

## Overview
This document defines comprehensive test cases covering:
- All requirements from `requirements.md`
- All implementation phases from `plan.md`
- Functional, integration, metric validation, and end-to-end observability tests

Test framework: **pytest** + **pytest-asyncio** + **httpx.AsyncClient**

---

## Test Environment Setup

### Fixtures (conftest.py)
- `client` — async httpx client connected to FastAPI app
- `registry` — fresh `CollectorRegistry` for isolated metric tests
- `reset_metrics` — clears metrics between tests
- `trigger_error` — utility to send a request that produces a 5xx
- `slow_request` — utility to simulate slow request (sleep)
- `mock_psutil` — patches psutil for deterministic system values

---

## Phase 1: Project Setup & Configuration Tests

### TC-1.1: Dependencies installed
| ID | Description | Expected |
|----|-------------|----------|
| TC-1.1.1 | All packages in requirements.txt install without error | `pip install -r requirements.txt` succeeds |
| TC-1.1.2 | Python 3.8+ syntax compatibility | No syntax errors on import |
| TC-1.1.3 | FastAPI imports | `from fastapi import FastAPI` works |
| TC-1.1.4 | prometheus_client imports | `from prometheus_client import Counter, Gauge, Histogram` works |
| TC-1.1.5 | psutil imports | `import psutil` works |

### TC-1.2: Configuration management
| ID | Description | Expected |
|----|-------------|----------|
| TC-1.2.1 | Default config loads | `Settings()` returns object with defaults |
| TC-1.2.2 | Env var override | `SYSTEM_METRICS_INTERVAL=10` reflected in settings |
| TC-1.2.3 | METRICS_ENDPOINT default | `"/metrics"` |
| TC-1.2.4 | Histogram buckets default | List of floats with sane latency values |
| TC-1.2.5 | Invalid interval value rejected | ValidationError raised |

---

## Phase 2: API Endpoints Tests

### TC-2.1: `GET /`
| ID | Description | Expected |
|----|-------------|----------|
| TC-2.1.1 | Root endpoint returns 200 | Status code 200 |
| TC-2.1.2 | Returns JSON with message | `{"message": "...", "version": "..."}` |
| TC-2.1.3 | Records HTTP metric for root | `http_requests_total{endpoint="/", method="GET", status_code="200"}` increments |

### TC-2.2: `GET /health`
| ID | Description | Expected |
|----|-------------|----------|
| TC-2.2.1 | Health check returns 200 | Status code 200 |
| TC-2.2.2 | Returns health status JSON | `{"status": "healthy", "timestamp": "..."}` |
| TC-2.2.3 | Records HTTP metric | `http_requests_total{endpoint="/health", ...}` increments |

### TC-2.3: `GET /health/ready`
| ID | Description | Expected |
|----|-------------|----------|
| TC-2.3.1 | Readiness probe returns 200 when healthy | Status 200 |
| TC-2.3.2 | Returns readiness JSON | `{"status": "ready"}` |

### TC-2.4: `POST /data`
| ID | Description | Expected |
|----|-------------|----------|
| TC-2.4.1 | Valid JSON payload returns 200/201 | Status 200 or 201 |
| TC-2.4.2 | Returns item with id | `{"id": "...", "received": ..., "size": ...}` |
| TC-2.4.3 | Empty body returns 422 | Validation error |
| TC-2.4.4 | Invalid JSON returns 422 | Validation error |
| TC-2.4.5 | Records HTTP metric with method=POST | `http_requests_total{..., method="POST", ...}` |
| TC-2.4.6 | Request size histogram observes payload | `http_request_size_bytes_count` increases |

### TC-2.5: `GET /data`
| ID | Description | Expected |
|----|-------------|----------|
| TC-2.5.1 | Returns list of stored items | Status 200, JSON list |
| TC-2.5.2 | `?limit=N` param respected | Returns at most N items |
| TC-2.5.3 | `?offset=N` param respected | Skips first N items |
| TC-2.5.4 | Records HTTP metric | `http_requests_total{endpoint="/data", method="GET"}` |
| TC-2.5.5 | Response size histogram observes | `http_response_size_bytes_count` increases |

### TC-2.6: `GET /metrics`
| ID | Description | Expected |
|----|-------------|----------|
| TC-2.6.1 | Returns 200 | Status 200 |
| TC-2.6.2 | Content-Type header is Prometheus format | `text/plain; version=0.0.4; charset=utf-8` |
| TC-2.6.3 | Body is non-empty | Body length > 0 |
| TC-2.6.4 | Body contains `# HELP` and `# TYPE` lines | Standard exposition format |
| TC-2.6.5 | Does NOT increment `http_requests_total` (skipped) | Counter unchanged after scrape |

---

## Phase 3: HTTP Metrics Tests

### TC-3.1: `http_requests_total` counter
| ID | Description | Expected |
|----|-------------|----------|
| TC-3.1.1 | Metric exists with correct name | `http_requests_total` registered |
| TC-3.1.2 | Has labels: method, endpoint, status_code | All three labels present |
| TC-3.1.3 | GET request increments counter by 1 | `.value == 1` |
| TC-3.1.4 | POST request increments counter by 1 | `.value == 1` |
| TC-3.1.5 | Multiple requests accumulate | `.value == N` after N requests |
| TC-3.1.6 | Status code label is correct | `status_code="200"` for success |
| TC-3.1.7 | 404 status code is captured | `status_code="404"` for missing route |
| TC-3.1.8 | 500 status code is captured | `status_code="500"` for errors |
| TC-3.1.9 | Different methods get different label values | `method="GET"` vs `method="POST"` |
| TC-3.1.10 | Per-endpoint tracking works | Separate series for `/data` vs `/health` |
| TC-3.1.11 | Global rate query works | `rate(http_requests_total[5m])` computable |

### TC-3.2: `http_request_duration_seconds` histogram
| ID | Description | Expected |
|----|-------------|----------|
| TC-3.2.1 | Metric exists with correct name | `http_request_duration_seconds` |
| TC-3.2.2 | Is of type histogram | `# TYPE http_request_duration_seconds histogram` |
| TC-3.2.3 | Has buckets `_bucket`, `_sum`, `_count` | All three series types present |
| TC-3.2.4 | Default buckets defined | Buckets include 0.005, 0.01, 0.025, ..., 10.0 |
| TC-3.2.5 | Has labels method, endpoint, status_code | All present |
| TC-3.2.6 | Observation recorded for request | `_count` increments |
| TC-3.2.7 | Sum reflects total duration | `_sum` is positive |
| TC-3.2.8 | Buckets are cumulative (le) | Bucket counts are monotonic |
| TC-3.2.9 | p95 query computable | `histogram_quantile(0.95, ...)` returns value |
| TC-3.2.10 | Configurable buckets via env var | `HTTP_HISTOGRAM_BUCKETS=...` works |

### TC-3.3: `http_request_size_bytes` histogram
| ID | Description | Expected |
|----|-------------|----------|
| TC-3.3.1 | Metric exists | `http_request_size_bytes` registered |
| TC-3.3.2 | Is histogram type | Confirmed via exposition |
| TC-3.3.3 | Has labels method, endpoint | Both present |
| TC-3.3.4 | POST with body records non-zero size | `_sum > 0` |
| TC-3.3.5 | GET with no body records zero | `_sum == 0` |
| TC-3.3.6 | Count increments per request | `_count` matches request count |

### TC-3.4: `http_response_size_bytes` histogram
| ID | Description | Expected |
|----|-------------|----------|
| TC-3.4.1 | Metric exists | `http_response_size_bytes` |
| TC-3.4.2 | Records non-zero for JSON response | `_sum > 0` |
| TC-3.4.3 | Has labels method, endpoint | Both present |

### TC-3.5: `http_requests_in_progress` gauge
| ID | Description | Expected |
|----|-------------|----------|
| TC-3.5.1 | Metric exists | `http_requests_in_progress` |
| TC-3.5.2 | Increments at request start | Value +1 during request |
| TC-3.5.3 | Decrements after response | Back to 0 after request |
| TC-3.5.4 | Multiple concurrent requests reflect count | Value == N during N parallel requests |

### TC-3.6: Middleware behavior
| ID | Description | Expected |
|----|-------------|----------|
| TC-3.6.1 | Skips recording for `/metrics` endpoint | No entry in `http_requests_total` for `/metrics` |
| TC-3.6.2 | Records metrics for all other endpoints | Each endpoint tracked |
| TC-3.6.3 | Route template used (not raw path) | `endpoint="/data"` not `endpoint="/data/123"` |
| TC-3.6.4 | Unmatched paths sanitized to `unknown` | No cardinality explosion |
| TC-3.6.5 | Exception path still records metric | 500 captured with proper status_code |
| TC-3.6.6 | Slow request (10s sleep) records in correct bucket | Observed in `le="10.0"` bucket |

---

## Phase 4: System Metrics Tests

### TC-4.1: `process_cpu_seconds_total` counter
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.1.1 | Metric exists with correct name | `process_cpu_seconds_total` |
| TC-4.1.2 | Is of type counter | `# TYPE process_cpu_seconds_total counter` |
| TC-4.1.3 | Has HELP description | Non-empty help string |
| TC-4.1.4 | Background collector updates it | Value increases after collection cycle |
| TC-4.1.5 | Rate query computable | `rate(process_cpu_seconds_total[5m])` valid PromQL |

### TC-4.2: `process_cpu_utilization_percent` gauge
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.2.1 | Metric exists | `process_cpu_utilization_percent` |
| TC-4.2.2 | Value is between 0 and 100 | `0 <= value <= 100` |
| TC-4.2.3 | Updated by background collector | Value changes across cycles |

### TC-4.3: `process_resident_memory_bytes` gauge
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.3.1 | Metric exists | `process_resident_memory_bytes` |
| TC-4.3.2 | Is of type gauge | Confirmed via exposition |
| TC-4.3.3 | Value is positive | `value > 0` |
| TC-4.3.4 | Updated by background collector | Non-zero after process start |

### TC-4.4: `process_virtual_memory_bytes` gauge
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.4.1 | Metric exists | `process_virtual_memory_bytes` |
| TC-4.4.2 | Value is positive | `value > 0` |
| TC-4.4.3 | Generally larger than RSS | `virtual > resident` |

### TC-4.5: `process_memory_utilization_percent` gauge
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.5.1 | Metric exists | `process_memory_utilization_percent` |
| TC-4.5.2 | Value in valid range | `0 <= value <= 100` |

### TC-4.6: `process_start_time_seconds` gauge
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.6.1 | Metric exists | `process_start_time_seconds` |
| TC-4.6.2 | Value is Unix timestamp | `value > time.time() - 86400` (within last day) |
| TC-4.6.3 | Stable across collections | Same value after multiple cycles |

### TC-4.7: `process_uptime_seconds` gauge
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.7.1 | Metric exists | `process_uptime_seconds` |
| TC-4.7.2 | Increases over time | `value2 > value1` after 1s wait |
| TC-4.7.3 | Initially small (process just started) | `< 60` at startup |

### TC-4.8: `process_open_fds` and `process_max_fds` gauges
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.8.1 | Both metrics exist | Both registered |
| TC-4.8.2 | `open_fds` is non-negative | `value >= 0` |
| TC-4.8.3 | `max_fds` is positive | `value > 0` |
| TC-4.8.4 | `open_fds <= max_fds` | Invariant holds |

### TC-4.9: `process_threads` and `process_num_cpu` gauges
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.9.1 | Both metrics exist | Both registered |
| TC-4.9.2 | `threads` is positive | `value >= 1` |
| TC-4.9.3 | `num_cpu` matches system | Matches `os.cpu_count()` |

### TC-4.10: Garbage collection metrics
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.10.1 | GC metrics exist | `python_gc_*` series present |
| TC-4.10.2 | Three generations tracked | Labels for 0, 1, 2 |
| TC-4.10.3 | Counts are non-negative | All values >= 0 |
| TC-4.10.4 | Forced GC triggers collection increase | `gc.collect()` updates counts |

### TC-4.11: Default platform/process metrics
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.11.1 | Default process metrics from `prometheus_client` | Standard `process_*` series present |
| TC-4.11.2 | Platform metrics from `prometheus_client` | E.g., `python_info`, `process_*` |

### TC-4.12: Background collector
| ID | Description | Expected |
|----|-------------|----------|
| TC-4.12.1 | Collector starts on app startup | All gauges populated |
| TC-4.12.2 | Collector runs at configured interval | Updates every N seconds |
| TC-4.12.3 | Collector cancels on shutdown | No errors on app close |
| TC-4.12.4 | Collector handles psutil errors gracefully | No crash if stat fails |

---

## Phase 5: Prometheus Configuration Tests

### TC-5.1: prometheus.yml
| ID | Description | Expected |
|----|-------------|----------|
| TC-5.1.1 | Valid YAML | Parses without error |
| TC-5.1.2 | Scrape interval is 5s | `global.scrape_interval == 5s` |
| TC-5.1.3 | Evaluation interval is 5s | `global.evaluation_interval == 5s` |
| TC-5.1.4 | FastAPI app job defined | `scrape_configs[].job_name == 'fastapi-app'` |
| TC-5.1.5 | App target is `app:8000` | Static config correct |
| TC-5.1.6 | Rule files referenced | `rule_files` includes alerts path |

---

## Phase 6: Prometheus Alert Rules Tests

### TC-6.1: system_alerts.yml
| ID | Description | Expected |
|----|-------------|----------|
| TC-6.1.1 | Valid YAML syntax | Parses cleanly |
| TC-6.1.2 | `HighCPUUsage` rule defined | Alert name present |
| TC-6.1.3 | HighCPU expression is valid PromQL | `rate(process_cpu_seconds_total[5m]) > 0.8` |
| TC-6.1.4 | HighCPU has `for: 2m` | Persistence threshold set |
| TC-6.1.5 | HighCPU has severity label | `severity: warning` |
| TC-6.1.6 | `HighMemoryUsage` rule defined | RSS > 500MB |
| TC-6.1.7 | `InstanceDown` rule defined | `up == 0` |
| TC-6.1.8 | `FileDescriptorExhaustion` rule defined | FD ratio > 0.8 |
| TC-6.1.9 | Each rule has annotations (summary, description) | Both fields present |
| TC-6.1.10 | Rules are `inactive` initially on fresh stack | Prometheus `/alerts` shows inactive state |

### TC-6.2: http_alerts.yml
| ID | Description | Expected |
|----|-------------|----------|
| TC-6.2.1 | Valid YAML | Parses cleanly |
| TC-6.2.2 | `HighErrorRate` rule defined | 5xx rate > 5% |
| TC-6.2.3 | Error rate expression valid | Uses `status_code=~"5.."` |
| TC-6.2.4 | `SlowRequests` rule defined | p95 > 1s |
| TC-6.2.5 | Uses `histogram_quantile` | Expression valid |
| TC-6.2.6 | `HighTrafficSpike` rule defined | Rate > 100 rps |
| TC-6.2.7 | All rules have severity label | warning/critical/info |
| TC-6.2.8 | All rules have `for:` duration | Persistence set |

### TC-6.3: Alert firing (synthetic)
| ID | Description | Expected |
|----|-------------|----------|
| TC-6.3.1 | Simulate 10x 5xx errors → HighErrorRate fires | Rule state `firing` after `for` duration |
| TC-6.3.2 | Simulate slow request → SlowRequests fires | p95 > 1s for endpoint |
| TC-6.3.3 | Stop app container → InstanceDown fires | `up == 0` for > 1m |
| TC-6.3.4 | Resume app → alerts resolve to inactive | State returns to inactive |

---

## Phase 7: Alertmanager Configuration Tests

### TC-7.1: alertmanager.yml structure
| ID | Description | Expected |
|----|-------------|----------|
| TC-7.1.1 | Valid YAML | Parses cleanly |
| TC-7.1.2 | Global `resolve_timeout` defined | Default 5m |
| TC-7.1.3 | Default route defined | Receiver set |
| TC-7.1.4 | Group_by configured | By alertname and category |
| TC-7.1.5 | Group_wait and group_interval set | Sane values |
| TC-7.1.6 | Severity-based sub-routes | `severity="critical"` and `severity="warning"` |

### TC-7.2: Receivers
| ID | Description | Expected |
|----|-------------|----------|
| TC-7.2.1 | `default-receiver` defined | Webhook config |
| TC-7.2.2 | `critical-receiver` defined | Slack + Email |
| TC-7.2.3 | `warning-receiver` defined | Slack |
| TC-7.2.4 | Slack api_url is a placeholder | Indicates where real URL goes |
| TC-7.2.5 | `send_resolved: true` set | Resolution notifications enabled |

### TC-7.3: Inhibition rules
| ID | Description | Expected |
|----|-------------|----------|
| TC-7.3.1 | Inhibition rule: critical silences warning | Source/target matchers correct |
| TC-7.3.2 | `equal: ['category']` set | Same category only |

### TC-7.4: Alertmanager runtime
| ID | Description | Expected |
|----|-------------|----------|
| TC-7.4.1 | Alertmanager starts on port 9093 | Container healthcheck passes |
| TC-7.4.2 | Web UI loads at `:9093` | Status page accessible |
| TC-7.4.3 | Firing alert appears in UI | After synthetic trigger |
| TC-7.4.4 | Silences can be created | Match label + duration works |
| TC-7.4.5 | Critical alert routes to critical-receiver | Verified in logs |
| TC-7.4.6 | Warning alert routes to warning-receiver | Verified in logs |

---

## Phase 8: Grafana Integration Tests

### TC-8.1: Datasource provisioning
| ID | Description | Expected |
|----|-------------|----------|
| TC-8.1.1 | Prometheus datasource auto-provisioned | Visible in Grafana datasources |
| TC-8.1.2 | Datasource URL is `http://prometheus:9090` | Configured correctly |
| TC-8.1.3 | Datasource marked as default | First in list |
| TC-8.1.4 | Health check passes | Datasource page shows "working" |

### TC-8.2: Dashboard provisioning
| ID | Description | Expected |
|----|-------------|----------|
| TC-8.2.1 | `fastapi-overview.json` auto-loaded | Dashboard visible in UI |
| TC-8.2.2 | `system-health.json` auto-loaded | Dashboard visible in UI |
| TC-8.2.3 | Dashboards in `FastAPI` folder | Folder structure correct |
| TC-8.2.4 | All panels render data (after metrics exist) | No "no data" errors |
| TC-8.2.5 | Refresh interval is 5s | Updates live |

### TC-8.3: fastapi-overview dashboard panels
| ID | Description | Expected |
|----|-------------|----------|
| TC-8.3.1 | "CPU rate" panel queries `rate(process_cpu_seconds_total[5m])` | Valid PromQL |
| TC-8.3.2 | "Memory RSS" panel shows humanized bytes | `humanize` unit applied |
| TC-8.3.3 | "Virtual memory" panel exists | Time series populated |
| TC-8.3.4 | "Open FDs / Max FDs" gauge panel | Ratio 0-100% |
| TC-8.3.5 | "Threads" stat panel | Shows numeric value |
| TC-8.3.6 | "Uptime" stat panel | Shows duration |
| TC-8.3.7 | "Request rate (total)" panel | Live updating |
| TC-8.3.8 | "Request rate by endpoint" panel | Multiple series |
| TC-8.3.9 | "Status code distribution" pie chart | Shows 2xx/4xx/5xx breakdown |
| TC-8.3.10 | "Top 5 endpoints" bar gauge | Ordered by traffic |
| TC-8.3.11 | "In-flight requests" stat panel | Matches gauge value |
| TC-8.3.12 | "p50 latency" panel | `histogram_quantile(0.50, ...)` |
| TC-8.3.13 | "p95 latency" panel | `histogram_quantile(0.95, ...)` |
| TC-8.3.14 | "p99 latency" panel | `histogram_quantile(0.99, ...)` |
| TC-8.3.15 | "Average duration" panel | `sum/sum(count)` |
| TC-8.3.16 | "Error rate" panel | 5xx/total ratio |
| TC-8.3.17 | "Request size p95" panel | Computed correctly |
| TC-8.3.18 | "Response size p95" panel | Computed correctly |

### TC-8.4: Template variables
| ID | Description | Expected |
|----|-------------|----------|
| TC-8.4.1 | `$endpoint` variable defined | Dropdown populated from label values |
| TC-8.4.2 | `$method` variable defined | GET/POST options |
| TC-8.4.3 | `$status_code` variable defined | 200/404/etc options |
| TC-8.4.4 | Variable selection filters panels | All panels update |

### TC-8.5: Grafana alerting (optional)
| ID | Description | Expected |
|----|-------------|----------|
| TC-8.5.1 | Unified alerting enabled | Alerting page accessible |
| TC-8.5.2 | Alert rule importable from YAML | Rules can be created |
| TC-8.5.3 | Alert state syncs with Prometheus | Contact point testable |

---

## Phase 9: Docker Compose Tests

### TC-9.1: Container stack
| ID | Description | Expected |
|----|-------------|----------|
| TC-9.1.1 | `docker-compose up` brings up 4 services | app, prometheus, grafana, alertmanager |
| TC-9.1.2 | All containers reach `healthy` state | Healthchecks pass |
| TC-9.1.3 | App container exposes port 8000 | Reachable from host |
| TC-9.1.4 | Prometheus container exposes port 9090 | UI accessible |
| TC-9.1.5 | Grafana container exposes port 3000 | UI accessible |
| TC-9.1.6 | Alertmanager container exposes port 9093 | UI accessible |
| TC-9.1.7 | Containers auto-restart on failure | `restart: unless-stopped` set |
| TC-9.1.8 | Containers on same network | Can resolve `prometheus`, `app`, etc. by name |

### TC-9.2: Prometheus targets
| ID | Description | Expected |
|----|-------------|----------|
| TC-9.2.1 | Target `app:8000` listed in `/targets` | Endpoint visible |
| TC-9.2.2 | Target state is `UP` | Healthy scrape |
| TC-9.2.3 | Last scrape time updates every 5s | Active scraping |

### TC-9.3: Prometheus rules
| ID | Description | Expected |
|----|-------------|----------|
| TC-9.3.1 | Rules loaded from `/etc/prometheus/alerts/*.yml` | Visible in `/rules` |
| TC-9.3.2 | Both groups (system_alerts, http_alerts) loaded | Both visible |
| TC-9.3.3 | All rules in `inactive` state initially | No false alerts |

---

## Phase 10: End-to-End Observability Tests

### TC-10.1: Full pipeline
| ID | Description | Expected |
|----|-------------|----------|
| TC-10.1.1 | Send 100 GETs to `/health` → Prometheus scrapes → Grafana shows 100 | Counts match |
| TC-10.1.2 | Trigger 5xx → alert fires → Alertmanager receives → notification dispatched | Full chain works |
| TC-10.1.3 | Slow request → p95 panel updates | Latency visible |
| TC-10.1.4 | Kill app container → InstanceDown alert fires within 1m | Detection works |
| TC-10.1.5 | Restart app → all alerts resolve within 5m | Recovery works |

### TC-10.2: PromQL query validation
| ID | Description | Expected |
|----|-------------|----------|
| TC-10.2.1 | `rate(process_cpu_seconds_total[5m])` returns value | Valid query |
| TC-10.2.2 | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{endpoint="/data", method="GET"}[5m])) by (le))` returns value | Matches requirements example |
| TC-10.2.3 | `sum by (endpoint) (rate(http_requests_total[5m]))` works | Per-endpoint rate |
| TC-10.2.4 | `sum(rate(http_requests_total{status_code=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))` works | Error rate |

### TC-10.3: Sample data flow
| ID | Description | Expected |
|----|-------------|----------|
| TC-10.3.1 | POST /data with payload → GET /data returns it | End-to-end data flow |
| TC-10.3.2 | Multiple POSTs accumulate | Counter reflects all |
| TC-10.3.3 | Metrics reflect both POST and GET | Per-method tracking |

---

## Phase 11: Performance & Load Tests (Bonus)

### TC-11.1: Baseline
| ID | Description | Expected |
|----|-------------|----------|
| TC-11.1.1 | Single GET /health latency < 50ms | p50 under 50ms |
| TC-11.1.2 | p99 latency < 200ms | p99 under 200ms |
| TC-11.1.3 | Middleware overhead < 100µs | Negligible added cost |

### TC-11.2: Load (k6/locust)
| ID | Description | Expected |
|----|-------------|----------|
| TC-11.2.1 | 100 RPS sustained for 1 minute | No errors, stable p95 |
| TC-11.2.2 | 1000 RPS burst | No memory leak, all metrics captured |
| TC-11.2.3 | `/metrics` scrape during load | Returns within 1s |

### TC-11.3: Failure modes
| ID | Description | Expected |
|----|-------------|----------|
| TC-11.3.1 | psutil fails (mock) → app continues | Graceful degradation |
| TC-11.3.2 | Background task exception → metrics still serve | Error logged, no crash |
| TC-11.3.3 | Invalid PromQL in alert rule → Prometheus logs error | Doesn't crash Prometheus |
| TC-11.3.4 | Alertmanager down → Prometheus buffers alerts | No data loss in short window |

---

## Phase 12: Documentation Tests

### TC-12.1: README completeness
| ID | Description | Expected |
|----|-------------|----------|
| TC-12.1.1 | README has Overview section | Present |
| TC-12.1.2 | README has Quick Start | Present |
| TC-12.1.3 | README lists all endpoints | Table present |
| TC-12.1.4 | README has Metrics Reference | All metrics documented |
| TC-12.1.5 | README has Grafana Setup section | Present |
| TC-12.1.6 | README has Alerting Setup section | Present |
| TC-12.1.7 | README has Sample PromQL queries | At least 5 examples |
| TC-12.1.8 | README has Docker deployment instructions | Present |
| TC-12.1.9 | README has Configuration section | Env vars documented |
| TC-12.1.10 | README has Troubleshooting section | Common issues covered |

---

## Test Execution Plan

### Test Layers
```
Layer 1: Unit (TC-1, TC-3.6, TC-4.10)        — fast, no app
Layer 2: API (TC-2.*)                          — httpx + ASGI transport
Layer 3: Metrics Validation (TC-3.*, TC-4.*)   — scrape /metrics, parse
Layer 4: Config (TC-5, TC-6, TC-7)             — YAML + rule files
Layer 5: Integration (TC-10.*)                 — requires docker-compose up
Layer 6: Performance (TC-11.*)                 — k6/locust, optional
```

### Run Order
1. **Pre-flight**: Verify environment, dependencies (TC-1.*)
2. **Unit tests**: Config, fixtures, isolated metrics (TC-1.2, TC-4.10)
3. **API tests**: All endpoints (TC-2.*)
4. **Metrics tests**: HTTP + system metrics (TC-3.*, TC-4.*)
5. **Config tests**: YAML validity (TC-5.*, TC-6.*, TC-7.*)
6. **Container stack**: `docker-compose up` then verify (TC-9.*)
7. **Grafana provisioning**: Verify auto-load (TC-8.*)
8. **End-to-end**: Send requests, verify full pipeline (TC-10.*)
9. **Synthetic alerts**: Trigger conditions, verify firing (TC-6.3, TC-7.4)
10. **Documentation review**: Cross-check README (TC-12.*)

### Pass Criteria
- All TC-1.* through TC-10.* pass = **MVP complete**
- TC-11.* (load) passes = **production-ready**
- TC-12.* complete = **documentation complete**

---

## Coverage Summary

| Source | Test Cases |
|--------|-----------|
| `requirements.md` (system metrics) | TC-4.1 to TC-4.12 (12 sections, ~50 cases) |
| `requirements.md` (HTTP metrics) | TC-3.1 to TC-3.6 (6 sections, ~35 cases) |
| `requirements.md` (endpoints) | TC-2.1 to TC-2.6 (6 sections, ~25 cases) |
| `plan.md` (Prometheus) | TC-5.*, TC-6.* (~20 cases) |
| `plan.md` (Alertmanager) | TC-7.* (~15 cases) |
| `plan.md` (Grafana) | TC-8.* (~25 cases) |
| `plan.md` (Docker) | TC-9.* (~10 cases) |
| `plan.md` (E2E + Perf) | TC-10.*, TC-11.* (~15 cases) |
| **Total** | **~200 test cases across 12 phases** |
