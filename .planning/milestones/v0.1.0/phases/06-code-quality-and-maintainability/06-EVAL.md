# Evaluation Plan: Phase 6 — Code Quality and Maintainability

**Designed:** 2026-02-28
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Seed/migration separation, Ruff formatter migration, ExecutionService facade decomposition
**Reference documents:** 06-RESEARCH.md, ROADMAP.md (Phase 6 success criteria)

## Evaluation Overview

Phase 6 consists of three independent refactoring tasks with zero functional behavior changes. Because none of the three tasks add new features or change runtime behavior, evaluation is entirely correctness-oriented: does the code still work exactly as before, and do the new structural constraints hold?

This makes the evaluation tractable and honest. The primary verification instruments are automated — import smoke tests, tool exit codes, and the existing test suite. There are no paper metrics, benchmark datasets, or approximated quality scores. All three requirements have binary pass/fail outcomes that can be verified locally and deterministically.

The phase has no meaningful proxy metrics in the traditional sense: "percentage improvement in code quality" would require subjective judgment. Instead, Level 2 (proxy) is used here for the full pytest regression suite, which is an indirect but highly correlated proxy for correctness of the refactoring. Level 3 deferred validations cover the one genuinely non-automatable check: end-to-end functional validation that the seed and execution path work correctly under real data through the facade.

**Baselines confirmed by direct measurement (2026-02-28):**
- pytest: 911 tests passing, 0 failing
- `ruff check .`: 2 errors (import sorting in `app/db/__init__.py`)
- `ruff format --check .`: 29 files need reformatting
- `execution_service.py`: 1,387 lines
- `migrations.py`: 3,220 lines (seed functions at lines 3039-3221)
- `seeds.py`: does not exist (must be created)
- `prompt_renderer.py`: does not exist (must be created)
- `command_builder.py`: does not exist (must be created)

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| pytest pass rate | Codebase baseline (911 tests) | Refactoring must not change behavior — test suite is the ground truth |
| `ruff check` exit code | RESEARCH.md + ROADMAP.md success criteria | QUAL-02 definition of done |
| `ruff format --check` exit code | RESEARCH.md + ROADMAP.md success criteria | QUAL-02 definition of done |
| seeds.py import smoke test | ROADMAP.md success criteria (QUAL-01) | Direct verification of module existence and correct import path |
| PromptRenderer/CommandBuilder import | ROADMAP.md success criteria (QUAL-03) | Direct verification of new modules |
| ExecutionService delegation | ROADMAP.md success criteria (QUAL-03) | Confirms facade wires to helpers correctly |
| migrations.py seed-free | RESEARCH.md anti-patterns section | Confirms separation is complete, not partial |
| No test file modifications | 06-03-PLAN.md constraint | Facade must preserve all call sites unchanged |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 13 | Import checks, config presence, structural constraints (grep-verifiable) |
| Proxy (L2) | 4 | Full test suite regression + targeted test subsets |
| Deferred (L3) | 2 | End-to-end runtime validation of seed path and execution facade |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

These checks run in seconds and require no test database, no server, and no integration. They verify structural correctness of the changes.

### S1: seeds.py module importable (QUAL-01)
- **What:** The new `seeds.py` module loads without ImportError and exports all four seed functions
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.db.seeds import seed_predefined_triggers, seed_preset_mcp_servers, migrate_existing_paths, auto_register_project_root, PRESET_MCP_SERVERS; print('OK')"`
- **Expected:** Prints `OK`, exits 0
- **Failure means:** Circular import, missing dependency, or incomplete extraction from migrations.py

### S2: seeds.py contains all expected items (QUAL-01)
- **What:** PRESET_MCP_SERVERS constant has at least one entry (not an empty list from a botched move)
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.db.seeds import PRESET_MCP_SERVERS; print(len(PRESET_MCP_SERVERS))" 2>&1`
- **Expected:** Prints a positive integer (128 entries in the original list; any value >= 1 passes)
- **Failure means:** PRESET_MCP_SERVERS was not moved or was accidentally cleared

### S3: migrations.py no longer contains seed functions (QUAL-01)
- **What:** The four seed function definitions have been removed from migrations.py
- **Command:** `grep -c "^def seed_\|^def migrate_existing_paths\|^def auto_register_project_root" /Users/edward.seo/dev/private/project/harness/Agented/backend/app/db/migrations.py`
- **Expected:** Prints `0`
- **Failure means:** Seed functions were duplicated (added to seeds.py but not removed from migrations.py)

### S4: migrations.py no longer contains PRESET_MCP_SERVERS (QUAL-01)
- **What:** The large MCP server data constant has been moved out of migrations.py
- **Command:** `grep -c "^PRESET_MCP_SERVERS" /Users/edward.seo/dev/private/project/harness/Agented/backend/app/db/migrations.py`
- **Expected:** Prints `0`
- **Failure means:** Data constant was duplicated, not moved

### S5: db __init__.py re-export chain intact (QUAL-01)
- **What:** The standard import path `from app.db import seed_predefined_triggers` still resolves after the __init__.py update
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.db import seed_predefined_triggers, init_db; print('OK')"`
- **Expected:** Prints `OK`, exits 0
- **Failure means:** `app/db/__init__.py` was not updated to import from `.seeds`

### S6: database.py shim import chain intact (QUAL-01)
- **What:** The `app.database` shim (used by execution_service.py and many routes) still resolves seed functions
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.database import seed_predefined_triggers; print('OK')"`
- **Expected:** Prints `OK`, exits 0
- **Failure means:** `app/db/__init__.py` re-export not updated, or `database.py` star import broken

### S7: ruff check exits 0 (QUAL-02)
- **What:** All Python files in the backend pass Ruff lint rules (E, F, I)
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run ruff check .`
- **Expected:** No output, exit code 0
- **Failure means:** Remaining lint errors not auto-fixed, or the reformatting introduced new violations

### S8: ruff format exits 0 (QUAL-02)
- **What:** All Python files match Ruff's formatting rules exactly
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run ruff format --check .`
- **Expected:** No output (no files to reformat), exit code 0
- **Failure means:** `ruff format .` was not run, or a file was modified after formatting without re-running

### S9: No Black configuration remains in pyproject.toml (QUAL-02)
- **What:** The `[tool.black]` section has been removed
- **Command:** `grep -q "\[tool\.black\]" /Users/edward.seo/dev/private/project/harness/Agented/backend/pyproject.toml && echo "FAIL: black config found" || echo "PASS: no black config"`
- **Expected:** Prints `PASS: no black config`
- **Failure means:** Black config was left in place alongside Ruff config, causing toolchain ambiguity

### S10: No Black dependency remains in pyproject.toml (QUAL-02)
- **What:** `black` is not listed in any dependency section
- **Command:** `grep -q "black" /Users/edward.seo/dev/private/project/harness/Agented/backend/pyproject.toml && echo "FAIL: black dependency found" || echo "PASS: no black dependency"`
- **Expected:** Prints `PASS: no black dependency`
- **Failure means:** Black is still installed as a dev dependency, creating unnecessary toolchain overhead

### S11: PromptRenderer module importable (QUAL-03)
- **What:** The new `prompt_renderer.py` module loads and exports `PromptRenderer` with both static methods
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.services.prompt_renderer import PromptRenderer; assert hasattr(PromptRenderer, 'render'); assert hasattr(PromptRenderer, 'warn_unresolved'); print('OK')"`
- **Expected:** Prints `OK`, exits 0
- **Failure means:** Module not created, or one of the expected static methods is missing

### S12: CommandBuilder module importable (QUAL-03)
- **What:** The new `command_builder.py` module loads and exports `CommandBuilder` with `build` static method
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.services.command_builder import CommandBuilder; assert hasattr(CommandBuilder, 'build'); print('OK')"`
- **Expected:** Prints `OK`, exits 0
- **Failure means:** Module not created, or method name differs from expected

### S13: ExecutionService delegates to helpers (QUAL-03)
- **What:** The facade imports and uses both helper classes (delegation wired, not bypassed)
- **Command:** `grep -c "CommandBuilder.build\|PromptRenderer.render" /Users/edward.seo/dev/private/project/harness/Agented/backend/app/services/execution_service.py`
- **Expected:** Prints `2` (one occurrence of each call)
- **Failure means:** Delegation import added but not used, or helper logic duplicated instead of delegated

**Sanity gate:** ALL 13 sanity checks must pass. Any single failure blocks progression to proxy evaluation — a failing sanity check indicates a structural defect in the implementation.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of correctness for the refactoring changes.
**IMPORTANT:** These proxy metrics are well-correlated with correctness but do not test end-to-end runtime behavior (see Level 3 for that).

### P1: Full pytest regression (all three requirements)
- **What:** The complete backend test suite passes with 0 regressions
- **How:** Run the full test suite; compare pass count against baseline of 911 passing
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest --tb=short -q`
- **Target:** 911 passed, 0 failed, 0 errors (or higher if tests were added during the phase)
- **Evidence:** All three plans explicitly require 100% pass rate; tests cover import chains, command building (7 tests in TestBuildCommand), and run_trigger integration (7 tests in test_budget_integration.py)
- **Correlation with full correctness:** HIGH — the test suite exercises import paths and call sites directly; any broken delegation or broken re-export chain will surface as a test failure within the first few tests
- **Blind spots:** The test suite does not include end-to-end prompt rendering integration tests (confirmed by RESEARCH.md open question 3 — "no tests that verify prompt rendering logic end-to-end"). The `PromptRenderer.render()` logic may have a regression that is not caught by the current test suite.
- **Validated:** No — awaiting deferred validation DEFER-06-02

### P2: TestBuildCommand targeted subset (QUAL-03)
- **What:** The 7 tests that directly invoke `ExecutionService.build_command()` all pass, confirming the facade delegation preserves exact behavior
- **How:** Run only the TestBuildCommand class
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest tests/test_backend_detection.py::TestBuildCommand -v`
- **Target:** 7/7 tests pass
- **Evidence:** These tests are the primary test coverage for the `build_command` logic (RESEARCH.md sources section). If CommandBuilder.build() differs even slightly from the original body, one of the 4-backend test cases will fail.
- **Correlation with full correctness:** HIGH — these tests directly exercise the delegated code path with parameterized inputs
- **Blind spots:** Tests use hardcoded prompt strings; does not cover all possible `codex_settings` configurations
- **Validated:** No — awaiting deferred validation DEFER-06-01

### P3: run_trigger integration tests (QUAL-03)
- **What:** Integration tests that call `run_trigger` with mocked subprocess continue to pass
- **How:** Run the budget integration and team execution test files
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest tests/test_budget_integration.py tests/test_team_execution.py tests/test_agent_scheduler.py -v --tb=short`
- **Target:** All tests in these 3 files pass (7 in budget, plus team/scheduler tests)
- **Evidence:** RESEARCH.md identifies these as the primary integration test files for run_trigger (Pitfall 4). If prompt rendering delegation breaks, `run_trigger` behavior changes and these tests fail.
- **Correlation with full correctness:** MEDIUM — these tests mock subprocess, so they verify the path up to command construction but not actual execution; prompt content passed to subprocess is not directly asserted
- **Blind spots:** Mocked subprocess means placeholder substitution bugs in PromptRenderer.render() may not surface unless the test asserts on the exact prompt string passed
- **Validated:** No — awaiting deferred validation DEFER-06-02

### P4: No test file modifications (QUAL-03)
- **What:** Zero test files were changed during Plan 06-03 execution, confirming the facade preserved all call sites
- **How:** Check git diff for changes to the tests directory after phase execution
- **Command:** `git diff --name-only HEAD -- /Users/edward.seo/dev/private/project/harness/Agented/backend/tests/`
- **Target:** Empty output (no test files modified)
- **Evidence:** 06-03-PLAN.md explicitly states "No test file modifications are allowed" — this is the strictest call-site preservation guarantee
- **Correlation with full correctness:** HIGH — if test call sites are unchanged and tests pass, the public API is provably preserved
- **Blind spots:** Does not check that internal implementation quality is maintained (only that the interface is preserved)
- **Validated:** No — this metric is binary and confirmed at execution time

---

## Level 3: Deferred Validations

**Purpose:** Full validation that requires runtime conditions not available during automated testing.

### D1: End-to-end seed path validation — DEFER-06-01
- **What:** Verify that `seed_predefined_triggers()` and `seed_preset_mcp_servers()` function correctly when called at real app startup, writing actual rows to a real SQLite database and being readable via the API
- **How:** Start the backend server with a fresh database (`just deploy` with a clean `agented.db`), make GET requests to `/admin/triggers` and `/api/mcp-servers` and confirm predefined entries are present
- **Why deferred:** The test suite uses an `isolated_db` fixture with a temp file. Seed functions are not called in this path — they are called only in production app startup (`create_app()`). No existing test covers the real startup seed sequence.
- **Validates at:** manual-integration-test (run before v0.1.0 release or when Phase 6 is marked complete)
- **Depends on:** Working backend server (Phase 2 complete — already done), clean database available
- **Target:** GET `/admin/triggers` returns at least 2 predefined triggers (bot-security, bot-pr-review); GET `/api/mcp-servers` returns preset MCP entries
- **Risk if unmet:** Startup seeding silently fails after the seeds.py extraction, leaving the application in an unseeded state on fresh installs. Risk is LOW given that the functions are moved verbatim, but the import chain has more steps than before.
- **Fallback:** Revert `__init__.py` re-export change and call seed functions directly from `.migrations` temporarily; then investigate the broken import chain.

### D2: End-to-end prompt rendering validation — DEFER-06-02
- **What:** Verify that `PromptRenderer.render()` produces identical prompt strings to the original inline code in `run_trigger()`, specifically for GitHub PR events and webhook events with all placeholders populated
- **How:** Manually trigger a test webhook with a GitHub PR payload containing `pr_url`, `pr_number`, `pr_title`, `pr_author`, `repo_url`, `repo_full_name` fields; inspect the execution log to confirm the rendered prompt matches expectations
- **Why deferred:** RESEARCH.md open question 3 confirms "no tests that verify prompt rendering logic end-to-end (placeholder substitution)." The current test suite mocks subprocess, so even a prompt rendering regression would not be caught unless a test asserts on the exact prompt string. Adding prompt content assertions to existing tests would require test file modifications, which is prohibited by Plan 06-03.
- **Validates at:** manual-integration-test (run before v0.1.0 release or when Phase 6 is marked complete)
- **Depends on:** Working webhook endpoint (Phase 3 auth), a test trigger configured with `{pr_url}` and `{pr_number}` placeholders in its `prompt_template`
- **Target:** Execution log shows rendered prompt with all PR placeholders substituted (no literal `{pr_url}` remaining); `warn_unresolved` log message does not appear for known placeholders
- **Risk if unmet:** Unresolved placeholders in rendered prompts would cause Claude/opencode to receive malformed instructions. Impact is HIGH but probability is LOW given verbatim code extraction.
- **Fallback:** Add targeted unit tests for `PromptRenderer.render()` with a GitHub PR event fixture; fix any discovered regressions in the helper class without touching ExecutionService.

---

## Ablation Plan

**Purpose:** Verify each requirement independently before integration.

### A1: QUAL-01 isolation
- **Condition:** Plan 06-01 merged alone (seeds.py extracted), before Plan 06-02 and 06-03 apply
- **Expected impact:** Test suite still passes at 100%; ruff errors remain at 2 (unchanged); ExecutionService unchanged
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest --tb=short -q`
- **Evidence:** Plans are designed to be independent (06-01 and 06-02 are both Wave 1 with no declared dependencies between them)

### A2: QUAL-02 isolation
- **Condition:** Plan 06-02 merged alone (Ruff replaces Black), before 06-03 applies
- **Expected impact:** `ruff check .` exits 0; `ruff format --check .` exits 0; test suite passes at 100%
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run ruff check . && uv run ruff format --check . && uv run pytest --tb=short -q`
- **Evidence:** Ruff is already installed and partially configured; the configuration change is additive

### A3: QUAL-03 isolation
- **Condition:** Plan 06-03 merged alone (ExecutionService split), building on top of 06-02 (declared dependency)
- **Expected impact:** test_backend_detection.py::TestBuildCommand all 7 pass; test_budget_integration.py all 7 pass; no test files modified
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest tests/test_backend_detection.py::TestBuildCommand tests/test_budget_integration.py tests/test_team_execution.py tests/test_agent_scheduler.py -v --tb=short`
- **Evidence:** 06-03-PLAN.md explicitly lists these test files as the acceptance gate

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views. All changes are confined to `backend/app/db/` and `backend/app/services/` Python files.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| pytest | Full backend test suite | 911 passed, 0 failed | Measured 2026-02-28 |
| ruff check errors | Lint violations before Phase 6 | 2 errors (I001 in app/db/__init__.py) | Measured 2026-02-28 |
| ruff format files | Files needing reformatting | 29 files | Measured 2026-02-28 |
| execution_service.py lines | Coordinator file size before split | 1,387 lines | Measured 2026-02-28 |
| migrations.py lines | Migration file size before seed extraction | 3,220 lines | Measured 2026-02-28 |
| seeds.py | New module | Does not exist | Measured 2026-02-28 |
| prompt_renderer.py | New module | Does not exist | Measured 2026-02-28 |
| command_builder.py | New module | Does not exist | Measured 2026-02-28 |

---

## Evaluation Scripts

**Location of evaluation code:** No separate evaluation scripts — all checks use standard CLI tools available in the dev environment.

**How to run full evaluation:**
```bash
cd /Users/edward.seo/dev/private/project/harness/Agented/backend

# Level 1: Sanity (run all in sequence; any failure is a hard blocker)
uv run python -c "from app.db.seeds import seed_predefined_triggers, seed_preset_mcp_servers, migrate_existing_paths, auto_register_project_root, PRESET_MCP_SERVERS; print('S1 OK')"
uv run python -c "from app.db.seeds import PRESET_MCP_SERVERS; assert len(PRESET_MCP_SERVERS) > 0; print('S2 OK')"
grep -c "^def seed_\|^def migrate_existing_paths\|^def auto_register_project_root" app/db/migrations.py | grep -q "^0$" && echo "S3 OK" || echo "S3 FAIL"
grep -c "^PRESET_MCP_SERVERS" app/db/migrations.py | grep -q "^0$" && echo "S4 OK" || echo "S4 FAIL"
uv run python -c "from app.db import seed_predefined_triggers, init_db; print('S5 OK')"
uv run python -c "from app.database import seed_predefined_triggers; print('S6 OK')"
uv run ruff check . && echo "S7 OK" || echo "S7 FAIL"
uv run ruff format --check . && echo "S8 OK" || echo "S8 FAIL"
grep -q "\[tool\.black\]" pyproject.toml && echo "S9 FAIL" || echo "S9 OK"
grep -q "black" pyproject.toml && echo "S10 FAIL" || echo "S10 OK"
uv run python -c "from app.services.prompt_renderer import PromptRenderer; assert hasattr(PromptRenderer, 'render'); assert hasattr(PromptRenderer, 'warn_unresolved'); print('S11 OK')"
uv run python -c "from app.services.command_builder import CommandBuilder; assert hasattr(CommandBuilder, 'build'); print('S12 OK')"
grep -c "CommandBuilder.build\|PromptRenderer.render" app/services/execution_service.py | grep -q "^2$" && echo "S13 OK" || echo "S13 FAIL"

# Level 2: Proxy
uv run pytest --tb=short -q
uv run pytest tests/test_backend_detection.py::TestBuildCommand -v
uv run pytest tests/test_budget_integration.py tests/test_team_execution.py tests/test_agent_scheduler.py -v --tb=short
git diff --name-only HEAD -- tests/
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: seeds.py import | [PASS/FAIL] | | |
| S2: PRESET_MCP_SERVERS length | [PASS/FAIL] | | |
| S3: No seed defs in migrations.py | [PASS/FAIL] | | |
| S4: No PRESET_MCP_SERVERS in migrations.py | [PASS/FAIL] | | |
| S5: db __init__ re-export | [PASS/FAIL] | | |
| S6: database.py shim | [PASS/FAIL] | | |
| S7: ruff check exits 0 | [PASS/FAIL] | | |
| S8: ruff format --check exits 0 | [PASS/FAIL] | | |
| S9: No [tool.black] in pyproject.toml | [PASS/FAIL] | | |
| S10: No black dependency in pyproject.toml | [PASS/FAIL] | | |
| S11: PromptRenderer import | [PASS/FAIL] | | |
| S12: CommandBuilder import | [PASS/FAIL] | | |
| S13: ExecutionService delegation wired | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Full pytest | 911 passed, 0 failed | | [MET/MISSED] | |
| P2: TestBuildCommand | 7/7 pass | | [MET/MISSED] | |
| P3: run_trigger integration | All pass | | [MET/MISSED] | |
| P4: No test file modifications | 0 test files changed | | [MET/MISSED] | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: QUAL-01 alone | 911 pass, ruff unchanged | | |
| A2: QUAL-02 alone | ruff 0 errors, 0 reformat | | |
| A3: QUAL-03 alone | 7+7+N pass, 0 test modifications | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-06-01 | Seed path end-to-end (real DB startup) | PENDING | manual-integration-test |
| DEFER-06-02 | PromptRenderer placeholder substitution (real webhook) | PENDING | manual-integration-test |

### Post-Refactoring Measurements

*To confirm structural goals were met (not just correctness):*

| File | Baseline | After | Delta |
|------|----------|-------|-------|
| `execution_service.py` | 1,387 lines | | |
| `migrations.py` | 3,220 lines | | |
| `seeds.py` | 0 lines (new) | | |
| `prompt_renderer.py` | 0 lines (new) | | |
| `command_builder.py` | 0 lines (new) | | |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 13 checks cover every structural constraint defined in the three plans' success criteria and must-have truths. Each check is deterministic and runs in under 1 second.
- Proxy metrics: Well-evidenced — the 911-test suite covers import chains (failures surface immediately as ImportError), command building logic (7 targeted TestBuildCommand tests), and run_trigger orchestration (7 budget integration tests + team/scheduler tests). The proxy correlation is HIGH for import correctness and MEDIUM for prompt rendering correctness (acknowledged gap).
- Deferred coverage: Appropriate — the two deferred items cover the genuinely untestable paths (real app startup seed call, real webhook prompt rendering) without inventing false confidence.

**What this evaluation CAN tell us:**
- Whether the import chains are correct after all three refactorings (S1-S6, S11-S12, P1)
- Whether `ruff check` and `ruff format` are satisfied (S7, S8) and whether Black was fully removed (S9, S10)
- Whether `ExecutionService.build_command()` continues to produce identical output for the 7 tested input cases (P2)
- Whether no test call sites were modified during Plan 06-03 (P4)
- Whether the full 911-test regression baseline is preserved (P1)

**What this evaluation CANNOT tell us:**
- Whether `seed_predefined_triggers()` correctly writes rows to SQLite and whether the app actually calls it at startup through the new import chain — addressed by DEFER-06-01 at manual integration test time
- Whether `PromptRenderer.render()` correctly handles all placeholder combinations for real webhook payloads (especially multi-field GitHub PR events) — addressed by DEFER-06-02 at manual integration test time
- Whether any Ruff formatting change introduced semantic differences invisible to AST-equivalent reformatting (extremely unlikely; Ruff's formatter is designed to be AST-preserving)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-02-28*
