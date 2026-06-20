"""v0.6.2: in-memory Prometheus-format metrics.

PerformanceMiddleware records each request; metrics route emits
the text exposition format. No external deps. workers=1 keeps
the in-process counters consistent.
"""

from __future__ import annotations

import threading
from collections import defaultdict

# Bucket upper-bound list shared by all histograms.
_HISTOGRAM_BUCKETS_MS: tuple[float, ...] = (10.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 5000.0)


class _Histogram:
    """Cumulative histogram with fixed bucket bounds. Thread-safe via
    a single lock — fine for workers=1 + occasional scrape."""

    def __init__(self, buckets: tuple[float, ...] = _HISTOGRAM_BUCKETS_MS) -> None:
        self._buckets = buckets
        self._counts: list[int] = [0] * (len(buckets) + 1)  # +1 for +Inf
        self._sum: float = 0.0
        self._total: int = 0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._sum += value
            self._total += 1
            for i, bound in enumerate(self._buckets):
                if value <= bound:
                    self._counts[i] += 1
            self._counts[-1] += 1  # +Inf bucket — always increments

    def snapshot(self) -> tuple[list[int], float, int, tuple[float, ...]]:
        with self._lock:
            return (list(self._counts), self._sum, self._total, self._buckets)


class _Registry:
    """Single in-process metric registry. PerformanceMiddleware writes;
    /admin/metrics reads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Counter: request count by (method, path_prefix, status)
        self._http_requests: dict[tuple[str, str, str], int] = defaultdict(int)
        # Counter: rate-limit denials by (path_prefix, key_kind)
        self._rate_limit_denied: dict[tuple[str, str], int] = defaultdict(int)
        # Histogram: request duration by (method, path_prefix)
        self._http_duration: dict[tuple[str, str], _Histogram] = {}

    @staticmethod
    def _path_prefix(path: str) -> str:
        """Bucket paths into a small set of prefixes so cardinality
        stays bounded."""
        if path.startswith("/api/auth/"):
            return "/api/auth"
        if path.startswith("/api/setup/"):
            return "/api/setup"
        if path.startswith("/api/webhooks/"):
            return "/api/webhooks"
        if path.startswith("/admin/auth/"):
            return "/admin/auth"
        if path.startswith("/admin/secrets"):
            return "/admin/secrets"
        if path.startswith("/admin/users") or path.startswith("/admin/rbac"):
            return "/admin/rbac"
        if path.startswith("/admin/agents"):
            return "/admin/agents"
        if path.startswith("/admin/projects"):
            return "/admin/projects"
        if path.startswith("/admin/triggers"):
            return "/admin/triggers"
        if path.startswith("/admin/"):
            return "/admin/other"
        if path.startswith("/api/"):
            return "/api/other"
        if path.startswith("/health"):
            return "/health"
        return "other"

    def record_request(self, method: str, path: str, status: int, duration_ms: float) -> None:
        prefix = self._path_prefix(path)
        with self._lock:
            self._http_requests[(method, prefix, str(status))] += 1
            hist = self._http_duration.setdefault((method, prefix), _Histogram())
        hist.observe(duration_ms)

    def record_rate_limit_denied(self, path: str, key_kind: str) -> None:
        prefix = self._path_prefix(path)
        with self._lock:
            self._rate_limit_denied[(prefix, key_kind)] += 1

    def render_text(self) -> str:
        """Prometheus text exposition format (version 0.0.4)."""
        lines: list[str] = []

        with self._lock:
            requests = dict(self._http_requests)
            denied = dict(self._rate_limit_denied)
            durations = dict(self._http_duration)

        # http_requests_total
        lines.append(
            "# HELP agented_http_requests_total Total HTTP requests by method, path prefix, and status."
        )
        lines.append("# TYPE agented_http_requests_total counter")
        for (method, prefix, status), n in sorted(requests.items()):
            lines.append(
                f'agented_http_requests_total{{method="{method}",path_prefix="{prefix}",status="{status}"}} {n}'
            )

        # rate_limit_denied_total
        lines.append(
            "# HELP agented_rate_limit_denied_total Rate-limit 429s by path prefix and key kind."
        )
        lines.append("# TYPE agented_rate_limit_denied_total counter")
        for (prefix, key_kind), n in sorted(denied.items()):
            lines.append(
                f'agented_rate_limit_denied_total{{path_prefix="{prefix}",key_kind="{key_kind}"}} {n}'
            )

        # http_request_duration_ms
        lines.append(
            "# HELP agented_http_request_duration_ms HTTP request handler duration in milliseconds."
        )
        lines.append("# TYPE agented_http_request_duration_ms histogram")
        for (method, prefix), hist in sorted(durations.items()):
            counts, total_sum, total_count, buckets = hist.snapshot()
            for i, bound in enumerate(buckets):
                lines.append(
                    f'agented_http_request_duration_ms_bucket{{method="{method}",path_prefix="{prefix}",le="{bound}"}} {counts[i]}'
                )
            lines.append(
                f'agented_http_request_duration_ms_bucket{{method="{method}",path_prefix="{prefix}",le="+Inf"}} {counts[-1]}'
            )
            lines.append(
                f'agented_http_request_duration_ms_sum{{method="{method}",path_prefix="{prefix}"}} {total_sum:.2f}'
            )
            lines.append(
                f'agented_http_request_duration_ms_count{{method="{method}",path_prefix="{prefix}"}} {total_count}'
            )

        # session_events_total — sourced from DB on demand for accuracy.
        try:
            from app.database import get_connection

            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT event_type, COUNT(*) FROM session_events GROUP BY event_type"
                ).fetchall()
            lines.append("# HELP agented_session_events_total Session lifecycle events by type.")
            lines.append("# TYPE agented_session_events_total counter")
            for event_type, n in rows:
                # Codex round-1 I1: Prometheus label-value escaping
                # requires `\` → `\\` BEFORE `"` → `\"` (otherwise an
                # event_type containing a backslash produces malformed
                # exposition that scrapers may reject).
                safe = (event_type or "unknown").replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'agented_session_events_total{{event_type="{safe}"}} {n}')
        except Exception:  # noqa: BLE001 — best-effort, never fail the scrape
            pass

        return "\n".join(lines) + "\n"

    def reset_for_test(self) -> None:
        with self._lock:
            self._http_requests.clear()
            self._rate_limit_denied.clear()
            self._http_duration.clear()


registry = _Registry()
