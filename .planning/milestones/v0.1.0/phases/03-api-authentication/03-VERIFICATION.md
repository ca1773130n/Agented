---
phase: 03-api-authentication
verified: 2026-02-28T09:43:28Z
status: passed
score:
  level_1: 10/10 sanity checks passed
  level_2: 4/4 proxy metrics met
  level_3: 3 items deferred (tracked below)
re_verification:
  previous_status: ~
  previous_score: ~
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
deferred_validations:
  - id: DEFER-03-01
    description: "SSE event delivery across all 20+ endpoints with X-API-Key header confirmed in browser DevTools"
    metric: "SSE event delivery + header presence"
    target: "All SSE endpoints deliver events; X-API-Key visible in every SSE request"
    depends_on: "Running full stack (backend + frontend) with AGENTED_API_KEY set and localStorage key configured"
    tracked_in: "This VERIFICATION.md (Level 3 section)"
  - id: DEFER-03-02
    description: "Webhook receiver bypass with realistic GitHub payloads + signature validation still enforced"
    metric: "POST /api/webhooks/github/ with valid signature returns non-401; invalid signature returns 401/400"
    target: "Bypass correct + signature validation preserved"
    depends_on: "WEBHOOK_SECRET configured + realistic GitHub payload"
    tracked_in: "This VERIFICATION.md (Level 3 section)"
  - id: DEFER-03-03
    description: "CORS enforcement in a real browser session for allowed vs. unlisted origins"
    metric: "Browser DevTools: ACAO present for localhost:3000, absent for other origins"
    target: "Allowed origin succeeds; any other origin gets CORS error in browser"
    depends_on: "Frontend running at localhost:3000 with CORS_ALLOWED_ORIGINS set"
    tracked_in: "This VERIFICATION.md (Level 3 section)"
human_verification:
  - test: "Open browser DevTools Network tab, trigger an execution log stream, confirm X-API-Key header is present on the EventSource SSE request"
    expected: "Request headers for the SSE stream include X-API-Key with the value from localStorage"
    why_human: "Browser-side SSE header inspection requires DevTools; cannot be confirmed programmatically without E2E test harness"
  - test: "Send a realistic GitHub webhook (with X-Hub-Signature-256 header) to POST /api/webhooks/github/ without X-API-Key — confirm 200/204 response; then send same payload with invalid signature — confirm 400/401"
    expected: "Valid signature succeeds (bypass works); invalid signature fails (signature validation preserved)"
    why_human: "Requires real GITHUB_WEBHOOK_SECRET + correctly computed HMAC payload"
---

# Phase 03: API Authentication Verification Report

**Phase Goal:** Every admin and API route requires a valid API key; SSE streaming endpoints authenticate without requiring custom headers; CORS rejects all cross-origin requests unless the origin is explicitly listed.

**Verified:** 2026-02-28T09:43:28Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Verification Summary by Tier

### Level 1: Sanity Checks

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| S1 | Backend pytest (911 tests, auth disabled by default) | PASS | `911 passed in 102.56s` — all tests pass with no AGENTED_API_KEY set |
| S2 | Frontend test:run (344 tests) | PASS | `344 passed` in 1.81s — no regressions from fetchEventSource or apiFetch changes |
| S3 | Frontend TypeScript build (vue-tsc + vite) | PASS | `built in 3.22s` — zero type errors, all 11 consumer type annotations correct |
| S4 | Protected route rejects unauthenticated request (HTTP 401) | PASS | `GET /admin/triggers` without key → `401` |
| S5 | Protected route accepts authenticated request (HTTP 200) | PASS | `GET /admin/triggers` with `X-API-Key: test-key-123` → `200` |
| S6 | Wrong key is rejected (HTTP 401) | PASS | `GET /admin/triggers` with `X-API-Key: wrong` → `401` |
| S7 | Health probe bypasses authentication | PASS | `GET /health/liveness` without key → `200` |
| S8 | Docs endpoint bypasses authentication | PASS | `GET /docs/` without key → `200` |
| S9 | OPTIONS preflight requests bypass authentication | PASS | `OPTIONS /admin/triggers` with `Origin: localhost:3000` → `200` |
| S10 | X-API-Key listed in CORS Access-Control-Allow-Headers | PASS | With `CORS_ALLOWED_ORIGINS=http://localhost:3000`: `Access-Control-Allow-Headers: Content-Type, X-API-Key` |

**Level 1 Score:** 10/10 passed

**Note on S10:** Without `CORS_ALLOWED_ORIGINS` set, an unlisted origin receives no CORS headers at all — this is correct fail-closed behavior. S10 requires CORS configured for the test origin to receive any CORS headers, which is the expected operational state.

---

### Level 2: Proxy Metrics

| # | Metric | Target | Achieved | Status |
|---|--------|--------|----------|--------|
| P1 | Zero native `new EventSource(` calls in frontend/src/ | 0 matches | 0 matches (grep returns empty) | PASS |
| P2 | No ACAO header for unlisted origin (https://evil.example.com) | No header | No `Access-Control-Allow-Origin` header present | PASS |
| P3 | curl auth script: 5/5 checks pass | 5/5 | 5/5: no-key=401, valid-key=200, wrong-key=401, health=200, docs=200 | PASS |
| P4 | apiFetch() sends X-API-Key header (static code inspection) | Pattern found | `getApiKey()` at line 17 reads `localStorage.getItem('agented-api-key')`; `X-API-Key` injected at line 68 in `apiFetchSingle()`; also injected at line 291 in `createAuthenticatedEventSource()` | PASS |

**Level 2 Score:** 4/4 met target

---

### Level 3: Deferred Validations

| # | Validation | Metric | Target | Depends On | Status |
|---|-----------|--------|--------|------------|--------|
| DEFER-03-01 | SSE event delivery across all 20+ endpoints + browser DevTools X-API-Key header | Event delivery + header presence | All SSE endpoints deliver events; X-API-Key visible in every SSE request | Full stack + AGENTED_API_KEY + localStorage | DEFERRED |
| DEFER-03-02 | Webhook bypass under realistic GitHub payload + signature validation preserved | HTTP response code | Valid signature non-401; invalid signature 400/401 | GITHUB_WEBHOOK_SECRET + real payload | DEFERRED |
| DEFER-03-03 | CORS enforcement in real browser session | ACAO header present/absent per origin | localhost:3000 succeeds; other origins blocked | Browser DevTools + CORS_ALLOWED_ORIGINS set | DEFERRED |

**Level 3:** 3 items deferred

---

## Goal Achievement

### Observable Truths

| # | Truth | Verification Level | Status | Evidence |
|---|-------|--------------------|--------|----------|
| 1 | /admin/* and /api/* without X-API-Key return HTTP 401 when AGENTED_API_KEY is set | Level 1 (S4, S6) | PASS | curl to /admin/triggers: no-key → 401, wrong-key → 401 |
| 2 | /admin/* and /api/* with valid X-API-Key return HTTP 200 | Level 1 (S5) | PASS | curl with valid key → 200 |
| 3 | Bypass routes (/, /api/webhooks/github/, /health/*, /docs/*, /openapi/*) respond without API key enforcement | Level 1 (S7, S8) + confirmed via test client | PASS | Health → 200, docs → 200; webhook bypass confirmed: /api/webhooks/github/ returns `{"error": "Invalid signature"}` not `{"error": "Unauthorized"}` — auth middleware is bypassed, route's own signature validation runs |
| 4 | OPTIONS preflight requests bypass auth | Level 1 (S9) | PASS | OPTIONS with Origin header → 200, no 401 |
| 5 | When AGENTED_API_KEY is not set, all routes remain accessible | Level 1 (S1) | PASS | 911 backend tests pass with no env key (auth hook returns None when key is empty) |
| 6 | CORS rejects cross-origin requests when CORS_ALLOWED_ORIGINS is empty (fail-closed) | Level 2 (P2) | PASS | No ACAO header for evil.example.com |
| 7 | X-API-Key listed in Access-Control-Allow-Headers | Level 1 (S10) | PASS | `Access-Control-Allow-Headers: Content-Type, X-API-Key` confirmed with configured origin |
| 8 | API key comparison uses hmac.compare_digest() | Level 1 (code inspection) | PASS | Line 149: `hmac.compare_digest(provided_key, api_key)` — no `==` comparison present |
| 9 | apiFetch() includes X-API-Key header on every REST request | Level 2 (P4) | PASS | `getApiKey()` reads localStorage; `authHeaders['X-API-Key'] = apiKey` injected at line 68 |
| 10 | All SSE connections use createAuthenticatedEventSource with X-API-Key header | Level 2 (P1, P4) | PASS | Zero `new EventSource(` remaining; `createAuthenticatedEventSource` injects `X-API-Key` at line 291 |
| 11 | SSE wrapper does NOT retry on 401 (fatal error) | Level 1 (code inspection) | PASS | Line 306: `if (response.status === 401) { throw new FatalSSEError('Unauthorized'); }` stops reconnection |
| 12 | API key read per-request (F7 fix — not cached at startup) | Level 1 (code inspection) | PASS | Line 128: `api_key = os.environ.get("AGENTED_API_KEY", "")` inside `_require_api_key()` function |
| 13 | SSE delivery across all 20+ endpoints in browser | Level 3 | DEFERRED | DEFER-03-01 |

### Required Artifacts

| Artifact | Expected | Exists | Sanity | Wired |
|----------|----------|--------|--------|-------|
| `backend/app/__init__.py` | before_request auth middleware + CORS fail-closed | Yes (390 lines) | PASS — runs, 911 tests pass | PASS — `@app.before_request` registered in `create_app()` |
| `backend/.env.example` | AGENTED_API_KEY documentation | Yes | PASS | PASS — `AGENTED_API_KEY=` with usage comments at line 18 |
| `frontend/src/services/api/client.ts` | apiFetch + createAuthenticatedEventSource + getApiKey | Yes (433 lines) | PASS — builds, 344 tests pass | PASS — X-API-Key injected in both apiFetchSingle and createAuthenticatedEventSource |
| `frontend/package.json` | @microsoft/fetch-event-source dependency | Yes | PASS | PASS — `"@microsoft/fetch-event-source": "^2.0.1"` at line 18 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `backend/app/__init__.py` | `os.environ AGENTED_API_KEY` | per-request env read | WIRED | `os.environ.get("AGENTED_API_KEY", "")` inside `_require_api_key()` at line 128 |
| `frontend/src/services/api/client.ts` | `localStorage agented-api-key` | `getApiKey()` | WIRED | `localStorage.getItem('agented-api-key')` at line 20 |
| `frontend/src/services/api/triggers.ts` | `client.ts` | `createAuthenticatedEventSource` | WIRED | Confirmed in consumer file list |
| `frontend/src/services/api/agents.ts` | `client.ts` | `createAuthenticatedEventSource` | WIRED | Confirmed in consumer file list |
| All 11 SSE consumer files | `client.ts` | `AuthenticatedEventSource` type + `createAuthenticatedEventSource` call | WIRED | 25 files reference `AuthenticatedEventSource` or `createAuthenticatedEventSource` |

---

## Experiment Verification

### Implementation Correctness Checks

| Check | Status | Details |
|-------|--------|---------|
| `hmac.compare_digest` used (not `==`) | PASS | Line 149 — prevents timing attacks |
| 401 throws FatalSSEError (no reconnect) | PASS | Lines 305-308 — `response.status === 401` → `throw new FatalSSEError` |
| CORS fallback is `{"origins": []}` not `"*"` | PASS | Line 79 — fail-closed when CORS_ALLOWED_ORIGINS empty |
| `allow_headers` includes both `Content-Type` and `X-API-Key` | PASS | Line 88 — required for browser preflight to succeed |
| Backpressure queue preserved in new wrapper | PASS | Lines 207-265 — full queue logic (MAX_QUEUE_SIZE=500, DRAIN_BATCH_SIZE=20, overflow warning) |
| `onmessage`/`onerror`/`onopen` property-assignment compatibility | PASS | Lines 352-358 — getter/setter pairs for all three callbacks |
| Auth disabled by default (AGENTED_API_KEY unset) | PASS | Lines 131-132 — `if not api_key: return None` |
| Per-request key read (F7 fix) | PASS | Line 128 — inside `_require_api_key()` not at module scope |
| Prefix guard for bypass paths (F2 fix) | PASS | Line 144 — `startswith(prefix + "/")` not bare `startswith(prefix)` |

### Webhook Bypass Verification

The `/api/webhooks/github/` route returns `{"error": "Invalid signature"}` (not `{"error": "Unauthorized"}`) when called without a key. This confirms:
1. The auth middleware bypass is working — the route is reached
2. The route's own GitHub HMAC signature validation is still enforced (not bypassed)

This is the correct behavior per ROADMAP.md Success Criteria 2.

---

## WebMCP Verification

WebMCP verification skipped — MCP not available in this environment (no WebMCP tool definitions in EVAL.md, section marked "WebMCP tool definitions skipped").

---

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| AUTH-01: /admin/* and /api/* require X-API-Key | PASS | S4, S5, S6: 401 without key, 200 with valid key |
| AUTH-02: Bypass allowlist for webhooks/health/docs | PASS | S7, S8: health/docs bypass; webhook bypass confirmed via test client |
| AUTH-03: Frontend apiFetch includes X-API-Key | PASS | P4: static code inspection confirms injection at line 68 |
| AUTH-04: SSE endpoints authenticate via fetch-event-source | PASS | P1: zero native EventSource calls; createAuthenticatedEventSource injects X-API-Key |
| AUTH-05: CORS fail-closed (no wildcard when origins unset) | PASS | P2: no ACAO header for evil.example.com; line 79 confirms `{"origins": []}` fallback |

---

## Anti-Patterns Found

No blocking anti-patterns detected.

| File | Pattern | Severity | Status |
|------|---------|----------|--------|
| `backend/app/__init__.py` | None found | - | Clean |
| `frontend/src/services/api/client.ts` | None found | - | Clean |

The `return None` at lines 132, 136, 140, 145, 152 in `_require_api_key()` are correct early returns in a Flask before_request hook — not stubs.

---

## Human Verification Required

### HV-1: Browser-side SSE header inspection

**What to do:** Open browser DevTools → Network tab → filter by "EventStream". Set `localStorage.setItem('agented-api-key', 'your-key')` and `AGENTED_API_KEY=your-key` on backend. Navigate to Triggers page and trigger an execution. Click the SSE stream in Network tab and inspect request headers.

**Expected:** `X-API-Key: your-key` appears in the request headers for the SSE connection.

**Why human:** Browser DevTools inspection of SSE headers cannot be automated without a browser E2E test harness (Playwright/Cypress).

### HV-2: Realistic webhook bypass test

**What to do:** Set `GITHUB_WEBHOOK_SECRET=your-secret`. Compute HMAC-SHA256 of the payload body using `your-secret`. Send `POST /api/webhooks/github/` with `X-Hub-Signature-256: sha256=<computed-hmac>` header and no `X-API-Key` header.

**Expected:** Response is 200 or 204 (webhook accepted). Then send same POST with an invalid signature — expect 400/401 from signature validation.

**Why human:** Requires real GitHub webhook secret + correct HMAC computation.

---

## Level 3 Deferred Validation Details

### DEFER-03-01: SSE Event Delivery Across All 20+ Endpoints

**Full description:** Every SSE consumer (execution log viewer, conversation stream, workflow execution, skills playground, planning session, etc.) delivers live events after `@microsoft/fetch-event-source` migration and auth is enabled.

**Target:** All SSE endpoints deliver events; browser DevTools shows `X-API-Key` header on every SSE request; no SSE endpoint returns 401.

**Validates at:** Phase 04 security hardening or manual pre-deployment verification.

**Depends on:** Both Plan 03-01 and 03-02 complete (done); AGENTED_API_KEY set; frontend built and served at localhost:3000.

**Risk:** SSE consumers that silently fail 401 will show blank UI panels — high-visibility regression.

### DEFER-03-02: Webhook Receiver Under Real Conditions

**Full description:** POST to `/api/webhooks/github/` with realistic GitHub webhook payloads succeeds (bypass correct) while invalid signatures are rejected (signature validation not bypassed by auth bypass).

**Target:** Valid signature non-401; invalid signature 400/401; bypass does not disable signature check.

**Validates at:** Phase 04 or manual pre-deployment smoke test.

**Note:** Partial evidence already gathered — test client confirms auth middleware bypassed (returns "Invalid signature" not "Unauthorized"). Full validation requires real GITHUB_WEBHOOK_SECRET.

### DEFER-03-03: CORS Enforcement in Production Browser

**Full description:** Real browser (not curl) correctly enforces CORS — allowed origin (localhost:3000) receives ACAO header and API calls succeed; any other origin does not receive ACAO header and browser DevTools shows CORS error.

**Target:** Allowed origin succeeds; any other origin blocked by browser.

**Validates at:** Phase 04 or manual pre-deployment verification.

**Note:** Partial evidence gathered — curl confirms no ACAO header for evil.example.com. Browser CORS enforcement deferred.

---

## Gaps Summary

No gaps found. All automated verifications pass at their designated tiers. Three Level 3 validations are correctly deferred to integration phase as specified in the EVAL.md plan.

The one check that appeared potentially failing (S10 with unlisted origin receiving no CORS headers) is actually correct fail-closed behavior. When CORS_ALLOWED_ORIGINS is configured for the test origin, `Access-Control-Allow-Headers: Content-Type, X-API-Key` is correctly present.

The `/api/webhooks/github/` returning HTTP 401 from curl is also correct — the 401 body is `{"error": "Invalid signature"}` from the route's own HMAC validation, not `{"error": "Unauthorized"}` from the auth middleware. The bypass is working.

---

_Verified: 2026-02-28T09:43:28Z_
_Verifier: Claude (grd-verifier)_
_Verification levels applied: Level 1 (sanity), Level 2 (proxy), Level 3 (deferred — 3 items)_
