# Evaluation Plan: Phase 15 — Code Consistency & Standards

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Systematic mechanical refactoring — CON-01 through CON-09
**Reference papers:** N/A (codebase audit metrics, not ML/model evaluation)

## Evaluation Overview

Phase 15 is a pure refactoring phase with no new features and no behavioral changes. The goal is to bring the backend and frontend codebases into compliance with documented conventions, replacing ad-hoc patterns with centralized, consistent alternatives. Because no new functionality is introduced, evaluation is entirely structural: can we verify, with certainty, that the old pattern is gone and the new pattern is present everywhere it should be?

Every requirement in this phase (CON-01 through CON-09) is verifiable by grep, lint, or build tool — these are not approximations or proxies. Where a grep returning empty means "zero violations remain," that is a Level 1 sanity check, not a proxy metric. This evaluation plan classifies almost everything as Level 1 because the verification is definitive and cheap.

The phase is split into three plans executed across two waves. Plan 15-01 (backend logging, config constants, ID factory) and Plan 15-02 (frontend type consolidation, useAsyncState composable) run in parallel as Wave 1. Plan 15-03 (route ErrorResponse, DB naming, type annotations, exception handling) depends on 15-01 completing first (Wave 2). Each plan's sanity gates are evaluated independently.

There are no paper metrics, no ML benchmarks, and no domain-specific quality measures. The baseline is the pre-refactoring violation count measured from the current codebase on 2026-03-04. Every target is zero violations or full test suite passage.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| `print()` count in services | Codebase grep audit (2026-03-04) | CON-01: structured logging requirement |
| `random.choices()` outside ids.py | Codebase grep audit | CON-04: cryptographic ID generation requirement |
| `add_` entity creation functions | Codebase grep audit | CON-06: DB naming convention requirement |
| Ad-hoc `{"error":` in routes | Codebase grep audit | CON-02: ErrorResponse standardization requirement |
| TypeScript `any` in src/ | Codebase grep audit | CON-08: type safety requirement |
| `ChatMessage` references | Codebase grep audit | CON-08: type deduplication requirement |
| Backend test pass rate | Existing pytest baseline (906/906) | Confirms no behavioral regression |
| Frontend build + type check | Existing vue-tsc baseline (0 errors) | Confirms no type regression |
| Frontend test pass rate | Existing vitest baseline (344/344) | Confirms no behavioral regression |
| Service files missing logger | Codebase grep audit | CON-01: prerequisite for exception standardization |

### Baselines (Measured 2026-03-04)

| Metric | Baseline Count | Target After Phase 15 |
|--------|---------------|----------------------|
| `print()` in `app/services/` | 12 | 0 |
| `random.choices()` outside ids.py | 2 | 0 |
| `add_` entity creation functions in db/ | ~15 (exempt collection-add functions excluded) | 0 |
| Ad-hoc `{"error":` dicts in routes/ | 475 | 0 |
| TypeScript `any` in frontend src/ | 147 | 0 (documented exceptions allowed) |
| `ChatMessage` references | 11 | 0 |
| Service files missing logger | 30 of 91 | 0 |
| `generate_id()` factory in ids.py | absent | present |
| `useAsyncState.ts` composable | absent | present |
| Named constants in config.py | absent (0 of expected domains) | present (all 5 domains) |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 18 | Grep-based violation counts, build pass/fail, test suite pass/fail |
| Proxy (L2) | 4 | Spot-checks that cannot be fully automated (exception severity, constant coverage) |
| Deferred (L3) | 2 | CI enforcement rules not yet wired into the project's lint configuration |

---

## Level 1: Sanity Checks

**Purpose:** Verify zero violations and full test suite passage. These are not approximations — a grep returning empty is definitive. ALL must pass before the phase is considered complete.

The checks are organized by plan to allow incremental validation as each plan completes.

---

### Plan 15-01 Sanity Gate (Wave 1 — Backend)

#### S1: Zero print() in service files

- **What:** No `print()` calls remain in any Python file under `backend/app/services/`
- **Command:** `grep -rn 'print(' /Users/neo/Developer/Projects/Agented/backend/app/services/ --include='*.py' | grep -v '__pycache__'`
- **Expected:** Empty output (zero lines)
- **Baseline:** 12 occurrences across service files
- **Failure means:** CON-01 is incomplete; some service files were not converted to logger

#### S2: All service files have logger declaration

- **What:** Every `.py` file in `backend/app/services/` (except `__init__.py`) declares a module-level logger
- **Command:** `grep -rLn 'logger = logging.getLogger' /Users/neo/Developer/Projects/Agented/backend/app/services/*.py | grep -v __init__`
- **Expected:** Empty output (no files missing logger)
- **Baseline:** 30 of 91 service files missing logger
- **Failure means:** Some service files are logging-incapable; CON-01 incomplete

#### S3: Zero random.choices() outside ids.py

- **What:** The two rogue `random.choices()` call sites have been eliminated
- **Command:** `grep -rn 'random\.choices' /Users/neo/Developer/Projects/Agented/backend/app/ --include='*.py' | grep -v '__pycache__' | grep -v 'ids\.py'`
- **Expected:** Empty output
- **Baseline:** 2 occurrences (super_agents.py:317, team_execution_service.py:62)
- **Failure means:** CON-04 incomplete; non-cryptographic ID generation still present

#### S4: generate_id() factory exists in ids.py

- **What:** The centralized factory function is present in the IDs module
- **Command:** `grep -n 'def generate_id' /Users/neo/Developer/Projects/Agented/backend/app/db/ids.py`
- **Expected:** At least one matching line showing the function definition
- **Failure means:** CON-04 incomplete; entity generators are not consolidated

#### S5: Config constants importable (5 domains)

- **What:** All five constant domains are present in config.py and importable
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.config import EXECUTION_TIMEOUT_DEFAULT, SSE_REPLAY_LIMIT, MAX_RETRY_ATTEMPTS, THREAD_JOIN_TIMEOUT, DEFAULT_5H_TOKEN_LIMIT, CLONE_TIMEOUT; print('OK')"`
- **Expected:** Prints `OK` with no errors
- **Failure means:** CON-07 incomplete; config.py lacks one or more constant domains

#### S6: config.py has no local app imports

- **What:** config.py remains a pure constants module (no circular dependency risk)
- **Command:** `grep -n 'from app\.\|import app\.' /Users/neo/Developer/Projects/Agented/backend/app/config.py`
- **Expected:** Empty output (no intra-app imports)
- **Failure means:** Circular import risk introduced; startup may fail on import

#### S7: Backend tests pass after Plan 15-01

- **What:** All 906 backend tests pass with no regressions
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest`
- **Expected:** Zero failures, zero errors (906 passed)
- **Failure means:** Refactoring broke behavior; regressions must be diagnosed and fixed before proceeding to Wave 2

#### S8: Ruff lint passes after Plan 15-01

- **What:** No lint violations introduced by the refactoring
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff check .`
- **Expected:** Exit code 0, no violations reported
- **Failure means:** Introduced imports or patterns that violate configured lint rules

#### S9: Ruff format passes after Plan 15-01

- **What:** All modified Python files are properly formatted
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check .`
- **Expected:** Exit code 0 (no formatting differences)
- **Failure means:** Files need formatting; run `ruff format .` to fix

---

### Plan 15-02 Sanity Gate (Wave 1 — Frontend)

#### S10: Zero ChatMessage references in frontend

- **What:** The duplicate `ChatMessage` interface is gone; all code uses `ConversationMessage`
- **Command:** `grep -rn 'ChatMessage' /Users/neo/Developer/Projects/Agented/frontend/src/ --include='*.ts' --include='*.vue' | grep -v node_modules`
- **Expected:** Empty output
- **Baseline:** 11 references (1 definition in useSketchChat + usages)
- **Failure means:** CON-08 type consolidation incomplete; duplicate type remains

#### S11: useAsyncState composable file exists

- **What:** The shared async state composable has been created
- **Command:** `test -f /Users/neo/Developer/Projects/Agented/frontend/src/composables/useAsyncState.ts && echo "EXISTS"`
- **Expected:** Prints `EXISTS`
- **Failure means:** CON-09 incomplete; useAsyncState not created

#### S12: Frontend build passes (includes vue-tsc)

- **What:** The frontend compiles with zero TypeScript errors and zero build errors
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run build`
- **Expected:** Build succeeds with exit code 0; no type errors reported by vue-tsc
- **Baseline:** 0 existing type errors before phase start
- **Failure means:** TypeScript `any` removal cascade broke type compatibility; must fix before declaring complete

#### S13: Frontend tests pass after Plan 15-02

- **What:** All 344 frontend tests pass with no regressions
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run`
- **Expected:** Zero failures (344 passed)
- **Failure means:** Type changes or composable creation broke component behavior

---

### Plan 15-03 Sanity Gate (Wave 2 — Backend)

#### S14: Zero direct ad-hoc error dicts in routes

- **What:** No route handler constructs `{"error": ...}` directly; all use `ErrorResponse(...).model_dump()`
- **Command:** `grep -rn 'return {"error":' /Users/neo/Developer/Projects/Agented/backend/app/routes/ --include='*.py' | grep -v '__pycache__'`
- **Expected:** Empty output
- **Baseline:** 475 ad-hoc error dict occurrences across all routes
- **Failure means:** CON-02 incomplete; some route error returns not converted

#### S15: Zero entity creation add_ functions in db/ (exemptions applied)

- **What:** All `add_*` entity creation functions have been renamed to `create_*`; collection-add functions (add_team_member, add_project_path, add_agent_message, etc.) are preserved
- **Command:** `grep -rn 'def add_' /Users/neo/Developer/Projects/Agented/backend/app/db/ --include='*.py' | grep -v '__pycache__' | grep -v '__init__' | grep -v 'add_team_member\|add_project_path\|add_team_edge\|add_team_agent_assignment\|add_team_connection\|add_agent_message\|add_plugin_component\|add_marketplace_plugin\|add_sync_state\|add_plugin_export\|add_project_skill\|add_project_installation\|add_project_team_edge\|add_project_to_trigger\|add_project_phase\|add_project_plan\|add_project_session\|add_github_repo\|add_pr_review\|add_user_skill\|add_super_agent_document\|add_super_agent_session\|add_workflow_version\|add_workflow_version_raw\|add_workflow_execution\|add_workflow_node_execution\|add_workflow_approval_state\|add_execution_type_handler\|add_rotation_event\|add_product_decision\|add_product_milestone\|add_milestone_project'`
- **Expected:** Empty output
- **Baseline:** ~15 entity creation functions still using `add_` prefix
- **Failure means:** CON-06 incomplete; DB naming convention not fully applied

#### S16: Exception blocks in services are classified

- **What:** No bare `except Exception: pass` exists without an explanatory comment
- **Command:** `grep -A1 'except.*Exception' /Users/neo/Developer/Projects/Agented/backend/app/services/*.py | grep -B1 'pass$' | grep 'except' | grep -v '#'`
- **Expected:** Empty or minimal output (any results indicate unclassified silent exception blocks)
- **Baseline:** 232 exception handlers in services; unknown proportion are unclassified bare `pass`
- **Failure means:** CON-05 incomplete; exception severity convention not applied

#### S17: Backend tests pass after Plan 15-03

- **What:** All 906 backend tests pass after the Wave 2 refactoring (includes DB renames and route changes)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest`
- **Expected:** Zero failures (906 passed)
- **Failure means:** DB rename broke imports or callers; diagnose via `ImportError` / `AttributeError` in failure output

#### S18: Final ruff check passes after Plan 15-03

- **What:** Backend lint remains clean after all Wave 2 changes
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff check . && uv run ruff format --check .`
- **Expected:** Exit code 0 for both commands
- **Failure means:** Wave 2 changes introduced lint or formatting violations

**Sanity gate:** ALL 18 sanity checks must pass. S1–S9 block Wave 2 (15-03 cannot start if 15-01 fails). S10–S13 are independent (15-02 runs in parallel). S14–S18 validate Wave 2 completion. Any failure blocks marking the phase complete.

---

## Level 2: Proxy Metrics

**Purpose:** Verify quality of the refactoring in dimensions not fully capturable by grep alone. These involve spot-checks requiring judgment.

**IMPORTANT:** These are human-review proxy checks, not automated metrics. They cannot be verified by running a command. Results are subject to reviewer judgment and should be documented in the SUMMARY.md for each plan.

### P1: Exception handling severity spot-check

- **What:** Representative sample of exception handlers in services follows the documented three-level severity convention
- **How:** Manually review 5 service files (randomly selected) and inspect each `except` block
- **Target:** All 5 spot-checked files show correct severity classification (Level 1 = error+exc_info+return, Level 2 = warning+continue, Level 3 = pass+comment)
- **Sample selection:** `ls backend/app/services/*.py | shuf | head -5`
- **Evidence:** CON-05 severity convention documented in 15-RESEARCH.md#Example-5
- **Correlation with full metric:** MEDIUM — 5 files out of 91 is a 5.5% sample; does not catch tail cases
- **Blind spots:** Intentionally silenced blocks that should have been escalated to Level 2; over-logging in cleanup paths not caught
- **Validated:** No — automation of this check would require AST analysis beyond grep scope

### P2: Config constants coverage spot-check

- **What:** Magic numbers previously scattered across services are now referenced as named imports from config.py
- **How:** Search for the 5 most common numeric literals used as timeouts/limits and verify they now import from config.py rather than being inline
- **Command:** `grep -rn 'from app.config import' /Users/neo/Developer/Projects/Agented/backend/app/services/ | wc -l`
- **Target:** At least 10 service files importing from config.py (showing adoption, not just constant definition)
- **Evidence:** CON-07 requirement; research identifies execution timeouts, SSE limits, retry counts as primary targets
- **Correlation with full metric:** MEDIUM — adoption count does not verify the right constants were extracted
- **Blind spots:** Constants added to config.py but never imported (definition without adoption)
- **Validated:** No — deferred to manual code review during PR review

### P3: TypeScript any reduction quality check

- **What:** Remaining `any` occurrences (documented exceptions) are actually justified third-party library interactions, not lazy shortcuts
- **How:** Review all remaining `eslint-disable-next-line @typescript-eslint/no-explicit-any` comments in frontend src/
- **Command:** `grep -rn 'eslint-disable.*no-explicit-any' /Users/neo/Developer/Projects/Agented/frontend/src/ --include='*.ts' --include='*.vue'`
- **Target:** Every eslint-disable comment has an explanation after the `--` separator naming the third-party library or specific reason
- **Evidence:** Research Open Question #4 establishes that Chart.js callbacks and Vue Flow events are acceptable exceptions; others require justification
- **Correlation with full metric:** HIGH — direct review of all exception cases
- **Blind spots:** Does not verify that genuinely eliminatable `any` wasn't also suppressed with eslint-disable
- **Validated:** No

### P4: DB rename completeness across the import chain

- **What:** The `add_` to `create_` rename propagated correctly through `db/__init__.py`, `database.py` (wildcard re-export), and all service callers
- **How:** Verify no `add_<entity>` calls remain in services or routes after the rename
- **Command:** `grep -rn '\.add_agent\|\.add_team\|\.add_trigger\|\.add_plugin\|\.add_product\|\.add_project\|add_bot\|add_rule\|add_skill\|add_hook\|add_command' /Users/neo/Developer/Projects/Agented/backend/app/services/ /Users/neo/Developer/Projects/Agented/backend/app/routes/ --include='*.py' | grep -v '__pycache__'`
- **Target:** Empty output (no callers using the old `add_` names for entity creation)
- **Evidence:** Research Pitfall 1 documents the wildcard import chain risk through database.py
- **Correlation with full metric:** HIGH — direct verification that callers adopted the new names
- **Blind spots:** Test files (covered by S17 pytest run rather than this grep)
- **Validated:** No — this check is a complement to S15 (which only checks definitions, not callers)

---

## Level 3: Deferred Validations

**Purpose:** Validations that require wiring into infrastructure not yet configured. These are not blockers for phase completion but represent the difference between local compliance and enforced compliance.

### D1: Ruff T201 (no-print) rule in CI — DEFER-15-01

- **What:** Automated enforcement that `print()` in service code is rejected by CI lint, not just removed as a one-time cleanup
- **How:** Add `T201` to the `select` list in `ruff.toml` / `pyproject.toml`; configure per-file ignores for migrations and seeds
- **Why deferred:** Enabling T201 globally requires deciding the scope of ignores (migrations, seeds, tests, CLI scripts); incorrect ignore patterns will generate false positives or false negatives. This requires a separate, focused configuration change.
- **Validates at:** Phase 16 (code quality enforcement) or first CI configuration phase
- **Depends on:** Ruff configuration audit to determine correct per-file-ignores scope
- **Target:** `ruff check --select T201 backend/app/services/` returns zero violations at all future points
- **Risk if unmet:** print() calls may re-accumulate in services after the one-time cleanup; enforcement is manual rather than automatic
- **Fallback:** Periodic grep audit in quarterly code reviews

### D2: TypeScript no-explicit-any ESLint rule — DEFER-15-02

- **What:** Automated enforcement that `any` usage in frontend src/ is rejected by CI lint
- **How:** Enable `@typescript-eslint/no-explicit-any` in `.eslintrc` or `eslint.config.js`; configure `ignoreRestArgs: false`; add justified exceptions as inline suppressions
- **Why deferred:** The frontend currently has no ESLint configured (or its configuration is not enforcing this rule). Enabling the rule requires first verifying the ESLint setup and then ensuring the 147 baseline `any` instances are resolved — otherwise CI would fail immediately. This is a follow-up enforcement step, not part of the initial cleanup.
- **Validates at:** Phase 16 (frontend quality enforcement) or first ESLint hardening phase
- **Depends on:** ESLint configured and operational in frontend CI pipeline; `any` reduction from 15-02 already complete
- **Target:** ESLint passes with zero `@typescript-eslint/no-explicit-any` violations (except documented suppressions)
- **Risk if unmet:** TypeScript `any` will re-accumulate after the one-time reduction; enforcement is manual
- **Fallback:** Periodic `grep -rn ': any' src/` audit run alongside frontend builds

---

## Ablation Plan

No ablation plan applies. This phase implements independent mechanical refactoring requirements (CON-01 through CON-09). There are no sub-components to isolate for contribution analysis.

The three plans (15-01, 15-02, 15-03) are the closest analogue: each can be evaluated independently, and each plan's sanity gate (S1–S9, S10–S13, S14–S18) confirms that plan's requirements are met regardless of the others' status.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views.

This phase touches `frontend/src/composables/`, `frontend/src/services/api/types.ts`, and `frontend/src/components/**/*.vue` only for type-level changes (no UI/layout/routing changes). No new pages, views, or visible features are introduced.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Backend test suite | Current passing test count | 906/906 (100%) | STATE.md — v0.1.0 complete metrics |
| Frontend build (vue-tsc) | Type errors at phase start | 0 errors | STATE.md — v0.1.0 complete metrics |
| Frontend test suite | Current passing test count | 344/344 (100%) | STATE.md — v0.1.0 complete metrics |
| `print()` in services | Violations before Phase 15 | 12 | Grep audit 2026-03-04 |
| `random.choices()` outside ids.py | Rogue calls before Phase 15 | 2 | Grep audit 2026-03-04 |
| `add_` entity creation functions | DB naming violations before Phase 15 | ~15 | Grep audit 2026-03-04 |
| Ad-hoc error dicts in routes | Route error format violations before Phase 15 | 475 | Grep audit 2026-03-04 |
| TypeScript `any` in frontend | Type safety violations before Phase 15 | 147 | Grep audit 2026-03-04 |
| `ChatMessage` references | Duplicate type references before Phase 15 | 11 | Grep audit 2026-03-04 |
| Service files missing logger | Missing logger setup before Phase 15 | 30 of 91 | Grep audit 2026-03-04 |

---

## Evaluation Scripts

**Location of evaluation code:**

No dedicated evaluation scripts needed. All Level 1 checks use standard tooling (grep, pytest, npm run build, npm run test:run). Commands are specified inline in each check above.

**How to run full sanity evaluation (copy-paste block):**

```bash
# Plan 15-01 Sanity Gate
cd /Users/neo/Developer/Projects/Agented

echo "--- S1: print() in services ---"
grep -rn 'print(' backend/app/services/ --include='*.py' | grep -v '__pycache__'

echo "--- S2: services missing logger ---"
grep -rLn 'logger = logging.getLogger' backend/app/services/*.py | grep -v __init__

echo "--- S3: random.choices() outside ids.py ---"
grep -rn 'random\.choices' backend/app/ --include='*.py' | grep -v '__pycache__' | grep -v 'ids\.py'

echo "--- S4: generate_id() factory ---"
grep -n 'def generate_id' backend/app/db/ids.py

echo "--- S5: config constants importable ---"
cd backend && uv run python -c "from app.config import EXECUTION_TIMEOUT_DEFAULT, SSE_REPLAY_LIMIT, MAX_RETRY_ATTEMPTS, THREAD_JOIN_TIMEOUT, DEFAULT_5H_TOKEN_LIMIT, CLONE_TIMEOUT; print('OK')" && cd ..

echo "--- S6: config.py no circular imports ---"
grep -n 'from app\.\|import app\.' backend/app/config.py

echo "--- S7: backend tests ---"
cd backend && uv run pytest && cd ..

echo "--- S8+S9: ruff ---"
cd backend && uv run ruff check . && uv run ruff format --check . && cd ..

# Plan 15-02 Sanity Gate
echo "--- S10: ChatMessage references ---"
grep -rn 'ChatMessage' frontend/src/ --include='*.ts' --include='*.vue' | grep -v node_modules

echo "--- S11: useAsyncState exists ---"
test -f frontend/src/composables/useAsyncState.ts && echo "EXISTS" || echo "MISSING"

echo "--- S12: frontend build ---"
cd frontend && npm run build && cd ..

echo "--- S13: frontend tests ---"
cd frontend && npm run test:run && cd ..

# Plan 15-03 Sanity Gate
echo "--- S14: ad-hoc error dicts in routes ---"
grep -rn 'return {"error":' backend/app/routes/ --include='*.py' | grep -v '__pycache__'

echo "--- S15: add_ entity creation functions ---"
grep -rn 'def add_' backend/app/db/ --include='*.py' | grep -v '__pycache__' | grep -v '__init__' | grep -v 'add_team_member\|add_project_path\|add_team_edge\|add_team_agent_assignment\|add_team_connection\|add_agent_message\|add_plugin_component\|add_marketplace_plugin\|add_sync_state\|add_plugin_export\|add_project_skill\|add_project_installation\|add_project_team_edge\|add_project_to_trigger\|add_project_phase\|add_project_plan\|add_project_session\|add_github_repo\|add_pr_review\|add_user_skill\|add_super_agent_document\|add_super_agent_session\|add_workflow_version\|add_workflow_version_raw\|add_workflow_execution\|add_workflow_node_execution\|add_workflow_approval_state\|add_execution_type_handler\|add_rotation_event\|add_product_decision\|add_product_milestone\|add_milestone_project'

echo "--- S16: unclassified bare except pass ---"
grep -A1 'except.*Exception' backend/app/services/*.py | grep -B1 'pass$' | grep 'except' | grep -v '#'

echo "--- S17+S18: backend tests + ruff (post-wave-2) ---"
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check . && cd ..
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Plan 15-01 Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: print() in services | [PASS/FAIL] | [grep output or "empty"] | |
| S2: services missing logger | [PASS/FAIL] | [file list or "empty"] | |
| S3: random.choices() outside ids.py | [PASS/FAIL] | [grep output or "empty"] | |
| S4: generate_id() factory exists | [PASS/FAIL] | [grep match] | |
| S5: config constants importable | [PASS/FAIL] | [OK or error] | |
| S6: config.py no circular imports | [PASS/FAIL] | [grep output or "empty"] | |
| S7: backend tests | [PASS/FAIL] | [N passed, M failed] | |
| S8: ruff check | [PASS/FAIL] | [violations or "clean"] | |
| S9: ruff format | [PASS/FAIL] | ["no changes" or diff] | |

### Plan 15-02 Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S10: ChatMessage references | [PASS/FAIL] | [grep output or "empty"] | |
| S11: useAsyncState.ts exists | [PASS/FAIL] | [EXISTS or MISSING] | |
| S12: frontend build | [PASS/FAIL] | [0 errors or error list] | |
| S13: frontend tests | [PASS/FAIL] | [N passed, M failed] | |

### Plan 15-03 Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S14: ad-hoc error dicts in routes | [PASS/FAIL] | [grep output or "empty"] | |
| S15: add_ entity creation functions | [PASS/FAIL] | [grep output or "empty"] | |
| S16: unclassified bare except pass | [PASS/FAIL] | [grep output or "empty"] | |
| S17: backend tests (post-wave-2) | [PASS/FAIL] | [N passed, M failed] | |
| S18: ruff (post-wave-2) | [PASS/FAIL] | [violations or "clean"] | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Exception severity spot-check | 5/5 files compliant | [N/5] | [MET/MISSED] | Files reviewed: |
| P2: Config constants adoption | ≥10 service files import from config.py | [N] | [MET/MISSED] | |
| P3: TypeScript any exceptions justified | All eslint-disable comments have explanation | [N with explanation / M total] | [MET/MISSED] | |
| P4: DB rename propagated to callers | Empty grep output | [grep output or "empty"] | [MET/MISSED] | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-15-01 | Ruff T201 no-print CI enforcement | PENDING | Phase 16 or CI hardening phase |
| DEFER-15-02 | ESLint no-explicit-any CI enforcement | PENDING | Phase 16 or ESLint hardening phase |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**

- **Sanity checks (18 checks):** High confidence. Every requirement in this phase is verifiable by grep or build tool. The baselines are exact counts from direct codebase measurement, not estimates. The commands are precise and testable.
- **Proxy metrics (4 checks):** Medium confidence. Three of the four proxy checks are themselves grep commands (P2, P4) and approach Level 1 quality. P1 (exception severity spot-check) is the only genuinely subjective metric; its 5.5% sample size is a real limitation.
- **Deferred coverage (2 items):** The deferred items are enforcement-layer concerns (CI rules), not validation gaps. The underlying compliance is verified by Level 1 checks. Missing deferred enforcement means re-accumulation is possible, not that the current state is unverified.

**What this evaluation CAN tell us:**

- Whether every measurable CON-01 through CON-09 requirement has zero remaining violations
- Whether the test suites still pass (behavioral regression detection)
- Whether the build toolchain accepts the refactored code
- Whether the new abstractions (generate_id, config constants, useAsyncState) are present and importable

**What this evaluation CANNOT tell us:**

- Whether the exception handling severity choices made during refactoring are semantically correct for each specific exception context (addressed partially by P1 spot-check; would require full code review to fully verify)
- Whether type annotations added to service/DB methods are semantically accurate vs. just syntactically present (no type-checking of the annotations themselves beyond what mypy/pyright would catch, and neither is configured)
- Whether `any` suppressions in frontend are truly justified vs. lazy (P3 spot-check approximates this; full review requires reading each third-party interaction)
- Whether CI enforcement will be added (D1, D2 are deferred)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
