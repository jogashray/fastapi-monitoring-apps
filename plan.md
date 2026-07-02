# FastAPI Metrics Monitoring System - Implementation Plan

## Project Overview
Build a production-ready FastAPI application with comprehensive Prometheus metrics monitoring covering system-level (CPU, memory, GC, FDs) and application-level (HTTP request patterns) metrics. Integrate **Grafana** for visualization and **Alertmanager + Prometheus alerting** for incident notification.

---

## Full Architecture

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
│  (dashboards,  │  │ (dedup, routing,│
│   also alerts) │  │  notifications) │
└────────────────┘  └──────┬──────────┘
                           │ Slack / Email / Webhook / PagerDuty
                     ┌─────▼──────┐
                     │ On-call /  │
                     │ Ops team   │
                     └────────────┘
```

---

## Directory Structure
```
fastapi-metrics-app/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI entry point
│   ├── config.py                        # Configuration management
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── registry.py                  # Custom Prometheus registry
│   │   ├── system_metrics.py            # CPU, memory, FD, GC, thread metrics
│   │   └── http_metrics.py              # HTTP request counters/histograms
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── metrics_middleware.py        # HTTP metrics collection middleware
│   ├── collectors/
│   │   ├── __init__.py
│   │   └── system_collector.py          # Background task for system metrics
│   └── routers/
│       ├── __init__.py
│       ├── api.py                       # Business endpoints (/data)
│       └── health.py                    # Health check endpoints (/health, /)
├── tests/
│   ├── __init__.py
│   ├── test_system_metrics.py
│   ├── test_http_metrics.py
│   └── test_endpoints.py
├── prometheus/
│   ├── prometheus.yml                   # Scrape configuration
│   └── alerts/                          # Alert rule files
│       ├── system_alerts.yml
│       └── http_alerts.yml
├── alertmanager/
│   └── alertmanager.yml                 # Routing & receivers
├── grafana/                             # Grafana configuration + dashboards
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── prometheus.yml           # Auto-provision Prometheus DS
│   │   └── dashboards/
│   │       └── dashboard.yml            # Auto-load dashboards
│   └── dashboards/
│       ├── fastapi-overview.json        # Main dashboard
│       └── system-health.json           # System metrics dashboard
├── docker-compose.yml                   # app + prometheus + grafana + alertmanager
├── Dockerfile                           # Container for FastAPI app
├── .dockerignore
├── .env.example                         # Example configuration
├── requirements.txt
└── README.md                            # Documentation
```

---

## Implementation Phases

### Phase 1: Project Setup & Dependencies
**File: `requirements.txt`**

Dependencies:
- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server with performance extras
- `prometheus-client` - Metrics collection library
- `psutil` - Cross-platform system resource monitoring
- `pydantic` & `pydantic-settings` - Configuration management
- `python-dotenv` - Environment variable loading
- `pytest`, `httpx`, `pytest-asyncio` - Testing

---

### Phase 2: Configuration Management
**File: `app/config.py`**

Implement `Settings` class using `pydantic-settings`:
- `APP_NAME` (default: "fastapi-metrics-app")
- `METRICS_ENDPOINT` (default: "/metrics")
- `SYSTEM_METRICS_INTERVAL` (default: 5 seconds)
- `HTTP_HISTOGRAM_BUCKETS` (default: `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]`)
- `REQUEST_SIZE_BUCKETS`, `RESPONSE_SIZE_BUCKETS`
- `ENABLE_DEFAULT_METRICS` (default: True)

---

### Phase 3: Metrics Module

#### 3.1 System Metrics — `app/metrics/system_metrics.py`
- `Counter` `process_cpu_seconds_total`
- `Gauge` `process_cpu_utilization_percent`
- `Gauge` `process_resident_memory_bytes`, `process_virtual_memory_bytes`, `process_memory_utilization_percent`
- `Gauge` `process_start_time_seconds`, `process_uptime_seconds`
- `Gauge` `process_open_fds`, `process_max_fds`
- `Gauge` `process_threads`, `process_num_cpu`
- GC metrics via custom collector

#### 3.2 HTTP Metrics — `app/metrics/http_metrics.py`
- `Counter` `http_requests_total` with labels `method`, `endpoint`, `status_code`
- `Histogram` `http_request_duration_seconds` (labels: `method`, `endpoint`, `status_code`)
- `Histogram` `http_request_size_bytes` (labels: `method`, `endpoint`)
- `Histogram` `http_response_size_bytes` (labels: `method`, `endpoint`)
- `Gauge` `http_requests_in_progress` (labels: `method`, `endpoint`)
- Helper functions: `record_request()`, `observe_duration()`, `observe_request_size()`, `observe_response_size()`

---

### Phase 4: Middleware
**File: `app/middleware/metrics_middleware.py`**

`BaseHTTPMiddleware` subclass `PrometheusMetricsMiddleware`:
1. Records `time.perf_counter()` at request start
2. Reads `Content-Length` for request size
3. Increments `http_requests_in_progress`
4. Awaits `call_next(request)`
5. Records status code, duration, response size
6. Increments `http_requests_total` with all labels
7. Decrements in-progress gauge
8. Uses route template (`request.scope["route"].path`) — falls back to a sanitized `unknown` bucket to prevent cardinality explosion
9. **Skips metric recording when `request.url.path == settings.METRICS_ENDPOINT`**
10. Exception handler ensures metrics still recorded on errors

---

### Phase 5: Background System Metrics Collector
**File: `app/collectors/system_collector.py`**

Async task running every `SYSTEM_METRICS_INTERVAL`:
- `psutil.Process(os.getpid())` for process-level stats
- Updates all gauges defined in Phase 3.1
- Started on FastAPI `startup`, cancelled on `shutdown`

---

### Phase 6: API Endpoints
**Files: `app/routers/health.py`, `app/routers/api.py`, `app/main.py`**

- `GET /` — basic app info
- `GET /health` — liveness probe (`{"status": "healthy"}`)
- `GET /health/ready` — readiness probe (checks dependencies)
- `GET /metrics` — Prometheus exposition with `Content-Type: text/plain; version=0.0.4`
- `POST /data` — accepts JSON, stores in memory
- `GET /data` — returns stored items (supports `limit`, `offset`)

---

### Phase 7: Prometheus Configuration

#### 7.1 `prometheus/prometheus.yml`
Configure scrape target `app:8000` every 5s with labels:
```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 5s  # how often alert rules are evaluated

rule_files:
  - "/etc/prometheus/alerts/*.yml"   # load all alert rule files

scrape_configs:
  - job_name: 'fastapi-app'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['app:8000']
        labels:
          service: 'fastapi-app'
          env: 'dev'
```

#### 7.2 `prometheus/alerts/system_alerts.yml`
Alert rules for system resources:
```yaml
groups:
  - name: system_alerts
    interval: 30s
    rules:
      - alert: HighCPUUsage
        expr: rate(process_cpu_seconds_total[5m]) > 0.8
        for: 2m
        labels:
          severity: warning
          category: system
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"
          description: "CPU rate is {{ $value }} cores (>0.8) for >2 minutes."

      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes > 500_000_000
        for: 2m
        labels:
          severity: warning
          category: system
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
          description: "RSS is {{ $value | humanize }}B (>500MB)."

      - alert: InstanceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
          category: availability
        annotations:
          summary: "Instance {{ $labels.instance }} is down"
          description: "Prometheus cannot scrape the target for >1 minute."

      - alert: FileDescriptorExhaustion
        expr: process_open_fds / process_max_fds > 0.8
        for: 5m
        labels:
          severity: warning
          category: system
```

#### 7.3 `prometheus/alerts/http_alerts.yml`
Alert rules for HTTP/application behavior:
```yaml
groups:
  - name: http_alerts
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status_code=~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m])) > 0.05
        for: 2m
        labels:
          severity: critical
          category: http
        annotations:
          summary: "Error rate >5% on {{ $labels.instance }}"
          description: "{{ $value | humanizePercentage }} of requests are 5xx."

      - alert: SlowRequests
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint)
          ) > 1
        for: 5m
        labels:
          severity: warning
          category: http
        annotations:
          summary: "p95 latency >1s on {{ $labels.endpoint }}"

      - alert: HighTrafficSpike
        expr: |
          sum(rate(http_requests_total[1m])) > 100
        for: 1m
        labels:
          severity: info
          category: http
```

---

### Phase 8: Alertmanager Configuration

#### 8.1 `alertmanager/alertmanager.yml`
```yaml
global:
  resolve_timeout: 5m

route:
  receiver: 'default-receiver'
  group_by: ['alertname', 'category']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity = "critical"
      receiver: 'critical-receiver'
      repeat_interval: 1h
    - matchers:
        - severity = "warning"
      receiver: 'warning-receiver'
      repeat_interval: 4h

receivers:
  - name: 'default-receiver'
    webhook_configs:
      - url: 'http://localhost:5001/alerts'   # log-only for dev

  - name: 'critical-receiver'
    # In production, swap to real integrations:
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/XXX/YYY/ZZZ'
        channel: '#ops-alerts'
        send_resolved: true
    email_configs:
      - to: 'oncall@example.com'

  - name: 'warning-receiver'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/XXX/YYY/ZZZ'
        channel: '#ops-warnings'
        send_resolved: true

inhibit_rules:
  - source_matchers:
      - severity = "critical"
    target_matchers:
      - severity = "warning"
    equal: ['category']
```

**Key features used:**
- **Deduplication** by alert fingerprint
- **Grouping** by `alertname` + `category`
- **Routing** by `severity` label → different receivers
- **Inhibition** — critical alerts silence related warnings
- **Multiple integrations** — Slack, Email, Webhook, PagerDuty, OpsGenie

---

### Phase 9: Grafana Integration

#### 9.1 Architecture in Docker Compose
Add `grafana` service to `docker-compose.yml`:
```yaml
grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_USER=admin
    - GF_SECURITY_ADMIN_PASSWORD=admin
    - GF_USERS_ALLOW_SIGN_UP=false
  volumes:
    - ./grafana/provisioning:/etc/grafana/provisioning:ro
    - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    - grafana_data:/var/lib/grafana
  depends_on:
    - prometheus
```

#### 9.2 `grafana/provisioning/datasources/prometheus.yml`
Auto-provisions Prometheus as the default datasource:
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
    jsonData:
      timeInterval: 5s
```

#### 9.3 `grafana/provisioning/dashboards/dashboard.yml`
Auto-loads dashboards from disk:
```yaml
apiVersion: 1
providers:
  - name: 'default'
    folder: 'FastAPI'
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

#### 9.4 `grafana/dashboards/fastapi-overview.json`
Main dashboard with panels:

**System Row:**
- **CPU rate** (time series): `rate(process_cpu_seconds_total[5m])`
- **Memory RSS** (time series): `process_resident_memory_bytes` with `humanize` unit
- **Virtual memory** (time series): `process_virtual_memory_bytes`
- **Open FDs / Max FDs** (gauge): `process_open_fds / process_max_fds * 100`
- **Threads** (stat): `process_threads`
- **Uptime** (stat): `time() - process_start_time_seconds`

**HTTP Volume Row:**
- **Request rate (total)** (time series): `sum(rate(http_requests_total[5m]))`
- **Request rate by endpoint** (time series): `sum by (endpoint) (rate(http_requests_total[5m]))`
- **Status code distribution** (pie chart): `sum by (status_code) (rate(http_requests_total[5m]))`
- **Top 5 endpoints by traffic** (bar gauge): `topk(5, sum by (endpoint) (rate(http_requests_total[5m])))`
- **In-flight requests** (stat): `sum(http_requests_in_progress)`

**HTTP Performance Row:**
- **p50 latency** (time series): `histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))`
- **p95 latency** (time series): `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))`
- **p99 latency** (time series): `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))`
- **Average duration by endpoint** (time series): `sum(rate(http_request_duration_seconds_sum[5m])) by (endpoint) / sum(rate(http_request_duration_seconds_count[5m])) by (endpoint)`
- **Error rate** (time series): `sum(rate(http_requests_total{status_code=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))`

**HTTP Size Row:**
- **Request size p95** (time series): `histogram_quantile(0.95, sum(rate(http_request_size_bytes_bucket[5m])) by (le, endpoint))`
- **Response size p95** (time series): `histogram_quantile(0.95, sum(rate(http_response_size_bytes_bucket[5m])) by (le, endpoint))`

**Template variables:**
- `$endpoint` (multi-select dropdown)
- `$method` (multi-select dropdown)
- `$status_code` (multi-select dropdown)

**Refresh interval:** 5s

#### 9.5 `grafana/dashboards/system-health.json`
Dedicated dashboard for system-level metrics + **firing alerts panel** (uses Grafana unified alerting).

#### 9.6 Optional: Grafana-side Alerts
Grafana can also manage alerts (alternative to Alertmanager). Enable unified alerting and create alert rules that query Prometheus — same PromQL expressions as Phase 7.2/7.3. We'll keep both paths (Alertmanager + Grafana alerts) since they coexist fine.

---

### Phase 10: Testing

**`tests/test_endpoints.py`:** Verify all routes return correct payloads and status codes.

**`tests/test_http_metrics.py`:** Send requests and verify `http_requests_total`, histograms, and in-progress gauge.

**`tests/test_system_metrics.py`:** Run collector once and assert gauges are numeric/positive.

Use `pytest` + `httpx.AsyncClient` + `pytest-asyncio`. Use isolated `CollectorRegistry` per test.

**Bonus (manual):** After `docker-compose up`:
- Open Prometheus at `:9090/alerts` — verify rules loaded
- Open Alertmanager at `:9093` — verify routing config
- Trigger a high-error condition → confirm alert reaches receiver (webhook logger)

---

### Phase 11: Documentation

**File: `README.md`** — sections:

1. **Overview** — purpose and features
2. **Architecture diagram** (text)
3. **Quick Start** — local dev and Docker
4. **Endpoints** — table
5. **Metrics Reference** — full list grouped by category
6. **Sample PromQL Queries** (CPU rate, p95 latency, error rate, memory growth)
7. **Grafana Setup** — access at `http://localhost:3000` (admin/admin), dashboard tour
8. **Alerting Setup** — what alerts exist, where they're routed, how to silence
9. **Docker Compose Deployment**
10. **Configuration** — env vars
11. **Troubleshooting** — common issues

---

## Requirement Coverage Matrix

| Requirement | Implementation |
|-------------|----------------|
| `process_cpu_seconds_total` Counter | `system_metrics.py` |
| CPU rate calculation `rate(...[5m])` | Documented & used in Grafana panels |
| CPU utilization % | `system_metrics.py` |
| `process_resident_memory_bytes` | `system_metrics.py` |
| `process_virtual_memory_bytes` | `system_metrics.py` |
| Memory usage alerts (mentioned in reqs) | `system_alerts.yml` |
| Process start time + uptime | `system_metrics.py` |
| File descriptor usage | `system_metrics.py` |
| GC statistics | `system_metrics.py` |
| Thread count | `system_metrics.py` |
| `http_requests_total` (method, endpoint, status_code) | `http_metrics.py` |
| Request rate & per-endpoint | Grafana panels |
| `http_request_duration_seconds` histogram | `http_metrics.py` |
| p95 latency query | Documented & Grafana panel |
| Request/response size histograms | `http_metrics.py` |
| FastAPI + Uvicorn + Python 3.8+ | `requirements.txt`, Dockerfile |
| Prometheus client | `requirements.txt` |
| psutil | `requirements.txt` |
| Custom middleware | `middleware/metrics_middleware.py` |
| asyncio | `collectors/system_collector.py` |
| Background collector | `collectors/system_collector.py` |
| `/metrics` with proper Content-Type | `main.py` |
| Default system metrics | `system_metrics.py` |
| Configurable intervals & buckets | `config.py` |
| Label standardization | `http_metrics.py` |
| Naming conventions | All metric files |
| `GET /` | `main.py` |
| `GET /health` | `health.py` |
| `POST /data` & `GET /data` | `api.py` |
| Metrics reference guide | `README.md` |
| Docker-compose deployment | `docker-compose.yml` |
| Configuration docs | `README.md` |
| **NEW** Grafana dashboards | `grafana/` |
| **NEW** Prometheus alerting | `prometheus/alerts/*.yml` |
| **NEW** Alertmanager routing | `alertmanager/alertmanager.yml` |
| **NEW** Multi-receiver notifications | Slack/Email/Webhook stubs |

---

## Verification Checklist

### Metrics & Endpoints
- [ ] All required metrics appear on `/metrics` endpoint
- [ ] HTTP metrics correctly labelled (no high-cardinality explosion — sanitized `unknown` bucket for unmatched paths)
- [ ] Background collector updates every interval
- [ ] `/metrics` returns correct `Content-Type`
- [ ] Sample PromQL queries yield sane values

### Grafana
- [ ] Grafana auto-loads dashboards on startup
- [ ] Prometheus datasource auto-provisioned
- [ ] All panels populate with live data
- [ ] Template variables work
- [ ] 5s refresh shows live updates

### Alerting
- [ ] Prometheus loads alert rules from `/etc/prometheus/alerts/*.yml`
- [ ] `/alerts` page shows all defined rules in `inactive` state initially
- [ ] Alertmanager reachable at `:9093`
- [ ] Webhook receiver logs incoming alerts (dev setup)
- [ ] Manually triggering HighErrorRate condition → alert fires → reaches receiver
- [ ] Critical severity routes to critical-receiver, warnings to warning-receiver
- [ ] Inhibition rule silences warnings when a critical alert is firing in the same category

### Container Stack
- [ ] `docker-compose up` brings up all 4 services (app, prometheus, grafana, alertmanager)
- [ ] Prometheus target `app:8000` shows `UP` at `:9090/targets`
- [ ] Grafana accessible at `:3000` (admin/admin)
- [ ] Alertmanager accessible at `:9093`

### Tests
- [ ] `pytest` passes
- [ ] Load test (manual) — k6/locust scenario sketched in README

---

## Service Port Map

| Service | Port | UI/Access |
|---------|------|-----------|
| FastAPI app | 8000 | `http://localhost:8000/metrics` |
| Prometheus | 9090 | `http://localhost:9090` (graphs, alerts, targets) |
| Alertmanager | 9093 | `http://localhost:9093` (silences, receivers) |
| Grafana | 3000 | `http://localhost:3000` (admin/admin) |

---

## Execution Order
1. Create `requirements.txt` + app skeleton
2. Implement `config.py`
3. Implement `system_metrics.py` & `http_metrics.py`
4. Implement `metrics_middleware.py`
5. Implement `system_collector.py`
6. Implement routers (`health.py`, `api.py`) and `main.py`
7. Write tests
8. Create `prometheus.yml` + alert rule files
9. Create `alertmanager.yml`
10. Create Grafana provisioning + dashboards
11. Create `docker-compose.yml` (4 services)
12. Write `README.md`
13. Run `docker-compose up` and verify each service
14. Trigger a synthetic error condition to validate alert pipeline

---

# ⚠️ Security Issues & Weaknesses — With Improvement Notes

This section catalogs honest security and design weaknesses identified in the current plan, along with concrete improvement actions. Items are prioritized from **🔴 Critical** to **🟢 Future** — implement at least the critical ones before delivery.

---

## 1. 🔴 Public `/metrics` Endpoint — Information Disclosure

**Issue:**  
The `/metrics` endpoint is exposed with no authentication. Anyone reaching the port can:
- Discover internal endpoint paths, traffic patterns, and response codes
- Enumerate application internals (route templates, label values)
- Detect version info from default Prometheus client output (`python_info`, `process_*`)
- Use it as a recon tool before launching an attack

**Improvement:**
- Add an optional `Bearer` token check in the metrics middleware (skip paths ≠ `/metrics`):
  ```python
  METRICS_BEARER_TOKEN=changeme-in-prod
  ```
- Mount `/metrics` on a separate port (`METRICS_PORT=9100`) accessible only on an internal Docker network — never published to the host.
- In `docker-compose.yml`, expose only port 8000 to the host; leave `:9100` on the internal `monitoring` network.
- For multi-host setups, restrict via firewall rules or service mesh policies.

---

## 2. 🔴 In-Memory `POST /data` Store — Memory Leak / DoS

**Issue:**  
`POST /data` appends to an unbounded Python list. After enough requests:
- RSS grows indefinitely → `HighMemoryUsage` alert would fire (correctly!) 
- Eventually OOM → process killed → InstanceDown

**Improvement:**
- Replace unbounded list with `collections.deque(maxlen=N)` or `cachetools.LRUCache(maxsize=1000)`.
- Expose `MAX_DATA_ITEMS` config (default 1000).
- Add a metric `data_store_items_current` (Gauge) to monitor store size and alert on it.
- Document explicitly in README: "This is a demo store; in production, use Redis/PostgreSQL."

---

## 3. 🔴 Hardcoded Secrets in `docker-compose.yml` & `alertmanager.yml`

**Issue:**  
`GF_SECURITY_ADMIN_PASSWORD=admin`, Slack webhook placeholders, and email recipients are written as plain literals. Real secrets committed to git = credential leak.

**Improvement:**
- Use `docker-compose` env interpolation with a `.env` file (gitignored):
  ```yaml
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
  ```
- For real deployments, use **Docker secrets** or **Kubernetes Secrets** mounted as files.
- Provide a `.env.example` with placeholder values; the real `.env` is gitignored.
- Add a pre-commit hook (`detect-secrets` or `gitleaks`) to block accidental commits.

---

## 4. 🔴 No `.gitignore` Defined — Risk of Committing Secrets/Caches

**Issue:**  
Plan doesn't specify what NOT to commit. Risk of pushing:
- `__pycache__/`, `.pytest_cache/`, `.env`, `.venv/`
- Compiled Python (`*.pyc`)
- IDE config (`.idea/`, `.vscode/`)
- Generated Prometheus data (if volumes are mapped)

**Improvement:**  
Add a `.gitignore` with at minimum:
```
__pycache__/
*.py[cod]
.env
.venv/
.pytest_cache/
.mypy_cache/
.idea/
.vscode/
*.log
data/
grafana_data/
```

---

## 5. 🟠 No Authentication on Admin Endpoints (`/health`, `/metrics`, `/`)

**Issue:**  
Health and root endpoints return service info freely. Combined with information disclosure, this aids attackers.

**Improvement:**
- For internal-only deployments, rely on network isolation (don't expose 8000 publicly).
- For internet-facing: add `fastapi-users` or simple API-key middleware.
- Differentiate public vs internal routes: keep `/` lightweight and unauthenticated; gate `/metrics` behind auth.

---

## 6. 🟠 CORS Not Configured

**Issue:**  
FastAPI's default CORS is restrictive — browsers from any non-same-origin domain cannot access the API. While this is a security *default*, if a frontend ever needs to call this, misconfiguration can accidentally allow everything (`allow_origins=["*"]`).

**Improvement:**
- Add `fastapi.middleware.cors.CORSMiddleware` with an explicit allowlist read from config:
  ```python
  CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
  ```
- Never use `allow_origins=["*"]` with `allow_credentials=True` — that's a known security flaw.
- Document the explicit allowlist pattern in README.

---

## 7. 🟠 No Rate Limiting — DoS Surface

**Issue:**  
A single client can hammer `/data`, `/metrics`, or any endpoint without restriction. Could:
- Inflate memory via the unbounded store (issue #2)
- Overload Prometheus scrapes
- Cause CPU spike

**Improvement:**
- Add `slowapi` (FastAPI rate-limiting library):
  ```python
  @limiter.limit("100/minute")
  async def post_data(...): ...
  ```
- Apply stricter limits on write endpoints vs reads.
- For `/metrics`, consider scrape-only access via IP allowlist.

---

## 8. 🟠 Missing Logging & Request Correlation

**Issue:**  
When something goes wrong in production, debugging requires correlating metrics, logs, and traces. The plan has metrics only — no structured logs and no request IDs.

**Improvement:**
- Add a `RequestIDMiddleware` that:
  1. Reads or generates a `X-Request-ID` UUID per request
  2. Stores it in `request.state.request_id`
  3. Adds it to all log records via a logging filter
  4. Returns it in response header
- Configure JSON-formatted logs (`python-json-logger`)
- Optionally add an `http_request_id` label to metrics for cross-referencing (watch cardinality)
- Document OpenTelemetry future integration

---

## 9. 🟠 No Dependency Pinning — Supply Chain Risk

**Issue:**  
`requirements.txt` likely contains unpinned versions like `fastapi>=0.100` or `prometheus-client`. This means:
- A malicious or buggy minor release could break production
- Reproducible builds are impossible
- CI vs prod behavior may diverge

**Improvement:**
- Use `requirements.in` (loose) + `pip-compile` (strict) workflow:
  ```
  pip-compile requirements.in
  pip-sync requirements.txt
  ```
- Or just pin everything in `requirements.txt` (e.g., `fastapi==0.115.0`)
- Commit a hash-pinned `requirements.txt` for reproducibility
- Optional: integrate `pip-audit` or `safety` to scan for known CVEs

---

## 10. 🟠 Health Checks Lack Detail — Wrong Signal Type

**Issue:**  
`/health` returns `{"status": "healthy"}` unconditionally. If the app is wedged (deadlocked, OOM-doomed), the probe may still pass — k8s won't restart it.

**Improvement:**
- **Liveness** (`/health/live`): "Am I running at all?" — return 200 unless the process is broken.
- **Readiness** (`/health/ready`): "Can I serve traffic?" — check critical dependencies (here: process responsive, metrics registered, etc.).
- For this app, liveness = always 200 unless the event loop is dead; readiness = collectors have run at least once.
- Document this distinction in README for k8s deployment.

---

## 11. 🟠 Unbounded Cardinality in `endpoint` Label — TSDB Outage Risk

**Issue:**  
Plan mitigates by sanitizing unmatched paths to `unknown`, but if a 404 handler is wrong, raw URLs could leak into labels. An attacker sending 1M unique paths → Prometheus memory exhaustion → **monitoring outage for ALL services**.

**Improvement:**
- Add a test (TC-3.6.4) that sends requests with random URLs and asserts no new label values are created.
- Whitelist allowed endpoints in middleware:
  ```python
  ALLOWED_ENDPOINTS = {"/", "/health", "/metrics", "/data"}
  endpoint = raw_path if raw_path in ALLOWED_ENDPOINTS else "unknown"
  ```
- Set Prometheus rule: alert on `count by (__name__)({__name__=~"http_.*"})` exceeding a threshold.

---

## 12. 🟠 No Centralized Error Tracking (Sentry)

**Issue:**  
Metrics show error *rates*, but not error *details*. Stack traces require log diving.

**Improvement:**
- Optional integration with **Sentry** via `sentry-sdk[fastapi]`:
  ```python
  sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"))
  ```
- Document as a future enhancement.
- Filters out the `/metrics` path to avoid noise.

---

## 13. 🟡 No Graceful Shutdown for In-Flight Requests

**Issue:**  
On `SIGTERM` (k8s pod termination), uvicorn may cut off active requests, losing their metric observations.

**Improvement:**
- Uvicorn handles this with `--timeout-graceful-shutdown` (default: no immediate kill).
- In docker-compose, use `stop_grace_period: 30s` and `stop_signal: SIGTERM`.
- Drain logic: stop accepting new requests, finish in-flight, then exit.

---

## 14. 🟡 Grafana Default Credentials

**Issue:**  
`admin/admin` is shipped in the docker-compose. Anyone reaching port 3000 gains full access (can edit dashboards, create datasources pointing anywhere).

**Improvement:**
- Require setting `GRAFANA_ADMIN_PASSWORD` via `.env` for any non-dev environment.
- Document the risk in README.
- For production, integrate with **OAuth/LDAP/SAML**.

---

## 15. 🟡 Prometheus & Alertmanager Have No Auth

**Issue:**  
`:9090` and `:9093` UIs are open. Attackers can:
- View all metrics (information disclosure)
- Silence alerts in Alertmanager → silently disable monitoring
- Modify Prometheus config if not read-only

**Improvement:**
- Enable `--web.enable-lifecycle` with care (do NOT enable `-web.enable-admin-api`)
- Bind Prometheus/Alertmanager to internal Docker network only (not host port).
- Document the secure topology in README.

---

## 16. 🟡 No Structured Audit Logging on Admin Actions

**Issue:**  
Alertmanager silences, Grafana dashboard edits, Prometheus rule changes — none are logged in a tamper-evident way.

**Improvement:**
- For production, enable audit logging on Grafana (`[audit] log_enabled = true`).
- Forward logs to a centralized system.
- Out of scope for this exam, document as future work.

---

## 17. 🟡 Single Prometheus = SPOF (Already Noted)

**Issue:**  
Already discussed: single Prometheus instance is a single point of failure for monitoring.

**Improvement:**
- Document recommended production stack: HA pair or Thanos.
- For exam: this is acceptable; flag explicitly in README.

---

## 18. 🟢 Tests Don't Cover Cardinality Regression / Security

**Issue:**  
`test_cases.md` has functional tests but no:
- "Send random URLs, assert no metric explosion"
- "Try to scrape `/metrics` without auth, assert blocked (if auth enabled)"
- "Verify alertmanager `/api/v1/silences` requires no auth but rate-limited"

**Improvement:**
- Add **TC-13 Cardinality & Security Tests** to `test_cases.md`:
  - Fuzz endpoint URLs with random UUIDs → assert `endpoint="unknown"` count grows but raw paths don't.
  - Verify Prometheus exposition format is strictly parseable (no malformed lines).
  - Auth-required tests if/when auth is added.

---

## Summary Table — Action Items

| # | Severity | Issue | Status | Implementation Phase |
|---|----------|-------|--------|---------------------|
| 1 | 🔴 | Public `/metrics` | Open | Add during Phase 6 (main.py) |
| 2 | 🔴 | Memory leak in `/data` | Open | Add during Phase 6 (api.py) |
| 3 | 🔴 | Hardcoded secrets | Open | Add during Phase 7 (docker-compose) |
| 4 | 🔴 | No `.gitignore` | Open | Phase 1 setup |
| 5 | 🟠 | No auth on admin endpoints | Open | Phase 6 (optional gate) |
| 6 | 🟠 | CORS not configured | Open | Phase 6 (main.py) |
| 7 | 🟠 | No rate limiting | Open | Phase 6 (optional middleware) |
| 8 | 🟠 | No logging / request IDs | Open | Add new phase (Pre-Phase 1) or fold into main.py |
| 9 | 🟠 | Unpinned deps | Open | Phase 1 (requirements.txt) |
| 10 | 🟠 | Weak health checks | Open | Phase 6 (health.py) |
| 11 | 🟠 | Cardinality risk | Open | Phase 4 (middleware) — already mitigated |
| 12 | 🟠 | No error tracking | Open | Document as future |
| 13 | 🟡 | No graceful shutdown | Open | Phase 7 (docker-compose) |
| 14 | 🟡 | Default Grafana creds | Open | Phase 9 (docker-compose) |
| 15 | 🟡 | Prom/AM have no auth | Open | Phase 7 (internal network) |
| 16 | 🟡 | No audit logging | Open | Document as future |
| 17 | 🟡 | Single Prometheus SPOF | Open | Document in README |
| 18 | 🟢 | Test coverage gaps | Open | Add to `test_cases.md` |

---

## Recommended Implementation Order (Security-First Slice)

To get a defensible MVP, implement these **first** before the main logic:

1. **Phase 0 — Security Baseline** (1-2 hours)
   - Write `.gitignore`
   - Write `.env.example` with placeholders
   - Pin dependencies
   - Plan CORS + auth + rate limiting in `config.py`
2. **Phase 0.5 — Operational Baseline** (30 min)
   - `RequestIDMiddleware` skeleton
   - Logging config
3. **Then proceed with Phases 1-11 as planned**

This order ensures security gaps are closed before any feature is built on top, avoiding costly retrofit.

