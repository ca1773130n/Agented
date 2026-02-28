---
phase: 04-security-hardening
plan: 02
subsystem: security
tags: [rate-limiting, flask-limiter, health-redaction, owasp, sec-02, sec-03]

requires:
  - phase: 04-security-hardening
    plan: 01
    provides: Limiter instance on app.extensions["limiter"]
provides:
  - Per-blueprint rate limits on webhook (20/10s), GitHub webhook (30/min), and admin (120/min) routes
  - Health endpoint exempt from rate limiting
  - Readiness endpoint redaction for unauthenticated callers (SEC-03)
affects: [all downstream phases (rate limits active globally), frontend (no impact — 120/min is generous)]

tech-stack:
  added: []
  patterns: [blueprint-level rate limiting via limiter.limit()(bp) before registration, self-contained auth check in health module]

key-files:
  created: []
  modified:
    - backend/app/routes/__init__.py
    - backend/app/routes/health.py

key-decisions:
  - "Rate limits applied BEFORE blueprint registration per flask-limiter official pattern"
  - "Admin rate limit set to 120/minute to accommodate SPA page loads, AJAX, and SSE reconnects"
  - "Health endpoint uses self-contained auth check (not Phase 3 middleware) for independence"
  - "Unauthenticated readiness returns fixed 'ok' status (does not reveal actual component state)"
  - "hmac.compare_digest() used for timing-safe API key comparison"
  - "AGENTED_API_KEY not set => always redact readiness (safe default)"

duration: 9min
completed: 2026-02-28
---

# Phase 04 Plan 02: Per-Blueprint Rate Limits and Health Redaction Summary

**Applied per-blueprint rate limits to webhook, GitHub webhook, and admin routes with health exemption; redacted sensitive readiness endpoint fields for unauthenticated callers using timing-safe API key verification.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-28T01:34:22Z
- **Completed:** 2026-02-28T01:43:32Z
- **Tasks:** 2 completed
- **Files modified:** 2 (routes/__init__.py, routes/health.py)

## Accomplishments

- Webhook endpoint (`POST /`) rate-limited at 20 requests per 10 seconds per IP
- GitHub webhook endpoint (`/api/webhooks/github/`) rate-limited at 30 requests per minute per IP
- All 38 admin blueprints rate-limited at 120 requests per minute per IP
- Health blueprint exempt from rate limiting (probes must always respond)
- Docs endpoint inherently exempt (no explicit limit applied, `default_limits=[]`)
- `/health/readiness` returns minimal `{status, timestamp}` for unauthenticated callers
- `/health/readiness` returns full component health (database, process_manager, cli_proxy, startup) for authenticated callers
- Self-contained `_is_authenticated_request()` helper in health.py using `hmac.compare_digest()`
- `/health/liveness` unchanged (already minimal)
- All 911 backend tests pass with rate limits active
- All 344 frontend tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Apply blueprint-level rate limits and exemptions** - `a275c34` (feat)
2. **Task 2: Redact sensitive health readiness fields** - `7f4a2b6` (feat)

## Files Created/Modified

- `backend/app/routes/__init__.py` - Added rate limit application block (limiter.limit/exempt) before blueprint registration
- `backend/app/routes/health.py` - Added `_is_authenticated_request()` helper and conditional readiness response redaction

## Decisions Made

1. **Rate limits before registration** - Flask-limiter requires `limiter.limit()(bp)` to be called before `app.register_api(bp)`. Limits applied post-registration may silently fail to cover already-registered view functions. This follows the official flask-limiter documentation pattern.

2. **Admin rate limit at 120/minute** - A generous limit (2 requests/second) that accommodates normal SPA usage including page loads, AJAX calls, and SSE reconnects after brief network interruptions. Tighter limits (e.g., 10/minute) would break the frontend after brief disconnections (04-RESEARCH.md Pitfall 4).

3. **Self-contained auth in health.py** - The readiness endpoint uses its own `_is_authenticated_request()` rather than relying on Phase 3's `_require_api_key` middleware. This keeps health independent of the auth middleware chain (health is on the auth bypass allowlist) while using the same `AGENTED_API_KEY` env var and `X-API-Key` header for consistency.

4. **Fixed "ok" status for unauthenticated** - Unauthenticated readiness always returns `"status": "ok"` regardless of actual component health. This prevents information leakage about degraded components to external probers.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Frontend `vue-tsc` build fails in worktree due to a pre-existing `@vitejs/plugin-vue` type definition issue (line 120 of `index.d.mts`). This is a worktree environment issue, not caused by any code changes in this plan. The main repository builds successfully with identical frontend code. All 344 frontend tests pass. Backend-only changes in this plan are unaffected.

## User Setup Required

None - no external service configuration required. Rate limits and health redaction are automatically active.

## Next Phase Readiness

- SEC-02 (rate limiting) and SEC-03 (health redaction) are complete
- Phase 04 Security Hardening plans are all complete (01 + 02)
- All 911 backend tests pass with both security extensions and rate limits active
- Ready for Phase 04 evaluation (04-EVAL.md)

---
*Phase: 04-security-hardening*
*Completed: 2026-02-28*
