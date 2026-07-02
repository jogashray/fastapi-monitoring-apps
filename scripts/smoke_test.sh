#!/usr/bin/env bash
# Smoke test for the metrics stack. Assumes the stack is running on localhost.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== 1. Health check ==="
HEALTH=$(curl -sf "${BASE_URL}/health")
echo "${HEALTH}" | grep -q '"status":"healthy"' || { echo "health check failed"; exit 1; }
echo "OK"

echo "=== 2. POST /data ==="
PAYLOAD='{"payload":{"smoke":"test"},"note":"smoke"}'
CREATE=$(curl -sf -X POST -H 'Content-Type: application/json' -d "${PAYLOAD}" "${BASE_URL}/data")
echo "${CREATE}" | grep -q '"id"' || { echo "POST /data failed"; exit 1; }
echo "OK"

echo "=== 3. GET /data ==="
LIST=$(curl -sf "${BASE_URL}/data")
echo "${LIST}" | grep -q '"smoke"' || { echo "GET /data missing payload"; exit 1; }
echo "OK"

echo "=== 4. /metrics endpoint ==="
METRICS=$(curl -sf "${BASE_URL}/metrics")
echo "${METRICS}" | grep -q '^# HELP' || { echo "missing HELP lines"; exit 1; }
echo "${METRICS}" | grep -q "http_requests_total" || { echo "missing http_requests_total"; exit 1; }
echo "${METRICS}" | grep -q "process_cpu_seconds_total" || { echo "missing process_cpu_seconds_total"; exit 1; }
echo "${METRICS}" | grep -q "process_resident_memory_bytes" || { echo "missing process_resident_memory_bytes"; exit 1; }
echo "OK"

echo ""
echo "=== SMOKE TEST PASSED ==="