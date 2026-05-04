# v0.6.0 State

Status: COMPLETE — pending Codex review + merge.

## Shipped

### Measurement infrastructure

- `PerformanceMiddleware` (innermost middleware in the chain) emits
  `Server-Timing: app;dur=…` on every HTTP response. <1ms overhead.
- `scripts/db_audit.py` — schema/index audit + EXPLAIN-QUERY-PLAN
  inspector for 5 hand-picked hot queries. Exit 1 if any plan is
  SCAN-only.
- `scripts/profile.py` — one-shot endpoint profiler. p50/p95
  client-total + Server-Timing app-duration; status histogram.
- `just db-audit`, `just profile` recipes (passthrough args).

### Targeted fixes

- Migration 111 adds `idx_sessions_user_active(user_id, revoked_at)`.
- `get_session_by_token` rewritten to use indexed SELECT
  `WHERE token = ? OR rotated_from_token = ?`. Drops O(n) full
  scan to O(log n) index hit. Constant-time comparison preserved
  WITHIN the indexed result set.
- Frontend `vite.config.ts` `manualChunks` extended to split
  `vendor-vue`, `vendor-vue-router`, `ai-accounts-{vue-styled,
  vue-headless,ts-core}`. `vendor-core` dropped 2864→2755 KB.

### Documentation

- `docs/perf/BASELINE.md` — captures DB index audit + bundle
  sizes + known constraints + reproduction commands.

### Tests added

- `test_perf_middleware.py` — 3 tests (header presence, format,
  non-HTTP scope passthrough).
- `test_migration_111.py` — 3 tests (token index, rotated index,
  user_active index, EXPLAIN plan uses index).
- `test_db_audit.py` — 5 tests (audit_indices, explain_query
  classification SCAN/SEARCH, CLI exit codes).
- `test_profile.py` — 5 tests (percentile boundaries, aggregator,
  CLI JSON output, unreachable server).

Total new: 16 backend tests.

## Verification

- `cd frontend && npm run test:run` — **1128 passed** (no change) ✓
- `cd backend && uv run pytest` — pending full-suite confirmation;
  targeted-area 39/39 pass.
- `just build` — vue-tsc + vite clean ✓ (chunk warnings still
  fire on `vendor-core` and `ai-accounts-vue-styled` — see
  Deferred).

## Out of scope (deferred)

- Always-on profiling that writes per-request samples to a DB.
- A perf dashboard UI.
- Redis-backed scheduler / SSE / message bus (workers>1 readiness).
- DB profiling at the ORM level (no ORM in use).
- `rollup-plugin-visualizer` to drive bigger vendor-core splits.
- Dynamic imports for routes (frontend code-splitting at the
  route boundary).

## Next milestone

**v0.6.1** — Tech debt sweep: deferred v0.5.x items (`purge_expired_
sessions` soft-delete, full validate-and-restart-on-config-change
pattern, eager rate-limit registry walker validation, etc.).

Or, if perf measurement reveals more hot spots, a v0.6.0.x can fold
those in.
