# Evaluation Plan: Phase 4 — Security Hardening

**Designed:** 2026-02-28
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** flask-talisman (security headers), flask-limiter (rate limiting), health endpoint conditional redaction
**Reference:** 04-RESEARCH.md (OWASP Secure Headers Project, flask-talisman GoogleCloudPlatform, flask-limiter 3.x), ROADMAP.md SEC-01/SEC-02/SEC-03

---

## Evaluation Overview

Phase 4 introduces three security controls to the Agented backend: HTTP security headers via flask-talisman (SEC-01), per-route rate limiting via flask-limiter (SEC-02), and sensitive data redaction from the health readiness endpoint for unauthenticated callers (SEC-03).

Unlike most R&D phases, this phase does not optimize a metric that requires statistical validation. Security controls are either present or absent, and rate limits either trigger or do not. Evaluation is therefore acceptance testing against deterministic behavior, not measurement against a stochastic benchmark. All three requirements produce binary outcomes that can be verified with `curl` commands run against the live server.

The primary evaluation risk is regression: adding security middleware can break Swagger UI (CSP blocks inline scripts), SSE streaming (tight rate limits exhaust on reconnect), or the frontend SPA (CORS + Talisman header interaction). These regression concerns are captured as proxy metrics because they require a running server and cannot be verified by static analysis or unit tests alone.

No paper-derived metrics apply — the requirements come from OWASP Secure Headers Project guidance and product requirements (SEC-01 through SEC-03). All targets are exact binary pass/fail criteria taken directly from the ROADMAP success criteria for Phase 4.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Presence of CSP header | ROADMAP.md Phase 4 success criteria #1 / OWASP Secure Headers Project | Required by SEC-01; absence means browsers cannot enforce content restrictions |
| Presence of HSTS header | ROADMAP.md Phase 4 success criteria #1 / OWASP Secure Headers Project | Required by SEC-01; absence leaves TLS downgrade attacks possible |
| X-Frame-Options: DENY | ROADMAP.md Phase 4 success criteria #1 / OWASP Secure Headers Project | Required by SEC-01; absence enables clickjacking attacks |
| X-Content-Type-Options: nosniff | ROADMAP.md Phase 4 success criteria #1 / OWASP Secure Headers Project | Required by SEC-01; absence enables MIME type sniffing attacks |
| HTTP 429 after 20 webhook requests in 10s | ROADMAP.md Phase 4 success criteria #2 | Required by SEC-02; verifies rate limit threshold is enforced exactly as configured |
| Health redaction key set | ROADMAP.md Phase 4 success criteria #3 | Required by SEC-03; verifies no execution IDs, PIDs, ports, or warnings leak to unauthenticated callers |
| Backend test suite passes | Project convention (CLAUDE.md) | Regression guard: confirms no existing functionality is broken |
| Frontend build passes | Project convention (CLAUDE.md) | Regression guard: type errors from middleware changes caught by vue-tsc |
| Swagger UI functional | 04-RESEARCH.md Pitfall 1 | CSP must not break the only interactive API documentation surface |
| SSE streaming unaffected | 04-RESEARCH.md Pitfall 4 | Admin rate limits must accommodate EventSource reconnect patterns |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 8 | Basic functionality: headers present, key set correct, tests pass, build passes |
| Proxy (L2) | 4 | Behavior requiring a running server: rate limit threshold, 429 JSON format, authenticated health response, health exempt from rate limiting |
| Deferred (L3) | 3 | Integration behaviors requiring SPA interaction or load testing |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

**Sanity gate:** ALL sanity checks must pass. Any failure blocks progression.

### S1: Security Headers on Liveness Endpoint

- **What:** All four required security headers are present on every HTTP response, verified on the simplest endpoint that has no auth or rate limit guards
- **Command:** `curl -I http://localhost:20000/health/liveness`
- **Expected:** Response includes all four of the following lines (case-insensitive key match):
  ```
  Content-Security-Policy: ...
  Strict-Transport-Security: max-age=...
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  ```
- **Failure means:** flask-talisman is not initialized in `create_app()`, or was initialized after blueprint registration (too late for `after_request` hooks to take effect), or the `OpenAPI` app class has incompatible response handling

### S2: Security Headers on Admin Endpoint

- **What:** Security headers are present on an authenticated admin route — confirms Talisman applies headers globally, not just to health endpoints
- **Command:** `curl -s -I -H "X-API-Key: $(cat backend/.secret_key 2>/dev/null || echo test)" http://localhost:20000/admin/triggers`
- **Expected:** Response includes `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options: DENY`, and `X-Content-Type-Options: nosniff` (this directly satisfies ROADMAP success criteria #1)
- **Failure means:** Admin blueprints are somehow exempt from Talisman, or the API key is wrong for the test environment

### S3: No HTTPS Redirect Loop on HTTP

- **What:** `force_https` defaults to `False`; the server does not redirect HTTP requests to HTTPS
- **Command:** `curl -s -o /dev/null -w "%{http_code}" http://localhost:20000/health/liveness`
- **Expected:** `200` (not `301` or `308`)
- **Failure means:** `force_https=True` is set without `FORCE_HTTPS` env var, creating an infinite redirect loop in development (04-RESEARCH.md Pitfall 2)

### S4: Unauthenticated Health Readiness — Key Set Allowlist

- **What:** `/health/readiness` without an API key returns only `status` and `timestamp` fields — no sensitive fields
- **Command:** `curl -s http://localhost:20000/health/readiness | python3 -c "import sys, json; d = json.load(sys.stdin); keys = set(d.keys()); forbidden = {'active_execution_ids','components','active_executions','warnings','port'}; assert not keys & forbidden, f'Sensitive keys found: {keys & forbidden}'; assert 'status' in keys and 'timestamp' in keys, f'Required keys missing from: {keys}'; print('PASS — keys:', sorted(keys))"`
- **Expected:** `PASS — keys: ['status', 'timestamp']` (this directly satisfies ROADMAP success criteria #3)
- **Failure means:** The conditional redaction branch in `readiness()` was not added, or the auth check always returns `True` (no redaction happening), or the unauthenticated branch returns additional fields

### S5: Liveness Endpoint Unchanged

- **What:** `/health/liveness` still returns HTTP 200 with no body — confirms security changes did not break the liveness probe
- **Command:** `STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:20000/health/liveness) && BODY=$(curl -s http://localhost:20000/health/liveness) && echo "Status: $STATUS, Body length: ${#BODY}"`
- **Expected:** `Status: 200, Body length: 0`
- **Failure means:** Talisman or the 429 handler is intercepting liveness requests, or health.py was unintentionally modified

### S6: Backend Test Suite Passes

- **What:** All existing unit tests pass — confirms flask-talisman and flask-limiter initialization does not break any existing behavior
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest`
- **Expected:** Exit code 0, zero failures, zero errors
- **Failure means:** Security middleware interferes with test setup (e.g., Talisman redirecting test requests, rate limiter shared state between tests), or a code change in health.py or `__init__.py` introduced a regression

### S7: Frontend Build Passes

- **What:** The frontend TypeScript build succeeds — confirms no type errors introduced by changes to backend API response shapes (health endpoint now returns different shapes depending on auth)
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented && just build`
- **Expected:** Exit code 0, no TypeScript errors, no Vite build errors
- **Failure means:** Frontend health service types expect fields that are no longer returned in the unauthenticated response, requiring frontend type updates

### S8: Custom 429 Handler Returns JSON

- **What:** The 429 error handler returns `application/json`, not HTML — verifiable without exhausting the rate limit by inspecting the error handler registration directly
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app import create_app; app = create_app(testing=True); rules = [str(r) for r in app.url_map.iter_rules()]; print('App created OK'); handlers = app.error_handler_spec[None]; print('429 handler registered:', 429 in (handlers.get(None) or {}))"`
- **Expected:** `App created OK` and `429 handler registered: True`
- **Failure means:** The `@app.errorhandler(429)` was placed inside a conditional block that does not execute during app creation, or has a syntax error

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation requiring a running server. These measure the behaviors specified in the ROADMAP success criteria and the key regression concerns from 04-RESEARCH.md.

**IMPORTANT:** Proxy metrics require the backend server to be running. Start with `just dev-backend` before running these checks.

### P1: Rate Limit Threshold — Webhook Endpoint

- **What:** The webhook endpoint enforces exactly "20 requests per 10 seconds" — the 21st request within the window returns HTTP 429 with a JSON body
- **How:** Send 21 POST requests in rapid succession; record the HTTP status of each; verify requests 1-20 return non-429 and request 21 returns 429
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented && \
  for i in $(seq 1 21); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      -H "Content-Type: application/json" -d '{}' \
      http://localhost:20000/)
    echo "Request $i: HTTP $STATUS"
    if [ "$i" -eq 21 ] && [ "$STATUS" -eq 429 ]; then
      echo "PASS — 21st request correctly rate limited"
    fi
  done
  ```
- **Target:** Requests 1-20 return HTTP 200 or 400 (not 429); request 21 returns HTTP 429 (directly satisfies ROADMAP success criteria #2)
- **Evidence:** 04-RESEARCH.md Recommendation 2 — flask-limiter fixed-window strategy with "20/10seconds" limit directly maps to this acceptance condition. The in-memory backend is appropriate for `workers=1` (confirmed by gunicorn.conf.py constraint)
- **Correlation with full metric:** HIGH — this IS the metric from the ROADMAP, not a proxy
- **Blind spots:** Tests a fixed-window limit with a single client from localhost. Does not test: multi-IP fairness, limit reset at window boundary, behavior under concurrent requests (gevent greenlets), or persistence across server restarts (in-memory: resets on restart, documented limitation)
- **Validated:** No — deferred validation for concurrent/multi-client behavior at DEFER-04-01

### P2: Rate Limit 429 Response Is JSON

- **What:** The custom 429 error handler returns `application/json` content, not the default HTML error page that flask-limiter would otherwise produce
- **How:** After exhausting the webhook rate limit in P1, inspect the body of the 429 response
- **Command:**
  ```bash
  # Wait 11 seconds after P1 to reset the window, then exhaust again
  sleep 11 && \
  for i in $(seq 1 20); do
    curl -s -o /dev/null -X POST -H "Content-Type: application/json" \
      -d '{}' http://localhost:20000/ > /dev/null
  done && \
  BODY=$(curl -s -X POST -H "Content-Type: application/json" -d '{}' http://localhost:20000/) && \
  echo "$BODY" | python3 -m json.tool && \
  echo "PASS — 429 body is valid JSON"
  ```
- **Target:** `{"error": "Rate limit exceeded: ..."}` — valid JSON with an `error` key (prevents 04-RESEARCH.md Pitfall 3: HTML 429 breaking frontend JSON parsing)
- **Evidence:** 04-RESEARCH.md Pattern 3 (Custom JSON 429 error handler). The project's existing error handlers all return JSON; the 429 handler must match this convention
- **Correlation with full metric:** HIGH — directly tests the custom error handler output format
- **Blind spots:** Does not test that the frontend `apiFetch()` displays a meaningful error message when receiving 429 (requires E2E browser test, deferred)
- **Validated:** No — frontend display behavior deferred to DEFER-04-02

### P3: Authenticated Health Response Contains Full Component Details

- **What:** `/health/readiness` with a valid `X-API-Key` header still returns the full component health object — confirms the redaction logic does not accidentally strip data from authenticated callers
- **How:** Call the endpoint with the `SECRET_KEY` value as the API key; verify the response contains `components` with `database` and `process_manager` sub-objects
- **Command:**
  ```bash
  SECRET=$(cat /Users/edward.seo/dev/private/project/harness/Agented/backend/.secret_key 2>/dev/null || echo "")
  if [ -z "$SECRET" ]; then
    echo "SKIP — no .secret_key file; set SECRET_KEY env var and retest"
  else
    curl -s -H "X-API-Key: $SECRET" http://localhost:20000/health/readiness | \
    python3 -c "
  import sys, json
  d = json.load(sys.stdin)
  assert 'components' in d, f'components missing from: {list(d.keys())}'
  assert 'database' in d['components'], f'database missing from components'
  assert 'process_manager' in d['components'], f'process_manager missing from components'
  assert 'status' in d, 'status missing'
  print('PASS — authenticated response has full component details')
  print('Keys:', sorted(d.keys()))
  print('Component keys:', sorted(d['components'].keys()))
  "
  fi
  ```
- **Target:** Response contains `status`, `components.database`, and `components.process_manager` (confirms existing readiness functionality is preserved for authenticated callers)
- **Evidence:** health.py lines 23-79 (existing readiness logic that must remain intact in the authenticated branch); 04-RESEARCH.md Pattern 4
- **Correlation with full metric:** HIGH — tests the authenticated code path directly
- **Blind spots:** Does not test monitoring tools that call the endpoint without auth and now receive incomplete data (04-RESEARCH.md Pitfall 5 — monitoring breakage risk documented in deferred items)
- **Validated:** No

### P4: Health Endpoint Exempt from Rate Limiting

- **What:** The health endpoint is not rate-limited; 25+ rapid requests all return 200, never 429
- **How:** Send 25 consecutive requests to `/health/liveness` without delay; verify none return 429
- **Command:**
  ```bash
  FAILED=0
  for i in $(seq 1 25); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:20000/health/liveness)
    if [ "$STATUS" -eq 429 ]; then
      echo "FAIL — Request $i returned 429 (health should be exempt)"
      FAILED=1
    fi
  done
  if [ "$FAILED" -eq 0 ]; then echo "PASS — all 25 health requests returned non-429"; fi
  ```
- **Target:** All 25 requests return HTTP 200 (confirms `limiter.exempt(health_bp)` is working)
- **Evidence:** 04-RESEARCH.md Pattern 2 and Pitfall 5 — health probes must always respond; rate limiting health would break monitoring and deployment orchestrators
- **Correlation with full metric:** HIGH — directly tests the exemption behavior
- **Blind spots:** Does not test that Swagger UI docs are similarly not rate-limited (low risk since `default_limits=[]` and docs blueprint is not explicitly limited)
- **Validated:** No

---

## Level 3: Deferred Validations

**Purpose:** Full validation requiring SPA interaction, load testing, or conditions not easily reproducible in unit/acceptance tests.

### D1: Frontend SPA Navigation Under Rate Limits — DEFER-04-01
- **What:** Normal multi-page SPA navigation (browsing triggers, agents, projects pages in rapid succession) does not trigger 429 responses from the admin blueprint rate limit (120/minute)
- **How:** Open the frontend at http://localhost:3000, navigate rapidly between 10+ pages, monitor browser DevTools Network tab for 429 responses
- **Why deferred:** Requires interactive browser session; the SPA's actual request volume per minute during normal navigation cannot be easily simulated without a browser or Playwright/Cypress test suite
- **Validates at:** phase-05-observability-and-process-reliability (structured logging in Phase 5 will make access log analysis possible; alternatively, add a Playwright smoke test during Phase 6)
- **Depends on:** Running frontend (just dev-frontend) + running backend (just dev-backend) + Phase 3 auth (API key configured in frontend)
- **Target:** Zero 429 responses during normal navigation within any 60-second window from a single browser session
- **Risk if unmet:** Admin rate limit of 120/minute is too tight for the SPA's actual request volume. Mitigation: raise limit to 300/minute and re-test. Cost: one config change + re-deploy.
- **Fallback:** Raise admin blueprint limit to 300/minute; add the limit value to an environment variable (`ADMIN_RATE_LIMIT_PER_MINUTE`) for tuning without code changes

### D2: SSE Streaming Reconnect Behavior Under Admin Rate Limits — DEFER-04-02
- **What:** The execution log SSE stream (`/admin/executions/{id}/stream`) reconnects successfully after a simulated network drop without triggering 429 from the admin blueprint rate limit
- **How:** Start a test bot execution, open the execution detail page in a browser, disconnect network briefly, verify EventSource reconnects and log streaming resumes without 429
- **Why deferred:** Requires a live execution (bot subprocess running), a browser with EventSource, and a simulated network interruption — not reproducible in curl-based acceptance tests
- **Validates at:** phase-05-observability-and-process-reliability (Phase 5 structured logging will capture SSE reconnect events with request IDs, making this verifiable from logs)
- **Depends on:** Running backend + running frontend + a configured bot trigger that executes successfully
- **Target:** Execution log stream reconnects within 3 seconds of network restore; no 429 responses during or after reconnect
- **Risk if unmet:** 04-RESEARCH.md Pitfall 4 manifests — EventSource reconnects exhaust admin rate limit, blocking all admin API calls. Mitigation: exempt specific SSE endpoints via `@limiter.exempt` on the streaming routes.
- **Fallback:** Add `@limiter.exempt` decorator to `/admin/executions/{id}/stream` route specifically

### D3: In-Memory Rate Limit Reset on Server Restart — DEFER-04-03
- **What:** Confirming (and documenting acceptance of) the behavior that rate limit counters reset to zero when the server restarts; an attacker who observes the restart has a window of full burst capacity
- **How:** Exhaust the webhook rate limit, restart the server, verify the 21st+ request succeeds again immediately after restart
- **Why deferred:** This is a known accepted limitation (documented in 04-RESEARCH.md "Known Failure Modes"), not a bug to fix. Deferred to document the behavior in the Phase 4 retrospective and confirm it is intentional.
- **Validates at:** manual-review (during Phase 4 retrospective / post-deploy observation)
- **Depends on:** Phase 4 deployed to any persistent environment
- **Target:** Behavior is accepted and documented; a comment in `create_app()` notes that in-memory storage resets on restart and references the Redis migration path
- **Risk if unmet:** No functional risk — the limitation is known and documented. Risk is only to deployment documentation if the comment is omitted.
- **Fallback:** N/A — this is an accepted limitation, not a failure condition

---

## Ablation Plan

**No ablation plan** — Phase 4 implements three independent security controls (headers, rate limits, health redaction), each mapped 1:1 to a product requirement (SEC-01, SEC-02, SEC-03). There are no sub-components to isolate: removing any one control would directly fail a ROADMAP success criterion. The research document (04-RESEARCH.md) explicitly evaluated alternatives (manual `after_request` hook vs. flask-talisman; in-memory dict vs. flask-limiter) and selected the standard extension approach. No ablation adds information here.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — MCP not available.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Security headers before Phase 4 | Zero security headers on any response | 0 of 4 headers present | Codebase analysis — no Talisman in `__init__.py` pre-phase |
| Rate limiting before Phase 4 | No rate limits enforced; all requests return 200 | No 429 ever | Codebase analysis — no Limiter in `__init__.py` pre-phase |
| Health readiness before Phase 4 | Full component data exposed to all callers | `active_execution_ids`, `port`, `warnings` always present | health.py lines 43-76 pre-phase — unconditional response |
| Backend test baseline | All tests pass | 0 failures | `cd backend && uv run pytest` on pre-phase code |
| Frontend build baseline | Build succeeds | Exit code 0 | `just build` on pre-phase code |

---

## Evaluation Scripts

**Location of evaluation code:**
```
No dedicated eval scripts — all checks use curl and inline Python one-liners (commands specified per check above).
```

**How to run all sanity checks sequentially:**
```bash
#!/usr/bin/env bash
# Run from project root: bash .planning/milestones/v0.1.0/phases/04-security-hardening/run-sanity.sh
# Requires: backend running at localhost:20000

set -e
BACKEND=http://localhost:20000

echo "=== S1: Security headers on liveness ==="
HEADERS=$(curl -sI "$BACKEND/health/liveness")
for h in "Content-Security-Policy" "Strict-Transport-Security" "X-Frame-Options: DENY" "X-Content-Type-Options: nosniff"; do
  echo "$HEADERS" | grep -qi "$h" && echo "PASS: $h" || echo "FAIL: $h missing"
done

echo ""
echo "=== S3: No HTTPS redirect ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND/health/liveness")
[ "$STATUS" = "200" ] && echo "PASS: HTTP 200 (no redirect)" || echo "FAIL: Got $STATUS"

echo ""
echo "=== S4: Unauthenticated health redaction ==="
curl -s "$BACKEND/health/readiness" | python3 -c "
import sys, json
d = json.load(sys.stdin)
keys = set(d.keys())
forbidden = {'active_execution_ids','components','active_executions','warnings','port'}
bad = keys & forbidden
if bad: print('FAIL: Sensitive keys exposed:', bad)
elif 'status' in keys and 'timestamp' in keys: print('PASS: Only status and timestamp present')
else: print('FAIL: Required keys missing:', keys)
"

echo ""
echo "=== S5: Liveness endpoint unchanged ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND/health/liveness")
BODY=$(curl -s "$BACKEND/health/liveness")
[ "$STATUS" = "200" ] && [ -z "$BODY" ] && echo "PASS: 200 with empty body" || echo "FAIL: Status=$STATUS Body='$BODY'"

echo ""
echo "=== S6: Backend tests ==="
cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest -q && echo "PASS: All tests pass" || echo "FAIL: Tests failed"

echo ""
echo "=== S7: Frontend build ==="
cd /Users/edward.seo/dev/private/project/harness/Agented && just build && echo "PASS: Build succeeded" || echo "FAIL: Build failed"
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Security headers on liveness | [PASS/FAIL] | | |
| S2: Security headers on admin endpoint | [PASS/FAIL] | | |
| S3: No HTTPS redirect loop | [PASS/FAIL] | | |
| S4: Unauthenticated health key set | [PASS/FAIL] | | |
| S5: Liveness endpoint unchanged | [PASS/FAIL] | | |
| S6: Backend test suite | [PASS/FAIL] | | |
| S7: Frontend build | [PASS/FAIL] | | |
| S8: Custom 429 handler registered | [PASS/FAIL] | | |

**Sanity gate:** [PASSED / BLOCKED — specify which checks failed]

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Rate limit at 21st webhook request | HTTP 429 on request 21 | | [MET/MISSED] | |
| P2: 429 body is JSON | `{"error": "..."}` | | [MET/MISSED] | |
| P3: Authenticated health has components | `components.database` + `components.process_manager` | | [MET/MISSED] | |
| P4: Health exempt from rate limiting | All 25 requests return 200 | | [MET/MISSED] | |

### Ablation Results

N/A — no ablation plan for this phase.

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-04-01 | SPA navigation under rate limits | PENDING | phase-05-observability-and-process-reliability |
| DEFER-04-02 | SSE streaming reconnect under rate limits | PENDING | phase-05-observability-and-process-reliability |
| DEFER-04-03 | In-memory rate limit reset on restart (accepted limitation) | PENDING | manual-review |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 8 checks cover all three requirements (SEC-01 headers, SEC-02 rate limit mechanism, SEC-03 health redaction) and the two regression surfaces (test suite, frontend build). Each check has a specific command and binary pass/fail criterion.
- Proxy metrics: Well-evidenced — all four proxy metrics test behaviors that ARE the product requirements, not correlates of them. P1 directly reproduces ROADMAP success criteria #2; P3 directly tests the authenticated branch that S4 cannot reach. Evidence sourced from 04-RESEARCH.md with HIGH confidence ratings for flask-talisman and flask-limiter APIs.
- Deferred coverage: Adequate — the three deferred items cover the only behaviors that cannot be tested with curl: browser-based SPA navigation (DEFER-04-01), browser-based SSE reconnect (DEFER-04-02), and an accepted limitation that requires a restart sequence (DEFER-04-03). All three have specific validates_at targets.

**What this evaluation CAN tell us:**
- Whether all four required security headers are present on every HTTP response
- Whether the webhook rate limit triggers exactly at the configured threshold
- Whether the health endpoint correctly redacts sensitive fields from unauthenticated callers
- Whether the authenticated health branch still returns full component details
- Whether existing tests and the frontend build are unaffected by the new middleware

**What this evaluation CANNOT tell us:**
- Whether the admin rate limit (120/minute) is calibrated correctly for real SPA usage patterns — addressed at DEFER-04-01
- Whether SSE EventSource reconnect behavior works correctly under admin rate limits — addressed at DEFER-04-02
- Whether the in-memory rate limit reset on restart is documented and accepted by the team — addressed at DEFER-04-03
- Whether monitoring tools that call `/health/readiness` without auth are broken by the redaction (04-RESEARCH.md Pitfall 5) — risk acknowledged; recommendation is to configure monitoring with an API key

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-02-28*
