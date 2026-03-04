# Evaluation Plan: Phase 14 — API Hardening & Developer Experience

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Unified error response (API-02), rate limit 429 (API-06), request ID propagation (API-07), universal pagination (API-03), execution filtering (API-04), dry-run dispatch (API-01), cost estimation (API-08), cron expression support (API-10), bulk operations (API-05), enhanced DAG validation (API-09)
**Reference papers:** RFC 9457 (Problem Details for HTTP APIs, 2023), Flask-Limiter v4.1.1 docs, APScheduler 3.x CronTrigger docs

## Evaluation Overview

Phase 14 is API infrastructure work — not a stochastic or ML problem. Every requirement has a deterministic, pass/fail acceptance condition. There are no benchmark datasets, no approximate metrics, and no external comparisons to make. The evaluation approach is therefore integration-test-centric: design concrete test scenarios for each of the 10 API requirements, run them against the Flask test client, and gate progression on zero regression across the existing 940-test suite.

Six of the ten requirements (API-01, API-03, API-06, API-07, API-08, API-09) are partially implemented in the codebase already — the phase extends and unifies these existing patterns. This means proxy metrics are well-evidenced: they measure the same behavior that the requirements specify, not a correlated proxy. The evaluation plan therefore maps each requirement directly to one or more integration tests, with sanity checks for import/model health and deferred coverage only for the cost estimation accuracy threshold.

The one genuinely uncertain outcome is API-08 (cost estimation within 30% of actual). The existing `BudgetService.estimate_cost()` uses a `len(prompt) // 4` heuristic for input tokens and historical averages for output tokens. Whether this heuristic achieves the 30% accuracy target cannot be determined without live execution data. This is the only Level 3 deferred item.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| ErrorResponse shape conformance | API-02 requirement + RFC 9457 | Machine-readable `code`/`message`/`details` is industry standard for structured HTTP errors |
| 429 + Retry-After on rate limit | API-06 requirement + Flask-Limiter docs | Flask-Limiter adds Retry-After by default; test verifies the header is present and the body uses ErrorResponse |
| X-Request-ID on every response | API-07 requirement | Request ID propagation enables end-to-end tracing; presence is a binary check |
| Pagination correctness: page 2 of 25 returns items 11-20 | API-03 requirement (success criterion 3) | Exact item range is the unambiguous acceptance test from the roadmap |
| SQL-level pagination (LIMIT/OFFSET, not list slicing) | API-03 research recommendation | Python list slicing causes full-table reads; SQL pushdown prevents unbounded memory usage |
| Execution filter composition (AND logic) | API-04 requirement (success criterion 4) | Composed filters must narrow the result set, not union it |
| Dry-run: no subprocess spawned | API-01 requirement | Core safety property — dry-run must never execute a subprocess |
| Dry-run response fields | API-01 requirement (success criterion 1) | rendered_prompt, cli_command, and estimated_tokens are the three mandatory fields |
| Cron expression "*/15 9-17 * * 1-5" parses correctly | API-10 requirement (success criterion 10) | The exact expression from the roadmap is the canonical test case |
| Bulk: 10 items, per-item status | API-05 requirement (success criterion 5) | 10-item minimum and per-item results are the exact acceptance criteria |
| DAG cycle detection with descriptive error | API-09 requirement (success criterion 9) | Descriptive error (listing cycle nodes) distinguishes enhanced validation from the existing basic check |
| Cost estimation accuracy within 30% | API-08 requirement (success criterion 8) | Heuristic accuracy requires live execution data to validate |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 9 | Import health, model instantiation, CLI/type builds, no-crash smoke tests |
| Proxy (L2) | 14 | Integration tests covering all 10 requirements against Flask test client |
| Deferred (L3) | 1 | Cost estimation accuracy vs. actual (requires live execution data) |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: ErrorResponse Model Import and Instantiation
- **What:** The extended `ErrorResponse` Pydantic model (with `code`, `message`, `details`, `request_id` fields) imports and validates without error
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.models.common import ErrorResponse, error_response; r = ErrorResponse(code='NOT_FOUND', message='test'); print(r.model_dump())"`
- **Expected:** Prints a dict with `code`, `message`, `details=None`, `request_id=None` keys; no import errors or validation errors
- **Failure means:** The model extension broke Pydantic validation or introduced a circular import

### S2: error_response() Helper Returns Correct Tuple Type
- **What:** `error_response()` helper returns a `(dict, HTTPStatus)` tuple with both `message` and `error` fields (backward compat)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.models.common import error_response; from http import HTTPStatus; r, s = error_response('NOT_FOUND', 'Not found', HTTPStatus.NOT_FOUND); print(r); print(s)"`
- **Expected:** Dict contains `code`, `message`, `error`, `details`, `request_id` keys; status is `HTTPStatus.NOT_FOUND` (404)
- **Failure means:** Helper signature or return type is wrong; backward-compat `error` field is missing

### S3: CronTrigger.from_crontab() Available and Parses Reference Expression
- **What:** APScheduler's `CronTrigger.from_crontab()` is importable and parses the canonical test expression without raising
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from apscheduler.triggers.cron import CronTrigger; t = CronTrigger.from_crontab('*/15 9-17 * * 1-5'); print('OK:', t)"`
- **Expected:** Prints `OK:` followed by a CronTrigger representation; no ValueError or ImportError
- **Failure means:** APScheduler version does not support `from_crontab()`, or expression syntax is incompatible

### S4: BudgetService.estimate_cost() Returns Expected Keys
- **What:** `BudgetService.estimate_cost()` returns a dict containing at least `estimated_input_tokens` (or equivalent) and `estimated_cost` keys
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.budget_service import BudgetService; r = BudgetService.estimate_cost('hello world ' * 100, 'claude-sonnet-4'); print(r)"`
- **Expected:** A dict with token count and cost fields; no exception raised
- **Failure means:** BudgetService API changed or the method signature is incompatible with dry-run usage

### S5: Full Backend Test Suite Passes (No Regression)
- **What:** All 940+ existing tests continue to pass after phase changes
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest -q --tb=no 2>&1 | tail -5`
- **Expected:** `X passed, 0 failed` (X >= 940); any failure count > 0 is a regression
- **Failure means:** Phase changes broke existing functionality — must diagnose before proceeding

### S6: Frontend Builds Without Type Errors
- **What:** `vue-tsc` type checking and Vite build succeed — covers the `client.ts` ApiError extraction change
- **Command:** `cd /Users/neo/Developer/Projects/Agented && just build 2>&1 | tail -10`
- **Expected:** Build completes with no errors; `dist/` directory is produced
- **Failure means:** The frontend `data.message || data.error` change introduced a TypeScript type error

### S7: New Test Files Collect Without Import Error
- **What:** The six new test files (test_error_response.py, test_request_id.py, test_pagination.py, test_execution_filter.py, test_dry_run.py, test_cron_support.py, test_bulk_operations.py, test_dag_validation.py) are collected by pytest without import errors
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_error_response.py tests/test_request_id.py tests/test_pagination.py tests/test_execution_filter.py tests/test_dry_run.py tests/test_cron_support.py tests/test_bulk_operations.py tests/test_dag_validation.py --collect-only -q 2>&1 | tail -5`
- **Expected:** All test files collected; `N tests collected` (N > 0 for each file); no `ERROR collecting` lines
- **Failure means:** Missing import, broken fixture, or missing test function — find the specific file and fix imports

### S8: BulkService Imports and MAX_ITEMS Constant Present
- **What:** `BulkService` class is importable; `MAX_ITEMS = 100` is set; `process()` method exists
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.bulk_service import BulkService; print('MAX_ITEMS:', BulkService.MAX_ITEMS); print('process:', BulkService.process)"`
- **Expected:** Prints `MAX_ITEMS: 100` and the method reference; no ImportError
- **Failure means:** `bulk_service.py` was not created or has a syntax error

### S9: ExecutionFilterQuery Model Has All Required Filter Fields
- **What:** `ExecutionFilterQuery` extends `PaginationQuery` and exposes `status`, `trigger_id`, `date_from`, `date_to`, and `q` fields
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.models.common import ExecutionFilterQuery; q = ExecutionFilterQuery(status='completed', trigger_id='trig-abc', q='test'); print(q.model_fields.keys())"`
- **Expected:** Output includes `status`, `trigger_id`, `date_from`, `date_to`, `q`, `limit`, `offset`; no ValidationError
- **Failure means:** `ExecutionFilterQuery` was not added to `common.py` or is missing fields

**Sanity gate:** ALL 9 sanity checks must pass. Any failure blocks progression to proxy metrics.

---

## Level 2: Proxy Metrics

**Purpose:** Integration tests against the Flask test client that directly verify each API requirement's acceptance condition.
**IMPORTANT:** These tests use the `isolated_db` fixture (auto-patches `DB_PATH` to a temp file). Results are deterministic — pass/fail, not approximate.

### P1: Flask Error Handlers Return Unified ErrorResponse Shape
- **What:** The 5 Flask-level error handlers (404, 405, 413, 500, sqlite3.OperationalError) all return JSON with `code`, `message`, and `details` fields
- **How:** pytest integration test — hit non-existent route, wrong-method route; assert response JSON structure
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_error_response.py -v`
- **Target:** All 5 error handler tests pass; zero endpoints return bare `{"error": "..."}` shape at Flask level
- **Evidence:** API-02 requirement; RFC 9457 error shape; `14-RESEARCH.md` Pattern 1
- **Correlation with full metric:** HIGH — the test directly exercises the exact error handlers being changed
- **Blind spots:** Individual route handlers (not Flask-level handlers) are not updated in this phase; they still return bare `{"error": "..."}` dicts. Phase 15 (CON-02) addresses route-level error consistency.
- **Validated:** No — deferred to Phase 15 for full route-level coverage

### P2: Rate Limiting Returns 429 with Retry-After Header
- **What:** Sending requests above the 120/minute admin rate limit threshold produces a 429 response with `Retry-After` header and structured error body
- **How:** pytest integration test — send N+1 requests to an admin endpoint; inspect response code and headers
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_request_id.py -v -k "rate_limit"`
- **Target:** Response status 429; `Retry-After` header present; response body has `code`, `message` fields (not bare string)
- **Evidence:** API-06 requirement; Flask-Limiter v4.1.1 adds Retry-After by default per its docs; `14-RESEARCH.md` Recommendation 2
- **Correlation with full metric:** HIGH — Flask-Limiter behavior is deterministic at the tested threshold
- **Blind spots:** In-memory rate limit storage is lost on server restart. Real-world sustained load testing (concurrent clients) is not simulated here.
- **Validated:** No — production load behavior deferred to operational monitoring

### P3: X-Request-ID Header on Every Response
- **What:** Every HTTP response includes an `X-Request-ID` header with a UUID-format value; the same ID is accessible via `flask.g.request_id` for `error_response()` to include in error bodies
- **How:** pytest integration test — make several requests to different endpoints; assert header presence and UUID format
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_request_id.py -v -k "request_id"`
- **Target:** 100% of tested responses include `X-Request-ID`; value matches UUID regex `[0-9a-f-]{36}`
- **Evidence:** API-07 requirement; existing `middleware.py` already uses `contextvars` — test verifies the g.request_id bridge is complete
- **Correlation with full metric:** HIGH — header presence is binary and directly testable
- **Blind spots:** Request ID propagation into subprocess CLI output (bot execution logs) is a known gap per `14-RESEARCH.md` Production Considerations. This requires passing the ID as an env var to the subprocess — not in scope for this phase.
- **Validated:** No — subprocess log propagation deferred to Phase 13 integration

### P4: Pagination Returns Correct Item Range for Page 2 of 25-Item Collection
- **What:** A list endpoint seeded with 25 items, queried with `limit=10&offset=10`, returns exactly 10 items and `total_count=25`
- **How:** pytest integration test — seed 25 agents; GET with pagination params; assert item range (items 11-20) and total_count
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_pagination.py -v`
- **Target:** Items 11-20 (by insertion order) returned; `total_count=25`; `limit=10&offset=20` returns 5 items; `limit=10&offset=30` returns 0 items
- **Evidence:** API-03 requirement success criterion 3 (exact item range specification from roadmap); `14-RESEARCH.md` Recommendation 1 on offset pagination for SQLite scale
- **Correlation with full metric:** HIGH — the test reproduces the exact acceptance scenario from the roadmap
- **Blind spots:** Test uses agents endpoint; other newly paginated endpoints (workflows, backends, audit, sketches, etc.) are not individually exercised — at least 3 are tested per plan requirement
- **Validated:** No

### P5: Pagination Is Implemented at SQL Level (Not Python Slicing)
- **What:** SQL queries for list endpoints use `LIMIT ? OFFSET ?` clauses rather than Python list slicing
- **How:** grep for anti-pattern + code review of DB layer functions changed in plan 14-02
- **Command:** `cd /Users/neo/Developer/Projects/Agented && grep -rn "fetchall()\[" backend/app/db/ 2>/dev/null | grep -v __pycache__ | wc -l`
- **Target:** 0 occurrences of Python list slicing `fetchall()[offset:offset+limit]` in any DB function touched by phase 14
- **Evidence:** `14-RESEARCH.md` anti-pattern section: "Pagination in service layer only" is explicitly called out; SQL pushdown is the required pattern
- **Correlation with full metric:** HIGH — this is a structural correctness check, not an approximation
- **Blind spots:** Only checks the files changed in this phase; pre-existing list slicing in untouched files is out of scope
- **Validated:** No

### P6: Execution Filtering Composes with AND Logic
- **What:** Combining `status=completed` and `trigger_id=trig-xxx` filters returns only the intersection — not the union
- **How:** pytest integration test — seed 20 executions with mixed statuses and trigger IDs; query with composed filters; assert result count matches expected intersection
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_execution_filter.py -v`
- **Target:** All 6 filter dimensions (status, trigger_id, date_from, date_to, q, and composed) return correct results; composed filters narrow to AND intersection
- **Evidence:** API-04 requirement success criterion 4; `14-RESEARCH.md` Pattern 5 on execution filtering; parameterized SQL WHERE clause composition
- **Correlation with full metric:** HIGH — deterministic with seeded test data
- **Blind spots:** Text search (`q` parameter) uses `LIKE '%q%'` which scans all rows — performance at high row counts not tested here
- **Validated:** No

### P7: Dry-Run Returns Correct Response Without Spawning Subprocess
- **What:** `POST /admin/triggers/<id>/dry-run` returns `rendered_prompt`, `cli_command`, `backend_type`, `model`, and `estimated_tokens` — and does NOT call `subprocess.Popen`
- **How:** pytest integration test — seed a trigger with `{message}` placeholder; POST dry-run with sample data; mock `subprocess.Popen`; assert response fields and assert mock not called
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_dry_run.py -v`
- **Target:** Response contains all 5 required fields; `subprocess.Popen` mock asserts `not called`; 404 on non-existent trigger
- **Evidence:** API-01 requirement success criterion 1; `14-RESEARCH.md` Pattern 4; existing `preview_prompt` service as the reuse point
- **Correlation with full metric:** HIGH — subprocess mock is a definitive non-execution check
- **Blind spots:** Does not validate that the CLI command string is syntactically correct for the target CLI (claude, opencode, etc.) — only that it is present and non-empty
- **Validated:** No

### P8: Cost Estimation Endpoint Returns Token and Cost Fields
- **What:** `POST /admin/triggers/<id>/estimate-cost` (or equivalent) returns `trigger_id`, `model`, and nested estimate fields (input tokens, output tokens, cost)
- **How:** pytest integration test — seed a trigger; POST to estimate endpoint; assert response shape
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_dry_run.py -v -k "estimate"`
- **Target:** Response contains `trigger_id`, `model`, and `estimate` object with token fields; HTTP 200
- **Evidence:** API-08 requirement; `BudgetService.estimate_cost()` already exists and is used in dry-run
- **Correlation with full metric:** MEDIUM — verifies the endpoint shape and that the heuristic runs without error, but NOT whether the 30% accuracy target is met (see DEFER-14-01)
- **Blind spots:** The heuristic (`len(prompt) // 4`) may be systematically off for certain model/prompt combinations. Actual accuracy requires live execution data.
- **Validated:** No — accuracy deferred to DEFER-14-01

### P9: Standard Cron Expression Parses and Produces Correct Next Fire Times
- **What:** The validate-cron endpoint returns `valid=true` and non-empty `next_fires` for valid expressions; returns `valid=false` with descriptive error for invalid ones; `*/15 9-17 * * 1-5` fires during weekday business hours only
- **How:** pytest integration test — call validate-cron with several valid and invalid expressions; check next_fires for the canonical expression fall within 09:00-17:00 Mon-Fri
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_cron_support.py -v`
- **Target:** Valid expressions return `valid=true` with 5 next fire times; invalid expressions return 400 with error describing which field is invalid; `*/15 9-17 * * 1-5` next fires are all within 09:00-17:00 Mon-Fri window
- **Evidence:** API-10 requirement success criterion 10; APScheduler 3.x `CronTrigger.from_crontab()` documentation; `14-RESEARCH.md` Recommendation 4
- **Correlation with full metric:** HIGH — APScheduler's fire time calculation is deterministic
- **Blind spots:** Timezone behavior is tested with the local system timezone. A user in a non-UTC timezone might see different results if `schedule_timezone` is not propagated correctly. Test should explicitly pass a fixed timezone.
- **Validated:** No

### P10: Bulk Create of 10 Entities Returns 10 Per-Item Results
- **What:** `POST /admin/bulk/agents` with `{"action": "create", "items": [...10 agents...]}` returns a response with 10 per-item result objects, each with `success`, `index`, and `id` fields
- **How:** pytest integration test — POST 10 agent definitions; assert 10 results; assert each has `success=true` and a valid `agent-*` ID
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_bulk_operations.py -v`
- **Target:** 10 results returned; each `success=true`; agents exist in DB afterward; 101-item request returns 400 with max-items error; mixed valid/invalid items produce per-item pass/fail (no full-batch rollback)
- **Evidence:** API-05 requirement success criterion 5; `14-RESEARCH.md` Pattern 3; OneUptime bulk endpoint design reference
- **Correlation with full metric:** HIGH — deterministic with test client and isolated_db fixture
- **Blind spots:** Bulk operations are tested against agents and at least one other entity type. The other three (triggers, plugins, hooks) receive lighter coverage. SQLite write contention under concurrent bulk requests is not simulated.
- **Validated:** No

### P11: DAG Validation Rejects Cycle with Descriptive Error
- **What:** Submitting a workflow DAG with cycle A->B->C->A returns 400 with an error message that names the cycle nodes; missing node reference returns 400 naming the missing node; invalid condition expression returns 400 with syntax error detail
- **How:** pytest integration test — POST crafted invalid DAG JSON to workflow creation endpoint and to standalone `/admin/workflows/validate` endpoint
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_dag_validation.py -v`
- **Target:** Cycle DAG: 400 + error contains cycle node IDs; missing ref: 400 + error names the missing node ID; invalid condition: 400 + error quotes the SyntaxError; dangerous expression (`__import__`): 400
- **Evidence:** API-09 requirement success criterion 9; `14-RESEARCH.md` architecture note on existing `graphlib.TopologicalSorter` usage; `14-04-PLAN.md` Task 2 specification
- **Correlation with full metric:** HIGH — the test input/expected output is exactly specified in the plan
- **Blind spots:** The existing `test_workflows.py` already has 8 DAG validation tests (TestDAGValidation class). This new test file extends coverage for the descriptive error messages and condition expression validation specifically.
- **Validated:** No

### P12: Frontend Test Suite Passes After client.ts Change
- **What:** Updating `ApiError` extraction from `data.error` to `data.message || data.error` does not break any frontend test
- **How:** Full frontend test suite run
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run 2>&1 | tail -5`
- **Target:** All tests pass; 0 failures; no TypeScript errors in test output
- **Evidence:** `14-01-PLAN.md` Task 1 step 3; `14-RESEARCH.md` Pitfall 1 on frontend backward compat
- **Correlation with full metric:** HIGH — frontend tests are deterministic unit tests
- **Blind spots:** Frontend tests use happy-dom, not a real browser. Manual verification that error messages display correctly in the UI remains a deferred concern.
- **Validated:** No

### P13: All List Endpoints Accept Pagination Params Without Crash
- **What:** Every list endpoint that was updated in plan 14-02 accepts `limit` and `offset` query parameters and returns `total_count` alongside the items array — no endpoint returns 400 or 500 for valid pagination params
- **How:** Smoke test — iterate over a defined list of known endpoints and GET each with `?limit=5&offset=0`
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_pagination.py -v -k "smoke"`
- **Target:** All updated endpoints return 200 with `total_count` field present in the response; no 500 errors
- **Evidence:** API-03 requirement; `14-02-PLAN.md` Task 1 lists 13 route files updated
- **Correlation with full metric:** HIGH — endpoint availability is a binary check
- **Blind spots:** Verifies smoke-level correctness across endpoints; does not verify item ordering or deep offset correctness for every endpoint. The page-2-of-25 test (P4) covers that for the agents/triggers endpoints specifically.
- **Validated:** No

### P14: New Tests Added (Phase Coverage Count)
- **What:** The phase adds at least 6 new test files with meaningful coverage — total test count increases by at least 40 tests
- **How:** Count tests before and after
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest --collect-only -q 2>&1 | tail -3`
- **Target:** Total collected tests >= 980 (baseline: 940 + ~40 new tests across 8 new files)
- **Evidence:** Each plan specifies exactly one test file; each test file has 6-10 test cases per the plans
- **Correlation with full metric:** MEDIUM — raw test count does not guarantee quality; meaningful only if the tests cover the specified scenarios
- **Blind spots:** Test count is a weak proxy for coverage. The qualitative check (does each test verify the acceptance condition?) is implicit in the other proxy metrics above.
- **Validated:** No

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring live execution data or production observability not available at test-suite time.

### D1: Cost Estimation Accuracy Within 30% of Actual — DEFER-14-01
- **What:** The pre-flight cost estimate from `BudgetService.estimate_cost()` is within 30% of the actual token count recorded after a real execution completes
- **How:** Collect actual token usage from 20+ real executions (via the `budget_entries` table or Claude API usage headers); compare to the pre-execution estimate for the same prompt; compute mean absolute percentage error (MAPE)
- **Why deferred:** The heuristic (`len(prompt) // 4` for input tokens, historical averages for output tokens) cannot be validated against reality without running real Claude/OpenCode executions and capturing their actual token responses. The test suite uses mocks — no real subprocess output is available.
- **Validates at:** phase-16-production-eval (after v0.2.0 ships to a live environment) or whenever 20+ real executions have been recorded in the budget_entries table
- **Depends on:** Live execution data with token counts stored per-execution; budget_entries table populated with real usage
- **Target:** Mean absolute percentage error (MAPE) <= 30% across the validation set of 20+ executions
- **Risk if unmet:** The cost estimate displayed to users is systematically misleading. Mitigation: add a "estimate accuracy: low" disclaimer to the UI, increase the heuristic's output token multiplier, or integrate the Claude API's usage response to calibrate the estimate post-run.
- **Fallback:** If MAPE > 30%, log actual vs. estimated for 20+ executions, identify the dominant error source (input vs. output token mismatch), and adjust `BudgetService.estimate_cost()` heuristic coefficients accordingly. A revised heuristic can be validated in a follow-up sprint.

---

## Ablation Plan

**No ablation plan** — This phase implements 10 distinct cross-cutting API requirements, each with a single well-defined implementation pattern. There are no sub-components to isolate or A/B compare. The research established the implementation approach (offset pagination, Flask-Limiter, APScheduler CronTrigger, graphlib) with HIGH confidence and no viable alternatives to compare against.

One structural decision worth noting: the codebase already has partial implementations for 6 of 10 requirements. The "ablation" question — "does the complete implementation perform better than the partial one?" — is answered by the proxy metrics (P1-P13) which verify the completion and unification of those partial implementations.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views in a user-visible way. The only frontend change is updating the `ApiError` extraction in `client.ts`, which is covered by the frontend test suite (P12) and does not produce a page-specific layout or UI component requiring browser validation.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Backend test suite | Existing 940 tests collected and passing | 940 passed, 0 failed | `cd backend && uv run pytest --collect-only -q` at phase start |
| Paginated endpoints | ~10 of ~29 list endpoints have PaginationQuery | 10/29 paginated | `14-RESEARCH.md` summary |
| Error response shape | Inconsistent — mix of `{"error": "..."}` and structured shapes | ~0% conformance at Flask error handler level | `14-01-PLAN.md` task 1 context |
| Rate limiting | Flask-Limiter configured; 429 response shape unverified | Partial (limits configured, Retry-After not verified) | `14-RESEARCH.md` current state |
| Request ID | Middleware sets ContextVar; `g.request_id` bridge incomplete | Partial (header set, not in `flask.g`) | `14-01-PLAN.md` task 2 context |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_error_response.py     (plan 14-01, task 1)
backend/tests/test_request_id.py         (plan 14-01, task 2)
backend/tests/test_pagination.py         (plan 14-02, task 1)
backend/tests/test_execution_filter.py   (plan 14-02, task 2)
backend/tests/test_dry_run.py            (plan 14-03, task 1)
backend/tests/test_cron_support.py       (plan 14-03, task 2)
backend/tests/test_bulk_operations.py    (plan 14-04, task 1)
backend/tests/test_dag_validation.py     (plan 14-04, task 2)
```

**How to run full evaluation:**
```bash
# Sanity checks (run first, fast)
cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.models.common import ErrorResponse, error_response, ExecutionFilterQuery; from app.services.bulk_service import BulkService; from apscheduler.triggers.cron import CronTrigger; CronTrigger.from_crontab('*/15 9-17 * * 1-5'); print('All sanity imports OK')"

# Full backend test suite (regression gate)
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest -q --tb=short

# New phase-specific tests only (for focused evaluation)
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_error_response.py tests/test_request_id.py tests/test_pagination.py tests/test_execution_filter.py tests/test_dry_run.py tests/test_cron_support.py tests/test_bulk_operations.py tests/test_dag_validation.py -v

# Frontend build and tests
cd /Users/neo/Developer/Projects/Agented && just build && cd frontend && npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: ErrorResponse import | [PASS/FAIL] | | |
| S2: error_response() tuple | [PASS/FAIL] | | |
| S3: CronTrigger.from_crontab() | [PASS/FAIL] | | |
| S4: BudgetService.estimate_cost() keys | [PASS/FAIL] | | |
| S5: Full backend test suite | [PASS/FAIL] | X passed, Y failed | |
| S6: Frontend build | [PASS/FAIL] | | |
| S7: New test files collect | [PASS/FAIL] | N tests collected | |
| S8: BulkService import + MAX_ITEMS | [PASS/FAIL] | | |
| S9: ExecutionFilterQuery fields | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Flask error handlers (ErrorResponse shape) | All 5 pass | | [MET/MISSED] | |
| P2: Rate limit 429 + Retry-After | 429 with header | | [MET/MISSED] | |
| P3: X-Request-ID on every response | 100% presence | | [MET/MISSED] | |
| P4: Pagination page 2 of 25 | Items 11-20, total_count=25 | | [MET/MISSED] | |
| P5: SQL-level pagination (no slicing) | 0 slicing occurrences | | [MET/MISSED] | |
| P6: Execution filter AND composition | Intersection, not union | | [MET/MISSED] | |
| P7: Dry-run no subprocess + fields | 5 fields, mock not called | | [MET/MISSED] | |
| P8: Cost estimation endpoint shape | trigger_id + model + estimate | | [MET/MISSED] | |
| P9: Cron parse + next fires in window | valid=true, 5 next fires | | [MET/MISSED] | |
| P10: Bulk create 10 items per-item | 10 results, all success=true | | [MET/MISSED] | |
| P11: DAG cycle rejected with node names | 400 + cycle in error message | | [MET/MISSED] | |
| P12: Frontend tests pass | 0 failures | | [MET/MISSED] | |
| P13: All list endpoints accept pagination | 200 + total_count on all | | [MET/MISSED] | |
| P14: Test count >= 980 | >= 980 collected | | [MET/MISSED] | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-14-01 | Cost estimation MAPE <= 30% | PENDING | phase-16-production-eval (20+ real executions required) |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 9 checks cover model imports, CLI commands, and no-crash validation for all new code paths
- Proxy metrics: Well-evidenced — 14 metrics, each mapping 1:1 to a roadmap success criterion; all use deterministic integration tests with seeded data; no stochastic approximations
- Deferred coverage: Minimal (1 item) and correctly scoped — the only genuinely unprovable-at-test-time property is the cost heuristic's real-world accuracy

**What this evaluation CAN tell us:**
- Whether all 10 API requirements are structurally implemented (correct endpoints exist, correct response shapes, correct behavior on known inputs)
- Whether existing functionality is preserved (940+ test regression gate)
- Whether the frontend backward-compatibility concern is addressed (P12)
- Whether the cron expression parser handles the canonical test case and a range of valid/invalid inputs

**What this evaluation CANNOT tell us:**
- Whether `BudgetService.estimate_cost()` achieves 30% accuracy against real Claude/OpenCode usage (DEFER-14-01 — requires live data)
- Whether rate limiting holds under real concurrent load from multiple clients (P2 is single-client simulation)
- Whether the UI correctly displays the new error message format (P12 tests `client.ts` logic only — browser-level error display is visual and untested)
- Whether request ID propagation reaches subprocess CLI output (documented gap in `14-RESEARCH.md` Production Considerations; not in scope for this phase)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
