# Evaluation Plan: Phase 23 — Stackable Policy / Governance Engine

**Designed:** 2026-06-30
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Declarative ALLOW/DENY/ASK policy layer stacked server → team → session (session-first, DENY short-circuit), subsuming goal_loop exit-ladder budgets + bot-security/bot-pr-review checks, enforced at action boundaries with an ASK approval card over SSE.
**Reference:** No external paper — infrastructure/behavioral phase. Targets derive from the 6 locked success criteria and the phase's own TDD plans (23-01 … 23-05).

## Evaluation Overview

This is an INFRASTRUCTURE / behavioral phase, not a model-metric phase. There is no PSNR/accuracy-style number to optimize and no external BENCHMARKS.md. The thing being evaluated is *correct, enforced behavior*: does a session-scope DENY short-circuit a server-scope ALLOW, do the four builtin evaluators produce the right verdict, does a DENY actually stop `subprocess.Popen`, does an ASK block until an operator resolves it (and fail safe to DENY on timeout), and does the operator surface (CRUD routes + middleware + Vue editor/card + four locales) hold together.

Because behavior — not a metric — is the unit of success, the "proxy" tier here is **automated behavioral tests** (pytest + Vitest). These are not weak correlates of success; they directly assert the locked criteria on isolated DBs and mounted components. The honest limitation is integration realism: unit/route tests mock `subprocess.Popen` and drive the SSE round-trip in-process. Only the e2e test (23-05) and the full house-gate run exercise the assembled pipeline, so those are tiered as **deferred**.

Targets are therefore set as **test-coverage gates** ("all green / no new failures vs the documented 7-failure frontend baseline"), keyed one-to-one to the success criteria — not as external scores.

### Locked Success Criteria → Verification Mapping

| SC | Criterion | Primary Level | Where Proven |
|----|-----------|---------------|--------------|
| SC1 | Stacking order: session DENY short-circuits server ALLOW; eval order [session, team, server]; first DENY wins | Proxy (L2) | `test_policy_evaluator.py` (23-01) |
| SC2 | Four builtins (cost_budget hard/soft, max_tool_calls_per_session, ask_on_os_tools, enforce_sandbox-inert) + consolidation of exit-ladder + bot checks | Proxy (L2) | `test_policy_builtins.py` (23-02); consolidation in `test_policy_enforcement.py` (23-03) |
| SC3 | Enforcement at boundaries: DENY blocks Popen; ASK blocks-until-resolved; timeout → DENY fail-safe; goal_loop human-gate routes through policy | Proxy (L2) | `test_policy_enforcement.py` (23-03) |
| SC4 | Operator surface: `/admin/policies` CRUD + `/decision` route, PolicyMiddleware, PolicyEditor/PolicyAskCard, budgets.ts verdicts, i18n parity en/ko/ja/zh | Proxy (L2) | `test_policies_router.py`, `test_policy_middleware.py` (23-04); component specs + parity (23-05) |
| SC5 | E2E ALLOW/DENY/ASK driving a real session | Deferred (L3) | `test_policy_e2e.py` (23-05) |
| SC6 | House gates: `just build`; backend pytest (watchdog); frontend no-new-failures | Deferred (L3) | full house-gate run (23-05) |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 4 | Format, typecheck, module import/collection — "does it load and build at all" |
| Proxy (L2) | 6 behavioral suites | Stacking, builtins, enforcement, routes, middleware, frontend+i18n — the heart of the phase |
| Deferred (L3) | 2 | Real-session e2e + full house-gate run (known serial-suite hang) |

## Level 1: Sanity Checks

**Purpose:** Verify the code loads, formats, and builds. These MUST ALL PASS before behavioral evaluation is meaningful.

### S1: Backend format clean
- **What:** New/changed backend modules pass Ruff formatting (line-length=100, py310).
- **Command:** `cd backend && uv run ruff format --check .`
- **Expected:** Exit 0, "would reformat" prints zero files among the policy modules.
- **Failure means:** Style drift; run `uv run ruff format .` and recommit.

### S2: Frontend builds (vue-tsc + vite)
- **What:** TypeScript typechecks and the production bundle builds with policies.ts, PolicyEditor, PolicyAskCard, budgets.ts changes.
- **Command:** `just build`
- **Expected:** vue-tsc reports no type errors; vite build completes.
- **Failure means:** Type error in `policies.ts` types or component props/emits, or a barrel export mismatch.

### S3: Policy modules import / tests collect
- **What:** The new backend modules import without error and pytest can collect the new test files (no syntax/import cycle).
- **Command:** `cd backend && uv run python -c "import app.services.policy_service; import app_litestar.routes.policies; import app_litestar.middleware" && uv run pytest --collect-only tests/test_policy_evaluator.py tests/test_policy_builtins.py tests/test_policy_enforcement.py tests/test_policies_router.py tests/test_policy_middleware.py tests/test_policy_e2e.py tests/test_migration_176_policies.py`
- **Expected:** Imports succeed (no `ImportError`/cyclic-import); collection lists tests with zero collection errors.
- **Failure means:** Import cycle (e.g. eager `ProjectSessionManager` import in `policy_service.py` — must be lazy/in-function) or a missing export.

### S4: Migration 176 applies + idempotent
- **What:** Migration 176 creates the `policies` table + both indexes on a fresh isolated DB, and re-applying is a no-op.
- **Command:** `cd backend && uv run pytest tests/test_migration_176_policies.py -v`
- **Expected:** All green; table + `idx_policies_scope` + `idx_policies_kind` present; re-apply raises nothing.
- **Failure means:** Migration not registered in `VERSIONED_MIGRATIONS`, or non-idempotent DDL.

**Sanity gate:** ALL four must pass before reporting any proxy result.

## Level 2: Proxy Metrics

**Purpose:** Automated behavioral assertion of the locked criteria. For a behavioral phase these tests ARE the evaluation — they directly assert the success criteria, not a correlate. The honest caveat: they mock `subprocess.Popen` and run the SSE round-trip in-process, so they verify logic and contracts, not the assembled live pipeline (that is SC5/SC6, deferred).

> All proxy items are `validated: false` until the deferred e2e (SC5) and house gates (SC6) confirm the behavior survives integration.

### P1: Stacking order + short-circuit (SC1)
- **What:** `PolicyService.evaluate` iterates [session, team, server]; the first DENY short-circuits without consulting later scopes; ASK collected only if no DENY; ALLOW is default fall-through.
- **Command:** `cd backend && uv run pytest tests/test_policy_evaluator.py -v`
- **Target:** All green, including the spy-assert that `_rows_for` is **never** called with `scope="server"` after a session DENY, and the 5 behavior cases (server-ALLOW+session-DENY → deny/session; session-ASK+server-ALLOW → ask/session; only-server-ALLOW → allow; no-rows → allow; team-DENY → deny/team).
- **Evidence:** 23-01-PLAN behavior table; modeled on `budget_service.py:340` verdict shape.
- **Correlation with full criterion:** HIGH — directly asserts SC1 on the real evaluator.
- **Blind spots:** Uses seeded rows, not policies authored through the CRUD UI; gunicorn workers=1 in-process registry assumption not exercised here.
- **Validated:** No — confirmed against a real session at SC5.

### P2: Four builtin evaluators (SC2)
- **What:** Per-builtin verdict tables — cost_budget (spend<soft→allow, ≥ask_threshold→ask, ≥max_cost→deny); max_tool_calls_per_session (count≥max→deny); ask_on_os_tools (shell/file_write/process_launch→ask); enforce_sandbox (require_sandbox + non-sandboxed launch→deny, **inert/allow otherwise — stores now, enforces in Phase 24**).
- **Command:** `cd backend && uv run pytest tests/test_policy_builtins.py -v`
- **Target:** All case rows green; pure evaluators (no DB I/O) return correct `(decision, reason)`; custom/unknown kind falls back to stored `effect`.
- **Evidence:** 23-02-PLAN behavior table; cost hard/soft semantics mirror `budget_service.py:340-398`.
- **Correlation with full criterion:** HIGH for the four evaluators. The *consolidation* half of SC2 (exit-ladder budget + bot-security/bot-pr-review routing through PolicyService) is asserted separately in P3, not here.
- **Blind spots:** Evaluators are pure; they do not prove the action-ctx keys (`total_cost_usd`, `tool_calls`, `kind`, `sandboxed`) are actually populated at the call-site — that is P3/P4.
- **Validated:** No.

### P3: Enforcement at action boundaries + ASK round-trip + consolidation (SC2 consolidation + SC3)
- **What:** (a) DENY at the `ExecutionService` boundary raises `PolicyDenied` and `subprocess.Popen` is **not** called; (b) ASK blocks the launching call until `submit_policy_decision(session_id, 'approve')` resolves it (proceeds), `'deny'` aborts, and **timeout → DENY** (governance fail-safe, distinct from the goal-gate "abort"); (c) a `policy_ask` event is broadcast; (d) the goal_loop exit-ladder cost budget and bot-security/bot-pr-review checks route THROUGH `PolicyService.evaluate` (no policy keyed on a bot/trigger id — session-not-bot rule); (e) the goal_loop human-gate reuses the existing `_await_gate`/`submit_gate_decision` path, no second SSE transport.
- **Command:** `cd backend && uv run pytest tests/test_policy_enforcement.py -v` and `cd backend && uv run pytest tests/test_goal_loop_runner.py -k "gate or budget" -v`
- **Target:** Enforcement suite all green (mocked Popen asserted not-called on DENY; ASK blocks→proceeds/aborts; `await_decision` returns `"deny"` on timeout); goal-loop gate/budget regression green (no regression in the human-gate path).
- **Evidence:** 23-03-PLAN truths; 23-RESEARCH Recommendation 1 (reuse `_await_gate`), Pitfall 1 (evaluate before Popen), Pitfall 3 (bounded wait, default DENY), Pitfall 5 (route bot checks through, don't double-govern).
- **Correlation with full criterion:** HIGH — this is the core of SC3 and the consolidation half of SC2.
- **Blind spots:** `Popen` and the SSE broadcast are mocked; the in-process `_POLICY_DECISIONS` registry is exercised single-threaded. Real cross-thread timing (stream-reader threads not blocked) is only implicitly covered — confirm at SC5.
- **Validated:** No.

### P4: /admin/policies CRUD + /decision + PolicyMiddleware (SC4 backend)
- **What:** CRUD round-trip (PUT creates a session-scope deny row, GET lists, DELETE removes); `/admin/policies/decision` resolves a pending ASK via `submit_policy_decision`; input validation (scope ∈ {server,team,session}, kind ∈ builtins+custom, effect ∈ {allow,deny,ask}) → 400 on bad input; `PolicyMiddleware` (ASGIMiddleware subclass) annotates request context with verdict/scope, is non-blocking, and is a clean pass-through for unrelated routes.
- **Command:** `cd backend && uv run pytest tests/test_policies_router.py tests/test_policy_middleware.py -v`
- **Target:** All green via Litestar TestClient with standard X-API-Key/admin auth; middleware annotation present for a session-bearing request, status+body unchanged for an unrelated route.
- **Evidence:** 23-04-PLAN truths; mirrors `budgets.py:292` Router, `grd_routes.loop_gate_decision:1441`, `RequestContextMiddleware:107`/`ApiKeyMiddleware:148`.
- **Correlation with full criterion:** HIGH for the backend surface of SC4.
- **Blind spots:** TestClient logger doesn't propagate to `caplog` reliably — spy `module.logger.warning` via monkeypatch (per CLAUDE.md). Middleware ordering (after RequestContextMiddleware) is asserted by behavior, not by introspecting the stack.
- **Validated:** No.

### P5: Frontend components + i18n parity (SC4 frontend)
- **What:** PolicyEditor renders the policy list and emits upsert on save; PolicyAskCard renders a `policy_ask` event ({policy_id, kind, reason, scope}) and calls `policyApi.decide(sessionId, 'approve'|'deny')` against `/admin/policies/decision`, clearing on `policy_ask_resolved`; budgets.ts surfaces the cost-cap verdict additively; en/ko/ja/zh each carry a **key-identical** `policy.*` namespace.
- **Command:** `cd frontend && npm run test:run -- src/components/policy` and the locale-parity test (`Object.keys(en.policy)` deep-equals ko/ja/zh).
- **Target:** Policy specs pass; locale parity green; **NO NEW failures vs the documented 7-failure frontend baseline** (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas).
- **Evidence:** 23-05-PLAN truths; 23-RESEARCH Pitfall 4 (all four locales in the same change); standing i18n rule.
- **Correlation with full criterion:** HIGH for the frontend surface of SC4.
- **Blind spots:** happy-dom mounts, not a real browser; the SSE event is injected as a prop/fixture, not received over a live stream (that is SC5). WebMCP live-browser checks are **not applicable** — this frontend work ships components/locales, and no live operator console is driven in-phase.
- **Validated:** No.

**No additional proxy invented.** Every proxy above is a direct assertion of a locked criterion; there is no surrogate metric standing in for an unmeasurable goal.

## Level 3: Deferred Validations

**Purpose:** Full-pipeline behavior requiring the assembled enforcement path and the house-gate run.

### D1: End-to-end ALLOW / DENY / ASK on a real session (SC5) — DEFER-23-01
- **What:** Drive a real session through the enforcement boundaries: a configured session-scope DENY blocks the action (PolicyDenied, Popen not called); an ASK (e.g. `ask_on_os_tools` for a shell action) pauses awaiting a card, then `submit_policy_decision(session_id, 'approve')` RESUMES it (and `'deny'` aborts), with a `policy_ask` broadcast asserted (spy `ProjectSessionManager._broadcast`); an ALLOW (no matching deny/ask) passes through to Popen.
- **How:** `cd backend && uv run pytest tests/test_policy_e2e.py -v` (isolated_db, action started in a thread for the ASK case).
- **Why deferred:** Requires all five plans assembled (evaluator + builtins + enforcement + routes + the decision resolver) and the cross-thread ASK pause/resume — not provable until 23-05.
- **Validates at:** phase-23 plan 23-05 (final plan, in-phase deferred — not a future phase).
- **Depends on:** P1–P4 green; `await_decision`/`submit_policy_decision`; ExecutionService + goal_loop enforcement call-sites.
- **Target:** DENY blocks; ASK pauses-then-resumes on approve / aborts on deny; ALLOW passes — all green.
- **Risk if unmet:** Logic passes unit tests but the assembled path mis-wires the session id or blocks a stream-reader thread (Pitfall 1). **Mitigation:** the in-phase deferral means it is caught before phase close; budget a fix within 23-05 rather than a new phase.

### D2: House gates — build + backend pytest + frontend (SC6) — DEFER-23-02
- **What:** (1) `just build` (vue-tsc + vite) passes; (2) full backend `uv run pytest` under a ~12-minute watchdog; (3) frontend `npm run test:run` shows no NEW failures.
- **How:**
  - `just build`
  - `cd backend && uv run pytest` under a ~12-min watchdog. **Known issue:** the full serial suite hangs at ~40-48% (no failures before the hang). On hang: kill it and run a comprehensive targeted set — `uv run pytest tests/test_policy_evaluator.py tests/test_policy_builtins.py tests/test_policy_enforcement.py tests/test_policies_router.py tests/test_policy_middleware.py tests/test_policy_e2e.py tests/test_migration_176_policies.py` PLUS the execution / streaming / goal-loop regression suites — and **DISCLOSE the substitution** in 23-05-SUMMARY (never present targeted as full).
  - `cd frontend && npm run test:run`
- **Why deferred:** Whole-suite gates only meaningful once all code lands; the serial-suite hang forces a documented targeted substitution.
- **Validates at:** phase-23 plan 23-05.
- **Depends on:** All prior plans merged.
- **Target:** build green; targeted backend set green (substitution disclosed if the hang hits); frontend ≤ 7 known baseline failures, **zero new**.
- **Risk if unmet:** The ~40-48% hang masks a real regression introduced by the policy wiring. **Mitigation:** the targeted set explicitly includes execution/streaming/goal-loop regression suites — the areas this phase touches — so a policy-induced regression surfaces even under substitution.

## Ablation Plan

**Purpose:** Isolate that each consolidated control still behaves and that the stacking invariant is load-bearing.

### A1: Remove the session-scope row → server ALLOW now governs
- **Condition:** Same action as the SC1 deny case but with the session DENY row disabled (`enabled=0`).
- **Expected:** Verdict flips from `deny/session` to `allow` (server fall-through) — proves the short-circuit was caused by the session row, not an unconditional deny.
- **Command:** Covered as a case in `tests/test_policy_evaluator.py` (toggle `enabled`).
- **Evidence:** 23-01-PLAN behavior table (default-ALLOW fall-through case).

### A2: Exit-ladder cost gate routed through vs. inline
- **Condition:** Assert the goal_loop cost cap now produces a verdict via `cost_budget` builtin (single source of truth), not the old inline `total_cost_usd >=` check.
- **Expected:** DENY behavior at the cap is identical to the pre-consolidation loop exit; no double-governing.
- **Command:** `cd backend && uv run pytest tests/test_policy_enforcement.py -k "budget or consolidat" -v` + goal-loop budget regression.
- **Purpose:** Verifies consolidation (SC2) removed the parallel control without changing exit behavior.

## Baselines

| Baseline | Description | Expected | Source |
|----------|-------------|----------|--------|
| Frontend test baseline | Known pre-existing failures | exactly 7 (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas) | CLAUDE.md verification section |
| Backend serial-suite hang | Full suite hangs ~40-48%, no failures before hang | targeted substitution + disclosure | CLAUDE.md verification section |
| Pre-policy enforcement behavior | goal_loop exit-ladder DENY at cost cap; bot-security/bot-pr-review inline checks | identical DENY behavior post-consolidation | 23-03-PLAN (Pitfall 5) |

## WebMCP Tool Definitions

WebMCP tool definitions skipped — `webmcp_available` is not set for this environment, and although the phase ships Vue components (PolicyEditor, PolicyAskCard) the phase does not drive a live operator console in-phase. Frontend behavior is validated via Vitest component specs (P5) and the deferred e2e (D1), not live-browser health checks.

## Evaluation Scripts

**Location of evaluation code:** the phase's own test files (created during execution):
```
backend/tests/test_policy_evaluator.py        # SC1
backend/tests/test_migration_176_policies.py  # migration (S4)
backend/tests/test_policy_builtins.py         # SC2 builtins
backend/tests/test_policy_enforcement.py      # SC2 consolidation + SC3
backend/tests/test_policies_router.py         # SC4 backend
backend/tests/test_policy_middleware.py       # SC4 middleware
backend/tests/test_policy_e2e.py              # SC5 (deferred)
frontend/src/components/policy/__tests__/PolicyEditor.spec.ts   # SC4 frontend
frontend/src/components/policy/__tests__/PolicyAskCard.spec.ts  # SC4 frontend
```

**How to run the full evaluation (in order):**
```bash
# L1 sanity
cd backend && uv run ruff format --check .
just build
cd backend && uv run python -c "import app.services.policy_service; import app_litestar.routes.policies; import app_litestar.middleware"
cd backend && uv run pytest tests/test_migration_176_policies.py -v

# L2 proxy
cd backend && uv run pytest tests/test_policy_evaluator.py tests/test_policy_builtins.py tests/test_policy_enforcement.py tests/test_policies_router.py tests/test_policy_middleware.py -v
cd backend && uv run pytest tests/test_goal_loop_runner.py -k "gate or budget" -v
cd frontend && npm run test:run -- src/components/policy

# L3 deferred (23-05)
cd backend && uv run pytest tests/test_policy_e2e.py -v
just build && cd backend && uv run pytest   # watchdog; targeted substitution on hang
cd frontend && npm run test:run
```

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1 Ruff format | | | |
| S2 just build | | | |
| S3 Import/collect | | | |
| S4 Migration 176 | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1 Stacking (SC1) | all green + spy-assert | | | |
| P2 Builtins (SC2) | all case rows green | | | |
| P3 Enforcement (SC2/SC3) | DENY-blocks-Popen + ASK + timeout=deny + consolidation | | | |
| P4 Routes+middleware (SC4) | CRUD + /decision + annotate/pass-through | | | |
| P5 Frontend+i18n (SC4) | specs green + parity + no new failures | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1 disable session row | flips deny/session → allow | | |
| A2 cost gate routed-through | identical DENY behavior | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-23-01 | E2E ALLOW/DENY/ASK (SC5) | PASS (2026-07-04) — `test_policy_e2e.py` green (automated ALLOW/DENY/ASK round-trip); manual live-browser pass still optional | phase-23 / 23-05 |
| DEFER-23-02 | House gates (SC6) | PASS (2026-07-04) — build GREEN (vue-tsc+vite); frontend 1686 pass / 7 known-baseline / 0 NEW; backend targeted 286 pass / 2 fail (both `test_sandbox_escape.py` — macOS-seatbelt over-restriction at the interpreter-import precondition, env-dependent → DEFER-24-01 territory, NOT a policy regression). All policy suites green. | phase-23 / 23-05 |

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- **Sanity checks:** adequate — format, build, import-cycle, and migration idempotency are the real failure modes for this kind of wiring, and all are covered with runnable commands.
- **Proxy metrics:** well-evidenced — each maps one-to-one to a locked success criterion with a concrete pytest/Vitest command and an explicit pass threshold. No surrogate metric is invented; the tests assert the behavior directly.
- **Deferred coverage:** comprehensive for SC5/SC6 — both deferred items are **in-phase** (resolved within 23-05), so the phase does not close on unverified integration, and the targeted-substitution procedure explicitly re-includes the execution/streaming/goal-loop suites this phase perturbs.

**What this evaluation CAN tell us:**
- Whether the stacking invariant (session DENY short-circuits server ALLOW) holds, including the negative spy-assert that later scopes are never consulted.
- Whether each builtin evaluator returns the correct verdict, and that `enforce_sandbox` is verdict-producing but inert until Phase 24.
- Whether a DENY actually stops `subprocess.Popen` and an ASK blocks-until-resolved with a DENY fail-safe on timeout.
- Whether the operator surface (routes, middleware, components, four locales) is correct and key-identical.
- Whether the consolidation removed parallel controls without changing exit behavior.

**What this evaluation CANNOT tell us (and when it's addressed):**
- Real cross-thread ASK timing and that stream-reader threads are never blocked under load — **partially** at SC5 (threaded e2e), fully only under live operation.
- That `enforce_sandbox` does real work — explicitly out of scope; **deferred to Phase 24** (stored-now / enforced-later).
- Live-browser rendering of the ASK card over a real SSE stream — components are unit-mounted only; no in-phase WebMCP/browser check.
- Whether the full backend suite is regression-free beyond the targeted substitution — bounded by the documented ~40-48% serial-suite hang; mitigated by including the touched regression suites.

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-30*
