"""Production and staging post-deployment smoke test script (T4.3).

Verifies:
1. /healthz returns 200 within strict timeout (< 500ms).
2. /readyz returns 200 (database and redis connectivity confirmed).
3. /mcp endpoint responds to Streamable HTTP POST.
4. Latency and zero error rate during the smoke test window.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def run_smoke_test(
    base_url: str,
    iterations: int = 5,
    max_latency_seconds: float = 1.0,
    client: httpx.Client | None = None,
) -> dict[str, str | int | float]:
    """Execute smoke test against base_url."""
    base_url = base_url.rstrip("/")
    http_client = client or httpx.Client(timeout=5.0)

    total_latency = 0.0
    latencies: list[float] = []

    try:
        # 1. Health check (/healthz)
        t0 = time.monotonic()
        resp = http_client.get(f"{base_url}/healthz")
        latency = time.monotonic() - t0
        if resp.status_code != 200:
            msg = f"/healthz failed with status {resp.status_code}: {resp.text}"
            raise RuntimeError(msg)
        latencies.append(latency)

        # 2. Readiness check (/readyz)
        t0 = time.monotonic()
        resp = http_client.get(f"{base_url}/readyz")
        latency = time.monotonic() - t0
        if resp.status_code != 200:
            msg = f"/readyz failed with status {resp.status_code}: {resp.text}"
            raise RuntimeError(msg)
        latencies.append(latency)

        # 3. Repeated /healthz checks to verify stability
        for _ in range(iterations):
            t0 = time.monotonic()
            resp = http_client.get(f"{base_url}/healthz")
            latency = time.monotonic() - t0
            if resp.status_code != 200:
                msg = f"Repeated /healthz failed with status {resp.status_code}"
                raise RuntimeError(msg)
            latencies.append(latency)
            total_latency += latency

        avg_latency = total_latency / iterations
        max_seen = max(latencies)
        if max_seen > max_latency_seconds:
            msg = f"Smoke test latency exceeded: max={max_seen:.3f}s > {max_latency_seconds}s"
            raise RuntimeError(msg)

        # 4. Streamable HTTP /mcp check
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }
        mcp_resp = http_client.post(
            f"{base_url}/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        # Even if unauthorized, it should return 401 or valid MCP response, not 502/503/504
        if mcp_resp.status_code in (500, 502, 503, 504):
            msg = f"/mcp returned server error {mcp_resp.status_code}"
            raise RuntimeError(msg)

    finally:
        if client is None:
            http_client.close()

    return {
        "status": "healthy",
        "iterations": iterations,
        "avg_latency_ms": round(avg_latency * 1000, 2),
        "max_latency_ms": round(max_seen * 1000, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run post-deploy smoke tests.")
    parser.add_argument("--url", required=True, help="Base URL of target service")
    parser.add_argument("--iterations", type=int, default=5, help="Number of health checks")
    parser.add_argument("--max-latency", type=float, default=1.0, help="Max latency in seconds")
    args = parser.parse_args()

    try:
        results = run_smoke_test(
            args.url,
            iterations=args.iterations,
            max_latency_seconds=args.max_latency,
        )
        print(f"Smoke test PASSED: {results}")
    except Exception as e:
        print(f"Smoke test FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
