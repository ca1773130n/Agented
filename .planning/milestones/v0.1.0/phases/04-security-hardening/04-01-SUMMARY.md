---
phase: 04-security-hardening
plan: 01
subsystem: security
tags: [flask-talisman, flask-limiter, security-headers, csp, hsts, rate-limiting]

requires:
  - phase: 03-api-authentication
    provides: API key middleware in app factory
provides:
  - OWASP-aligned security headers on all HTTP responses (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
  - Limiter instance on app.extensions["limiter"] for blueprint-level rate limits
  - Custom JSON 429 error handler
affects: [04-02 (per-blueprint rate limits), all downstream plans (headers active globally)]

tech-stack:
  added: [flask-talisman 1.1.0, flask-limiter 4.1.1]
  patterns: [extension initialization in app factory after CORS, env-configurable security toggles]

key-files:
  created: []
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/app/__init__.py

key-decisions:
  - "HSTS header only sent over HTTPS/X-Forwarded-Proto (per RFC 6797, flask-talisman default behavior)"
  - "CSP allows 'unsafe-inline' for script-src and style-src to preserve Swagger UI functionality"
  - "force_https defaults to False via FORCE_HTTPS env var to prevent redirect loops in dev"
  - "In-memory limiter storage (memory://) safe for workers=1 Gunicorn deployment"
  - "No global rate limits — defaults to empty list; per-blueprint limits deferred to Plan 02"

patterns-established:
  - "Security extension initialization order: CORS -> Talisman -> Limiter -> auth middleware -> blueprints"
  - "Env-configurable security toggle pattern: os.environ.get('FLAG', 'false').lower() == 'true'"

duration: 5min
completed: 2026-02-27
---

# Phase 04 Plan 01: Security Extensions Summary

**Installed flask-talisman and flask-limiter, initialized OWASP-aligned security headers and rate limiter foundation in app factory with Swagger UI-compatible CSP and JSON 429 error handler.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T19:25:28Z
- **Completed:** 2026-02-27T19:30:24Z
- **Tasks:** 2 completed
- **Files modified:** 3 (pyproject.toml, uv.lock, app/__init__.py)

## Accomplishments
- All HTTP responses include Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, and Referrer-Policy headers
- Strict-Transport-Security header sent when behind HTTPS/reverse proxy (per RFC 6797)
- Limiter instance accessible via `app.extensions["limiter"]` for Plan 02 blueprint-level rate limits
- Custom JSON 429 error handler returns `{"error": "Rate limit exceeded: ..."}` format
- force_https defaults to False (env-configurable) to prevent dev redirect loops
- CSP permits inline scripts/styles for Swagger UI compatibility

## Task Commits

Each task was committed atomically:

1. **Task 1: Add flask-talisman and flask-limiter dependencies** - `f398da5` (chore)
2. **Task 2: Initialize Talisman, Limiter, and 429 handler in create_app()** - `fce21d6` (feat)

## Files Created/Modified
- `backend/pyproject.toml` - Added flask-talisman>=1.1.0 and flask-limiter>=3.0.0 dependencies
- `backend/uv.lock` - Updated with transitive deps (limits, deprecated, wrapt, ordered-set)
- `backend/app/__init__.py` - Talisman + Limiter initialization in create_app(), 429 JSON handler

## Decisions Made

1. **HSTS only over HTTPS** - flask-talisman correctly omits Strict-Transport-Security on plain HTTP per RFC 6797 section 7.2. In production behind a reverse proxy sending X-Forwarded-Proto: https, the header is sent correctly. This is the standard behavior and not a deviation.

2. **Extension placement** - Talisman and Limiter initialized outside the `if not testing:` block so security headers and rate limiting are active during tests too, matching how CORS is currently initialized.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Limiter is ready for Plan 02 to apply per-blueprint rate limits via `app.extensions["limiter"]`
- All 911 backend tests pass with security extensions active
- Frontend build (vue-tsc + vite) succeeds

---
*Phase: 04-security-hardening*
*Completed: 2026-02-27*
