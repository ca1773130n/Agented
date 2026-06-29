# Evaluation Plan: Phase 25 — Real-time Multi-user Collaboration

**Designed:** 2026-06-30
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Live-share (REQ-34), Co-drive (REQ-35), Session fork (REQ-36), OIDC SSO (REQ-37)
**Plans covered:** 25-01 through 25-05

## Evaluation Overview

Phase 25 is a product-implementation phase delivering four independent-but-composing
collaboration features. There are no ML accuracy metrics. All evaluation is behavioral
correctness: do the right things happen, do the wrong things fail, are regressions absent?

The phase has one hard external dependency: co-drive (25-02) requires Phase-23's policy
enforcement artifacts (`enforce_action`, `PolicyContext`, `PolicyDeniedError`). Tier-2
items that exercise the policy gate are marked GATED — they cannot run until Phase 23 is
merged and its artifacts are importable from the backend. All other tiers are independent.

Evaluation is divided into: fast deterministic sanity (Tier 1, seconds per module), automated
behavioral tests with binary pass/fail criteria (Tier 2), and deferred human/integration
validation (Tier 3). No numeric quality score exists or is appropriate here — pass/fail
thresholds are stated behaviorally.

### Success Criteria Map

| # | Criterion | Tier | Plan |
|---|-----------|------|------|
| 1 | Second client attaches by token and receives streamed deltas read-only | 2 | 25-01 |
| 2 | Non-owner without token gets 404 on stream_project_session | 2 | 25-01 |
| 3 | DENY verdict blocks send_input; ASK pauses; ALLOW proceeds | 2 (GATED) | 25-02 |
| 4 | Parent messages byte-identical after fork; child diverges independently | 2 | 25-03 |
| 5 | Mocked OIDC callback mints session cookie; X-API-Key path unchanged | 2 | 25-04 |
| 6 | Two-client live-share + policy-checked co-drive end-to-end | 2 (GATED) | 25-05 |
| 7 | House gates: build + backend targeted + frontend no-new-failures | 1 | 25-05 |
| 8 | 4-locale parity (en/ko/ja/zh key-identical for new namespaces) | 1/2 | 25-01..05 |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 7 | Build, lint, format, per-module unit tests, frontend baseline, locale parity |
| Proxy (L2) | 8 | Behavioral correctness assertions mapped to criteria 1–6 |
| Deferred (L3) | 4 | Real OIDC provider, real multi-browser UX, ASK round-trip latency, full suite |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. ALL must pass before proceeding to Tier 2.

### S1: Ruff format check
- **What:** Python formatting is consistent across all new backend files
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check .`
- **Expected:** Exit 0; no reformatting needed
- **Failure means:** Formatting inconsistency — run `uv run ruff format .` and re-check

### S2: Type check + frontend build (vue-tsc + vite)
- **What:** TypeScript types are valid; vite bundle compiles; no new type errors from session-shares.ts, conversation-branches.ts, SharedSessionView.vue, LoginPage.vue changes
- **Command:** `cd /Users/neo/Developer/Projects/Agented && just build`
- **Expected:** Exit 0; no vue-tsc errors; vite build succeeds
- **Failure means:** Type error in new frontend code — fix before proceeding

### S3: Live-share DB layer unit tests (25-01)
- **What:** mint/resolve/expire/revoke round-trips pass; V08 migration wires into VERSIONED_MIGRATIONS
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_session_shares.py -q`
- **Expected:** All tests pass; 0 failures
- **Failure means:** Token DB layer broken — fix session_shares.py or migration

### S4: Stream gate unit tests (25-01)
- **What:** Non-owner without token gets NotFoundException(404) from stream_project_session; owner streams normally
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_stream_project_session_gate.py -q`
- **Expected:** All tests pass; 0 failures
- **Failure means:** Owner-gate regression or 404 logic wrong

### S5: Session fork unit tests (25-03)
- **What:** fork_to_run creates new branch_id and new psess- session_id; parent messages JSON unchanged; child independent
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_session_fork.py -q`
- **Expected:** All tests pass; 0 failures
- **Failure means:** Fork composition broken (create_branch or create_session wiring)

### S6: OIDC auth unit tests (25-04)
- **What:** Mocked exchange_code yields session cookie + correct user; state-mismatch → 403; closed-signup unlinked → denied
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_oidc_auth.py -q`
- **Expected:** All tests pass; 0 failures
- **Failure means:** OIDC flow wiring broken (authlib integration, session creation, or cookie path)

### S7: 4-locale parity assertion
- **What:** en/ko/ja/zh JSON catalogs have identical key sets for the Phase-25 namespaces (share/attach, fork, sso/oidc, co-drive)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_phase25_locale_parity.py -q`
- **Expected:** All assertions pass; 0 failures
- **Failure means:** A locale is missing a key — add the missing translation before proceeding

**Sanity gate:** ALL 7 sanity checks must pass. Any single failure blocks progression to Tier 2.

---

## Level 2: Proxy Metrics

**Purpose:** Automated behavioral correctness assertions mapped to success criteria.
These are the primary evaluation mechanism for this phase.

**IMPORTANT:** Co-drive items (P3, P6) are GATED on Phase-23 merge. They must be marked
PENDING until `backend/app/services/policy_enforcement.py:enforce_action` is importable
from the test environment. Running them before Phase 23 merges will produce ImportErrors,
not meaningful results.

### P1: Two-client attach delivers a broadcast delta (criterion 1)
- **What:** A second client attached via a scoped share token receives a line broadcast on a running session
- **How:** test_session_shares.py two-client attach test: mint token, drive subscribe() in thread, _broadcast a line, assert second client's queue received it
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_session_shares.py::test_two_client_attach -q`
- **Pass condition:** Test passes; second subscriber queue is non-empty after broadcast
- **Failure means:** Fan-out wiring broken — subscribe() generator not shared correctly
- **Correlation with real goal:** HIGH — directly tests the service-level attach/broadcast path
- **Blind spots:** Does not test HTTP-level SSE framing or network behavior (deferred to D1)
- **Validated:** No — awaiting D1 (real multi-browser live-share)

### P2: Non-owner without token gets 404 (criterion 2)
- **What:** The previously ungated stream_project_session route now rejects tokenless non-owners
- **How:** test_stream_project_session_gate.py: a non-owner caller with no token → NotFoundException; owner streams normally
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_stream_project_session_gate.py -q`
- **Pass condition:** All assertions pass; 404 raised for non-owner/no-token; owner allowed
- **Failure means:** Authorization gap not closed — regression risk
- **Correlation with real goal:** HIGH — directly tests the security gate
- **Blind spots:** Does not test an attacker using a valid token for a different session
- **Validated:** No

### P3: DENY verdict blocks send_input; ASK pauses; ALLOW proceeds (criterion 3) — GATED on Phase 23
- **What:** co_drive() routes through enforce_action BEFORE send_input; policy verdicts are respected
- **How:** test_co_drive.py: seed DENY policy → assert PolicyDeniedError raised AND spy on send_input (not called); seed ASK → assert pending ask-request created; seed ALLOW → assert send_input called once; read-scope token rejected
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_co_drive.py -q`
- **Pass condition:** DENY blocks send_input (spy: call_count == 0); ASK creates pending request; ALLOW calls send_input once; read token rejected before policy
- **Phase-23 gate:** Test imports `policy_enforcement.enforce_action` and `PolicyDeniedError`. Do NOT run until Phase 23 is merged. Mark PENDING until then.
- **Failure means:** Policy gate bypassed — co-drive unsafe; or enforce_action call order wrong
- **Correlation with real goal:** HIGH — directly tests the governance safety property
- **Blind spots:** Uses seeded/mocked policy, not a real policy evaluator round-trip (deferred to D2)
- **Validated:** No

### P4: Parent messages byte-identical after fork; child diverges (criterion 4)
- **What:** fork_to_run does not mutate the parent conversation; the child session is independent
- **How:** test_session_fork.py: snapshot parent messages JSON before fork; call fork_to_run; assert parent messages JSON == snapshot (bytes); append to child; assert parent unchanged; assert child session_id distinct and _subscribers isolated
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_session_fork.py -q`
- **Pass condition:** Parent JSON byte-identical; new branch_id and new psess- session_id returned; child divergence does not appear in parent; parent _subscribers unmodified
- **Failure means:** Fork mutates parent (data loss) or cross-wires streams
- **Correlation with real goal:** HIGH — directly tests immutability and isolation
- **Blind spots:** Does not test a running session being forked mid-stream (deferred to D3)
- **Validated:** No

### P5: OIDC mocked callback mints session cookie; X-API-Key path unchanged (criterion 5)
- **What:** The OIDC callback correctly maps a verified identity to a user and issues a session; the existing API-key path is not broken
- **How:** test_oidc_auth.py: stub exchange_code with fixed verified id_token/userinfo; assert session cookie set and redirect to SPA; state mismatch → 403; closed-signup unlinked identity → denied; make an X-API-Key request with OIDC routes mounted and assert it authenticates normally
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_oidc_auth.py -q`
- **Pass condition:** Cookie set for valid exchange; 403 for state mismatch; denied for closed-signup unlinked; X-API-Key authenticated (regression: 0 new auth failures)
- **Failure means:** OIDC flow broken, or API-key regression introduced
- **Correlation with real goal:** HIGH for code paths exercised; MEDIUM for real OIDC (mocked exchange)
- **Blind spots:** Does not exercise real JWKS fetch or provider-specific token quirks (deferred to D4)
- **Validated:** No

### P6: Two-client live-share + policy-checked co-drive e2e (criterion 6) — GATED on Phase 23
- **What:** Combined end-to-end: client A mints token, client B attaches and reads delta, a DENY co-drive is blocked before send_input, an ALLOW co-drive reaches send_input
- **How:** test_live_share_e2e.py::test_two_client_live_share_co_drive_policy_checked (isolated_db): full sequence in one test
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_live_share_e2e.py -q`
- **Pass condition:** B receives broadcast delta; DENY co-drive: PolicyDeniedError raised AND send_input spy call_count == 0; ALLOW co-drive: send_input spy call_count == 1
- **Phase-23 gate:** Same as P3 — requires enforce_action and PolicyDeniedError importable. Mark PENDING until Phase 23 merged.
- **Failure means:** Integration between live-share and policy enforcement broken
- **Correlation with real goal:** HIGH — this is criterion 5 verbatim
- **Blind spots:** Service-level only; HTTP framing and real network deferred
- **Validated:** No

### P7: Frontend no NEW failures (criterion 7 partial)
- **What:** Phase-25 frontend changes introduce no new test failures; baseline of 7 known failures holds
- **How:** Run the full frontend test suite and count failures
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run`
- **Pass condition:** Total failures <= 7 (the 7 known pre-existing: RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas); zero new failures
- **Failure means:** New frontend regression introduced by Phase-25 code
- **Blind spots:** Pre-existing failures mask any regressions in those same areas
- **Validated:** No

### P8: Backend targeted regression set green
- **What:** All Phase-25 suites plus execution/streaming/policy regression modules pass under the watchdog procedure
- **How:** Run targeted set (full suite first under ~12-min watchdog; on known hang at ~40-48%, kill and run targeted set; disclose substitution)
- **Command (targeted set):**
  ```
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest \
    tests/test_session_shares.py \
    tests/test_stream_project_session_gate.py \
    tests/test_co_drive.py \
    tests/test_session_fork.py \
    tests/test_oidc_auth.py \
    tests/test_live_share_e2e.py \
    tests/test_phase25_locale_parity.py \
    tests/test_project_session_manager.py \
    tests/test_policy_enforcement.py \
    tests/test_policy_evaluator.py \
    -q
  ```
- **Pass condition:** 0 failures across all modules in the targeted set; substitution disclosed if watchdog triggered
- **Note on test_co_drive.py and test_live_share_e2e.py:** These remain PENDING until Phase 23 merges. Run the targeted set without them until then; re-run with them once Phase 23 is merged.
- **Validated:** No

---

## Level 3: Deferred Validations

**Purpose:** Full validation requiring real infrastructure, real browsers, or compute/time not available in-phase.

### D1: Real multi-browser live-share UX — DEFER-25-01
- **What:** Two actual browser clients attach by share URL; second client sees streamed output in real time; read-only enforcement visible to user (no input box)
- **How:** Manual test: start a running session, mint a share URL, open in a second browser profile (or incognito), verify live deltas render, verify no input affordance
- **Why deferred:** Requires a running instance, real browser, and SSE-over-HTTP framing; service-level tests do not exercise HTTP framing or EventSource reconnects
- **Validates at:** manual-review (post-phase-25-deploy)
- **Depends on:** Deployed instance with a running session
- **Target:** Second browser receives deltas within 500ms of broadcast; no input box visible on the read scope view
- **Risk if unmet:** SSE framing bug (chunked encoding, Content-Type, keep-alive) invisible to service-level tests; SharedSessionView.vue may not render correctly

### D2: Real enforce_action round-trip under a live policy — DEFER-25-02
- **What:** A real co-drive message routed through the live Phase-23 policy engine (not seeded/mocked) produces the correct DENY/ASK/ALLOW outcome; ASK approval round-trip completes within an acceptable latency
- **How:** Integration test against a live policy-enforced session; measure time from ASK event to approval to unblocked send_input
- **Why deferred:** Requires Phase 23 deployed and a real policy seeded in the operator's session scope; ASK latency requires real network timing
- **Validates at:** phase-26-integration (or first post-25/26 full integration test run)
- **Depends on:** Phase 23 merged + deployed; operator session with real policy
- **Target:** ASK round-trip < 5s under manual approval; DENY blocking is synchronous (no latency target)
- **Risk if unmet:** Policy enforcement latency may degrade UX for co-drive; if ASK timeout is too short, teammate messages time out silently

### D3: Mid-stream session fork under a running process — DEFER-25-03
- **What:** Fork a session while the harness process is actively running; verify the parent process is not interrupted and the child session starts from the seeded transcript
- **How:** Manual test: start a long-running session, fork mid-stream, verify parent continues outputting and child starts fresh from branch point
- **Why deferred:** Requires a real running harness process; test_session_fork.py uses lightweight stand-ins for ProjectSessionManager that do not exercise subprocess interaction
- **Validates at:** manual-review (post-phase-25-deploy)
- **Depends on:** Deployed instance with a running harness session
- **Target:** Parent output uninterrupted; child session starts correctly from branch transcript; no process cross-wiring
- **Risk if unmet:** process-level state (subprocess pipes) may be entangled in ways not visible to unit tests

### D4: Real OIDC provider end-to-end (Google, GitHub, or Okta) — DEFER-25-04
- **What:** Complete OIDC authorization code flow against a live provider; id_token JWKS validation succeeds; user is found/created; session cookie is set
- **How:** Manual test: configure a real OIDC provider in the running instance; navigate to Login and click SSO; complete the provider's auth UI; verify redirect back with session cookie
- **Why deferred:** Requires live provider credentials and registered redirect URI; JWKS fetch and id_token crypto cannot be fully exercised by mocked authlib
- **Validates at:** manual-review (requires provider credentials)
- **Depends on:** A registered OAuth application at one provider (Google, GitHub, or Okta)
- **Target:** Login completes in < 10s from SSO button click; session cookie set; user appears in DB; X-API-Key path unaffected
- **Risk if unmet:** Provider-specific token quirks (claim naming, JWKS rotation, nonce handling) may cause callback failures not caught by mocked tests; fallback is disabling OIDC config and relying on API-key auth

---

## Ablation Plan

**No ablation plan** — Phase 25 implements four independent product features, each with its own success criterion. There are no sub-components to isolate within a feature; the correctness of each feature is tested directly by its behavioral tests. The Phase-23 policy engine dependency (co-drive) is itself externally tested; no ablation of the policy gate is appropriate here.

---

## WebMCP Tool Definitions

Phase 25 modifies frontend views (SharedSessionView.vue, LoginPage.vue) but WebMCP availability is not confirmed for this evaluation. WebMCP tool definitions are included for completeness and will be used by the grd-verifier if WebMCP is available.

### Generic Checks

| Tool | Purpose | Expected |
|------|---------|----------|
| hive_get_health_status | Backend health after Phase-25 deploy | status: healthy |
| hive_check_console_errors | No JS errors from SharedSessionView or LoginPage changes | No new errors |
| hive_get_page_info | App renders after routing changes | Page loads with expected content |

### Page-Specific Tools

| Tool | Page | Purpose | Expected |
|------|------|---------|----------|
| hive_check_shared_session_readonly | /shared/{token} | SharedSessionView renders deltas, no input box | Delta stream visible; no textarea/input element |
| hive_check_login_sso_buttons | /login | SSO buttons appear for configured providers | Provider buttons visible; existing API-key form intact |

### useWebMcpTool() Definitions

```js
// Generic health checks
useWebMcpTool("hive_get_health_status", {})
useWebMcpTool("hive_check_console_errors", { since: "phase_start" })
useWebMcpTool("hive_get_page_info", {})

// Shared session read-only view
useWebMcpTool("hive_check_shared_session_readonly", {
  url: "/shared/{token}",
  checks: ["delta_stream_visible", "no_input_element", "read_only_indicator"]
})

// Login page SSO buttons
useWebMcpTool("hive_check_login_sso_buttons", {
  url: "/login",
  checks: ["sso_button_visible", "api_key_form_intact"]
})
```

---

## Baselines

| Baseline | Description | Expected Behavior | Source |
|----------|-------------|-------------------|--------|
| Single-attach owner-only stream | Pre-phase behavior: only owner can stream a session | Owner streams; no sharing | Pre-existing code |
| API-key-only auth | Pre-phase behavior: X-API-Key is the only auth path | API-key requests authenticated | Pre-existing code |
| 7 known frontend failures | Pre-existing failures: RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine | These 7 fail; no others | CLAUDE.md |
| No policy enforcement on send_input | Pre-phase behavior: send_input is called directly by the operator | No policy gate exists | Pre-existing code |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_session_shares.py           # S3, P1
backend/tests/test_stream_project_session_gate.py  # S4, P2
backend/tests/test_co_drive.py                 # P3 (GATED)
backend/tests/test_session_fork.py             # S5, P4
backend/tests/test_oidc_auth.py                # S6, P5
backend/tests/test_live_share_e2e.py           # P6 (GATED)
backend/tests/test_phase25_locale_parity.py    # S7
```

**How to run ungated evaluation (pre-Phase-23 merge):**
```bash
cd /Users/neo/Developer/Projects/Agented
just build  # S2
cd backend
uv run ruff format --check .  # S1
uv run pytest \
  tests/test_session_shares.py \
  tests/test_stream_project_session_gate.py \
  tests/test_session_fork.py \
  tests/test_oidc_auth.py \
  tests/test_phase25_locale_parity.py \
  tests/test_project_session_manager.py \
  -q
cd ../frontend
npm run test:run  # P7
```

**How to run full evaluation (post-Phase-23 merge):**
```bash
# Attempt full suite under ~12-min watchdog; on hang at ~40-48%, kill and run:
cd /Users/neo/Developer/Projects/Agented/backend
uv run pytest \
  tests/test_session_shares.py \
  tests/test_stream_project_session_gate.py \
  tests/test_co_drive.py \
  tests/test_session_fork.py \
  tests/test_oidc_auth.py \
  tests/test_live_share_e2e.py \
  tests/test_phase25_locale_parity.py \
  tests/test_project_session_manager.py \
  tests/test_policy_enforcement.py \
  tests/test_policy_evaluator.py \
  -q
# DISCLOSE substitution if watchdog triggered — never present targeted run as full suite
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: ruff format --check | [PASS/FAIL] | | |
| S2: just build | [PASS/FAIL] | | |
| S3: test_session_shares.py | [PASS/FAIL] | | |
| S4: test_stream_project_session_gate.py | [PASS/FAIL] | | |
| S5: test_session_fork.py | [PASS/FAIL] | | |
| S6: test_oidc_auth.py | [PASS/FAIL] | | |
| S7: test_phase25_locale_parity.py | [PASS/FAIL] | | |

### Proxy Results

| Metric | Criterion | Status | Phase-23 Gate | Notes |
|--------|-----------|--------|--------------|-------|
| P1: two-client attach | 1 | [PASS/FAIL] | No | |
| P2: non-owner 404 | 2 | [PASS/FAIL] | No | |
| P3: DENY/ASK/ALLOW co_drive | 3 | [PASS/FAIL/PENDING] | YES — wait for Phase 23 | |
| P4: fork immutability | 4 | [PASS/FAIL] | No | |
| P5: OIDC mocked + X-API-Key regression | 5 | [PASS/FAIL] | No | |
| P6: live-share + co-drive e2e | 6 | [PASS/FAIL/PENDING] | YES — wait for Phase 23 | |
| P7: frontend no new failures | 7 partial | [PASS/FAIL] | No | Known failures: [count] |
| P8: backend targeted regression | 7 partial | [PASS/FAIL] | Partial | Watchdog substitution: [Y/N] |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-25-01 | Real multi-browser live-share UX | PENDING | manual-review |
| DEFER-25-02 | Real enforce_action round-trip + ASK latency | PENDING | phase-26-integration |
| DEFER-25-03 | Mid-stream fork under running process | PENDING | manual-review |
| DEFER-25-04 | Real OIDC provider end-to-end | PENDING | manual-review (requires provider credentials) |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH for correctness; MEDIUM for integration

**Justification:**
- Sanity checks: adequate — format, build, and all four feature modules covered with exact commands
- Proxy metrics: well-evidenced — each test directly exercises the stated behavior (not a surrogate); co-drive tests are gated cleanly rather than skipped silently
- Deferred coverage: partial — the four deferred items are real gaps (HTTP framing, real OIDC, live subprocess fork, real network ASK latency), all acknowledged explicitly

**What this evaluation CAN tell us:**
- Whether the token mint/resolve/revoke/expire DB layer is correct
- Whether the stream gate correctly blocks non-owners
- Whether fork_to_run does not mutate parent conversations
- Whether the OIDC code path finds/creates users and sets cookies (mocked exchange)
- Whether the policy gate order is respected (GATED: only after Phase 23)
- Whether any of the 7 known frontend failures have grown to 8+
- Whether 4-locale parity holds for all new i18n namespaces

**What this evaluation CANNOT tell us:**
- Whether SSE chunked-encoding framing works over a real HTTP connection (deferred to D1)
- Whether a real OIDC provider's JWKS rotation or claim naming causes failures (deferred to D4)
- Whether a running harness process is correctly isolated from a fork (deferred to D3)
- Whether ASK round-trip UX is acceptable under real network conditions (deferred to D2)
- Whether the full backend suite is clean (known hang; watchdog substitution disclosed, not resolved)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-30*
