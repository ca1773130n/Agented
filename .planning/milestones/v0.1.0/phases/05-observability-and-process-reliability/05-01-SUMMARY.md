---
phase: 05-observability-and-process-reliability
plan: 01
subsystem: observability
tags: [structured-logging, json-logging, request-id, contextvars, python-json-logger, flask-middleware]

# Dependency graph
requires:
  - phase: 02-environment-and-wsgi-foundation
    provides: gunicorn.conf.py, run.py entry point, app factory
provides:
  - Structured JSON logging with per-request UUID correlation
  - Request ID middleware (X-Request-ID header on all responses)
  - LOG_FORMAT=json/text toggle via environment variable
  - Gunicorn access log disabled in favor of middleware-based JSON request log
affects: [05-02, 05-03, 06-code-quality-and-maintainability]

# Tech tracking
tech-stack:
  added: [python-json-logger>=3.2.0]
  patterns: [contextvars-based request ID propagation, handler-level logging filter, middleware-based request lifecycle logging]

key-files:
  created:
    - backend/app/logging_config.py
    - backend/app/middleware.py
    - backend/gunicorn.conf.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/app/__init__.py
    - backend/run.py

key-decisions:
  - "Filter attached to handler (not root logger) to ensure child logger events are captured"
  - "Gunicorn accesslog=None to prevent garbled mixed JSON/plaintext output"
  - "request_id_var cleared in teardown_request for greenlet context leakage defense"

patterns-established:
  - "ContextVar-based request context: use request_id_var from logging_config.py for per-request state"
  - "Handler-level filter: attach logging.Filter to handler, not logger, for propagation to child loggers"
  - "Middleware lifecycle: before_request sets context, after_request logs and sets header, teardown clears context"

# Metrics
duration: 9min
completed: 2026-02-28
---

# Phase 05 Plan 01: Structured JSON Logging Summary

**Structured JSON logging with per-request UUID correlation via python-json-logger and contextvars, emitting machine-parseable log lines with X-Request-ID traceability on every HTTP response.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-28T01:53:02Z
- **Completed:** 2026-02-28T02:02:38Z
- **Tasks:** 2/2 completed
- **Files modified:** 7

## Accomplishments

- Every application log line during an HTTP request is valid JSON with `request_id`, `timestamp`, `level`, `logger`, and `message` fields
- All log lines for a single request share the same UUID, returned to the client via `X-Request-ID` response header
- Background tasks (APScheduler jobs) log with `request_id: null`, preventing stale UUID leakage
- `LOG_FORMAT=text` env var reverts to human-readable plaintext format for local development
- Gunicorn access log disabled; request lifecycle is now logged by middleware in JSON format

## Task Commits

Each task was committed atomically:

1. **Task 1: Add python-json-logger dependency and create logging_config.py with RequestIdFilter** - `5bf443c` (feat)
2. **Task 2: Create request ID middleware and wire into run.py and gunicorn.conf.py** - `86aa02e` (feat)

## Files Created/Modified

- `backend/app/logging_config.py` - JSON logging configuration with RequestIdFilter and configure_logging()
- `backend/app/middleware.py` - Flask before/after/teardown hooks for request ID lifecycle and request logging
- `backend/gunicorn.conf.py` - Gunicorn config with accesslog disabled, gevent worker, workers=1
- `backend/pyproject.toml` - Added python-json-logger>=3.2.0 dependency
- `backend/uv.lock` - Updated lockfile with new dependency
- `backend/run.py` - Replaced logging.basicConfig with configure_logging()
- `backend/app/__init__.py` - Wired init_request_middleware(app) after blueprint registration

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Filter on handler, not root logger | Python logging filters on a logger only fire for events logged directly to that logger; child logger events propagate to parent handlers but skip parent-logger filters. Attaching the filter to the handler ensures ALL log records get request_id injected. |
| Gunicorn accesslog = None | Request lifecycle now logged by after_request middleware in JSON format. Keeping Gunicorn's native access log produces garbled mixed JSON/plaintext output (05-RESEARCH.md Pitfall 2). |
| request_id_var cleared in teardown_request | Defense-in-depth against greenlet context leakage. Even though contextvars should be per-greenlet, explicit cleanup prevents subtle bugs if the ContextVar is accidentally shared (05-RESEARCH.md Pitfall 1). |
| gunicorn.conf.py created in worktree | File was not present in worktree git history (added in Phase 2 on main). Created from scratch with all Phase 2 settings plus accesslog=None. |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RequestIdFilter attached to handler instead of root logger**
- **Found during:** Task 1 (logging_config.py creation)
- **Issue:** Plan specified attaching RequestIdFilter to the root logger. However, Python logging filters on a logger only fire for events logged directly to that logger -- events propagated from child loggers (e.g., `logging.getLogger("app.request")`) skip parent-logger filters entirely. This caused `request_id` to always be `null` in log output.
- **Fix:** Attached RequestIdFilter to the StreamHandler instead of the root logger. Handler-level filters fire for ALL records passing through the handler, including propagated events from child loggers.
- **Files modified:** `backend/app/logging_config.py`
- **Verification:** Tested with child logger `test.child` -- confirmed request_id correctly propagates from ContextVar.
- **Committed in:** `5bf443c` (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Minimal -- same module, same API surface, corrected filter attachment point.

## Issues Encountered

- **gunicorn.conf.py not in worktree git history:** The file was added in Phase 2 but is not committed to the worktree's branch (based on older main). Created from scratch using the main repo's version as reference, with `accesslog = None` applied.
- **Server startup latency during verification:** CLIProxyManager initialization takes several seconds, delaying the server readiness check. Used `--debug` mode for faster startup during functional verification.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Structured logging infrastructure is in place for Plans 02 (health probes) and 03 (process supervision)
- `request_id_var` ContextVar is available for any future middleware or service that needs request correlation
- `configure_logging()` is the single entry point for all logging configuration changes

---
*Phase: 05-observability-and-process-reliability*
*Completed: 2026-02-28*
