#!/usr/bin/env bash
# Smoke test for the metrics stack. Assumes the stack is running on localhost.
#
# Exit codes:
#   0 — all checks passed
#   1 — a check failed (diagnostic dump is printed before exit)
#   7 — the app is unreachable on $BASE_URL (curl exit code, not a check failure)
#
# On any failure we dump:
#   - First 50 lines of /metrics (so the operator can see what's actually exposed)
#   - docker compose / docker-compose ps (which containers are up)
#   - Last 20 lines of the app container logs
#
# This makes the failure debuggable from a single command instead of forcing
# the operator to re-run multiple commands by hand.

set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"

# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------
dump_diagnostics() {
    local reason="$1"
    echo ""
    echo "=== DIAGNOSTIC DUMP (reason: ${reason}) ==="

    echo ""
    echo "--- /metrics (first 50 lines, response code ${metrics_http_code:-unknown}) ---"
    if [ -n "${METRICS:-}" ]; then
        echo "${METRICS}" | head -50
    else
        echo "(no metrics captured)"
    fi

    echo ""
    echo "--- container status ---"
    if command -v "${COMPOSE_CMD%% *}" >/dev/null 2>&1; then
        ${COMPOSE_CMD} ps 2>&1 || true
    elif command -v docker-compose >/dev/null 2>&1; then
        docker-compose ps 2>&1 || true
    else
        echo "(neither '${COMPOSE_CMD}' nor 'docker-compose' is available)"
    fi

    echo ""
    echo "--- last 20 lines of app logs ---"
    if command -v "${COMPOSE_CMD%% *}" >/dev/null 2>&1; then
        ${COMPOSE_CMD} logs --tail=20 app 2>&1 || true
    elif command -v docker-compose >/dev/null 2>&1; then
        docker-compose logs --tail=20 app 2>&1 || true
    fi

    echo ""
    echo "=== END DIAGNOSTIC DUMP ==="
}

# ---------------------------------------------------------------------------
# Step 1 — health check
# ---------------------------------------------------------------------------
echo "=== 1. Health check ==="
HEALTH=$(curl -sf "${BASE_URL}/health") || {
    echo "FAIL: could not reach ${BASE_URL}/health"
    dump_diagnostics "health endpoint unreachable"
    exit 1
}
echo "${HEALTH}" | grep -q '"status":"healthy"' || {
    echo "FAIL: /health response missing 'status:healthy'"
    echo "got: ${HEALTH}"
    dump_diagnostics "health body malformed"
    exit 1
}
echo "OK"

# ---------------------------------------------------------------------------
# Step 2 — POST /data
# ---------------------------------------------------------------------------
echo "=== 2. POST /data ==="
PAYLOAD='{"payload":{"smoke":"test"},"note":"smoke"}'
CREATE=$(curl -sf -X POST -H 'Content-Type: application/json' -d "${PAYLOAD}" "${BASE_URL}/data") || {
    echo "FAIL: POST /data returned non-2xx"
    dump_diagnostics "POST /data failed"
    exit 1
}
echo "${CREATE}" | grep -q '"id"' || {
    echo "FAIL: POST /data response missing 'id'"
    echo "got: ${CREATE}"
    dump_diagnostics "POST /data response malformed"
    exit 1
}
echo "OK"

# ---------------------------------------------------------------------------
# Step 3 — GET /data
# ---------------------------------------------------------------------------
echo "=== 3. GET /data ==="
LIST=$(curl -sf "${BASE_URL}/data") || {
    echo "FAIL: GET /data returned non-2xx"
    dump_diagnostics "GET /data failed"
    exit 1
}
echo "${LIST}" | grep -q '"smoke"' || {
    echo "FAIL: GET /data missing the smoke payload we just POSTed"
    echo "got: ${LIST}"
    dump_diagnostics "GET /data round-trip mismatch"
    exit 1
}
echo "OK"

# ---------------------------------------------------------------------------
# Step 4 — /metrics endpoint
#
# We make TWO attempts with a 2-second gap. This handles a benign race we
# have seen on slower machines: the HTTP middleware is registered at module
# import time, but on a very fresh container the first request that hits
# the Counter with labels can be processed before the asyncio scheduler
# has flushed the metric into the registry view used by generate_latest().
# A short retry absorbs that race without making the test flaky.
# ---------------------------------------------------------------------------
echo "=== 4. /metrics endpoint ==="

metrics_check() {
    # Fetch /metrics, capturing body and HTTP code separately.
    local body_file
    body_file=$(mktemp)
    local code
    code=$(curl -s -o "${body_file}" -w "%{http_code}" "${BASE_URL}/metrics") || {
        rm -f "${body_file}"
        echo "METRICS_FETCH_FAILED"
        return 1
    }
    METRICS=$(cat "${body_file}")
    metrics_http_code="${code}"
    rm -f "${body_file}"

    # Check the four required markers.
    local missing=()
    echo "${METRICS}" | grep -q '^# HELP' || missing+=("# HELP lines")
    echo "${METRICS}" | grep -q "http_requests_total" || missing+=("http_requests_total")
    echo "${METRICS}" | grep -q "process_cpu_seconds_total" || missing+=("process_cpu_seconds_total")
    echo "${METRICS}" | grep -q "process_resident_memory_bytes" || missing+=("process_resident_memory_bytes")

    if [ ${#missing[@]} -ne 0 ]; then
        echo "MISSING: ${missing[*]}"
        return 1
    fi
    return 0
}

if metrics_check; then
    echo "OK (first attempt)"
else
    echo "First attempt failed (http=${metrics_http_code:-?}, ${METRICS_FETCH_STATUS:-missing=$(echo "${METRICS:-}" | grep -E '^(# HELP|http_|process_)' | head -3 || true)})"
    echo "Retrying after 2 seconds..."
    sleep 2
    if metrics_check; then
        echo "OK (after retry)"
    else
        echo "FAIL: /metrics missing required metrics after retry"
        dump_diagnostics "metrics missing required series"
        exit 1
    fi
fi

echo ""
echo "=== SMOKE TEST PASSED ==="