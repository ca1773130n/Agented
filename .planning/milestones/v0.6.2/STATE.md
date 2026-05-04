# v0.6.2 State

Status: COMPLETE — pending Codex review + merge.

## Shipped

### `app_litestar/metrics.py` (new)

Thread-safe in-memory metrics registry. PerformanceMiddleware writes;
`/admin/metrics` reads. Counters: HTTP requests by (method, path
prefix, status); rate-limit denials by (path prefix, key kind).
Histogram: HTTP duration by (method, path prefix), buckets
[10, 50, 100, 250, 500, 1000, 5000] ms. Session-event counts read
live from `session_events` table on each scrape.

### `app_litestar/routes/metrics.py` (new)

`GET /admin/metrics` — admin-only, Prometheus text format,
content-type `text/plain; version=0.0.4`.

### Middleware

- `PerformanceMiddleware` — extended to record request timings into
  the metrics registry post-response (in `finally` so error paths
  still count).
- `SlowRequestMiddleware` (new) — innermost-after-Performance.
  Logs WARN for any request exceeding `SLOW_REQUEST_THRESHOLD_MS`
  (default 500). Method, path, duration, threshold all in the log.

### Env var + .env.example + check_env

- `SLOW_REQUEST_THRESHOLD_MS` — default 500.

### Tests

- `test_metrics.py` — 8 tests (path-prefix bucketing, counter +
  histogram, rate-limit counter, render format, empty state,
  histogram cumulative buckets).
- `test_slow_request_middleware.py` — 3 tests (fast request no
  log, slow request logs, non-HTTP scope no-op).
- Total new: 11 backend tests.

## Verification

- Frontend 1128 ✓ (no change).
- Backend touched-area: 24/24 (metrics + slow + check_env + perf).
- Backend full suite: pending.

## Out of scope (deferred)

- Frontend session-events viewer page → v0.6.3 (UX polish, fits
  the milestone better).
- Grafana dashboard JSON exports — operator builds their own.
- OpenTelemetry traces — v0.5.10 traces feature exists; this
  milestone is metrics + log only.

## Next milestone

**v0.6.3** — UX polish (per autopilot directive).
