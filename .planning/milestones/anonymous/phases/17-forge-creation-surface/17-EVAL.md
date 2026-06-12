# Evaluation Plan: Phase 17 — Forge Creation Surface

**Designed:** 2026-06-13
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Forge primitive system extension — subagent kind, atomic create endpoint, cross-kind bundles, forge-creator seed, session auto-import
**Reference plans:** 17-01 through 17-06-PLAN.md; 17-RESEARCH.md

## Evaluation Overview

Phase 17 is a pure backend software phase with no ML components. Evaluation is entirely about behavioral correctness: do the new data structures persist correctly, do the routes maintain transactional integrity, do the renderers project the right text, and does the auto-import pipeline gate correctly on session provenance?

The verification strategy mirrors the phase wave structure. Wave 1 plans (17-01, 17-03) produce isolated DB fixes with simple round-trip tests. Wave 2/3 plans (17-02, 17-04, 17-05) build the subagent primitive end-to-end — DB through materialization through renderer through route. Wave 4 (17-06) wires startup seeding and session-completion auto-import. Proxy-level tests are the primary gate: each plan's pytest target directly proves the behavioral claim.

The frontend is not touched. `just build` runs as a regression guard only.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| replace_for_project round-trip | 17-01-PLAN.md must_haves | Directly proves success criterion #3 |
| subagent CRUD + kinds registry | 17-02-PLAN.md must_haves | Directly proves success criterion #1 (DB half) |
| .claude/agents/ golden materialization | 17-02-PLAN.md + 17-04-PLAN.md | Proves .md file written with correct frontmatter (success #1) |
| 4-backend renderer golden | 17-04-PLAN.md must_haves | Proves success criterion #1 (renderer half) |
| Atomic create + no-orphan on injected failure | 17-05-PLAN.md must_haves | Directly proves success criterion #2 |
| forge_bundles cross-kind + skill_sets unchanged | 17-03-PLAN.md must_haves | Directly proves success criterion #4 |
| forge-creator seed idempotence | 17-06-PLAN.md must_haves | Proves success criterion #5 (seed half) |
| Import handler diff/gate/provenance | 17-06-PLAN.md must_haves | Proves success criterion #5 (import half) |
| House gates | CLAUDE.md Verification | Required for any phase to pass |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 7 | Format + import + schema smoke checks |
| Proxy (L2) | 10 | Behavioral pytest targets per plan |
| Deferred (L3) | 2 | End-to-end against real workspace; live session dogfood |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: Ruff format + lint on touched backend files
- **What:** No formatting violations or lint errors introduced
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check . && uv run ruff check app/db/project_forge_bindings.py app/db/subagents.py app/db/forge_bundles.py app/db/forge_origin.py app/services/forge_materialization_service.py app/services/context_compiler_service.py app/services/forge_creator_seed.py app/services/forge_session_import.py app_litestar/routes/project_forge_bindings.py app_litestar/lifecycle.py`
- **Expected:** Exit code 0, no output
- **Failure means:** A plan left reformatting or lint debt; fix before running proxy tier

### S2: Python import smoke — new modules
- **What:** All six new modules are importable without error
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import app.db.subagents; import app.db.forge_bundles; import app.db.forge_origin; import app.services.forge_creator_seed; import app.services.forge_session_import; import app.services.forge_materialization_service; print('OK')"`
- **Expected:** `OK`
- **Failure means:** Import error in a new module; circular import or missing dependency

### S3: Both kind registries contain 'subagent'
- **What:** VALID_KINDS and VALID_FORGE_BINDING_KINDS are consistent (Risk 2 drift prevention)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.db import VALID_FORGE_BINDING_KINDS; from app.db.project_forge_bindings import VALID_KINDS; assert 'subagent' in VALID_KINDS, 'VALID_KINDS missing subagent'; assert 'subagent' in VALID_FORGE_BINDING_KINDS, 'VALID_FORGE_BINDING_KINDS missing subagent'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** Registry drift — create would accept subagent but bind would silently skip it (Risk 2 from RESEARCH.md)

### S4: DB schema smoke — all new tables created at init
- **What:** forge_bundles, forge_bundle_items, forge_origin, subagents tables exist after schema init
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import tempfile, os; os.environ['DB_PATH'] = tempfile.mktemp(suffix='.db'); import app.db.schema as s; from app.db.database import get_connection; conn = get_connection().__enter__(); tables = {r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()}; required = {'subagents','forge_bundles','forge_bundle_items','forge_origin'}; missing = required - tables; assert not missing, f'Missing tables: {missing}'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** A schema registration was missed in schema/__init__.py

### S5: SKILL.md files parse as valid YAML frontmatter
- **What:** All five forge-creator seed files have parseable frontmatter with name + description keys
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import pathlib, re; seeds = list(pathlib.Path('app/forge_seeds/forge-creator').rglob('SKILL.md')); assert len(seeds) == 5, f'Expected 5 SKILL.md, found {len(seeds)}'; [__import__('re').search(r'name:', s.read_text()) or (_ for _ in ()).throw(AssertionError(f'No name: in {s}')) for s in seeds]; print('OK')"`
- **Expected:** `OK`
- **Failure means:** A seed file is missing or malformed

### S6: forge/create route is registered (router reachable)
- **What:** The new endpoint path exists in the Litestar app's route table
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import os; os.environ['AGENTED_LITESTAR_SKIP_STARTUP'] = '1'; from app_litestar.main import create_app; app = create_app(); paths = [str(r.path) for r in app.routes]; assert any('forge/create' in p for p in paths), f'forge/create not found in routes: {paths}'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** Handler not registered in forge_bindings_router or router not mounted

### S7: just build passes (frontend regression guard)
- **What:** vue-tsc type check + vite build succeed (frontend not touched, but gate is required)
- **Command:** `cd /Users/neo/Developer/Projects/Agented && just build`
- **Expected:** Exit code 0
- **Failure means:** A pre-existing frontend issue or accidental frontend file modification

**Sanity gate:** ALL sanity checks must pass. Any failure blocks proxy evaluation.

---

## Level 2: Proxy Metrics

**Purpose:** Behavioral pytest targets. These are automated tests that directly assert the phase success criteria.

**IMPORTANT:** Each test is a proxy in the sense that it runs against an isolated_db fixture and tmp_path workspace — not a live production system. Full-system validation is deferred to Tier 3.

### P1: replace_for_project propagation-column round-trip (success criterion #3)
- **What:** PUT-replace preserves source_scope, source_shared_binding_id, fingerprint, conflict_policy
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_forge_replace_for_project.py -v`
- **Target:** All assertions pass; test also passes a second case verifying default coalescing matches add_binding
- **Evidence:** 17-01-PLAN.md task 2 — the test seeds non-default values, calls replace_for_project, reloads, and asserts exact equality
- **Correlation with full metric:** HIGH — the test exercises the exact SQL path that was buggy
- **Blind spots:** Does not test concurrent replace calls; does not test the route layer
- **Validated:** No — deferred to Tier 3 (end-to-end route call with real DB)

### P2: subagent CRUD + kind registry (success criterion #1, DB half)
- **What:** subagents table CRUD, subag- prefix, UNIQUE constraint, both registries
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_subagents_db.py -v`
- **Target:** create returns subag- prefixed id; get/list/delete round-trip; UNIQUE enforced; 'subagent' in both VALID_KINDS and VALID_FORGE_BINDING_KINDS
- **Evidence:** 17-02-PLAN.md task 3 — direct DB layer assertions
- **Correlation with full metric:** HIGH — directly tests the DB primitives the rest of the phase builds on
- **Blind spots:** Does not test route-layer create; does not test concurrent inserts
- **Validated:** No

### P3: subagent golden materialization to .claude/agents/ (success criterion #1, materialization half)
- **What:** materialize_primitives(kinds=['subagent']) writes correct file + frontmatter + manifest
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_forge_materialization.py -v`
- **Target:** .claude/agents/<safe-name>.md exists; frontmatter contains agented-kind: "subagent" and agented-asset-id; body present; result.rel_paths() includes path; second identical run produces identical bytes; manifest tracks under paths_by_kind.subagent
- **Evidence:** 17-02-PLAN.md task 2/3 — golden pattern mirroring existing command/rule golden tests
- **Correlation with full metric:** HIGH — directly asserts the materialized file content; determinism check prevents renderer drift
- **Blind spots:** tmp_path workspace, not a real project repo; does not test the cleanup path
- **Validated:** No

### P4: forge_bundles cross-kind CRUD + skill_sets unchanged (success criterion #4, DB half)
- **What:** forge_bundles/forge_bundle_items tables exist and hold cross-kind items; skill_sets DDL byte-for-byte unchanged
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_forge_bundles_db.py -v`
- **Target:** Cross-kind bundle round-trips; items ordered by position; delete cascades; skill_sets schema assertion passes
- **Evidence:** 17-03-PLAN.md task 3 — includes explicit sqlite_master check for skill_sets schema
- **Correlation with full metric:** HIGH — directly tests the constraint that is easiest to accidentally violate (Risk 8)
- **Blind spots:** Does not test the bundle-bind route; does not test interaction with bindings table
- **Validated:** No

### P5: 4-backend renderer golden tests for subagent projection (success criterion #1, renderer half)
- **What:** All four renderers project a bound subagent correctly; codex/gemini/opencode emit system-prompt block; claude uses native discovery
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_prompt_renderer.py -v`
- **Target:** Per-backend golden assertions pass for a bound subagent; deterministic (same input → same output); claude does NOT duplicate body inline
- **Evidence:** 17-04-PLAN.md task 3 — golden tests per backend with asymmetry documented (claude vs non-claude)
- **Correlation with full metric:** HIGH — directly asserts the projected text; deferred test only adds live harness smoke
- **Blind spots:** Fixture data, not a real harness invocation; overlay file behavior not tested in isolation
- **Validated:** No

### P6: subagent in ContextBundle (success criterion #1, compiler half)
- **What:** ContextCompilerService includes bound subagents in the compiled bundle
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/services/test_context_compiler_service.py -v`
- **Target:** Bound subagent name/body appears in compiled ContextBundle; compiler imports get_subagent
- **Evidence:** 17-04-PLAN.md task 1 — seeded subagent + binding through compiler
- **Correlation with full metric:** HIGH — tests the compilation layer that all renderers consume
- **Blind spots:** Does not test all four renderers in this file
- **Validated:** No

### P7: Atomic create success + no-orphan injected failure + bundle-bind (success criterion #2 + #4 route half)
- **What:** forge/create creates row+binding+file on success; compensating cleanup on injected failure at bind stage and at materialize stage; bundle-bind binds cross-kind in one call
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/routes/test_forge_bindings_routes.py -v`
- **Target (create success):** 201 response; subagents row exists; binding exists; .claude/agents/<name>.md exists on disk
- **Target (no-orphan at bind failure):** 5xx response; no orphaned subagents row; no binding; no .claude/agents/ file
- **Target (no-orphan at materialize failure):** same orphan assertions
- **Target (bundle-bind):** 200 response; all cross-kind items bound
- **Evidence:** 17-05-PLAN.md tasks 1-3 — monkeypatch injected failure at two stages; this is the primary atomicity gate
- **Correlation with full metric:** HIGH — directly tests the compensating cleanup path that is the core risk of the phase (Risk 5)
- **Blind spots:** monkeypatched failure, not a real DB crash or disk-full condition; isolated_db not production SQLite
- **Validated:** No

### P8: forge-creator seed idempotence (success criterion #5, seed half)
- **What:** seed_forge_creator_bundle produces exactly five skills + one global bundle; re-run adds nothing
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_forge_creator_seed.py -v`
- **Target:** Five user_skills rows with skill_name unique; one forge_bundles row (scope=global) named "forge-creator"; five forge_bundle_items; calling seed twice results in same state (no duplicates)
- **Evidence:** 17-06-PLAN.md task 1 — models idempotence on predefined-bot seed pattern
- **Correlation with full metric:** HIGH — startup idempotence is the critical production property
- **Blind spots:** Does not test AGENTED_LITESTAR_SKIP_STARTUP=1 path; isolated_db not lifecycle-integrated
- **Validated:** No

### P9: session auto-import diff/gate/provenance (success criterion #5, import half)
- **What:** on_session_complete imports only Agented-driven-session artifacts from .claude/ diff; records content-hash + session id; ignores operator edits; idempotent
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_forge_session_import.py -v`
- **Target:** Fixture tree with one scaffolded subagent + one operator file; Agented session_kind → subagent imported + forge_origin row written with correct content_hash + session_id; operator file NOT imported; second call is no-op
- **Evidence:** 17-06-PLAN.md task 3 — explicit fixture tree with contrasting session_kind gate
- **Correlation with full metric:** MEDIUM — fixture tree simulates but does not reproduce a real session; Agented-driven gate logic inferred from session_kind field (see RESEARCH.md risk 7 note on gate mechanism confidence)
- **Blind spots:** Does not test what happens when manifest is absent or corrupt; Agented-driven detection relies on session_kind being correctly set by the harness
- **Validated:** No

### P10: Backend pytest house gate — targeted set
- **What:** All forge/materialization/renderer/route/bundle/import tests pass under the watchdog substitution procedure
- **Command (attempt full first):** `cd /Users/neo/Developer/Projects/Agented/backend && timeout 720 uv run pytest 2>&1 | tail -20`
- **Command (targeted fallback on hang):** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_forge_replace_for_project.py tests/test_subagents_db.py tests/test_forge_materialization.py tests/test_forge_bundles_db.py tests/test_prompt_renderer.py tests/services/test_context_compiler_service.py tests/routes/test_forge_bindings_routes.py tests/test_forge_creator_seed.py tests/test_forge_session_import.py tests/test_forge_git_commit.py tests/test_forge_round_wiring.py tests/test_forge_skill_dispatch.py -v`
- **Target:** All targeted tests pass; 0 new failures relative to pre-phase baseline
- **Procedure:** Attempt full suite under 12-minute watchdog. On hang (known issue, ~40-48%), kill and run targeted set. Disclose substitution in PR.
- **Evidence:** CLAUDE.md Verification section — house gate is mandatory
- **Correlation with full metric:** MEDIUM (targeted set) / HIGH (full suite, if it completes)
- **Blind spots:** Full suite hang means some non-forge tests may not run
- **Validated:** No

### P11: Frontend no-new-failures gate
- **What:** No new test failures introduced (baseline carries 7 known pre-existing failures)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run`
- **Target:** Failure count <= 7 (the known pre-existing set); no new failures
- **Evidence:** CLAUDE.md Verification section — phase is backend-only so no delta expected
- **Correlation with full metric:** HIGH (this is the exact gate condition)
- **Blind spots:** Does not catch runtime frontend regressions from indirect backend changes
- **Validated:** No

---

## Level 3: Deferred Validations

**Purpose:** Full integration checks requiring a live project workspace or a real Agented-driven session.

### D1: End-to-end forge/create against a real project workspace — DEFER-17-01
- **What:** POST /admin/projects/{id}/forge/create with a live Litestar instance against a real git-tracked workspace; verify .claude/agents/<name>.md actually lands on disk, all four backend renderers compile the projection without error, and the manifest JSON reflects the new file
- **Why deferred:** Route tests use isolated_db + tmp_path. A real workspace has git state, existing .claude/ files, and production SQLite — edge cases the fixture cannot reproduce
- **Validates at:** phase-21-integration (or any phase that exercises end-to-end forge materialization in a production-like setup)
- **Depends on:** Running Litestar instance + a project with a real workspace path + all four harness binaries available for compilation smoke
- **Target:** HTTP 201; file exists at expected path; manifest updated; all four renderer compiles exit 0
- **Risk if unmet:** Path resolution bug in ProjectWorkspaceService not caught by fixture tests; cross-kind manifest conflict not caught
- **Fallback:** Manual smoke test against a dev instance before merging; document result in PR

### D2: Live session-completion auto-import dogfood — DEFER-17-02
- **What:** Run at least one real Agented-driven session that scaffolds a subagent or skill primitive; confirm on_session_complete fires, imports the artifact, writes forge_origin row with correct content_hash + source_session_id, and a subsequent session does not re-import (idempotent)
- **Why deferred:** The Agented-driven gate (session_kind field from execution_events) is inferred from the harness_takeaway_extractor pattern; the exact session_kind values produced by real harness runs are not verified by the fixture test. A real session is the only way to confirm the gate fires correctly
- **Validates at:** phase-21-integration (or manually against a dev instance with at least one logged session)
- **Depends on:** Running Agented instance with lifecycle.py fully wired; at least one harness session completing via the existing orchestration path
- **Target:** Imported primitive appears in subagents/skills table; forge_origin row has sha256 of the file bytes; second session with identical file produces no new row
- **Risk if unmet:** Session_kind gate may be too narrow (misses Agented sessions) or too broad (imports operator edits); medium probability, medium impact
- **Fallback:** Adjust gate condition in forge_session_import.py and re-run targeted test with updated fixture session_kind values

---

## Ablation Plan

**No ablation plan** — This phase implements six concrete engineering changes (bug fix, new kind, new tables, renderer extension, atomic route, seed + import). There are no competing algorithmic approaches to ablate. The injected-failure test in P7 serves as the closest analogue: it directly measures the value of the compensating cleanup logic.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Pre-phase forge test suite | Existing tests/test_forge_*.py all pass before phase starts | All pass | RESEARCH.md "Existing forge tests" |
| Pre-phase frontend tests | 7 known pre-existing failures only | Exactly 7 failures | CLAUDE.md Verification #3 |
| replace_for_project (pre-fix) | Drops four propagation columns silently | Bug confirmed at L157 | RESEARCH.md "THE replace_for_project BUG" |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_forge_replace_for_project.py   (plan 17-01)
backend/tests/test_subagents_db.py                (plan 17-02)
backend/tests/test_forge_materialization.py       (plan 17-02, extended)
backend/tests/test_forge_bundles_db.py            (plan 17-03)
backend/tests/test_prompt_renderer.py             (plan 17-04, extended)
backend/tests/services/test_context_compiler_service.py  (plan 17-04, extended)
backend/tests/routes/test_forge_bindings_routes.py (plan 17-05, extended)
backend/tests/test_forge_creator_seed.py          (plan 17-06)
backend/tests/test_forge_session_import.py        (plan 17-06)
```

**How to run full targeted evaluation:**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest \
  tests/test_forge_replace_for_project.py \
  tests/test_subagents_db.py \
  tests/test_forge_materialization.py \
  tests/test_forge_bundles_db.py \
  tests/test_prompt_renderer.py \
  tests/services/test_context_compiler_service.py \
  tests/routes/test_forge_bindings_routes.py \
  tests/test_forge_creator_seed.py \
  tests/test_forge_session_import.py \
  tests/test_forge_git_commit.py \
  tests/test_forge_round_wiring.py \
  tests/test_forge_skill_dispatch.py \
  -v
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: ruff format + lint | [PASS/FAIL] | | |
| S2: import smoke | [PASS/FAIL] | | |
| S3: kind registries | [PASS/FAIL] | | |
| S4: DB schema smoke | [PASS/FAIL] | | |
| S5: SKILL.md frontmatter | [PASS/FAIL] | | |
| S6: route registered | [PASS/FAIL] | | |
| S7: just build | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: replace_for_project round-trip | all pass | | [MET/MISSED] | |
| P2: subagent CRUD | all pass | | [MET/MISSED] | |
| P3: subagent golden materialization | all pass | | [MET/MISSED] | |
| P4: forge_bundles + skill_sets guard | all pass | | [MET/MISSED] | |
| P5: 4-backend renderer goldens | all pass | | [MET/MISSED] | |
| P6: subagent in ContextBundle | all pass | | [MET/MISSED] | |
| P7: create success + no-orphan + bundle-bind | all pass (3 sub-cases) | | [MET/MISSED] | |
| P8: forge-creator seed idempotence | all pass | | [MET/MISSED] | |
| P9: session import diff/gate/provenance | all pass | | [MET/MISSED] | |
| P10: backend pytest house gate | 0 new failures | | [MET/MISSED] | full/targeted? |
| P11: frontend no-new-failures | <=7 failures | | [MET/MISSED] | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-17-01 | End-to-end forge/create real workspace | PENDING | phase-21-integration |
| DEFER-17-02 | Live session auto-import dogfood | PENDING | phase-21-integration |

---

## Success Criteria to Proxy Test Mapping

| Success Criterion | Proxy Test(s) |
|-------------------|---------------|
| #1 subagent valid forge kind (DB + materialization + renderer) | P2, P3, P5, P6 |
| #2 atomic create with compensating cleanup | P7 (create success + no-orphan cases) |
| #3 replace_for_project preserves propagation columns | P1 |
| #4 forge_bundles + bundle-bind; skill_sets unchanged | P4, P7 (bundle-bind case) |
| #5 forge-creator seed + auto-import with provenance | P8, P9 |
| #6 House gates pass | S7 (just build), P10, P11 |

---

## Verdict Rule

**Phase 17 passes at proxy level when:**

1. ALL seven Tier-1 sanity checks pass (S1-S7)
2. ALL eleven Tier-2 proxy tests pass (P1-P11), including:
   - P7 must pass all three sub-cases (create success, no-orphan at bind failure, no-orphan at materialize failure)
   - P10 must pass either the full suite (preferred) or the full targeted set with the hang substitution disclosed
   - P11 must show no new frontend failures beyond the 7 known pre-existing ones
3. Tier-3 deferred items (DEFER-17-01, DEFER-17-02) are tracked as PENDING for phase-21-integration

**If any Tier-1 or Tier-2 check fails, the phase is NOT complete at proxy level.** Tier-3 deferred items do not block the proxy verdict.

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: adequate — all directly executable from the phase directory with no external deps
- Proxy metrics: well-evidenced — every test directly maps to a plan must_have and tests the exact code path named in the plan; the injected-failure test (P7) is the gold standard for atomicity verification
- Deferred coverage: partial but honest — the Agented-driven gate mechanism is the only MEDIUM-confidence element (RESEARCH.md explicitly flags this); the fixture test covers the logic but real session_kind values are unconfirmed until a live run

**What this evaluation CAN tell us:**
- All six data structures (subagents, forge_bundles, forge_bundle_items, forge_origin, updated bindings, forge_origin) persist correctly in isolation
- The atomic create/cleanup path is correct for the monkeypatched failure scenarios
- All four renderers project subagents deterministically per the golden fixture
- The session import correctly gates on session_kind and records provenance against a fixture tree

**What this evaluation CANNOT tell us (until Tier 3):**
- Whether the ProjectWorkspaceService path resolution works against a real git-tracked project (DEFER-17-01)
- Whether the session_kind values emitted by real harness executions match the gate condition in forge_session_import.py (DEFER-17-02)
- Whether compensating cleanup handles disk-full or mid-write filesystem errors (beyond the scope of monkeypatched failure)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-13*
