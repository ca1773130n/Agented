---
phase: 03-api-authentication
wave: "all"
plans_reviewed: ["03-01", "03-02"]
timestamp: 2026-02-28T12:00:00Z
blockers: 1
warnings: 3
info: 4
verdict: blocker_found
---

# Code Review: Phase 03 (API Authentication)

## Verdict: BLOCKERS FOUND

Phase 03 implementation is structurally sound and closely follows the research recommendations. The backend auth middleware and frontend SSE migration are complete with correct use of `hmac.compare_digest`, CORS fail-closed posture, and full `new EventSource` elimination. However, SUMMARY.md files are missing for both plans (a plan alignment blocker), and the backend middleware omits the `/admin` and `/api` prefix guard specified in the plan.

## Stage 1: Spec Compliance

### Plan Alignment

**Plan 03-01 (Backend Auth Middleware + CORS Lockdown)**

All plan tasks were executed and are present in commit `5356dae`:

- Task 1 (before_request auth middleware): Implemented correctly in `backend/app/__init__.py` lines 122-152. `hmac` imported at module level (line 4). `@app.before_request` decorator present inside `create_app()`. Bypass paths cover `/`, `/health`, `/docs`, `/openapi`, `/api/webhooks/github`. OPTIONS method bypassed. `hmac.compare_digest()` used for key comparison. Auth disabled when `AGENTED_API_KEY` is empty.
- Task 2, Part A (CORS lockdown): CORS fallback changed from `{"origins": "*"}` to `{"origins": []}` (line 79). `allow_headers=["Content-Type", "X-API-Key"]` added to `CORS()` call (line 88). Health and docs routes retain `{"origins": "*"}`.
- Task 2, Part B (.env.example): `AGENTED_API_KEY` documented in `backend/.env.example` (lines 14-18) with usage description.

**Plan 03-02 (Frontend Auth Header + SSE Migration)**

All plan tasks were executed and are present in commit `5356dae`:

- Task 1, Part A: `@microsoft/fetch-event-source` installed (`^2.0.1` in `frontend/package.json`).
- Task 1, Part B: `getApiKey()` function at line 17 of `client.ts`, reads from `localStorage.getItem('agented-api-key')` with `typeof window` guard. `apiFetchSingle()` injects `X-API-Key` header (line 68).
- Task 1, Part C: `createAuthenticatedEventSource()` implemented (lines 190-386). Uses `fetchEventSource` from `@microsoft/fetch-event-source`. Backpressure queue with rAF batching preserved. 401 throws `FatalSSEError` (no retry). `onmessage`/`onerror`/`onopen` property-assignment callbacks supported via getter/setter. `createBackoffEventSource` backward-compatible alias at line 389. `BackoffEventSource` and `BackoffEventSourceOptions` type aliases at lines 159, 168.
- Task 2: All 13 SSE consumer files migrated. Zero `new EventSource(` calls remain in `frontend/src/`. All 11 consumer type annotations updated from `EventSource` to `AuthenticatedEventSource`. `ConversationApi` interface in `useConversation.ts` updated (line 16).

| Finding | Severity | Detail |
|---------|----------|--------|
| F1 | **BLOCKER** | SUMMARY.md files missing for both plans. `03-01-SUMMARY.md` and `03-02-SUMMARY.md` do not exist in the phase directory. Both plans explicitly require these as output artifacts. Without them, deviation documentation and completion status cannot be verified against the workflow specification. |
| F2 | WARNING | Backend auth middleware omits the `/admin` and `/api` prefix guard. Plan 03-01 Task 1 step 5 specifies: "Only enforce auth on paths starting with `/admin` or `/api` -- all other paths (static files, SPA catch-all) pass through." The implementation at `backend/app/__init__.py` lines 128-152 enforces auth on ALL paths not in the bypass list. In practice all current routes start with `/admin/`, `/api/`, or `/health/`, so this causes no runtime bug, but it is stricter than specified and could break future non-API routes. |
| F3 | INFO | `.env.example` section heading differs from plan. Plan specifies a separate `# --- API Authentication ---` section; implementation places the entry under the existing `# --- Security ---` section. Functionally equivalent; documentation is present and clear. |
| F4 | INFO | `onopen` callback type is `(() => void) | null` instead of `((event: Event) => void) | null` as specified in the plan's interface. No consumer files use `onopen`, so this has no practical impact. |

### Research Methodology

Implementation faithfully follows 03-RESEARCH.md recommendations:

- **Recommendation 1 (Flask before_request):** Correctly implemented as centralized middleware, not per-route decorators. Path-based bypass allowlist matches the research pattern.
- **Recommendation 2 (@microsoft/fetch-event-source):** Used for all SSE connections. Native `EventSource` completely eliminated. Query-string tokens avoided (research anti-pattern).
- **Recommendation 4 (CORS fail-closed):** Implemented exactly as specified -- empty origins list when `CORS_ALLOWED_ORIGINS` unset.
- **Pitfall 1 (SSE breaks after auth):** Addressed -- SSE migration in same commit as auth middleware.
- **Pitfall 2 (trailing slash mismatch):** Addressed -- bypass check uses both exact match and prefix match with `/` separator (`request.path == prefix or request.path.startswith(prefix + "/")`).
- **Pitfall 3 (CORS preflight for X-API-Key):** Addressed -- `allow_headers=["Content-Type", "X-API-Key"]` in CORS config, OPTIONS requests bypass auth.
- **Pitfall 5 (fetchEventSource reconnection drops auth):** Partially addressed -- `getApiKey()` is called fresh on each `connect()` call (line 289), so reconnections pick up updated keys. This is better than the research's concern about captured headers.

| Finding | Severity | Detail |
|---------|----------|--------|
| F5 | INFO | Research Pitfall 5 is well-handled. The `connect()` function calls `getApiKey()` on each reconnection attempt (line 289), so key rotation during a session is supported without server restart. This exceeds the plan's specification. |

### Context Decision Compliance

No CONTEXT.md exists for this phase. N/A.

### Known Pitfalls (KNOWHOW.md)

KNOWHOW.md is empty (initialized but no entries). N/A.

### Eval Coverage

03-EVAL.md exists and defines comprehensive evaluation criteria (10 sanity checks, 4 proxy metrics, 3 deferred validations).

| Finding | Severity | Detail |
|---------|----------|--------|
| F6 | INFO | All eval metrics (S1-S10, P1-P4) can be computed against the current implementation. `grep "new EventSource"` for P1 returns zero matches. `X-API-Key` and `getApiKey` patterns exist in `client.ts` for P4. curl-based checks (S4-S10, P2-P3) target correct paths. No evaluation gap detected. |

## Stage 2: Code Quality

### Architecture

Implementation follows existing project patterns:

- `before_request` hook placed inside `create_app()` alongside CORS and Talisman setup -- consistent with the app factory pattern.
- `getApiKey()` exported from `client.ts` alongside `apiFetch` and SSE helpers -- consistent with the centralized API client pattern.
- All API service files import from `./client` -- consistent with existing barrel export pattern.
- `AuthenticatedEventSource` interface is minimal and matches the subset of `EventSource` properties actually used by consumers.
- Backward-compatible aliases (`createBackoffEventSource`, `BackoffEventSource`, `BackoffEventSourceOptions`) maintain API stability.

| Finding | Severity | Detail |
|---------|----------|--------|
| F7 | WARNING | `api_key` is captured once at `create_app()` scope (line 123), not read per-request from `os.environ`. This means changing `AGENTED_API_KEY` requires a server restart. While acceptable for v0.1.0 (single-user local tool), the plan step 6 says "Read AGENTED_API_KEY from `os.environ.get()`" which could be interpreted as per-request. The research (03-RESEARCH.md Pitfall 5) flags key rotation as a concern. Moving the `os.environ.get()` inside the `_require_api_key()` function body would allow key changes without restart. |

### Reproducibility

N/A -- no experimental code. This is infrastructure/middleware implementation.

### Documentation

- `client.ts` has JSDoc comments on `createAuthenticatedEventSource()`, `getApiKey()`, and `AuthenticatedEventSource` interface.
- Backend middleware has inline comments explaining bypass logic and backward compatibility.
- `.env.example` documents `AGENTED_API_KEY` with generation instructions.
- Research references are in 03-RESEARCH.md, not inline, which is appropriate for infrastructure code.

No findings.

### Deviation Documentation

| Finding | Severity | Detail |
|---------|----------|--------|
| F8 | WARNING | Cannot verify deviation documentation because SUMMARY.md files do not exist (see F1). The commit `5356dae` message summarizes changes at a high level but does not document deviations from the plan (e.g., the missing `/admin`/`/api` prefix guard, the `.env.example` section heading, the `onopen` type change). |

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| F1 | BLOCKER | 1 | Plan Alignment | `03-01-SUMMARY.md` and `03-02-SUMMARY.md` do not exist -- both plans specify these as required output artifacts |
| F2 | WARNING | 1 | Plan Alignment | Backend auth middleware omits the `/admin` and `/api` prefix guard from Plan 03-01 Task 1 step 5; enforces auth on all non-bypassed paths instead |
| F3 | INFO | 1 | Plan Alignment | `.env.example` uses existing `# --- Security ---` section instead of plan-specified `# --- API Authentication ---` section |
| F4 | INFO | 1 | Plan Alignment | `onopen` callback type is `() => void` instead of `(event: Event) => void` -- no consumers use this, no impact |
| F5 | INFO | 1 | Research | `getApiKey()` called on each reconnection -- exceeds research recommendation for key rotation support |
| F6 | INFO | 1 | Eval Coverage | All eval metrics computable against current implementation; no gaps |
| F7 | WARNING | 2 | Architecture | `api_key` captured at startup, not per-request -- key changes require server restart |
| F8 | WARNING | 2 | Deviation Docs | Cannot verify deviations because SUMMARY.md files are missing |

## Recommendations

**F1 (BLOCKER -- Missing SUMMARY.md):** Create `03-01-SUMMARY.md` and `03-02-SUMMARY.md` in the phase directory. Each should document: completed tasks, key files modified, commit references, any deviations from the plan (F2, F3, F4), and verification results.

**F2 (WARNING -- Missing prefix guard):** Add the explicit `/admin` and `/api` prefix check to the `_require_api_key()` function in `backend/app/__init__.py`. Insert before the key validation block:
```python
# Only protect /admin and /api routes
if not (request.path.startswith("/admin") or request.path.startswith("/api")):
    return None
```
This matches the plan specification and prevents accidental auth enforcement on future non-API routes.

**F7 (WARNING -- api_key at startup):** Move `os.environ.get("AGENTED_API_KEY", "")` inside the `_require_api_key()` function body so key changes take effect without restart. Alternatively, document this as a known limitation in the SUMMARY.md deviation section.

**F8 (WARNING -- Deviation docs):** Resolved by fixing F1. Ensure deviations F2, F3, and F4 are documented in the SUMMARY.md files.
