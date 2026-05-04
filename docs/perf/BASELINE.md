# Performance baseline (v0.6.0)

Captured 2026-05-05. Future passes (v0.6.0.x) re-measure and
record before/after deltas here.

## How to reproduce

```bash
just db-audit                    # static schema + EXPLAIN-QUERY-PLAN audit
just deploy-prod                 # start the stack on :20000 + :20001
just profile -- --requests 200   # client-side p50/p95 over 200 reqs
```

## DB index audit (v0.6.0)

After migration 111, every hot-path query hits an index:

| Query                           | Plan                                                                 |
|---|---|
| `sessions_lookup_by_token`      | SEARCH via `sqlite_autoindex_sessions_2` (token) + `idx_sessions_rotated_from_token` |
| `sessions_active_for_user`      | SEARCH via `idx_sessions_user_active` |
| `user_roles_by_api_key`         | SEARCH via `sqlite_autoindex_user_roles_2 (api_key=?)` |
| `session_events_by_session`     | SEARCH via `idx_session_events_session_id` |
| `session_events_by_user`        | SEARCH via `idx_session_events_user_id` |

`scan_only_count: 0` — no full table scans on hot paths.

## Frontend bundle (v0.6.0)

Post-`just build`, the chunks (top 10 by size):

| Chunk                                    | Size      | Gzip     |
|---|---|---|
| `vendor-core`                            | 2755 KB   | 421 KB   |
| `ai-accounts-vue-styled`                 | 1093 KB   | 348 KB   |
| `vendor-vue-flow`                        | 261 KB    | 87 KB    |
| `index`                                  | 260 KB    | 68 KB    |
| `vendor-chart`                           | 248 KB    | 79 KB    |
| `vendor-vue` (NEW v0.6.0 split)          | 82 KB     | 32 KB    |
| `ProjectDashboard`                       | 71 KB     | 18 KB    |
| `vendor-markdown`                        | 64 KB     | 21 KB    |
| `TokenUsageDashboard`                    | 60 KB     | 18 KB    |
| `TriggerManagement`                      | 60 KB     | 16 KB    |

Notes:
- `vendor-core` dropped from 2864 KB (v0.5.15) to 2755 KB after
  splitting out `vendor-vue` + `vendor-vue-router` + the
  `@ai-accounts/*` packages.
- `ai-accounts-vue-styled` is the second-largest chunk; it's a
  single sibling-repo package and would need upstream splitting
  to reduce. Deferred.
- The `>500KB` warning still fires on `vendor-core` and
  `ai-accounts-vue-styled`. Bigger wins require
  `rollup-plugin-visualizer` to identify the actual culprits in
  vendor-core and consider dynamic imports for routes — both
  deferred to v0.6.0.x.

## Server timings (placeholder)

`just profile` requires the server to be running. Operator records
results here after the first run:

```
Profile: http://127.0.0.1:20000  n=200 per endpoint

  endpoint                              p50_ms     p95_ms    app_p50
  /health/liveness                      ___        ___        ___
  /health/readiness                     ___        ___        ___
```

Re-run after each v0.6.0.x change and update.

## Known constraints

- Workers=1 mandated by in-memory state in
  `ExecutionLogService`, `ProcessManager`, `AgentMessageBusService`,
  `SchedulerService`, `MonitoringService`, and the
  `_FixedWindowLimiter`. Migrating to Redis is its own milestone
  (v0.6.x.y, not yet scoped — only do it if profiling shows we're
  CPU-bound on a single worker).
- Frontend chunk-splitting wins are bounded without dynamic imports
  for routes. Deferred to v0.6.0.x.

## Tooling shipped in v0.6.0

- `PerformanceMiddleware` — emits `Server-Timing: app;dur=…` on
  every response. Always-on, ~1ms overhead.
- `scripts/profile.py` — one-shot endpoint profiler. Aggregates
  client-observed and Server-Timing-reported latency.
- `scripts/db_audit.py` — schema + index audit + hot-query
  EXPLAIN-QUERY-PLAN inspector. Exit 1 if any hot query is
  SCAN-only.
- `just profile`, `just db-audit` recipes.

These tools enable subsequent v0.6.0.x passes to make targeted,
measurable improvements.
