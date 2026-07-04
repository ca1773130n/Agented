# Evaluation Plan: Phase 24 — OS-level harness sandboxing + egress control

**Designed:** 2026-06-30
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** `sandbox_wrap.build_sandbox_prefix` (bwrap/seatbelt), `egress_proxy` (L7 deny-by-default allowlist), `cloud_sandbox_runner.select_runner` (E2B/Modal), execution-service Popen seam + Phase-23 `enforce_sandbox` gate
**Reference papers:** none — security/ops phase, no research-paper benchmarks. Targets are boolean pass/fail or count-based.

## Evaluation Overview

This phase generalizes the existing `sandbox_eval.py` isolation to every live harness `subprocess.Popen`, fronts it with an L7 egress allowlist that is deny-by-default for autonomous/auto-implement runs, and adds an optional cloud-sandbox runner. Because the strongest guarantee — a *real* sandbox-escape attempt being blocked by the kernel — requires the OS primitive (Linux bwrap + unprivileged user namespaces) that is absent on the dev macOS box and on CI runners without the primitive, the binding success criterion (crit-5) is **deferred** to a Linux host that has the primitive. Everything verifiable without the live kernel primitive is pulled forward into Tier 1 (composition/degrade unit tests) and Tier 2 (the gate-refuses-launch integration test, the Popen-site sweep, and deny-by-default egress).

The roadmap pegs this phase at **proxy** verification level, which matches: Tier 1 + Tier 2 establish that the wiring is correct and that the *control logic* (refuse-to-launch, route-through-prefix, deny-by-default) behaves as specified, while the actual OS-enforced containment is honestly deferred to Tier 3.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| sandbox prefix argv / SBPL composition | crit-1, REQ-31 | Confirms `build_sandbox_prefix` emits the right bwrap/seatbelt invocation before any kernel is involved |
| graceful degrade + logged warning | crit-1 | A missing primitive must degrade (not crash) and leave an audit trail |
| egress allow-pass / deny-block + deny-log | crit-2, REQ-32 | Deny-by-default for autonomous is the security-relevant behavior |
| 6/6 Popen sites wrapped | crit-1 (sweep), CLAUDE.md bug-class-sweep rule | Any unwrapped launch site is a hole in the guarantee |
| enforce_sandbox DENY → Popen NOT called | crit-4, REQ-31, Phase-23 seam | The Phase-23 policy must be able to refuse an unsandboxed launch |
| cloud runner selection + absent-credential skip | crit-3, REQ-33 | Optional feature must select correctly and degrade gracefully without creds |
| real escape blocked + logged | crit-5 | The actual containment guarantee — deferred (needs kernel primitive) |
| house gates | crit-6, CLAUDE.md | Repo-wide green bar |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 5 | Format/lint + unit suites + build no-op stays green |
| Proxy (L2) | 5 | Gate-refuses-launch, Popen-sweep coverage, deny-by-default egress, backend targeted suite, frontend no-new-failures |
| Deferred (L3) | 3 | Real escape test on bwrap host, live E2B/Modal run, prod-image primitive check |

---

## Level 1: Sanity Checks

**Purpose:** Verify the new modules are well-formed and their unit logic holds — runs in seconds, no kernel primitive needed. ALL must pass before Tier 2.

### S1: Ruff format + lint on new modules
- **What:** New backend modules are formatted (line-length=100, py310) and lint-clean.
- **Command:** `cd backend && uv run ruff format --check app/services/sandbox_wrap.py app/services/egress_proxy.py app/services/cloud_sandbox_runner.py && uv run ruff check app/services/sandbox_wrap.py app/services/egress_proxy.py app/services/cloud_sandbox_runner.py`
- **Expected:** Exit 0, "All checks passed", no reformat diff.
- **Failure means:** Style/lint regression — fix before proceeding.

### S2: sandbox_wrap unit suite (argv/SBPL composition + degrade)
- **What:** `build_sandbox_prefix` emits a correct bwrap argv on Linux and SBPL profile on macOS; when the primitive is absent it returns the no-op/degrade prefix AND emits a logged warning.
- **Command:** `cd backend && uv run pytest tests/test_sandbox_wrap.py -v`
- **Expected:** 100% of tests pass. Must cover: (a) Linux bwrap argv contains `--unshare-net`/bind-workspace flags; (b) macOS seatbelt SBPL composed; (c) detect+probe path; (d) degrade path returns prefix that still launches AND a `logger.warning` deny/degrade line is asserted (spy on `module.logger.warning` per CLAUDE.md).
- **Failure means:** Prefix composition or degrade contract broken.

### S3: egress_proxy unit suite (allow pass / deny block + deny-log)
- **What:** The asyncio CONNECT/HTTP proxy passes an allowlisted host, blocks a non-allowlisted host with a 403, and writes exactly one deny-log line per denial.
- **Command:** `cd backend && uv run pytest tests/test_egress_proxy.py -v`
- **Expected:** 100% pass. Must cover: allowlisted host → tunnel established; denied host → 403 (CONNECT 403 / HTTP 403); each denial → exactly 1 deny-log line; `proxy_env` builder returns `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` correctly.
- **Failure means:** Egress control logic incorrect — security-relevant, blocks progression.

### S4: cloud_sandbox_runner unit suite (selection + absent-credential skip)
- **What:** `select_runner` picks E2B/Modal/local per config; with no credentials it returns the local runner (graceful skip), never raising.
- **Command:** `cd backend && uv run pytest tests/test_cloud_sandbox_runner.py -v`
- **Expected:** 100% pass. Must cover: explicit E2B selection when creds present (mocked); explicit Modal selection when creds present (mocked); absent-credential → falls back to local + logged skip (no exception).
- **Failure means:** Runner selection or graceful-skip contract broken.

### S5: `just build` stays green (frontend no-op gate)
- **What:** Backend-only phase must not break the frontend type-check/build.
- **Command:** `just build`
- **Expected:** Exit 0 (vue-tsc + vite). Effectively a no-op for this phase but must remain green.
- **Failure means:** Unexpected frontend coupling — investigate.

**Sanity gate:** S1–S5 must ALL pass. Any failure blocks Tier 2.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of the *control logic* and *coverage* — establishes the wiring is correct without the live kernel primitive.
**IMPORTANT:** These prove the harness *would* be sandboxed and egress *would* be denied per the control paths; they do NOT prove the OS kernel actually contains an escape. That guarantee is Tier 3 (crit-5). Treat Tier 2 green as "correctly wired", not "proven contained".

### P1: enforce_sandbox DENY refuses to launch an unsandboxed harness
- **What:** When Phase-23 policy yields `enforce_sandbox` and the sandbox prefix cannot be applied (degrade on a host where the policy *requires* enforcement), the execution seam refuses to launch — `subprocess.Popen` is NOT called.
- **How:** Integration test mocks `PolicyContext.sandbox_enabled`/`enforce_action` to DENY-unsandboxed and asserts Popen is not invoked + a refusal is surfaced.
- **Command:** `cd backend && uv run pytest tests/test_execution_service.py -k "enforce_sandbox or sandbox_refuse or unsandboxed" -v`
- **Target:** Test passes; `Popen` mock assert_not_called(); refusal logged.
- **Evidence:** crit-4, REQ-31, Phase-23 enforce_sandbox seam. Directly measures the same control the requirement specifies.
- **Correlation with real guarantee:** HIGH — this is the exact pre-Popen gate; only the *underlying* containment is deferred.
- **Blind spots:** Does not prove the sandbox, once applied, actually contains; only that an *unsandboxed* launch is refused when policy requires enforcement.
- **Validated:** No — full containment awaits D1.

### P2: Popen-site sweep coverage (6/6 launch sites routed through build_sandbox_prefix)
- **What:** All 6 harness launch sites (the execution-service chokepoint + the 5 swept sites from 24-03) route their command through `build_sandbox_prefix` (and proxy_env) before Popen.
- **How:** A coverage test parametrized over the 6 known sites, OR a static-assertion test that each site's command construction calls the prefix builder; assert count == 6.
- **Command:** `cd backend && uv run pytest tests/test_execution_service.py -k "popen_sweep or sandbox_prefix_applied or all_launch_sites" -v`
- **Target:** **6/6 sites** wrapped. 0 unwrapped sites.
- **Evidence:** crit-1 sweep; CLAUDE.md bug-class-sweep rule ("grep every caller, fix in shared layer + defense-in-depth").
- **Correlation:** HIGH for coverage; an unwrapped site is a literal hole.
- **Blind spots:** Confirms the call is present, not that the resulting argv is honored by the kernel (Tier 3).
- **Validated:** No.

### P3: Deny-by-default egress for autonomous / auto-implement runs
- **What:** For autonomous and auto-implement run modes, the egress policy is deny-by-default — only the explicit allowlist passes; everything else is blocked + logged.
- **How:** Integration test exercises an autonomous-mode run config through the proxy_env wiring: allowlisted host succeeds, a non-allowlisted host is blocked (403) and produces exactly one deny-log line.
- **Command:** `cd backend && uv run pytest tests/test_egress_proxy.py tests/test_execution_service.py -k "deny_by_default or autonomous_egress or auto_implement_egress" -v`
- **Target:** allowlisted host → pass; denied host → **403 + exactly 1 deny-log line**; default posture for autonomous == deny.
- **Evidence:** crit-2, REQ-32.
- **Correlation:** HIGH — measures the deny-by-default posture directly via the real proxy.
- **Blind spots:** Uses the in-process proxy; does not prove a child process cannot bypass the proxy via a hardcoded socket (that bypass-resistance is part of D1's network-escape test).
- **Validated:** No — bypass-resistance awaits D1.

### P4: Backend targeted pytest suite (under hang watchdog)
- **What:** Backend regression across sandbox/egress/execution/streaming/policy-seam suites stays green.
- **How:** Per CLAUDE.md, attempt the full serial suite under a ~12-min watchdog; the suite is known to hang at ~40–48% with no failures before the hang. On hang, kill and run the comprehensive targeted set below; disclose the substitution in the PR.
- **Command (attempt full, watchdog):** `cd backend && timeout 720 uv run pytest`
- **Command (targeted substitution on hang):** `cd backend && uv run pytest tests/test_sandbox_wrap.py tests/test_egress_proxy.py tests/test_cloud_sandbox_runner.py tests/test_execution_service.py tests/test_conversation_streaming.py tests/test_sandbox_eval.py -v` (plus any policy-seam suite touched by Phase-23 wiring, e.g. `tests/test_*policy*.py`)
- **Target:** 0 failures in the targeted set. If full suite completes, 0 new failures vs baseline.
- **Evidence:** crit-6, CLAUDE.md verification procedure.
- **Correlation:** HIGH for regression coverage of the touched seams.
- **Blind spots:** Targeted substitution may miss an unrelated regression beyond the hang point — disclosed per procedure.
- **Validated:** N/A (regression gate).

### P5: Frontend `npm run test:run` — no NEW failures
- **What:** Frontend suite carries 7 known pre-existing failures (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas). Gate is no NEW failures.
- **Command:** `cd frontend && npm run test:run`
- **Target:** Failures ≤ 7 baseline; **0 new** failures. (Backend-only phase — expected exactly the 7 baseline.)
- **Evidence:** crit-6, CLAUDE.md frontend gate.
- **Correlation:** HIGH (regression gate).
- **Validated:** N/A.

---

## Level 3: Deferred Validations

**Purpose:** The actual OS-enforced containment guarantee and live cloud runs — require the kernel primitive or real credentials not available in dev/CI.

### D1: Real sandbox-escape attempt blocked + logged — DEFER-24-01
- **What:** crit-5. A child harness attempts (a) writing a file outside its workspace and (b) connecting to a non-allowlisted host. Both must be blocked by the OS sandbox + egress proxy and logged.
- **How:** Run the escape-verification integration test (from 24-05) on a Linux host with **bwrap installed and unprivileged user namespaces enabled**. Assert the out-of-workspace write fails (EPERM/EACCES) and the non-allowlisted connect is refused, with both denials logged.
- **Why deferred:** Dev box is macOS; CI runners lack the bwrap + unprivileged-userns primitive. The test must `skip` cleanly where the primitive is absent (assert the skip-marker fires on dev/CI).
- **Command (on primitive host):** `cd backend && uv run pytest tests/test_sandbox_escape.py -v -m sandbox_escape`
- **Command (dev/CI — assert clean skip):** `cd backend && uv run pytest tests/test_sandbox_escape.py -v -rs` → expect SKIPPED with reason "bwrap/unprivileged-userns unavailable".
- **Validates at:** A Linux host/runner with the primitive (provision in Phase 26 deploy, or a dedicated runner).
- **Depends on:** bwrap binary + `kernel.unprivileged_userns_clone=1` (or equivalent).
- **Target:** Out-of-workspace write → blocked; non-allowlisted connect → blocked; both → 1 log line each.
- **Risk if unmet:** The headline containment guarantee is unproven — the sandbox may be misconfigured even with green Tier 1/2. **Mitigation:** Tier 1 asserts argv/SBPL composition; treat phase as "wired, containment-unverified" until D1 runs; budget a follow-up if escape succeeds.
- **Fallback:** If bwrap unavailable in prod, document the degrade posture and require the policy to refuse enforcement-required runs (P1 covers the refusal path).

### D2: Live E2B / Modal cloud run with real credentials — DEFER-24-02
- **What:** crit-3. Select and execute an actual auto-implement/autonomy iteration inside an E2B or Modal cloud sandbox.
- **How:** Provide real E2B or Modal credentials; run one short auto-implement iteration through `select_runner` → cloud adapter; assert the run completes inside the cloud sandbox and returns output.
- **Why deferred:** No live cloud credentials in dev/CI; the unit suite (S4) covers selection + graceful skip only.
- **Validates at:** Manual operator run with credentials, or a credentialed integration runner.
- **Depends on:** `E2B_API_KEY` or Modal token configured.
- **Target:** One cloud iteration completes; output returned; no credential leak in logs.
- **Risk if unmet:** Cloud adapters work in mock only; a real-API mismatch could surface. **Mitigation:** adapters are credential-gated and skip gracefully (S4) — absence does not break local runs.
- **Fallback:** Cloud runner stays optional; local sandbox (D1) is the primary path.

### D3: bwrap + unprivileged-userns present in prod deploy image — DEFER-24-03
- **What:** The production deploy image ships bwrap and has unprivileged user namespaces enabled, so enforcement-required runs are not silently degraded in prod.
- **How:** Image-build assertion / runtime probe at deploy: `which bwrap` and read `kernel.unprivileged_userns_clone`.
- **Why deferred:** Deploy image hardening is owned by the deployment-ergonomics phase.
- **Validates at:** **phase-26-deployment-extensibility-ergonomics** (flag carried forward).
- **Depends on:** Deploy image definition / Dockerfile.
- **Target:** `bwrap` on PATH; unprivileged userns enabled.
- **Risk if unmet:** Prod degrades to no-op sandbox; with enforce_sandbox policy, runs get refused (P1) — safe-fail but blocks autonomous runs. **Mitigation:** raise as a Phase-26 deploy requirement.
- **Fallback:** Operator docs (24-05) document the primitive requirement.

---

## Ablation Plan

**No ablation plan** — this phase composes three cooperating mechanisms (sandbox prefix, egress proxy, policy gate) rather than tuning a single model with isolable sub-components. The Popen-site sweep (P2) and the degrade path (S2) already isolate "with/without sandbox prefix"; the deny-by-default test (P3) isolates "with/without allowlist".

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views (backend-only: `app/services/*`, no HTML/JSX/Vue/CSS or frontend routes in scope).

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Frontend known failures | Pre-existing failing tests | 7 (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine) | CLAUDE.md |
| Backend full-suite hang | Serial suite hangs ~40–48%, no failures before hang | known issue | CLAUDE.md |
| sandbox_eval.py isolation | Existing eval-time sandbox this phase generalizes | working | repo (`app/services/sandbox_eval.py`) |
| Popen launch sites | Harness launch sites to wrap | 6 (1 chokepoint + 5 swept) | 24-03 plan |

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_sandbox_wrap.py          # S2
backend/tests/test_egress_proxy.py          # S3, P3
backend/tests/test_cloud_sandbox_runner.py  # S4
backend/tests/test_execution_service.py     # P1, P2 (+ P3 wiring)
backend/tests/test_sandbox_escape.py        # D1 (skips without primitive)
```

**How to run full evaluation (Tier 1 + Tier 2):**
```bash
# Tier 1
cd backend && uv run ruff format --check app/services/sandbox_wrap.py app/services/egress_proxy.py app/services/cloud_sandbox_runner.py && uv run ruff check app/services/sandbox_wrap.py app/services/egress_proxy.py app/services/cloud_sandbox_runner.py
cd backend && uv run pytest tests/test_sandbox_wrap.py tests/test_egress_proxy.py tests/test_cloud_sandbox_runner.py -v
just build
# Tier 2
cd backend && uv run pytest tests/test_execution_service.py -k "enforce_sandbox or sandbox_refuse or unsandboxed or popen_sweep or sandbox_prefix_applied or all_launch_sites or deny_by_default or autonomous_egress or auto_implement_egress" -v
cd backend && timeout 720 uv run pytest   # full attempt; on hang → targeted substitution (see P4)
cd frontend && npm run test:run
```

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1 ruff format/lint | [PASS/FAIL] | | |
| S2 sandbox_wrap unit | [PASS/FAIL] | | |
| S3 egress_proxy unit | [PASS/FAIL] | | |
| S4 cloud_runner unit | [PASS/FAIL] | | |
| S5 just build | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1 gate refuses unsandboxed | Popen not called | | [MET/MISSED] | |
| P2 Popen-site sweep | 6/6 wrapped | | [MET/MISSED] | |
| P3 deny-by-default egress | 403 + 1 deny-log | | [MET/MISSED] | |
| P4 backend targeted suite | 0 failures | | [MET/MISSED] | full or targeted? disclose |
| P5 frontend test:run | 0 new (≤7) | | [MET/MISSED] | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-24-01 | Real escape blocked+logged | PENDING — 2026-07-04 macOS run: `test_sandbox_escape.py` seatbelt profile OVER-restricts (denies interpreter's own path-cache read → `PermissionError` at the "legit run still works" precondition). Confirms the wrap denies aggressively; the escape-blocked assertions need a Linux/bwrap host to run past the precondition. Env-dependent, tracked here. | Linux host w/ bwrap + userns |
| DEFER-24-02 | Live E2B/Modal run | PENDING | credentialed manual/integration run |
| DEFER-24-03 | bwrap+userns in prod image | PENDING | phase-26-deployment-extensibility-ergonomics |

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM-HIGH

**Justification:**
- Sanity checks: adequate — composition, degrade, allow/deny, and runner-selection logic are all unit-testable without the kernel primitive.
- Proxy metrics: well-evidenced — the gate-refusal (P1), 6/6 sweep (P2), and deny-by-default (P3) measure the exact control logic the requirements specify, through the real proxy and the real seam.
- Deferred coverage: comprehensive on the *limitation* — the one thing Tier 1/2 cannot prove (actual OS containment of a real escape) is explicitly D1, with the dev/CI skip-marker asserted so green CI never masquerades as proven containment.

**What this evaluation CAN tell us:**
- The sandbox prefix and SBPL are composed correctly and degrade with a logged warning.
- All 6 harness launch sites route through the sandbox prefix + proxy_env (no holes).
- Autonomous/auto-implement egress is deny-by-default; denied hosts get 403 + a deny-log line.
- The Phase-23 policy can refuse to launch an unsandboxed harness (Popen not called).
- The cloud runner selects correctly and skips gracefully without credentials.

**What this evaluation CANNOT tell us (and when it will be):**
- Whether the OS kernel actually blocks a real escape (out-of-workspace write + non-allowlisted connect) — **D1**, on a bwrap + unprivileged-userns Linux host.
- Whether a child can bypass the in-process proxy via a raw socket — **D1** (network-escape leg).
- Whether E2B/Modal work against the real API — **D2**, with credentials.
- Whether prod actually ships the primitive — **D3**, in Phase 26.

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-30*
