---
phase: 03-api-authentication
plan: 01
subsystem: authentication
tags: [api-key, before-request, hmac, cors, middleware, flask]

requires: []
provides:
  - before_request API key authentication middleware in app factory
  - CORS fail-closed configuration (empty origins list blocks all cross-origin)
  - X-API-Key in CORS allow_headers for preflight support
  - AGENTED_API_KEY documented in .env.example
affects: [03-02 (frontend SSE auth integration), 04-01 (security headers build on auth middleware)]

tech-stack:
  added: []
  patterns: [before_request middleware for auth, hmac.compare_digest for constant-time key comparison, env-var-gated auth toggle]

key-files:
  created: []
  modified:
    - backend/app/__init__.py
    - backend/.env.example

key-decisions:
  - "Auth disabled when AGENTED_API_KEY env var is unset for backward compatibility"
  - "API key read per-request (inside before_request) so changes take effect without server restart"
  - "CORS fallback is empty origins list (fail-closed) not wildcard (fail-open)"
  - "Bypass allowlist uses prefix matching with explicit trailing-slash handling for security"
  - "Only /admin and /api routes require auth -- static files and SPA catch-all pass through"

patterns-established:
  - "before_request auth pattern: check env var -> bypass OPTIONS -> bypass prefix list -> enforce on /admin|/api -> hmac.compare_digest"
  - "Public endpoint bypass via _AUTH_BYPASS_PREFIXES tuple with exact and prefix matching"

duration: 3min
completed: 2026-03-04
---

# Phase 03 Plan 01: API Key Authentication Middleware and CORS Lockdown Summary

**Added before_request API key middleware with hmac.compare_digest validation, OPTIONS and path-based bypass allowlist, and CORS fail-closed configuration rejecting all cross-origin requests when CORS_ALLOWED_ORIGINS is unset.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T17:37:27Z
- **Completed:** 2026-03-03T17:40:00Z
- **Tasks:** 2 completed
- **Files modified:** 2 (app/__init__.py, .env.example)

## Accomplishments

- All /admin/* and /api/* routes require X-API-Key header when AGENTED_API_KEY is set
- Auth disabled by default when AGENTED_API_KEY env var is unset (backward compatible)
- OPTIONS requests always bypass auth (CORS preflight never blocked)
- Bypass allowlist covers /health/*, /docs/*, /openapi/*, /api/webhooks/github/*
- hmac.compare_digest used for constant-time key comparison (timing attack prevention)
- CORS fallback changed from wildcard ("*") to empty list ([]) -- fail-closed posture
- X-API-Key added to CORS allow_headers so browsers permit the custom header
- .env.example documents AGENTED_API_KEY with generation instructions
- All 911 backend tests pass with auth disabled by default

## Task Commits

Each task was committed atomically:

1. **Task 1: Add before_request API key authentication middleware** - `5356dae` (feat)
2. **Task 2: CORS fail-closed configuration and env documentation** - `5356dae` (feat, combined commit)

Follow-up fix from code review:
- **F2/F7: Add /admin|/api prefix guard, move env read inside function** - `e2b1f87` (fix)

## Files Created/Modified

- `backend/app/__init__.py` - Added _AUTH_BYPASS_PREFIXES tuple, @app.before_request _require_api_key hook with hmac.compare_digest, CORS origins=[] fallback, allow_headers with X-API-Key
- `backend/.env.example` - Added AGENTED_API_KEY documentation section with generation command

## Decisions Made

1. **Auth disabled when unset** - When AGENTED_API_KEY env var is empty or missing, all routes remain accessible without authentication. This preserves backward compatibility for existing deployments.

2. **Per-request env read** - The API key is read from os.environ inside the before_request handler (not at module load time) so operators can rotate keys without restarting the server.

3. **Fail-closed CORS** - Changed the CORS fallback from `{"origins": "*"}` to `{"origins": []}`. When CORS_ALLOWED_ORIGINS is unset, no cross-origin requests are permitted. Health and docs endpoints retain wildcard CORS for monitoring and Swagger UI access.

4. **Prefix-based bypass** - The _AUTH_BYPASS_PREFIXES tuple uses both exact match and startswith(prefix + "/") to correctly handle paths with and without trailing slashes.

## Deviations from Plan

None - plan executed exactly as written. Code review findings (F2: prefix guard, F7: per-request env read) were addressed in follow-up commit e2b1f87.

## Issues Encountered

None.

## User Setup Required

To enable API key authentication:
```bash
# Generate a key
python -c 'import secrets; print(secrets.token_hex(32))'

# Add to backend/.env
AGENTED_API_KEY=<generated-key>
```

All requests to /admin/* and /api/* must then include `X-API-Key: <key>` header.

## Next Phase Readiness

- Auth middleware is ready for Plan 02 to integrate frontend X-API-Key header injection
- CORS allow_headers includes X-API-Key for browser preflight support
- All 911 backend tests pass with auth middleware active (disabled by default)

## Self-Check: PASSED

- [x] `backend/app/__init__.py` contains @app.before_request with _require_api_key
- [x] hmac.compare_digest used (not ==)
- [x] CORS fallback is {"origins": []} not {"origins": "*"}
- [x] X-API-Key in allow_headers
- [x] OPTIONS bypass present
- [x] .env.example documents AGENTED_API_KEY
- [x] Bypass paths cover /health, /docs, /openapi, /api/webhooks/github
- [x] All 911 backend tests pass

---
*Phase: 03-api-authentication*
*Completed: 2026-03-04*
