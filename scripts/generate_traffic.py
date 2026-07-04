#!/usr/bin/env python3
"""Synthetic-traffic generator for the FastAPI metrics stack.

Fires a configurable mix of requests against a running stack so the
Grafana dashboards have enough data points to populate latency
percentiles, status-code distributions, and request/response size
histograms.

Defaults to ~1500 requests — enough to fill Prometheus histograms with
realistic data without taking long enough to feel slow.

Usage:
    python scripts/generate_traffic.py
    python scripts/generate_traffic.py --count 2000
    python scripts/generate_traffic.py --base-url http://localhost:8000 --concurrency 8
    python scripts/generate_traffic.py --error-rate 0.05   # ~5% 4xx responses

What it generates:
    ~60%  GET  /health              (cheap, varied status from 200)
    ~25%  POST /data                (varied payload sizes 100 B to ~10 KB)
    ~10%  GET  /data                (lists, paginated)
    ~5%   GET  /data/count          (small, very fast)
    <error_rate>  invalid POSTs     (returns 422, populates 4xx series)
    <error_rate>  unknown routes    (returns 404, populates 404 series)

The middleware records every request, so all of the above become
data points in http_requests_total, http_request_duration_seconds,
http_request_size_bytes, and http_response_size_bytes.

Notes:
    - This is NOT a load test (no throughput / p99 SLO assertions).
      It is a data-source for the Grafana dashboards.
    - Uses httpx (already a dev dependency).
    - Designed to be safe to interrupt with Ctrl-C; uses a thread pool
      and prints partial progress.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Tuple

import httpx


# ---------------------------------------------------------------------------
# Payload generators
# ---------------------------------------------------------------------------
def random_payload(min_bytes: int = 100, max_bytes: int = 10_000) -> dict:
    """Build a JSON payload whose serialized size is in [min_bytes, max_bytes].

    The structure is `{"payload": {"k1": "...", ...}, "note": "..."}`. We
    fill the inner dict with random string values until the JSON hits the
    target size.
    """
    target = random.randint(min_bytes, max_bytes)
    payload: dict = {}
    note_chars: list[str] = []

    # Grow until we're at or above the target size.
    while True:
        key = "k" + "".join(random.choices(string.ascii_lowercase, k=4))
        value = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        payload[key] = value

        body = {"payload": payload, "note": "".join(note_chars)}
        encoded = json.dumps(body, separators=(",", ":"))
        if len(encoded) >= target:
            return body


def invalid_payload() -> dict:
    """Build a payload that the API will reject with 422.

    Pydantic v2 validates `note: Optional[str]`, so a non-string value
    triggers a validation error and the route returns 422.
    """
    return {"payload": {"x": 1}, "note": 12345}  # type: ignore[dict-item]


# ---------------------------------------------------------------------------
# Request builders — each returns (method, path, body_or_None, weight)
# ---------------------------------------------------------------------------
def build_request_plan(count: int, error_rate: float) -> list[Tuple[str, str, dict | None]]:
    """Generate a list of (method, path, body) tuples to fire.

    The distribution is tuned to populate the dashboards:
      - mostly cheap GETs (p50/p95/p99 visible)
      - meaningful POST traffic so request/response size histograms
        have non-zero buckets beyond the smallest
      - some 4xx traffic so the status_code label has multiple values
    """
    # Effective weights — adjust for error_rate by splitting each bucket.
    plan: list[Tuple[str, str, dict | None]] = []

    # Bucket counts. We split out errors as a separate category.
    n_get_health = int(count * 0.60)
    n_post_data = int(count * 0.25)
    n_get_data = int(count * 0.10)
    n_get_count = max(0, count - n_get_health - n_post_data - n_get_data)

    n_errors = int(count * error_rate)
    # Distribute errors: 70% invalid POSTs (422), 30% unknown routes (404).
    n_invalid_post = int(n_errors * 0.7)
    n_not_found = n_errors - n_invalid_post

    # Cheap GETs to /health.
    plan.extend([("GET", "/health", None)] * n_get_health)

    # POST /data with varied payload sizes.
    for _ in range(n_post_data):
        plan.append(("POST", "/data", random_payload()))

    # GET /data — occasionally with pagination params.
    for _ in range(n_get_data):
        if random.random() < 0.3:
            limit = random.choice([1, 5, 10, 25, 100])
            offset = random.randint(0, 50)
            plan.append(("GET", f"/data?limit={limit}&offset={offset}", None))
        else:
            plan.append(("GET", "/data", None))

    # GET /data/count.
    plan.extend([("GET", "/data/count", None)] * n_get_count)

    # Invalid POSTs — 422.
    for _ in range(n_invalid_post):
        plan.append(("POST", "/data", invalid_payload()))

    # Unknown routes — 404.
    for _ in range(n_not_found):
        bogus = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 12)))
        plan.append(("GET", f"/{bogus}", None))

    # Shuffle so the requests interleave in time (closer to real traffic).
    random.shuffle(plan)
    return plan


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
def fire_request(
    client: httpx.Client,
    method: str,
    path: str,
    body: dict | None,
    results: list,
    lock: threading.Lock,
) -> None:
    """Send a single request and record (status, latency_ms, body_size)."""
    start = time.perf_counter()
    try:
        if method == "POST":
            resp = client.post(path, json=body, timeout=10.0)
        else:
            resp = client.get(path, timeout=10.0)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        with lock:
            results.append((resp.status_code, elapsed_ms, len(resp.content)))
    except httpx.RequestError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        with lock:
            results.append(("ERR", elapsed_ms, 0))
        print(f"  network error: {exc.__class__.__name__}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(results: list, duration_s: float, count: int) -> None:
    """Print a summary table of what we sent and what came back."""
    if not results:
        print("No requests completed.")
        return

    statuses = Counter(r[0] for r in results)
    latencies = sorted(r[1] for r in results)
    body_sizes = sorted(r[2] for r in results)

    def pct(p: float, xs: list[float]) -> float:
        if not xs:
            return 0.0
        i = max(0, min(len(xs) - 1, int(len(xs) * p)))
        return xs[i]

    print()
    print("=" * 60)
    print(f"  Traffic generator — {count} requests, {duration_s:.1f}s")
    print(f"  Throughput: {count / duration_s:.1f} req/s")
    print("=" * 60)
    print()
    print("Status code distribution:")
    for code, n in sorted(statuses.items(), key=lambda x: -x[1]):
        pct_of_total = 100.0 * n / len(results)
        print(f"  {code!s:>6}  {n:>5}  ({pct_of_total:5.1f}%)")

    print()
    print("Latency (ms):")
    print(f"  min  {latencies[0]:7.1f}")
    print(f"  p50  {pct(0.50, latencies):7.1f}")
    print(f"  p90  {pct(0.90, latencies):7.1f}")
    print(f"  p95  {pct(0.95, latencies):7.1f}")
    print(f"  p99  {pct(0.99, latencies):7.1f}")
    print(f"  max  {latencies[-1]:7.1f}")

    if any(body_sizes):
        print()
        print("Response body size (bytes):")
        print(f"  min  {body_sizes[0]:7d}")
        print(f"  p50  {int(pct(0.50, body_sizes)):7d}")
        print(f"  p95  {int(pct(0.95, body_sizes)):7d}")
        print(f"  max  {body_sizes[-1]:7d}")

    print()
    print("Next steps:")
    print("  - Open http://localhost:3000/dashboards  (Grafana)")
    print("  - Wait ~10 s for Prometheus to scrape and Grafana to refresh")
    print("  - 'FastAPI Overview' should now show real distributions")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic traffic to populate Grafana dashboards.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the FastAPI app (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1500,
        help="Total number of requests to send (default: 1500)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of concurrent workers (default: 4)",
    )
    parser.add_argument(
        "--error-rate",
        type=float,
        default=0.05,
        help="Fraction of requests that should fail (0.0 to 1.0, default: 0.05)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible traffic (default: nondeterministic)",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.seed is not None:
        random.seed(args.seed)

    if not 0.0 <= args.error_rate <= 1.0:
        print("--error-rate must be in [0.0, 1.0]", file=sys.stderr)
        return 2

    if args.count <= 0:
        print("--count must be positive", file=sys.stderr)
        return 2

    # Sanity-check the app is reachable before we send 1500 requests into
    # the void. Use a short timeout so we fail fast.
    try:
        with httpx.Client(base_url=args.base_url, timeout=5.0) as probe:
            r = probe.get("/health")
            r.raise_for_status()
    except Exception as exc:
        print(f"Cannot reach {args.base_url}/health: {exc}", file=sys.stderr)
        print("Is the stack up? Try: docker compose up -d", file=sys.stderr)
        return 1

    print(f"Firing {args.count} requests at {args.base_url} "
          f"(concurrency={args.concurrency}, error_rate={args.error_rate:.0%})...")
    print("Press Ctrl-C to abort.")

    plan = build_request_plan(args.count, args.error_rate)
    results: list = []
    lock = threading.Lock()
    completed = 0
    start = time.perf_counter()
    last_print = start

    try:
        with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [
                    pool.submit(fire_request, client, method, path, body, results, lock)
                    for method, path, body in plan
                ]
                for fut in as_completed(futures):
                    completed += 1
                    now = time.perf_counter()
                    # Print a heartbeat at most every 0.5 s so we don't spam.
                    if now - last_print > 0.5 or completed == args.count:
                        print(f"  {completed}/{args.count} "
                              f"({100.0 * completed / args.count:5.1f}%)",
                              end="\r", flush=True)
                        last_print = now
                    fut.result()  # propagate exceptions
    except KeyboardInterrupt:
        print("\nAborted by user. Partial results follow.")
    finally:
        duration = time.perf_counter() - start

    print()  # newline after the \r progress line
    summarize(results, duration, args.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())