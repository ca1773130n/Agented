"""v0.6.0: one-shot endpoint p50/p95 profiler.

Hits a running server N times per endpoint, captures Server-Timing
'app;dur' and total client-observed duration, aggregates min/p50/p95/max.

Usage:
  just profile                                     # localhost:20000, 50 reqs
  just profile -- --requests 200
  just profile -- --base http://staging:20000 --endpoints /admin/agents,/admin/products

Exit codes:
  0 — server reachable (per-endpoint failures don't abort)
  1 — server unreachable on the first probe
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Optional


_DEFAULT_ENDPOINTS = (
    "/health/liveness",
    "/health/readiness",
)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[idx]


def _request(url: str, *, timeout: float, headers: dict[str, str]) -> tuple[int, float, Optional[float]]:
    """Return (status, total_ms, server_app_ms or None)."""
    req = urllib.request.Request(url, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()  # drain
            total_ms = (time.monotonic() - started) * 1000.0
            st = resp.headers.get("Server-Timing", "")
            app_ms: Optional[float] = None
            for part in st.split(","):
                part = part.strip()
                if part.startswith("app;dur="):
                    try:
                        app_ms = float(part.split("=", 1)[1])
                    except ValueError:
                        pass
                    break
            return resp.status, total_ms, app_ms
    except urllib.error.HTTPError as exc:
        total_ms = (time.monotonic() - started) * 1000.0
        return exc.code, total_ms, None


def profile_endpoint(
    base: str, endpoint: str, *, n: int, timeout: float, headers: dict[str, str],
) -> dict:
    url = base.rstrip("/") + endpoint
    totals: list[float] = []
    apps: list[float] = []
    statuses: list[int] = []
    for _ in range(n):
        status, total_ms, app_ms = _request(url, timeout=timeout, headers=headers)
        totals.append(total_ms)
        if app_ms is not None:
            apps.append(app_ms)
        statuses.append(status)
    ok_count = sum(1 for s in statuses if 200 <= s < 400)
    return {
        "endpoint": endpoint,
        "n": n,
        "ok_count": ok_count,
        "client_total_ms": {
            "min": min(totals) if totals else 0.0,
            "p50": _percentile(totals, 50),
            "p95": _percentile(totals, 95),
            "max": max(totals) if totals else 0.0,
        },
        "server_app_ms": {
            "min": min(apps) if apps else None,
            "p50": _percentile(apps, 50) if apps else None,
            "p95": _percentile(apps, 95) if apps else None,
            "max": max(apps) if apps else None,
            "samples": len(apps),
        },
        "status_codes": dict.fromkeys(statuses, 0) | {s: statuses.count(s) for s in set(statuses)},
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile Agented endpoints.")
    parser.add_argument("--base", default=os.environ.get("AGENTED_BACKEND_URL", "http://127.0.0.1:20000"))
    parser.add_argument("--requests", "-n", type=int, default=50)
    parser.add_argument("--endpoints", default=",".join(_DEFAULT_ENDPOINTS))
    parser.add_argument("--api-key", default=os.environ.get("AGENTED_API_KEY"))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    headers: dict[str, str] = {}
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    endpoints = [e.strip() for e in args.endpoints.split(",") if e.strip()]

    # Probe once first — fail fast if server is unreachable.
    try:
        first = endpoints[0]
        _request(args.base.rstrip("/") + first, timeout=args.timeout, headers=headers)
    except urllib.error.URLError as exc:
        print(f"ERROR: server unreachable at {args.base}: {exc.reason}", file=sys.stderr)
        return 1

    summary = {
        "base": args.base,
        "requests_per_endpoint": args.requests,
        "endpoints": [],
    }
    for ep in endpoints:
        try:
            entry = profile_endpoint(
                args.base, ep, n=args.requests, timeout=args.timeout, headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            entry = {"endpoint": ep, "error": str(exc)}
        summary["endpoints"].append(entry)

    # Human-readable table on stderr.
    print(f"Profile: {args.base}  n={args.requests} per endpoint", file=sys.stderr)
    print(file=sys.stderr)
    print(f"  {'endpoint':<35}  {'p50_ms':>8}  {'p95_ms':>8}  {'app_p50':>8}", file=sys.stderr)
    for entry in summary["endpoints"]:
        if "error" in entry:
            print(f"  {entry['endpoint']:<35}  ERROR: {entry['error']}", file=sys.stderr)
            continue
        ct = entry["client_total_ms"]
        sa = entry["server_app_ms"]
        app_p50 = f"{sa['p50']:.1f}" if sa["p50"] is not None else "-"
        print(
            f"  {entry['endpoint']:<35}  {ct['p50']:>8.1f}  {ct['p95']:>8.1f}  {app_p50:>8}",
            file=sys.stderr,
        )
    print(file=sys.stderr)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
