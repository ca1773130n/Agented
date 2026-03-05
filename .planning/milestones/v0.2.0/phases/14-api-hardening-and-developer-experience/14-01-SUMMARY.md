---
phase: 14-api-hardening-and-developer-experience
plan: 01
subsystem: api-error-handling
tags: [error-response, request-id, rate-limiting, api-contract]
dependency_graph:
  requires: []
  provides: [unified-error-response, error-response-helper, retry-after-header]
  affects: [all-flask-error-handlers, frontend-api-client]
tech_stack:
  added: []
  patterns: [error_response-helper, backward-compat-dual-field]
key_files:
  created:
    - backend/tests/test_error_response.py
    - backend/tests/test_request_id.py
  modified:
    - backend/app/models/common.py
    - backend/app/__init__.py
    - frontend/src/services/api/client.ts
decisions:
  - "Keep legacy 'error' field alongside new 'code'/'message' for indefinite backward compatibility"
  - "Extract Retry-After from Flask-Limiter limit.get_expiry() since RateLimitExceeded does not set retry_after"
  - "429 handler returns explicit Response with Retry-After header (not plain tuple) to propagate header"
metrics:
  duration: 14min
  completed: 2026-03-06
---

# Phase 14 Plan 01: Unified Error Response & Request ID Propagation Summary

Unified all Flask error handlers to a consistent ErrorResponse shape with code/message/details/request_id fields, verified rate limit 429 responses include Retry-After header, and confirmed request ID propagation via X-Request-ID header on every response.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend ErrorResponse model and update all Flask error handlers | e57225c | backend/app/models/common.py, backend/app/__init__.py, frontend/src/services/api/client.ts, backend/tests/test_error_response.py |
| 2 | Verify rate limit 429 response and extend request ID to execution logs | a8b4772 | backend/app/__init__.py, backend/tests/test_request_id.py |

## Key Changes

### ErrorResponse Model (backend/app/models/common.py)
- Extended with `code` (machine-readable), `message` (human-readable), `details` (optional dict), `request_id` (trace ID)
- Legacy `error` field kept as Optional for backward compatibility
- New `error_response()` helper builds unified response tuples for Flask handlers
- Helper reads `g.request_id` from Flask context automatically

### Flask Error Handlers (backend/app/__init__.py)
- All 6 handlers (404, 405, 413, 429, 500, sqlite3.OperationalError) now use `error_response()`
- Machine-readable codes: NOT_FOUND, METHOD_NOT_ALLOWED, PAYLOAD_TOO_LARGE, RATE_LIMITED, INTERNAL_SERVER_ERROR, SERVICE_UNAVAILABLE
- 429 handler extracts Retry-After from Flask-Limiter's limit window via `limit.limit.get_expiry()`

### Frontend ApiError (frontend/src/services/api/client.ts)
- Error extraction updated to `data.message || data.error || 'HTTP ...'` for dual-format support

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Flask-Limiter RateLimitExceeded does not set retry_after**
- **Found during:** Task 2
- **Issue:** `werkzeug.exceptions.TooManyRequests.retry_after` is None by default; Flask-Limiter's `RateLimitExceeded` does not populate it
- **Fix:** Extract retry window from `e.limit.limit.get_expiry()` (the parsed rate limit's expiry in seconds) and set Retry-After header explicitly
- **Files modified:** backend/app/__init__.py
- **Commit:** a8b4772

## Verification

- 8 error response tests pass (helper shape, backward compat, Flask handlers)
- 7 request ID tests pass (header presence, client-supplied IDs, error body, 429 format, logs)
- Full backend suite: 1365 passed (1 pre-existing unrelated failure in test_post_execution_hooks)
- Frontend: 409 tests pass, build succeeds

## Self-Check: PASSED

All created files exist and all commits verified.
