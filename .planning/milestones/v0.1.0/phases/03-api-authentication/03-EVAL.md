# Evaluation Plan: Phase 3 — API Authentication

**Designed:** 2026-02-28
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Flask before_request middleware, Flask-CORS fail-closed config, @microsoft/fetch-event-source SSE auth
**Reference papers:** 03-RESEARCH.md (Flask docs, @microsoft/fetch-event-source README, MDN Web Docs SSE, HAHWUL SSE Security 2025)

## Evaluation Overview

Phase 3 adds API key authentication to a Flask backend that previously had zero authentication on any route. The change is structural: a single `app.before_request` hook enforces `X-API-Key` validation on all `/admin/*` and `/api/*` routes, with an explicit bypass allowlist for webhooks, health probes, and docs. Simultaneously, the CORS policy shifts from permissive wildcard to fail-closed (empty list when `CORS_ALLOWED_ORIGINS` is unset). On the frontend, `apiFetch()` gains header injection and all 20+ native `EventSource` calls are replaced with `@microsoft/fetch-event-source`, which supports custom headers.

Authentication behavior is deterministic — HTTP status codes are binary pass/fail, not probabilistic. This makes Level 1 (sanity) checks the primary verification mechanism for the backend half, and Level 2 (proxy) checks the primary mechanism for the frontend SSE integration. There are no paper benchmarks to reproduce; the metrics are derived directly from the phase success criteria in ROADMAP.md and the research-defined test plan in 03-RESEARCH.md.

The most significant evaluation gap is comprehensive SSE coverage. The phase includes 20+ SSE endpoints migrated from native `EventSource` to `@microsoft/fetch-event-source`. Curl-based tests can confirm the backend auth gate; browser-side verification of all 20+ SSE consumers individually requires a running application and manual interaction that is deferred. The structural completeness check (zero `new EventSource(` calls remaining) is a reliable proxy for migration completeness.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| HTTP 401 on protected route without key | ROADMAP.md Success Criteria 1 + 03-RESEARCH.md Level 1 checks | Direct functional requirement; deterministic |
| HTTP 200 on protected route with valid key | ROADMAP.md Success Criteria 1 | Confirms middleware does not over-block |
| HTTP 200 on bypass routes without key | ROADMAP.md Success Criteria 2 | Confirms webhook receiver and health probes remain accessible |
| No ACAO header for unlisted origin | ROADMAP.md Success Criteria 4 | Confirms CORS fail-closed; verifiable via curl response headers |
| Zero `new EventSource(` calls remaining | 03-RESEARCH.md Pitfall 1 + 03-02-PLAN.md verify step | Structural completeness proxy for migration; grep-verifiable |
| Frontend build (vue-tsc) exits 0 | 03-02-PLAN.md success criteria | Type correctness of AuthenticatedEventSource interface across 11 consumer files |
| Backend pytest suite exits 0 | 03-01-PLAN.md, 03-02-PLAN.md success criteria | Confirms auth disabled by default (no env key set) = no regressions in existing tests |
| SSE event delivery (execution log) | ROADMAP.md Success Criteria 3 | Confirms fetch-event-source wrapper functions end-to-end; requires running app |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 10 | Basic functionality, format, no regressions, HTTP status codes |
| Proxy (L2) | 4 | Indirect quality: migration completeness, type safety, curl-based end-to-end auth, CORS header check |
| Deferred (L3) | 3 | Full browser-side SSE validation across all 20+ endpoints; load testing; key rotation behavior |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: Backend test suite passes (auth disabled by default)

- **What:** All 911 backend tests pass with no AGENTED_API_KEY set, confirming the before_request hook is a no-op when the key is unconfigured and causes zero regressions
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest`
- **Expected:** Exit code 0, all tests pass
- **Failure means:** The auth middleware broke an existing route or test fixture — check that the hook returns `None` when `AGENTED_API_KEY` is empty

### S2: Frontend tests pass

- **What:** All 344 frontend tests pass after `@microsoft/fetch-event-source` installation and `apiFetch` header injection
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/frontend && npm run test:run`
- **Expected:** Exit code 0, all tests pass
- **Failure means:** The `getApiKey()` helper or `apiFetch` header change broke a mocked fetch test — check for header assertion mismatches in test fixtures

### S3: Frontend TypeScript build succeeds

- **What:** `vue-tsc` compiles all migrated consumer files without type errors — confirms `AuthenticatedEventSource` interface is compatible with all 11 consumer variable declarations that previously used `EventSource`
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/frontend && npm run build`
- **Expected:** Exit code 0, zero TypeScript errors, vite build output generated
- **Failure means:** A consumer file still declares `EventSource` type while the API function now returns `AuthenticatedEventSource` — update the type annotation in the affected consumer

### S4: Protected route rejects unauthenticated request (HTTP 401)

- **What:** The before_request hook intercepts `/admin/triggers` and returns 401 when AGENTED_API_KEY is set and no key is provided in the request
- **Command:** `AGENTED_API_KEY=test-key-for-eval cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -m flask --app app run --port 20001 &; sleep 2; curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20001/admin/triggers`
- **Expected:** `401`
- **Failure means:** The before_request hook is not registered, not reaching the path, or the path matching is wrong — check that the hook is inside `create_app()` and that `/admin` prefix match is correct

### S5: Protected route accepts authenticated request (HTTP 200)

- **What:** The before_request hook passes the request through when a valid `X-API-Key` header matches `AGENTED_API_KEY`
- **Command:** `curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: test-key-for-eval" http://127.0.0.1:20001/admin/triggers`
- **Expected:** `200`
- **Failure means:** `hmac.compare_digest` is failing on identical strings, or the key is being read from the wrong location — check env var name and header name spelling

### S6: Wrong key is rejected (HTTP 401)

- **What:** The before_request hook rejects requests with an incorrect key value, confirming key validation is active (not just presence check)
- **Command:** `curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: wrong-key" http://127.0.0.1:20001/admin/triggers`
- **Expected:** `401`
- **Failure means:** Key comparison is not validating the value — check `hmac.compare_digest` usage

### S7: Health probe bypasses authentication

- **What:** `/health/liveness` (or equivalent) returns 200 without an API key, confirming the `/health` prefix is in the bypass allowlist
- **Command:** `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20001/health/liveness`
- **Expected:** `200`
- **Failure means:** The bypass allowlist prefix check is missing `/health` or has a typo — verify the `startswith` check in the before_request hook

### S8: Docs endpoint bypasses authentication

- **What:** `/docs/` returns 200 without an API key, confirming the Swagger UI remains accessible without auth
- **Command:** `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20001/docs/`
- **Expected:** `200`
- **Failure means:** `/docs` prefix is missing from the bypass allowlist

### S9: OPTIONS preflight requests bypass authentication

- **What:** A CORS preflight OPTIONS request to a protected route does not return 401 (browsers send OPTIONS before actual requests containing custom headers; blocking OPTIONS breaks all CORS pre-flighted requests)
- **Command:** `curl -s -o /dev/null -w "%{http_code}" -X OPTIONS -H "Origin: http://localhost:3000" -H "Access-Control-Request-Headers: X-API-Key" http://127.0.0.1:20001/admin/triggers`
- **Expected:** `200` (Flask-CORS handles OPTIONS; before_request must skip `OPTIONS` method)
- **Failure means:** The `request.method == "OPTIONS"` check is missing from the before_request hook — all browser requests with custom headers will be blocked

### S10: X-API-Key is listed in CORS Access-Control-Allow-Headers

- **What:** Preflight response includes `X-API-Key` in `Access-Control-Allow-Headers`, enabling browsers to send the auth header without CORS blocking
- **Command:** `curl -s -I -X OPTIONS -H "Origin: http://localhost:3000" -H "Access-Control-Request-Headers: X-API-Key" http://127.0.0.1:20001/admin/triggers`
- **Expected:** Response headers contain `Access-Control-Allow-Headers: Content-Type, X-API-Key` (or similar including `X-API-Key`)
- **Failure means:** `allow_headers=["Content-Type", "X-API-Key"]` is missing from the `CORS()` call — all frontend requests will be blocked by CORS preflight

**Sanity gate:** ALL sanity checks must pass. Any failure blocks progression to proxy metrics or phase sign-off.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of quality and completeness.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full browser-based end-to-end evaluation. Results should be treated as strong indicators, not guarantees.

### P1: Zero native EventSource calls remaining in frontend source

- **What:** Structural completeness of the SSE migration — every `new EventSource(` in frontend source has been replaced with `createAuthenticatedEventSource(`
- **How:** Grep the frontend source directory for the pattern; count must be zero
- **Command:** `grep -r "new EventSource" /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/ --include="*.ts" --include="*.vue" | grep -v "//"`
- **Target:** Zero matches (empty output)
- **Evidence:** 03-RESEARCH.md Pitfall 1 — "Adding before_request auth breaks all SSE streams because EventSource cannot send custom headers." 03-02-PLAN.md verifies this grep explicitly as a done condition.
- **Correlation with full metric:** HIGH — structural absence of `new EventSource` is a necessary (though not sufficient) condition for all SSE streams to authenticate. It misses configuration errors inside the wrapper itself.
- **Blind spots:** Does not verify that the new wrapper correctly passes headers at runtime; does not verify that all 20+ SSE consumer components actually receive events. A wrapper that compiles but has a logic bug passes this check.
- **Validated:** No — runtime SSE event delivery is deferred to DEFER-03-01

### P2: CORS rejects requests from unlisted origins (no ACAO header)

- **What:** When `CORS_ALLOWED_ORIGINS` is empty or unset, a cross-origin request receives no `Access-Control-Allow-Origin` header, causing browsers to block the response
- **How:** Send a curl request with a foreign `Origin` header; inspect the response for the ACAO header
- **Command:** `curl -s -I -H "Origin: https://evil.example.com" -H "X-API-Key: test-key-for-eval" http://127.0.0.1:20001/admin/triggers`
- **Target:** Response does NOT contain `Access-Control-Allow-Origin` in any form
- **Evidence:** ROADMAP.md Success Criteria 4. Flask-CORS docs (corydolphin/flask-cors): an empty `origins` list causes Flask-CORS to omit the ACAO header entirely. 03-RESEARCH.md Recommendation 4.
- **Correlation with full metric:** HIGH — Flask-CORS behavior is deterministic; if the header is absent in this test it will be absent in production browsers. The only gap is proxy-vs-same-origin scenarios.
- **Blind spots:** curl simulates the browser check but browsers may behave differently for certain response types. Does not test CORS for preflight (OPTIONS) requests from unlisted origins.
- **Validated:** No — production browser CORS behavior deferred to DEFER-03-03

### P3: curl-based auth end-to-end script passes all 5 checks

- **What:** Automated validation of the full auth matrix: protected route without key (401), protected route with valid key (200), protected route with wrong key (401), health bypass (200), docs bypass (200)
- **How:** Run the verification script from 03-02-PLAN.md against a live backend with `AGENTED_API_KEY` set
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend
  AGENTED_API_KEY=test-key-123 uv run python -m flask --app app run --port 20002 &
  BACKEND_PID=$!
  sleep 2

  PASS=0; FAIL=0

  status=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20002/admin/triggers)
  [ "$status" = "401" ] && PASS=$((PASS+1)) && echo "PASS: no-key returns 401" || { FAIL=$((FAIL+1)); echo "FAIL: expected 401, got $status"; }

  status=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: test-key-123" http://127.0.0.1:20002/admin/triggers)
  [ "$status" = "200" ] && PASS=$((PASS+1)) && echo "PASS: valid-key returns 200" || { FAIL=$((FAIL+1)); echo "FAIL: expected 200, got $status"; }

  status=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: wrong" http://127.0.0.1:20002/admin/triggers)
  [ "$status" = "401" ] && PASS=$((PASS+1)) && echo "PASS: wrong-key returns 401" || { FAIL=$((FAIL+1)); echo "FAIL: expected 401, got $status"; }

  status=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20002/health/liveness)
  [ "$status" = "200" ] && PASS=$((PASS+1)) && echo "PASS: health bypasses auth" || { FAIL=$((FAIL+1)); echo "FAIL: expected 200, got $status"; }

  status=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20002/docs/)
  [ "$status" = "200" ] && PASS=$((PASS+1)) && echo "PASS: docs bypasses auth" || { FAIL=$((FAIL+1)); echo "FAIL: expected 200, got $status"; }

  kill $BACKEND_PID 2>/dev/null
  echo "Result: $PASS/5 PASS, $FAIL/5 FAIL"
  [ "$FAIL" = "0" ] && echo "PROXY METRIC P3: PASS" || echo "PROXY METRIC P3: FAIL"
  ```
- **Target:** 5/5 checks pass (`FAIL=0`)
- **Evidence:** 03-02-PLAN.md verification section; ROADMAP.md Success Criteria 1 and 2. These are the exact same checks specified in both plans' verify sections.
- **Correlation with full metric:** HIGH — these curl checks directly match the roadmap success criteria for backend auth. The only gap is that curl does not test the frontend sending the header (which is covered by P4).
- **Blind spots:** Does not test webhook receiver bypass (`POST /`, `POST /api/webhooks/github/`) — those require POST bodies. Does not test the frontend automatically including the header.
- **Validated:** No — webhook receiver bypass confirmed separately in DEFER-03-02; frontend header inclusion deferred to DEFER-03-01

### P4: apiFetch() sends X-API-Key header in source code inspection

- **What:** Static code inspection confirms `X-API-Key` header is injected in `apiFetch()` and that `getApiKey()` reads from `localStorage.getItem('agented-api-key')`
- **How:** Grep for the key pattern in client.ts; confirm both the header injection and the localStorage read are present
- **Command:** `grep -n "X-API-Key\|agented-api-key\|getApiKey" /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/services/api/client.ts`
- **Target:** Output shows: `getApiKey()` function reading from `localStorage.getItem('agented-api-key')`, and `'X-API-Key': apiKey` in the headers object inside `apiFetchSingle`
- **Evidence:** 03-02-PLAN.md Task 1 Part B specifies exact implementation. AUTH-03 requirement: "Frontend apiFetch() includes X-API-Key header on every request."
- **Correlation with full metric:** MEDIUM — static presence of the header injection code confirms intent, but does not confirm the header is actually transmitted (that requires browser DevTools inspection). It also does not verify that all callers use `apiFetch` rather than raw `fetch`.
- **Blind spots:** Any code paths that bypass `apiFetch()` and call `fetch()` directly will silently omit the auth header. Runtime browser inspection deferred to DEFER-03-01.
- **Validated:** No — browser DevTools confirmation deferred to DEFER-03-01

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring a running application with both frontend and backend, or user interaction.

### D1: SSE event delivery across all 20+ endpoints — DEFER-03-01

- **What:** Every SSE consumer (execution log viewer, conversation stream, workflow execution, skills playground, planning session, etc.) delivers live events after `@microsoft/fetch-event-source` migration and auth is enabled
- **How:** Set `AGENTED_API_KEY` in backend and `localStorage.setItem('agented-api-key', key)` in browser; trigger each SSE-consuming feature and observe event delivery in the UI and browser DevTools Network tab; confirm `X-API-Key` header is present on each SSE request
- **Why deferred:** Requires a fully running frontend + backend with auth enabled, manual triggering of each feature, and human inspection of event delivery. 20+ endpoints cannot be verified programmatically without an end-to-end test harness that does not currently exist.
- **Validates at:** phase-04-security-hardening (first phase where a running full stack is routinely tested) or during manual pre-deployment verification
- **Depends on:** Both Plan 03-01 and Plan 03-02 complete; AGENTED_API_KEY set; frontend built and served
- **Target:** All SSE endpoints deliver events; browser DevTools shows `X-API-Key` header on every SSE request; no SSE endpoint returns 401
- **Risk if unmet:** SSE consumers that silently fail 401 will show blank UI panels — users will see missing execution logs, conversation history, and workflow output. This is a high-visibility regression that would surface immediately during any functional test.
- **Fallback:** If a subset of SSE endpoints fail, the scope of affected consumers can be identified from the grep list in 03-02-PLAN.md Task 2; individual files can be re-examined for missed migration

### D2: Webhook receiver bypass under real webhook conditions — DEFER-03-02

- **What:** POST requests to `/` (webhook receiver) and `/api/webhooks/github/` succeed without an `X-API-Key` header, with realistic webhook payloads and headers (not just empty curl requests)
- **How:** Send test payloads mimicking real GitHub webhook format (including `X-Hub-Signature-256` header); confirm non-401 responses; confirm the existing webhook signature validation still applies (auth bypass does not disable signature check)
- **Why deferred:** Requires a configured webhook secret and realistic GitHub payload. The bypass is structurally verifiable via curl (S7, P3), but production correctness (signature validation still enforced, payload routing still works) requires a full test payload.
- **Validates at:** phase-04-security-hardening or manual pre-deployment smoke test
- **Depends on:** Backend running with both `AGENTED_API_KEY` and `WEBHOOK_SECRET` configured
- **Target:** POST to `/api/webhooks/github/` with valid payload and signature returns 200 (or 204); without API key header; POST with invalid signature still returns 401/400 (signature validation not bypassed)
- **Risk if unmet:** Real GitHub webhooks would be blocked (if bypass is wrong) or signature validation disabled (if bypass is too broad). Both are high-severity operational failures.
- **Fallback:** Adjust the bypass allowlist — either tighten the path match or add/remove exact-match entries

### D3: CORS behavior in production browser session — DEFER-03-03

- **What:** A browser session with a configured `localhost:3000` origin can access the API (ACAO header present for allowed origin); a different origin (e.g., `evil.example.com`) cannot (ACAO header absent); browser blocks the cross-origin response
- **How:** Open browser DevTools; navigate to frontend; check Network tab that API calls show correct CORS headers; attempt to load a page from an unlisted origin and confirm browser blocks the response
- **Why deferred:** curl can verify header presence/absence, but actual browser CORS enforcement (including the browser's own policy evaluation, preflight caching, and cookie handling) is only fully testable in a real browser session.
- **Validates at:** phase-04-security-hardening or manual pre-deployment verification
- **Depends on:** Frontend running at `localhost:3000`; `CORS_ALLOWED_ORIGINS=http://localhost:3000` set in backend env
- **Target:** Allowed origin (`localhost:3000`) receives ACAO header and requests succeed; any other origin does not receive ACAO header and browser DevTools shows CORS error
- **Risk if unmet:** Either legitimate frontend requests are blocked (misconfigured allowlist) or cross-origin requests succeed (fail-closed not working). The first is immediately visible; the second is a security gap.
- **Fallback:** Adjust `CORS_ALLOWED_ORIGINS` env var or CORS resource configuration in `create_app()`

---

## Ablation Plan

**Purpose:** Isolate component contributions and confirm the entangled design (auth middleware + SSE migration in same phase) is correctly implemented.

### A1: Auth middleware without SSE migration (expected: SSE breaks)

- **Condition:** Apply Plan 03-01 only (before_request hook + CORS lockdown); do NOT apply Plan 03-02 (EventSource migration)
- **Expected impact:** All SSE endpoints return 401 silently; execution log viewer shows blank panel; no connection error visible to user (native EventSource swallows 401 responses per MDN spec)
- **Command:** `grep -r "new EventSource" /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/ --include="*.ts" --include="*.vue" | wc -l` (should be 12 if Plan 02 not applied)
- **Evidence:** 03-RESEARCH.md Pitfall 1; ROADMAP.md Key Constraints: "AUTH-04 must be implemented in the same phase as AUTH-01"
- **Purpose:** Confirms the dependency documented in the roadmap is real; validates that Plan 03-02 is not optional

### A2: CORS wildcard vs. empty list behavior

- **Condition:** Set `CORS_ALLOWED_ORIGINS=` (empty) and compare response headers before and after the fail-closed fix
- **Expected impact:** Before fix: ACAO header is `*` (allows all origins). After fix: ACAO header is absent for unlisted origins.
- **Command:** Before and after comparison using P2 curl command
- **Evidence:** 03-RESEARCH.md Recommendation 4; Flask-CORS docs — empty `origins` list causes header omission

### A3: Auth disabled when AGENTED_API_KEY unset

- **Condition:** Start backend with no `AGENTED_API_KEY` environment variable; send unauthenticated request to protected route
- **Expected impact:** Protected route returns 200 (not 401) — backward compatibility for existing installs without auth configured
- **Command:** `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20001/admin/triggers` (no env key set, no X-API-Key header)
- **Expected:** `200`
- **Evidence:** 03-01-PLAN.md Task 1 action step 7: "If no key is configured (empty string), return None — auth is disabled for backward compatibility." Also verified by S1 (backend tests pass without env key).

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — MCP not available in this environment.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Backend test count | Number of tests passing before Phase 3 | 911/911 (100%) | STATE.md Performance Metrics |
| Frontend test count | Number of frontend tests passing before Phase 3 | 344/344 (100%) | STATE.md Performance Metrics |
| TypeScript build | vue-tsc + vite build exits 0 | 0 errors | STATE.md Performance Metrics |
| Native EventSource count | `new EventSource` calls in frontend/src/ before migration | 12 files (count from grep in pre-phase state) | grep -r "new EventSource" frontend/src/ |
| Auth enforcement | Protected routes require key | 0% (no auth before Phase 3) | ROADMAP.md Phase 3 context |
| CORS posture | CORS allows all origins | wildcard `*` (insecure default) | backend/app/__init__.py line 74 |

---

## Evaluation Scripts

**Location of evaluation code:** Inline curl commands defined in Level 1 and Level 2 sections above. No separate evaluation script file required — all checks are one-liner curl commands or grep commands.

**How to run backend sanity checks (with auth enabled):**

```bash
# Step 1: Start backend with auth key
cd /Users/edward.seo/dev/private/project/harness/Agented/backend
AGENTED_API_KEY=test-key-123 uv run python -m flask --app app run --port 20002 &
BACKEND_PID=$!
sleep 2

# Step 2: Run sanity checks (S4-S10)
echo "=== S4: 401 without key ===" && \
  curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:20002/admin/triggers

echo "=== S5: 200 with valid key ===" && \
  curl -s -o /dev/null -w "HTTP %{http_code}\n" -H "X-API-Key: test-key-123" http://127.0.0.1:20002/admin/triggers

echo "=== S6: 401 with wrong key ===" && \
  curl -s -o /dev/null -w "HTTP %{http_code}\n" -H "X-API-Key: wrong" http://127.0.0.1:20002/admin/triggers

echo "=== S7: 200 health bypass ===" && \
  curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:20002/health/liveness

echo "=== S8: 200 docs bypass ===" && \
  curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:20002/docs/

echo "=== S9: OPTIONS bypass ===" && \
  curl -s -o /dev/null -w "HTTP %{http_code}\n" -X OPTIONS \
    -H "Origin: http://localhost:3000" \
    -H "Access-Control-Request-Headers: X-API-Key" \
    http://127.0.0.1:20002/admin/triggers

echo "=== S10: X-API-Key in allow-headers ===" && \
  curl -s -I -X OPTIONS \
    -H "Origin: http://localhost:3000" \
    -H "Access-Control-Request-Headers: X-API-Key" \
    http://127.0.0.1:20002/admin/triggers | grep -i "Access-Control-Allow-Headers"

echo "=== P2: No ACAO for unlisted origin ===" && \
  curl -s -I -H "Origin: https://evil.example.com" \
    -H "X-API-Key: test-key-123" \
    http://127.0.0.1:20002/admin/triggers | grep -i "Access-Control-Allow-Origin" || echo "PASS: no ACAO header"

kill $BACKEND_PID 2>/dev/null
```

**How to run frontend sanity checks:**

```bash
# S1: Backend tests (no key set = auth disabled = no regressions)
cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest

# S2: Frontend tests
cd /Users/edward.seo/dev/private/project/harness/Agented/frontend && npm run test:run

# S3: TypeScript build
cd /Users/edward.seo/dev/private/project/harness/Agented/frontend && npm run build

# P1: Zero native EventSource remaining
grep -r "new EventSource" /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/ \
  --include="*.ts" --include="*.vue" | grep -v "//"

# P4: apiFetch sends X-API-Key
grep -n "X-API-Key\|agented-api-key\|getApiKey" \
  /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/services/api/client.ts
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Backend pytest | | | |
| S2: Frontend test:run | | | |
| S3: Frontend build | | | |
| S4: 401 without key | | | |
| S5: 200 with valid key | | | |
| S6: 401 with wrong key | | | |
| S7: Health bypass 200 | | | |
| S8: Docs bypass 200 | | | |
| S9: OPTIONS bypass | | | |
| S10: X-API-Key in allow-headers | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Zero EventSource calls | 0 matches | | | |
| P2: No ACAO for evil origin | No header | | | |
| P3: curl auth script (5 checks) | 5/5 PASS | | | |
| P4: apiFetch header in source | Pattern found | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Auth only, no SSE fix | SSE returns 401 | | |
| A2: CORS wildcard vs empty | ACAO absent for unlisted origin after fix | | |
| A3: No AGENTED_API_KEY set | All routes return 200 | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-03-01 | SSE event delivery across all 20+ endpoints + browser DevTools X-API-Key header | PENDING | phase-04-security-hardening |
| DEFER-03-02 | Webhook receiver bypass with realistic payloads + signature validation still enforced | PENDING | phase-04-security-hardening |
| DEFER-03-03 | CORS behavior in real browser session (allowed origin vs. blocked origin) | PENDING | phase-04-security-hardening |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**

- **Sanity checks:** HIGH confidence — 10 checks covering both waves of the phase. HTTP status codes are deterministic; curl is a reliable test tool. The checks directly map to the ROADMAP.md success criteria. No statistical uncertainty.
- **Proxy metrics:** HIGH for P1, P2, P3 (structural grep and deterministic HTTP); MEDIUM for P4 (static code inspection does not confirm runtime behavior). Proxy limitations are documented per item.
- **Deferred coverage:** Comprehensive — the three deferred items cover the known gaps: SSE runtime delivery (requires browser), webhook payload handling (requires real payloads), and browser CORS enforcement (requires browser). All have concrete "validates at" references.

**What this evaluation CAN tell us:**

- Whether the backend auth middleware correctly enforces 401/200 based on key presence and correctness (S4-S6, P3)
- Whether the bypass allowlist correctly exempts health, docs, and OPTIONS preflight (S7, S8, S9)
- Whether `X-API-Key` is correctly listed in CORS allow-headers (S10)
- Whether CORS is fail-closed for unlisted origins (P2)
- Whether all native EventSource calls have been structurally removed from the codebase (P1)
- Whether the TypeScript interface changes compile correctly across all 11 consumer files (S3)
- Whether existing tests still pass with auth disabled by default (S1, S2)

**What this evaluation CANNOT tell us:**

- Whether any of the 20+ SSE endpoints actually deliver events end-to-end in a browser after migration (DEFER-03-01 — requires browser + running full stack)
- Whether `@microsoft/fetch-event-source` reconnection behavior preserves the existing backoff and backpressure queue logic at runtime (partially covered by S2 tests, but full runtime behavior deferred to DEFER-03-01)
- Whether the webhook receiver bypass handles realistic GitHub payloads with signature headers correctly (DEFER-03-02)
- Whether browsers correctly enforce CORS for the configured allowlist in production (DEFER-03-03)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-02-28*
