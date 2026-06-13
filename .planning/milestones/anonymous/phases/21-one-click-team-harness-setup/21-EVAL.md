# Evaluation Plan: Phase 21 — One-click Team Harness Setup

**Designed:** 2026-06-13
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** TeamHarnessSetupService (6-step idempotent orchestrator), step-level SSE progress, STACK.md-tailored bundle binding, 4-harness materialization + per-backend compile smoke check
**Reference papers:** None — codebase-internal integration phase. No academic citations applicable.

## Evaluation Overview

Phase 21 is a pure integration phase. There are no numeric model-quality targets (PSNR, FID, etc.) — every metric is a binary pass/fail gate or an idempotency invariant. The evaluation focuses on three correctness axes: (1) persistence correctness (migration schema, status state machine), (2) behavioral correctness (step idempotency under fresh/partial/full-re-run, no destructive deletes, driver column set correctly, bundle tailoring picks right bundle, policy row expresses correct semantics), and (3) surface correctness (route status transitions, SSE event shape, dashboard renders expected controls with no new frontend test failures).

The live dogfood run (SC5) and house gates (SC6) are deferred — they require a live database, real project, and 4 real AI backends that are not available in the automated unit test environment. All three evaluation tiers are necessary; proxy metrics cannot substitute for the deferred dogfood because no automated test can exercise the real subprocess/PTY/renderer chain end-to-end.

No proxy metric involves a numeric threshold — targets are stated as "all green", "no new failures", or a specific structural assertion. This reflects the integration nature of the phase.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|-----------------|
| Migration idempotency (double-apply no-op) | 21-01-PLAN.md task 1 / RESEARCH.md Seam 0 | Mirrors grd_init_status pattern; PRAGMA-guard is the codebase convention |
| `harness_setup_status` default "none" | RESEARCH.md Seam 0 | SC1 foundation — status column must exist and default correctly |
| `driver=grd` on SA instances | RESEARCH.md Seam 2 / 21-03-PLAN.md | SC1 — driver resolves correctly for Phase-19 instance routing |
| Step idempotency (no duplicate rows) | RESEARCH.md Seam 7 / success criterion 4 | Core correctness invariant — re-run reconciles, never duplicates |
| No destructive deletes | SC4 explicit | Safety invariant — failed step leaves step log intact |
| STACK.md bundle selection | RESEARCH.md Seam 3 / SC3 | REQ-21 tailoring correctness |
| 4 renderers compile projection | RESEARCH.md Seam 6 / SC2, SC5 | Per-backend compile smoke; prior art test_forge_materialization.py |
| Route status transitions none→running→ready | RESEARCH.md Seam 0 / SC1 | Route wiring correctness via Litestar TestClient |
| SSE streams step events | RESEARCH.md Seam 0 / SC1 | Step-level progress delivery |
| Failed step leaves failed status + step log + is retryable | SC4 | Failure-mode correctness |
| Conservative autonomy policy + scoped auto-apply ON | RESEARCH.md Seam 5 / SC2 | Policy row semantics |
| Live dogfood 4-backend compile | SC5 / DEFER-17-01/02 | End-to-end integration validation |
| House gates (build / pytest / frontend) | SC6 / CLAUDE.md | Release readiness |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 5 | Basic persistence, imports, format, driver value |
| Proxy (L2) | 8 | Automated correctness gates: idempotency, bundle tailoring, renderer compile, route/SSE, failure mode, policy |
| Deferred (L3) | 4 | Live dogfood run + 3 house gates requiring real environment |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic persistence and module structure. ALL must pass before integration proceeds.

### S1: Migration schema — column + table exist, defaults correct (SC1)
- **What:** Migrations 159 and 160 create `projects.harness_setup_status` (default NULL/"none") and `harness_setup_steps` table with `(project_id, step_key)` primary key. Double-apply is a no-op.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_harness_setup_status_migration.py -v`
- **Expected:** All tests green. Specifically: column present in `PRAGMA table_info(projects)`; `harness_setup_steps` table exists with correct PK; idempotent re-apply raises nothing.
- **Failure means:** Migration not registered in V07_MIGRATIONS, or PRAGMA guard missing, or column name typo. Blocks every downstream step.

### S2: `get_harness_setup_status` returns "none" for fresh project (SC1)
- **What:** Status helper defaults to "none" when column is NULL, exactly mirroring `get_init_status`.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_harness_setup_status_migration.py::test_get_harness_setup_status_defaults_none -v`
- **Expected:** PASS — `get_harness_setup_status(project_id)` returns `"none"` before any `set_harness_setup_status` call.
- **Failure means:** Helper reads the raw NULL instead of coercing to "none"; detail route will expose NULL to SPA.

### S3: Import smoke — `TeamHarnessSetupService` importable, no NameError (SC2)
- **What:** The service module imports cleanly with no missing dependencies or circular imports.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.team_harness_setup_service import TeamHarnessSetupService, HARNESS_SETUP_STEP_KEYS; assert len(HARNESS_SETUP_STEP_KEYS) == 6; print('ok')"`
- **Expected:** Prints `ok` with exit code 0.
- **Failure means:** Import error or step-key count wrong. Blocks all service-level tests.

### S4: `driver=grd` on created SA instances (SC1, SC2)
- **What:** SA instances created by step (b) have `get_instance_driver(instance_id) == "grd"`.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_team_harness_setup_service.py -k "driver" -v`
- **Expected:** Test asserting `get_instance_driver(instance_id) == "grd"` passes for all SA instances created by step b.
- **Failure means:** `create_team_instances` does not forward the `driver` kwarg; Phase-19 routing will fall back to wrong backend.

### S5: Ruff format/check clean on all new modules (SC6 house gate prerequisite)
- **What:** New Python modules pass ruff formatting and lint checks (line-length=100, py310).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff check app/services/team_harness_setup_service.py app/db/projects.py app_litestar/routes/grd_routes.py app_litestar/routes/projects.py && uv run ruff format --check app/services/team_harness_setup_service.py app/db/projects.py app_litestar/routes/grd_routes.py`
- **Expected:** Exit code 0, no violations.
- **Failure means:** Style violation; must be fixed before PR.

**Sanity gate:** ALL five sanity checks must pass. Any failure blocks progression to proxy evaluation.

---

## Level 2: Proxy Metrics

**Purpose:** Automated correctness gates for the behaviors that matter most. All proxy metrics are binary pass/fail — no numeric thresholds.

**IMPORTANT:** These are unit/integration tests running against `isolated_db` fixtures. They do NOT exercise the real subprocess/PTY chain or real AI backends. They validate structural correctness only.

### P1: Step idempotency — fresh / partial / full-re-run matrix, no duplicate rows (SC4)
- **What:** For each of the 6 steps (grd_init, team_topology, bundle_binding, tesserae_enable, default_policies, materialize_compile), running the step twice produces no duplicate rows in any table.
- **How:** Three fixture scenarios: (1) fresh DB — step runs from scratch; (2) partial — some upstream steps already done, this step is new; (3) full re-run — all steps already done, re-running produces no new rows and no destructive deletes.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_team_harness_setup_service.py -k "idempotent" -v`
- **Target:** All idempotency tests green. Zero duplicate rows in `project_forge_bindings`, `project_sa_instances`, `harness_setup_steps`, `project_autonomy_config`.
- **Evidence:** RESEARCH.md Seam 7 — existing upsert/unique constraints are the mechanism; this test exercises them end-to-end via the service layer.
- **Correlation with SC4:** HIGH — directly tests the success criterion.
- **Blind spots:** Does not test concurrent re-runs (race condition); does not test partial network failure mid-step.
- **Validated:** No — awaiting deferred dogfood at phase-21-08.

### P2: No destructive deletes on re-run (SC4)
- **What:** A full re-run of `TeamHarnessSetupService.setup()` does not call `unset_tesserae_root_bindings`, does not delete SA instances, does not un-bind bundles, does not delete `project_autonomy_config` rows.
- **How:** Monkeypatch destructive DB helpers to raise; assert they are never called during a full re-run scenario.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_team_harness_setup_service.py -k "no_destructive" -v`
- **Target:** All no-destructive tests pass.
- **Evidence:** SC4 explicit constraint; RESEARCH.md pitfall 4.
- **Correlation with SC4:** HIGH — directly tests the invariant.
- **Blind spots:** Monkeypatching may miss indirect deletion paths through helper chains.
- **Validated:** No — awaiting deferred dogfood at phase-21-08.

### P3: STACK.md-tailored bundle selection — correct bundle per stack fixture + fallback (SC3)
- **What:** Step (c) parses a fixture STACK.md and selects the correct language-conditional bundle; when STACK.md is absent, falls back to the global `forge-creator` bundle floor.
- **How:** Three fixtures: (a) Python STACK.md → picks python-keyed bundle (or forge-creator if no language-specific bundle seeded); (b) TypeScript STACK.md → picks ts-keyed bundle or forge-creator; (c) missing STACK.md → picks forge-creator only. Assert `bind_bundle_to_project` called with the correct `bundle_id`.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_team_harness_setup_service.py -k "bundle_selection" -v`
- **Target:** All 3 fixture scenarios assert the expected bundle call.
- **Evidence:** RESEARCH.md Seam 3 — `get_forge_bundle_by_name` + `bind_bundle_to_project` are the bind primitives; `forge-creator` is the guaranteed floor.
- **Correlation with SC3:** HIGH for fallback (forge-creator always bound); MEDIUM for language-conditional (depends on whether language-keyed bundles are seeded).
- **Blind spots:** Does not test partial STACK.md (e.g., Languages section present but Frameworks absent). Does not test bundle ordering.
- **Validated:** No — awaiting deferred dogfood at phase-21-08.

### P4: 4 renderers compile the materialized projection — golden-file pattern (SC2, SC5 partial)
- **What:** After step (f) materializes primitives into a tmp workspace, all four renderers (`claude`, `codex`, `gemini`, `opencode`) produce non-empty output without raising an exception.
- **How:** Mirror `backend/tests/test_forge_materialization.py` golden-file pattern. Materialize into `tmp_path`, then call `renderer_for(backend).render(...)` for each of the 4 backends and assert `output is not None and len(output) > 0`.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_team_harness_setup_service.py -k "renderer_compile" -v`
- **Target:** All 4 renderer assertions pass; no exception raised for any backend.
- **Evidence:** RESEARCH.md Seam 6 — `RENDERERS` dict confirmed present; `test_forge_materialization.py` is prior art for exactly this check.
- **Correlation with SC2/SC5:** MEDIUM — tests the renderer compile path but with fixture primitives, not real project content. The deferred dogfood tests against a real project.
- **Blind spots:** Fixture primitives may not exercise edge cases in renderer logic (e.g., deeply nested agents, large prompt context). Real project content tested only in dogfood (L3).
- **Validated:** No — awaiting deferred dogfood at phase-21-08.

### P5: Route status transitions none→running→ready, SSE streams step events (SC1)
- **What:** `POST /admin/projects/{id}/harness-setup` flips `harness_setup_status` to "running"; `GET /admin/projects/{id}/harness-setup/status` returns step list; `GET /admin/projects/{id}/harness-setup/stream` yields `text/event-stream` content type with JSON step events.
- **How:** Litestar `TestClient` with `isolated_db`, mirroring `backend/tests/routes/test_forge_bindings_routes.py`. Monkeypatch `TeamHarnessSetupService.setup` to a synchronous stub that writes 2 step rows and flips status to "ready". Assert: POST returns 202; status endpoint returns step records; stream endpoint returns `content-type: text/event-stream` with at least one `data:` line containing `{"step":"grd_init",...}` shape.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/routes/test_harness_setup_routes.py -v`
- **Target:** All route tests green.
- **Evidence:** RESEARCH.md Seam 0 — SSE pattern lifted from `agents_and_tracing.py:228`; `test_forge_bindings_routes.py` is the prior-art SSE route test.
- **Correlation with SC1:** HIGH for route/status assertions; MEDIUM for SSE (TestClient may not exercise async generator timing faithfully).
- **Blind spots:** TestClient does not verify the real-time streaming behavior under load. Does not test SSE reconnect or large step logs.
- **Validated:** No — awaiting deferred dogfood at phase-21-08.

### P6: Failed step leaves `failed` status + step log + step is retryable (SC4)
- **What:** When step (b) fails (monkeypatched to raise), the service sets `harness_setup_status = "failed"`, the `harness_setup_steps` row for that step has `status = "failed"` with non-empty `detail`, and re-triggering runs only the failed step without re-running already-ok steps.
- **How:** Test with isolated_db: inject a failure in step (b), run `setup()`, assert status = "failed", assert the step row exists with status="failed". Then retry via `POST /admin/projects/{id}/harness-setup` and assert step (a) (already ok) is skipped and step (b) is re-attempted.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_team_harness_setup_service.py -k "failed_step" -v`
- **Target:** Status is "failed", step log row exists, retry skips completed steps.
- **Evidence:** SC4 explicit; RESEARCH.md pitfall — "non-blocking failure: wrap per-step in try/except, record StepResult(failed), set overall failed, leave a step log."
- **Correlation with SC4:** HIGH.
- **Blind spots:** Does not test failure in the last step (step f) specifically, which has the most downstream state (rendered files may be partial).
- **Validated:** No — awaiting deferred dogfood at phase-21-08.

### P7: Conservative autonomy policy row + scoped auto-apply (SC2)
- **What:** After step (e), `get_policy(project_id)` returns review-mode defaults (`enabled=False` OR enabled with block_deletes=True, allowed_kinds as conservative set) AND `_auto_apply_policy(project_id)` returns True for kind `"discovered_procedure"`.
- **How:** Step test with isolated_db. After calling the step-e function, assert: (1) `get_policy` returns the row; (2) `_auto_apply_policy(project_id)` returns True (mock the gate to read from the same isolated DB); (3) `policy.block_deletes == True`.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_team_harness_setup_service.py -k "autonomy_policy" -v`
- **Target:** Both assertions pass — conservative evolution AND scoped auto-apply ON.
- **Evidence:** RESEARCH.md Seam 5 — dual-consumer tension documented; `_auto_apply_policy` at `repeated_request_gate.py:125` reads `enabled` + `policy_json.kinds`; `upsert_policy` is the write primitive.
- **Correlation with SC2:** HIGH for policy row structure; MEDIUM for dual-consumer semantics (the tension between `harness_autonomy.autonomous_apply_eligible` and `repeated_request_gate._auto_apply_policy` reading the same row may not be fully exposed by this test alone).
- **Blind spots:** Does not test whether `harness_autonomy.autonomous_apply_eligible` is also correctly gated (that gate has its own `AGENTED_AUTONOMY` env kill-switch that this test cannot exercise without env manipulation).
- **Validated:** No — awaiting deferred dogfood at phase-21-08.

### P8: ProjectDashboard — button + status chip + step panel render, no new frontend test failures (SC1)
- **What:** The new `ProjectDashboard.harness-setup.test.ts` tests that: "Setup Team Harness" button renders when `harnessSetupStatus` is "none"; a status chip shows the correct state for each status value; the step panel renders step rows from a mocked SSE `EventSource`.
- **How:** Vitest + @vue/test-utils, mocking `EventSource` and `harnessSetupApi`. Prior-art: no ProjectDashboard test exists yet — this creates it.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run`
- **Target:** No NEW failures beyond the 7 known pre-existing failures (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas). New harness-setup tests pass.
- **Evidence:** RESEARCH.md Seam 0 — `ProjectDashboard.vue:91,298,304,519` are the wiring points; `harnessSetupStatus = ref('none')` mirrors `grdInitStatus`.
- **Correlation with SC1:** HIGH for render assertions; MEDIUM for EventSource mock (real SSE timing not tested).
- **Blind spots:** Mocked EventSource does not test reconnect behavior. i18n key parity across en/ko/ja/zh not verified by Vitest alone.
- **Validated:** No — awaiting deferred end-to-end at phase-21-08.

**Proxy gate:** All 8 proxy checks must be green (or explain any skipped test with a documented rationale). The frontend gate is no-NEW-failures, not all-green (7 known pre-existing failures are exempt).

---

## Level 3: Deferred Validations

**Purpose:** Full validation requiring a real project, live AI backends, and subprocess/PTY execution. Cannot be automated in the unit test environment.

### D1: Live dogfood run — all 4 backends compile the materialized projection (SC5, closes DEFER-17-01) — DEFER-21-01
- **What:** One end-to-end run of `TeamHarnessSetupService.setup(project_id)` against a real git-tracked project in the live environment. HTTP 201 on trigger; all 6 steps reach "ok" or "skipped"; materialized `.claude/` directory exists on disk; forge manifest updated; all 4 renderers (claude/codex/gemini/opencode) compile the projection without error.
- **How:** Operator triggers via the "Setup Team Harness" button in ProjectDashboard on a known real project. Verify: SSE stream completes with `{"step":"__done__","status":"ready"}`; check `harness_setup_status == "ready"` via GET status endpoint; inspect `.claude/` in the project workspace; manually run each renderer or observe the compile smoke log in step (f).
- **Why deferred:** Requires a real project with `.planning/` and STACK.md, real subprocess execution for GRD init, real AI backend credentials for 4-harness materialization, and real disk write access — none available in `isolated_db` unit tests.
- **Validates at:** phase-21-08 (live dogfood + DEFER-17-01/02 closeout)
- **Depends on:** All 21-01 through 21-07 plans complete and merged; live environment with 4 AI backend credentials; a real project with `local_path` set and accessible.
- **Target:** HTTP 201; `harness_setup_status == "ready"`; `.claude/` directory on disk with non-empty content; all 4 renderer compile outputs non-empty; no exceptions in step log.
- **Risk if unmet:** The 4-harness materialization or one renderer fails on real project content (e.g., unusual STACK.md, large primitive set). Fallback: identify failing renderer, open targeted fix, re-run step (f) alone via retry mechanism.
- **Fallback:** Per-step retry via re-trigger route isolates the failing step without re-running completed ones.

### D2: Session-completion auto-import dogfood — idempotent second run (SC5, closes DEFER-17-02) — DEFER-21-02
- **What:** After the live dogfood run (D1), trigger `forge_session_import.on_session_complete_import` for the same project. Assert: imported primitive is present in DB; `forge_origin` sha256 recorded; second trigger is a no-op (no duplicate import, no new `forge_origin` row for the same content hash).
- **How:** Manual or scripted trigger of the session-complete import hook on the live project; inspect DB for idempotency. The sha256 fingerprint in `forge_origin` table must match between runs.
- **Why deferred:** Requires a real completed session and the live import pipeline; not mockable in isolation without the full session lifecycle.
- **Validates at:** phase-21-08
- **Depends on:** D1 complete; a real completed session on the dogfood project.
- **Target:** Second import produces zero new rows in `forge_origin` for the same content_hash; primitive count unchanged.
- **Risk if unmet:** Import is not idempotent — each session completion creates duplicate primitives. Fallback: add content-hash dedup guard to the import hook.
- **Fallback:** `forge_origin` sha256 unique constraint should surface the duplicate as an integrity error; add an explicit skip-if-exists guard.

### D3: House gate — `just build` (vue-tsc + vite build) passes (SC6) — DEFER-21-03
- **What:** `just build` (TypeScript type checking via vue-tsc + Vite production build) completes without errors.
- **How:** `cd /Users/neo/Developer/Projects/Agented && just build`
- **Why deferred:** Requires all wave-1 through wave-3 plan files executed and all frontend changes landed. Running `just build` against an incomplete phase would produce false negatives.
- **Validates at:** phase-21-08 (house gates)
- **Depends on:** 21-01 through 21-07 all complete; frontend i18n keys for all 4 locales added (en/ko/ja/zh harnessSetup.* namespace).
- **Target:** Exit code 0; no TypeScript errors; no Vite build errors.
- **Risk if unmet:** TypeScript type errors in new Vue component or API client types; or i18n key missing in one locale. Fallback: fix type errors before final gate.
- **Fallback:** vue-tsc errors point to exact file:line; targeted fix.

### D4: House gate — backend pytest watchdog + frontend no-new-failures (SC6) — DEFER-21-04
- **What:** (a) Backend: full `uv run pytest` suite under a ~12-minute watchdog. Per the known serial-hang issue (hangs at ~40-48% with no failures before the hang), on hang: kill and run a targeted comprehensive set covering all new test files + execution/streaming/harness regressions, disclosing the substitution. (b) Frontend: `npm run test:run` with no failures beyond the 7 known pre-existing ones.
- **How:** (a) `cd /Users/neo/Developer/Projects/Agented/backend && timeout 720 uv run pytest || (echo "HANG — running targeted" && uv run pytest tests/test_team_harness_setup_service.py tests/test_harness_setup_status_migration.py tests/routes/test_harness_setup_routes.py tests/test_forge_materialization.py tests/test_forge_bindings_db.py tests/test_instance_service.py tests/test_tesserae_integration.py tests/test_harness_autonomy.py -v)`. (b) `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run`.
- **Why deferred:** Full suite must run after all phase plans are complete. The hang procedure requires human judgment (targeted set selection and disclosure).
- **Validates at:** phase-21-08 (house gates)
- **Depends on:** All plans executed; no new test files introduce circular imports or DB fixture conflicts.
- **Target:** (a) No new test failures (all new tests green; prior-art tests not broken). (b) Frontend: no failures beyond the 7 known pre-existing ones.
- **Risk if unmet:** A new test file has an incompatible DB fixture or import that causes the suite to fail (not just hang). Fallback: fix the failing test; re-run targeted set.
- **Fallback:** Per CLAUDE.md procedure — targeted set disclosed in PR if hang occurs.

---

## Ablation Plan

**No ablation plan** — This phase implements a single sequential orchestrator over existing primitives. Each "step" is already independently testable as a unit test (P1–P7). There are no sub-components to ablate against each other; each step's contribution is fixed by the success criteria.

The closest analog to an ablation is the "fresh / partial / full-re-run" idempotency matrix in P1, which isolates each step's behavior in isolation.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — MCP not available in this evaluation context.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| grd_init_status pattern | Existing status column (grd_init_status, default "none", PRAGMA-guarded migration) | Binary: column exists, double-apply is no-op | backend/app/db/migrations/v07_features.py:1181 |
| forge-creator bundle floor | Global bundle seeded at startup, always bound as floor | Binary: bind call succeeds, no duplicate binding rows | backend/app/services/forge_creator_seed.py:36 |
| 4-renderer compile prior art | test_forge_materialization.py golden-file tests across claude/codex/gemini/opencode | Binary: all 4 renderers produce non-empty output | backend/tests/test_forge_materialization.py |
| 7 known frontend failures | Pre-existing failures in RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine | 7 failures (exempt) | CLAUDE.md verification section |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_harness_setup_status_migration.py   (L1 S1, S2)
backend/tests/test_team_harness_setup_service.py       (L1 S3, S4; L2 P1–P7)
backend/tests/routes/test_harness_setup_routes.py      (L2 P5)
frontend/src/views/__tests__/ProjectDashboard.harness-setup.test.ts  (L2 P8)
```

**How to run full automated evaluation (L1 + L2):**
```bash
# L1 sanity
cd /Users/neo/Developer/Projects/Agented/backend
uv run pytest tests/test_harness_setup_status_migration.py -v
uv run python -c "from app.services.team_harness_setup_service import TeamHarnessSetupService, HARNESS_SETUP_STEP_KEYS; assert len(HARNESS_SETUP_STEP_KEYS) == 6; print('ok')"
uv run ruff check app/services/team_harness_setup_service.py app/db/projects.py app_litestar/routes/grd_routes.py app_litestar/routes/projects.py

# L2 proxy
uv run pytest tests/test_team_harness_setup_service.py tests/routes/test_harness_setup_routes.py -v
cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Migration schema | [PASS/FAIL] | | |
| S2: Status default "none" | [PASS/FAIL] | | |
| S3: Import smoke | [PASS/FAIL] | | |
| S4: driver=grd on SA instances | [PASS/FAIL] | | |
| S5: Ruff clean | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Idempotency matrix | All green | | [MET/MISSED] | |
| P2: No destructive deletes | All green | | [MET/MISSED] | |
| P3: Bundle selection | 3/3 fixtures | | [MET/MISSED] | |
| P4: 4 renderers compile | 4/4 renderers | | [MET/MISSED] | |
| P5: Route/SSE transitions | All green | | [MET/MISSED] | |
| P6: Failed step leaves log + retryable | All green | | [MET/MISSED] | |
| P7: Autonomy policy row | Both assertions | | [MET/MISSED] | |
| P8: Frontend no-new-failures | 0 new failures | | [MET/MISSED] | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-21-01 | Live dogfood 4-backend compile (closes DEFER-17-01) | PENDING | phase-21-08 |
| DEFER-21-02 | Session auto-import idempotent second run (closes DEFER-17-02) | PENDING | phase-21-08 |
| DEFER-21-03 | just build passes | PENDING | phase-21-08 |
| DEFER-21-04 | Backend pytest watchdog + frontend no-new-failures | PENDING | phase-21-08 |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: adequate — 5 checks covering migration schema, status helper, import smoke, driver value, and ruff; all directly runnable with exact commands.
- Proxy metrics: well-evidenced — every L2 metric traces to a specific RESEARCH.md seam (file:line) or an explicit success criterion. Targets are binary (all green). Prior-art test files (`test_forge_materialization.py`, `test_forge_bindings_routes.py`, `test_instance_service.py`) are confirmed present.
- Deferred coverage: comprehensive for the phase — the dogfood + house gates cover all three success criteria (SC5, SC6) that cannot be automated.

**What this evaluation CAN tell us:**
- Whether the persistence layer is correctly structured (migrations, status column, steps table)
- Whether each step is structurally idempotent under fixture scenarios
- Whether the route/SSE wiring delivers the correct event shape via TestClient
- Whether all 4 renderers compile against fixture primitives
- Whether the policy row expresses the correct semantics for dual-consumer gates
- Whether the frontend renders the new surface without breaking existing tests

**What this evaluation CANNOT tell us:**
- Whether GRD init completes successfully against a real project's filesystem (deferred to DEFER-21-01 / phase-21-08)
- Whether real AI backend subprocess execution produces valid materialization content (deferred to DEFER-21-01 / phase-21-08)
- Whether SSE reconnect and large-step-log scenarios are reliable under production load (not covered by any tier — out of scope for this phase)
- Whether the dual-consumer autonomy tension (RESEARCH.md Seam 5 open question) is fully resolved — P7 tests the structural assertion but cannot exercise both consumers simultaneously in isolation (partially addressed; full confirmation requires reading both gate implementations during execution)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-13*
