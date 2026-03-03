# Evaluation Plan: Phase 7 — Workflow Automation & Pipeline Intelligence

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** DAG workflow execution engine extensions, VueFlow custom node types, threading.Event approval gates, AST-based safe expression evaluation, OrchestrationService fallback chain wiring
**Reference sources:** 07-RESEARCH.md (codebase analysis), Python graphlib stdlib, VueFlow docs, TeamExecutionService._execute_human_in_loop pattern

---

## Evaluation Overview

Phase 7 extends an already-functional 70-80% complete workflow system. The evaluation covers six requirements (WF-01 through WF-06) delivered across three plans and two waves. Because the codebase already has `WorkflowExecutionService` (DAG engine), `@vue-flow/core` canvas, `OrchestrationService` (fallback chains), and `threading.Event`-based approval patterns in `TeamExecutionService`, most work is extension rather than greenfield — making proxy-level verification through unit and integration tests achievable without needing a full production environment.

There are no external benchmark papers to reference for this phase. All metric targets derive from the ROADMAP.md success criteria and the research document's experimental design section (07-RESEARCH.md#Recommended-Metrics). The dominant risks are: (1) conditional branch routing correctness — if non-matching branches aren't skipped the DAG executes incorrect paths silently, and (2) approval gate state loss on server restart — an in-memory-only approach would leave workflows stuck in `pending_approval` permanently. Both risks are addressed by the proxy-level test suite in Plan 07-02.

No external benchmark data exists for this project (BENCHMARKS.md has not been created for v0.2.0). All targets are derived from ROADMAP.md success criteria and the research document's experimental recommendations.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Conditional expression evaluation accuracy | ROADMAP.md SC-2: "verified with at least 5 distinct condition expressions" | Directly measures WF-02 correctness |
| Branch routing correctness (true/false/skip) | ROADMAP.md SC-5: "at least 3 branching scenarios" | Directly measures WF-05 correctness |
| Approval gate pause/resume/reject behavior | ROADMAP.md SC-3: "execution resumes only after explicit approve/reject action" | Directly measures WF-03 correctness |
| Fallback chain failover time | ROADMAP.md SC-4: "next provider tried within 5 seconds" | Directly measures WF-04 availability |
| Per-node retry correctness | ROADMAP.md SC-6: "without restarting the entire DAG" | Directly measures WF-06 resilience |
| End-to-end pipeline execution | ROADMAP.md SC-1: "drag, connect, save DAG, execute end-to-end" | Directly measures WF-01 functional completeness |
| Frontend build success (zero type errors) | Plan 07-03 verification; CLAUDE.md verification protocol | Required for any frontend phase |
| Backend test suite regression | CLAUDE.md: "all three must pass with zero errors" | No regressions policy |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 12 | Basic functionality, format verification, build passes, no regressions |
| Proxy (L2) | 9 | Automated behavioral tests — expression evaluation, branching, approval gate, fallback, retry, end-to-end |
| Deferred (L3) | 5 | Full E2E in browser, real fallback timing, multi-user approval, server-restart recovery |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: WorkflowNodeType enum includes approval_gate

- **What:** The `APPROVAL_GATE` value is present in the `WorkflowNodeType` enum
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.models.workflow import WorkflowNodeType; assert 'approval_gate' in [e.value for e in WorkflowNodeType]; print('PASS')"`
- **Expected:** `PASS`
- **Failure means:** Plan 07-01 Task 1 Part D was not completed; no other code can safely register approval gate nodes

### S2: WorkflowExecutionStatus and NodeExecutionStatus include pending_approval

- **What:** Status enums contain the `pending_approval` state needed for approval gate pause signaling
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.models.workflow import WorkflowExecutionStatus, NodeExecutionStatus; assert 'pending_approval' in [e.value for e in WorkflowExecutionStatus]; assert 'pending_approval' in [e.value for e in NodeExecutionStatus]; print('PASS')"`
- **Expected:** `PASS`
- **Failure means:** SSE events and DB state for approval gates cannot be persisted correctly

### S3: NODE_DISPATCHERS contains approval_gate entry

- **What:** The execution engine's dispatch table includes the approval gate handler
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.workflow_execution_service import WorkflowExecutionService; assert 'approval_gate' in WorkflowExecutionService.NODE_DISPATCHERS; print('PASS')"`
- **Expected:** `PASS`
- **Failure means:** Approval gate nodes will raise `Unknown node type` during DAG execution

### S4: evaluate_condition function is importable and callable

- **What:** The safe expression evaluator exists and can be imported without error
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.workflow_execution_service import evaluate_condition; result = evaluate_condition('1 > 0', {}); assert result == True; print('PASS')"`
- **Expected:** `PASS`
- **Failure means:** WF-02 and WF-05 cannot function at all; conditional nodes have no expression evaluation

### S5: Agent node references OrchestrationService (not stub text)

- **What:** `_execute_agent_node` contains a real OrchestrationService call, not the stub return
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import inspect; from app.services.workflow_execution_service import WorkflowExecutionService; src = inspect.getsource(WorkflowExecutionService._execute_agent_node); assert 'OrchestrationService' in src or 'execute_with_fallback' in src, 'Still a stub'; print('PASS')"`
- **Expected:** `PASS`
- **Failure means:** WF-04 multi-model fallback is non-functional; agent nodes return mock text

### S6: WorkflowNode model has backoff_strategy field

- **What:** The `WorkflowNode` Pydantic model has the `backoff_strategy` field for WF-06
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.models.workflow import WorkflowNode; n = WorkflowNode(id='t', type='command', label='T', backoff_strategy='linear'); assert n.backoff_strategy == 'linear'; print('PASS')"`
- **Expected:** `PASS`
- **Failure means:** Named backoff strategies (fixed/linear/exponential) cannot be configured per node

### S7: Existing backend test suite passes with zero regressions

- **What:** No previously passing tests are broken by Phase 7 changes
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/ -x -q 2>&1 | tail -5`
- **Expected:** Last line shows something like `N passed` with no failures or errors
- **Failure means:** Phase 7 changes broke existing functionality; investigate before proceeding

### S8: ApprovalGateNode.vue file exists with Handle components

- **What:** The new Vue component file was created and includes VueFlow Handle elements
- **Command:** `grep -c "Handle" /Users/neo/Developer/Projects/Agented/frontend/src/components/workflow/nodes/ApprovalGateNode.vue`
- **Expected:** Count >= 1 (at least one Handle component present)
- **Failure means:** The node cannot participate in the VueFlow canvas drag-and-drop system

### S9: WorkflowCanvas.vue registers approval_gate in nodeTypes

- **What:** The canvas registers the new node type with `markRaw()` following VueFlow requirements
- **Command:** `grep "approval_gate" /Users/neo/Developer/Projects/Agented/frontend/src/components/workflow/WorkflowCanvas.vue`
- **Expected:** Line containing both `approval_gate` and `markRaw` (or `approval_gate` as a key in nodeTypes)
- **Failure means:** Approval gate nodes will not render on the canvas (VueFlow treats them as unknown types)

### S10: Frontend API client has approveNode and rejectNode methods

- **What:** The API client exposes the approve/reject methods needed by ApprovalModal
- **Command:** `grep -c "approveNode\|rejectNode" /Users/neo/Developer/Projects/Agented/frontend/src/services/api/workflows.ts`
- **Expected:** Count >= 2
- **Failure means:** ApprovalModal cannot call the backend; approve/reject UI actions will fail silently

### S11: Frontend build succeeds with zero type errors

- **What:** `vue-tsc` type check and Vite build both succeed
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run build 2>&1 | tail -5`
- **Expected:** Output ends with build size summary (no `error TS` lines, no `Build failed`)
- **Failure means:** TypeScript errors in new components; the app cannot be deployed

### S12: Existing frontend tests pass

- **What:** No previously passing frontend tests are broken
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run 2>&1 | tail -5`
- **Expected:** Last line shows test count with no failures
- **Failure means:** Shared composables or types broken by Phase 7 frontend changes

**Sanity gate:** ALL sanity checks must pass. Any failure blocks progression to proxy metric evaluation.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of behavioral correctness via automated tests.
**IMPORTANT:** These proxy metrics are NOT validated substitutes for full browser E2E testing. All proxy metrics start as unvalidated — deferred items confirm real-world behavior.

### P1: Safe Expression Evaluator — 6 Distinct PR Attribute Conditions

- **What:** The AST-based safe evaluator correctly handles all required operator categories on nested context dicts, without using `eval()`
- **How:** Run each condition expression against a known context dict and assert the expected boolean result
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.services.workflow_execution_service import evaluate_condition
  ctx = {'pr': {'lines_changed': 600, 'branch': 'feature/auth', 'draft': False, 'file_count': 12, 'labels': ['bug', 'security']}}
  assert evaluate_condition('pr.lines_changed > 500', ctx) == True
  assert evaluate_condition('pr.branch == \"feature/auth\"', ctx) == True
  assert evaluate_condition('pr.draft == True', ctx) == False
  assert evaluate_condition('pr.file_count >= 10 and pr.lines_changed < 1000', ctx) == True
  assert evaluate_condition('\"security\" in pr.labels', ctx) == True
  assert evaluate_condition('pr.lines_changed <= 100 or pr.draft == True', ctx) == False
  print('ALL 6 PASS')
  "
  ```
- **Target:** All 6 assertions pass
- **Evidence:** ROADMAP.md SC-2 requires "at least 5 distinct condition expressions"; 07-RESEARCH.md Recommendation 4 specifies exactly these operator categories. The test uses the same context format as the plan's verify block
- **Correlation with full metric:** HIGH — these expressions map 1:1 to the ROADMAP success criterion; no gap between test and requirement
- **Blind spots:** Does not test malformed expressions (see Group 1 in Plan 07-02 tests), does not verify the evaluator rejects `eval()`/`exec()` injection attempts
- **Validated:** No — awaiting deferred validation D1 for security injection testing

### P2: Edge-Aware Conditional Branching — 3 Branching Scenarios

- **What:** Non-matching branch targets are skipped; only the correct downstream path executes
- **How:** Unit tests using graph fixtures that construct minimal DAGs (trigger -> conditional -> true_branch, false_branch)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "branch" -v 2>&1 | tail -15`
- **Target:** All branch routing tests pass, covering:
  1. `test_conditional_branch_true_path` — true branch executes, false branch skipped
  2. `test_conditional_branch_false_path` — false branch executes, true branch skipped
  3. `test_conditional_branch_skip_downstream` — skip propagates recursively to downstream-of-skipped nodes
  4. `test_conditional_no_sourcehandle_passthrough` — backward compat: edges without sourceHandle execute all successors
- **Evidence:** ROADMAP.md SC-5 requires "at least 3 branching scenarios (pass/fail/skip)"; 07-RESEARCH.md Pitfall 1 specifically warns that the current engine executes ALL downstream nodes unless `skipped_nodes` is populated after conditional evaluation
- **Correlation with full metric:** HIGH — tests directly exercise `_run_workflow` DAG traversal logic, not a mock
- **Blind spots:** Tests use mocked DB calls (not real SQLite); does not test branching under concurrent execution or with deeply nested DAGs (10+ nodes)
- **Validated:** No — awaiting deferred validation D2 for full E2E canvas-to-execution flow

### P3: Approval Gate Pause, Resume, and Reject

- **What:** The approval gate node pauses execution via `threading.Event.wait()`, resumes on `approve_node()`, and aborts downstream on `reject_node()`
- **How:** Unit tests that start a workflow in a background thread and call approve/reject from the test thread after a short delay
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "approval_gate" -v 2>&1 | tail -15`
- **Target:** All approval gate tests pass, covering:
  1. `test_approval_gate_approve` — execution completes successfully after approve_node() call at t+0.5s
  2. `test_approval_gate_reject` — downstream nodes do not execute; execution status is failed
  3. `test_approval_gate_timeout` — 1-second timeout causes node failure without hanging the test
  4. `test_approval_state_db_persistence` — approval state written to and readable from `workflow_approval_states` table
- **Evidence:** ROADMAP.md SC-3 requires pause/resume with reject aborting downstream; 07-RESEARCH.md Recommendation 2 confirms the `threading.Event` pattern is already proven in `TeamExecutionService._execute_human_in_loop` lines 589-661
- **Correlation with full metric:** HIGH — tests exercise the actual `threading.Event` mechanism and DB persistence; not simulated
- **Blind spots:** Does not test server-restart recovery (in-memory Event lost); does not test concurrent multiple approval gates in one workflow; SSE emission to frontend is not verified by this test
- **Validated:** No — awaiting deferred validation D3 for server-restart recovery and D4 for multi-user approval flow

### P4: Approval State DB CRUD Correctness

- **What:** `workflow_approval_states` table CRUD functions work correctly (add/get/update lifecycle)
- **How:** Direct DB function calls with an isolated temp database
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.db.workflows import add_workflow_approval_state, get_workflow_approval_state, update_workflow_approval_state
  from app.db.migrations import init_db
  import tempfile, os
  os.environ['AGENTED_DB_PATH'] = tempfile.mktemp(suffix='.db')
  init_db()
  add_workflow_approval_state('wfx-test1', 'node-1', 1800)
  state = get_workflow_approval_state('wfx-test1', 'node-1')
  assert state is not None and state['status'] == 'pending'
  update_workflow_approval_state('wfx-test1', 'node-1', 'approved')
  state2 = get_workflow_approval_state('wfx-test1', 'node-1')
  assert state2['status'] == 'approved'
  print('PASS')
  "
  ```
- **Target:** PASS — all assertions succeed
- **Evidence:** 07-RESEARCH.md Pitfall 2 establishes DB persistence as a mandatory requirement (not optional); server restart must not leave workflows permanently stuck
- **Correlation with full metric:** HIGH — directly tests the persistence layer that provides restart resilience
- **Blind spots:** Does not verify cleanup_stale_approval_states() marks timed-out states on startup
- **Validated:** No — awaiting deferred validation D3

### P5: Approve/Reject REST Endpoints Are Routable

- **What:** The three new API endpoints exist and respond (not 405 Method Not Allowed)
- **How:** Flask test client checks route registration
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app import create_app
  app = create_app()
  with app.test_client() as client:
      r1 = client.post('/admin/workflows/executions/fake/nodes/fake/approve')
      assert r1.status_code != 405, f'approve route missing: got {r1.status_code}'
      r2 = client.post('/admin/workflows/executions/fake/nodes/fake/reject')
      assert r2.status_code != 405, f'reject route missing: got {r2.status_code}'
      r3 = client.get('/admin/workflows/pending-approvals')
      assert r3.status_code != 405, f'pending-approvals route missing: got {r3.status_code}'
  print('PASS')
  "
  ```
- **Target:** PASS — all three routes respond with something other than 405
- **Evidence:** 07-03-PLAN.md requires `approveNode()` and `rejectNode()` API client methods; those methods call these endpoints
- **Correlation with full metric:** MEDIUM — tests route existence, not full request/response semantics
- **Blind spots:** Does not verify correct 200/400 status codes, authentication, or response body shape
- **Validated:** No — awaiting deferred validation D4 for full UX flow

### P6: Per-Node Retry Policy — All 3 Backoff Strategies

- **What:** Retry loops respect `max_attempts` and compute delay correctly for fixed, linear, and exponential modes
- **How:** Unit tests with nodes that fail a configurable number of times before succeeding
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "retry" -v 2>&1 | tail -15`
- **Target:** All retry tests pass, covering:
  1. `test_retry_exponential_backoff` — delay doubles each attempt
  2. `test_retry_fixed_backoff` — delay is constant
  3. `test_retry_respects_max_attempts` — exactly max_attempts+1 attempts then failure
  4. `test_retry_does_not_restart_dag` — prior successful nodes are not re-executed
- **Evidence:** ROADMAP.md SC-6 requires "per-node retry policy retries a failed node up to configured max_attempts with the specified backoff strategy, without restarting the entire DAG"; per 07-RESEARCH.md the existing `retry_max` and `retry_backoff_seconds` fields are already 90% complete — this confirms the backoff_strategy enhancement works
- **Correlation with full metric:** HIGH — tests verify the exact retry behavior described in the requirement
- **Blind spots:** Uses mocked `time.sleep` to avoid real delays (may miss edge cases in timing); does not test retry under concurrent DAG execution
- **Validated:** No — awaiting deferred validation D5 (real timing under load)

### P7: Agent Node Calls OrchestrationService with Fallback

- **What:** `_execute_agent_node` calls `OrchestrationService.execute_with_fallback()` and handles `CHAIN_EXHAUSTED`
- **How:** Mock-based test verifying OrchestrationService is called with correct arguments and routing rules are applied
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "agent_node" -v 2>&1 | tail -15`
- **Target:** All agent node tests pass, covering:
  1. `test_agent_node_calls_orchestration_service` — mock verifies execute_with_fallback is called
  2. `test_agent_node_routing_rules` — small diff (below threshold) selects cheap tier, large diff selects expensive tier
- **Evidence:** ROADMAP.md SC-4 requires "cheap-vs-expensive routing selects model tier based on diff size threshold"; 07-RESEARCH.md Recommendation 3 confirms `OrchestrationService.execute_with_fallback()` is the correct integration point (lines 44-247 of the existing service already handle all edge cases)
- **Correlation with full metric:** MEDIUM — mock tests verify routing logic but cannot test actual fallback timing (< 5 seconds target requires real rate-limit simulation)
- **Blind spots:** Does not verify fallback chain actually attempts next provider within 5 seconds; real rate-limit behavior cannot be tested with mocks
- **Validated:** No — awaiting deferred validation D5 for real fallback timing

### P8: Full Backend Test Suite — 16+ Tests in test_workflow_execution.py

- **What:** The new test file exists and all tests pass
- **How:** Run the complete test file and verify test count and pass rate
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -v 2>&1 | tail -30`
- **Target:** 16 or more tests, all passing; zero failures or errors
- **Evidence:** Plan 07-02 Task 2 specifies 16+ tests across 6 groups covering all WF requirements; this is the primary proxy-level verification for Phase 7 backend completeness
- **Correlation with full metric:** HIGH — tests were designed from the exact ROADMAP success criteria
- **Blind spots:** Mock-heavy tests may not catch integration issues between real components; in-memory execution tracking is not tested under concurrent load
- **Validated:** No — awaiting deferred validation D2 for end-to-end canvas-to-execution flow

### P9: End-to-End Workflow Execution via Flask Test Client

- **What:** A 2+ node workflow can be created via API, executed, and verified to complete with per-node output (WF-01 SC-1 proxy)
- **How:** Flask test client integration test with mocked subprocess (to avoid external CLI dependencies)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "end_to_end" -v 2>&1 | tail -20`
- **Target:** Test creates workflow via POST, triggers execution, polls to completion, asserts `status == "completed"` and each node has non-empty output
- **Evidence:** ROADMAP.md SC-1: "drag nodes, connect edges, save DAG, execute end-to-end with topological order"; the API-level test covers everything except the visual drag-and-drop step (which is deferred to D2)
- **Correlation with full metric:** MEDIUM — API test verifies DAG execution correctness but cannot verify the visual canvas interaction; drag-and-drop UX is not tested
- **Blind spots:** Mocked subprocess means actual CLI execution (claude/opencode) is not tested; the topological order assertion relies on node execution timestamps, which may be clock-dependent
- **Validated:** No — awaiting deferred validation D2 for full drag-and-drop canvas flow

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring browser environment, real external services, or conditions not reproducible in automated tests.

### D1: Security — Expression Evaluator Injection Resistance — DEFER-07-01

- **What:** The safe expression evaluator rejects all injection attempts (function calls, imports, attribute access to dunder methods, `__class__`, `__globals__`, etc.)
- **How:** Run a battery of malicious expression strings and verify each raises `ValueError` (not executes arbitrary code)
- **Why deferred:** Security testing requires a dedicated review of the AST whitelist implementation; the test set for injection attempts needs to be designed by someone familiar with Python's AST security surface. This is not a time-boxed automated check.
- **Validates at:** Manual security review — to be conducted before Phase 7 merge to main
- **Depends on:** Safe expression evaluator implemented (Plan 07-01 Task 1 Part A)
- **Target:** Zero successful injection attempts against the evaluator; all malicious expressions raise `ValueError`
- **Risk if unmet:** Code injection vulnerability in the workflow engine — a malicious condition expression could execute arbitrary Python (CONCERNS.md section 1.4 documents this as a known platform risk)
- **Fallback:** Switch to a known-safe library (`simpleeval` or `asteval`) instead of the custom evaluator; accept the added dependency

### D2: Full Browser E2E — Drag, Connect, Save, Execute — DEFER-07-02

- **What:** A user can drag bot/agent nodes onto the VueFlow canvas, connect them with edges, save the resulting DAG, execute it, and verify the pipeline runs each node in topological order (ROADMAP.md SC-1 complete)
- **How:** Playwright E2E test or manual QA session against the running dev server
- **Why deferred:** Requires a running dev server (`just dev-backend` + `just dev-frontend`), a real browser, and Playwright or equivalent — no E2E test infrastructure exists in the project yet
- **Validates at:** Manual QA session before Phase 7 is marked complete, or Phase 16 (Frontend Quality) if E2E infrastructure is added
- **Depends on:** Both backend (07-01, 07-02) and frontend (07-03) plans complete; dev server running
- **Target:** Complete drag-to-execution flow for a 3-node workflow (trigger -> conditional -> agent) in under 2 minutes without errors
- **Risk if unmet:** VueFlow canvas integration may have visual issues not caught by unit tests (e.g., Pitfall 5: node type not registered with markRaw(), causing rendering warnings); approval modal may not trigger on pending_approval SSE events
- **Fallback:** Manual QA checklist for canvas interactions; defer Playwright tests to Phase 16

### D3: Server Restart Recovery — Approval Gate State Cleanup — DEFER-07-03

- **What:** After a server restart with a workflow in `pending_approval` state, the execution is correctly marked as `timed_out` (not left stuck in `running` or `pending_approval` forever)
- **How:** Integration test: start workflow, trigger approval gate, kill and restart server, verify DB record transitions to `timed_out`, verify UI shows failed status
- **Why deferred:** Requires process-level server restart simulation — cannot be done within a single pytest session; the `cleanup_stale_executions()` logic runs at app startup and requires a fresh `create_app()` call after DB has a pending record
- **Validates at:** Phase 13 (Execution Resilience & Infrastructure) — RES-08 addresses persistent execution state more broadly
- **Depends on:** Approval state DB persistence (Plan 07-01 Task 2 Part A); startup cleanup extension (Part F)
- **Target:** 100% of pending approval states are marked `timed_out` within 5 seconds of server startup; no executions remain stuck in `pending_approval` after restart
- **Risk if unmet:** Workflows appear permanently stuck in the UI; operators must manually query the DB to unstick them. Impact is operational (annoying but not data-loss)
- **Fallback:** Document the restart limitation; add an admin API endpoint to manually expire stale approval states

### D4: Multi-User Approval Flow with SSE — DEFER-07-04

- **What:** When an approval gate enters `pending_approval`, the frontend shows the ApprovalModal correctly; one user can approve/reject and another user watching the same execution sees the status update in real time via SSE
- **How:** Manual QA session with two browser windows, or Playwright test with two page contexts watching the same execution stream
- **Why deferred:** Requires running server with SSE streaming, a real browser with EventSource, and coordination between two user sessions
- **Validates at:** Manual QA session before Phase 7 is marked complete
- **Depends on:** Plan 07-03 (frontend SSE handling for pending_approval, ApprovalModal, API client methods); Plan 07-01 (backend SSE emission on _update_node_state pending_approval)
- **Target:** Approval modal appears within 2 seconds of the backend emitting the `pending_approval` SSE event; approve/reject action completes within 1 second of API call
- **Risk if unmet:** The approval UX is broken for users — the primary WF-03 user-facing feature doesn't work. High impact, likely to surface quickly in practice
- **Fallback:** Verify SSE emission via backend logs; test approve/reject API endpoints manually with curl

### D5: Real Fallback Chain Timing — Under 5 Seconds — DEFER-07-05

- **What:** When the primary provider returns a rate-limit error, the next provider in the fallback chain is attempted within 5 seconds (ROADMAP.md SC-4)
- **How:** Integration test with a real (or realistically mocked with delay) rate-limit response from `RateLimitService`; measure wall-clock time from rate-limit detection to the next provider attempt
- **Why deferred:** The mock-based tests in Plan 07-02 cannot measure real timing; actual rate-limit cooldown behavior in `OrchestrationService` depends on `RateLimitService` cooldown schedules that are timing-sensitive
- **Validates at:** Phase 8 (Execution Intelligence & Replay) — EXE-01 execution replay infrastructure would enable timing comparison; alternatively, a targeted integration test once the full Phase 7 stack is in place
- **Depends on:** Plan 07-02 Task 1 (OrchestrationService wired into agent node); at least one configured backend/account pair in the test DB
- **Target:** Failover latency < 5 seconds from rate-limit detection to next provider attempt (ROADMAP.md SC-4)
- **Risk if unmet:** Multi-model fallback appears to work in tests (via mocks) but is too slow in production; user-facing latency spikes > 5 seconds on rate-limited workflows
- **Fallback:** Accept mock-based verification as sufficient for Phase 7; schedule timing test as part of Phase 13 load testing

---

## Ablation Plan

**Purpose:** Isolate component contributions to verify each enhancement adds value independently.

### A1: Without Edge-Aware Branching (sourceHandle filtering disabled)

- **Condition:** Comment out the `skipped_nodes` population logic that reads `sourceHandle` from edges in `_run_workflow`
- **Expected impact:** Both true and false branch paths execute for every conditional node; downstream-of-skipped nodes also execute; test `test_conditional_branch_true_path` fails because command_b still executes
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "branch" -v`
- **Evidence:** 07-RESEARCH.md Pitfall 1 explicitly describes this failure mode — "Both true and false branch paths execute for every conditional node"
- **Purpose:** Confirms that the edge-aware routing code is the actual mechanism providing WF-05 correctness, not test artifacts

### A2: Without Approval Gate DB Persistence (in-memory Event only)

- **Condition:** Remove the `add_workflow_approval_state` call from `_execute_approval_gate_node` (keep the threading.Event)
- **Expected impact:** Approval gate still works within a single server session (Event is in-memory); test `test_approval_gate_approve` still passes; test `test_approval_state_db_persistence` fails
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "approval" -v`
- **Evidence:** 07-RESEARCH.md Pitfall 2 establishes that without DB persistence, server restart leaves workflows permanently stuck
- **Purpose:** Confirms DB persistence adds resilience beyond what in-memory alone provides; validates that the DB layer is independently tested

### A3: Without OrchestrationService Wiring (agent node returns stub)

- **Condition:** Revert `_execute_agent_node` to return stub text `[agent:{agent_id}] executed`
- **Expected impact:** `test_agent_node_calls_orchestration_service` fails; end-to-end test still passes if using non-agent nodes; WF-04 cannot be demonstrated
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -k "agent_node or end_to_end" -v`
- **Evidence:** 07-RESEARCH.md Recommendation 3 describes the stub as the current state before Phase 7
- **Purpose:** Confirms that the OrchestrationService wiring is what provides real multi-model execution (WF-04), not the existing stub

---

## WebMCP Tool Definitions

WebMCP tool definitions are conditionally applicable.

**Condition check:** Phase 7 includes frontend modifications (07-03-PLAN.md modifies `.vue`, `.ts` files in `frontend/src/components/workflow/` and `frontend/src/composables/`). If WebMCP is available in the environment, the following tools should be used by the grd-verifier.

If WebMCP is not available in the environment, skip this section.

### Generic Checks

| Tool | Purpose | Expected |
|------|---------|----------|
| hive_get_health_status | Backend is responding after frontend changes | status: healthy |
| hive_check_console_errors | No new JavaScript errors from VueFlow registration changes | No new errors since phase start |
| hive_get_page_info | App renders without blank screen | Page loads with expected content |

### Page-Specific Tools

| Tool | Page | Purpose | Expected |
|------|------|---------|----------|
| hive_check_workflow_canvas_nodes | /workflows (canvas view) | Approval gate appears in sidebar palette; can be dragged to canvas | Approval gate node renders with pause icon and amber styling |
| hive_check_workflow_config_panel | /workflows (node selected) | NodeConfigPanel shows approval_gate fields when node selected | Timeout and notification message fields visible |
| hive_check_workflow_approval_modal | /workflows (during execution with approval gate) | ApprovalModal appears when node enters pending_approval | Modal with Approve/Reject buttons visible |

### useWebMcpTool() Definitions

```js
// Generic health checks
useWebMcpTool("hive_get_health_status", {})
useWebMcpTool("hive_check_console_errors", { since: "phase_start" })
useWebMcpTool("hive_get_page_info", {})

// Canvas: approval gate node in palette and on canvas
useWebMcpTool("hive_check_workflow_canvas_nodes", {
  url: "/workflows",
  checks: [
    "approval_gate node type present in sidebar palette",
    "dragging approval_gate to canvas creates a rendered node",
    "node has amber/yellow color scheme"
  ]
})

// Config panel: approval gate config fields
useWebMcpTool("hive_check_workflow_config_panel", {
  url: "/workflows",
  checks: [
    "selecting approval_gate node shows timeout field",
    "selecting approval_gate node shows notification message field",
    "selecting conditional node with expression type shows expression input"
  ]
})

// Approval modal: appears during execution
useWebMcpTool("hive_check_workflow_approval_modal", {
  url: "/workflows",
  checks: [
    "modal appears when execution reaches pending_approval state",
    "Approve button calls /admin/workflows/executions/{id}/nodes/{id}/approve",
    "Reject button calls /admin/workflows/executions/{id}/nodes/{id}/reject"
  ]
})
```

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Conditional node behavior (pre-Phase 7) | Only `has_text`, `exit_code_zero`, `contains` conditions; all branches execute regardless of result | 0 of 5 PR attribute expressions evaluate correctly; branch routing accuracy = 0% | 07-RESEARCH.md#State-of-the-Art |
| Agent node behavior (pre-Phase 7) | Returns stub text `[agent:{agent_id}] executed` | 0% real multi-model execution | 07-RESEARCH.md#Recommended-Verification-Tiers |
| Approval gate (pre-Phase 7) | Does not exist as a node type | No pause/resume capability | 07-RESEARCH.md#State-of-the-Art |
| Per-node retry (pre-Phase 7) | Exists with `retry_max` and `retry_backoff_seconds`; only exponential mode | 2 of 3 backoff strategies missing | 07-RESEARCH.md#State-of-the-Art |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_workflow_execution.py  (to be created in Plan 07-02)
```

**How to run full proxy evaluation:**
```bash
# All sanity checks in sequence:
cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
from app.models.workflow import WorkflowNodeType, WorkflowExecutionStatus, NodeExecutionStatus
from app.services.workflow_execution_service import WorkflowExecutionService, evaluate_condition
assert 'approval_gate' in [e.value for e in WorkflowNodeType]
assert 'pending_approval' in [e.value for e in WorkflowExecutionStatus]
assert 'approval_gate' in WorkflowExecutionService.NODE_DISPATCHERS
assert evaluate_condition('1 > 0', {}) == True
print('S1-S4 PASS')
"

# Full backend test suite (sanity S7 + proxy P8):
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/ -x -q

# Focused Phase 7 tests (proxy P1-P9):
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_workflow_execution.py -v

# Frontend build (sanity S11):
cd /Users/neo/Developer/Projects/Agented/frontend && npm run build

# Frontend tests (sanity S12):
cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: WorkflowNodeType enum | | | |
| S2: Status enums pending_approval | | | |
| S3: NODE_DISPATCHERS approval_gate | | | |
| S4: evaluate_condition importable | | | |
| S5: Agent node OrchestrationService | | | |
| S6: backoff_strategy field | | | |
| S7: Backend test suite no regressions | | | |
| S8: ApprovalGateNode.vue file exists | | | |
| S9: WorkflowCanvas nodeTypes registration | | | |
| S10: API client approveNode/rejectNode | | | |
| S11: Frontend build zero errors | | | |
| S12: Frontend tests no regressions | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Expression evaluator 6 conditions | All 6 pass | | | |
| P2: Branch routing 4 scenarios | All 4 pass | | | |
| P3: Approval gate approve/reject/timeout | All 4 tests pass | | | |
| P4: Approval state DB CRUD | PASS | | | |
| P5: API endpoints routable | All 3 routes 2xx/4xx (not 405) | | | |
| P6: Retry policy 4 tests | All 4 pass | | | |
| P7: Agent node OrchestrationService mock | Both tests pass | | | |
| P8: Full test suite test count | >= 16 tests, 0 failures | | | |
| P9: End-to-end workflow via API | status == completed | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Without edge-aware branching | branch tests fail | | |
| A2: Without approval DB persistence | persistence test fails only | | |
| A3: Without OrchestrationService wiring | agent_node tests fail | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-07-01 | Expression evaluator injection resistance | PENDING | Manual security review before merge |
| DEFER-07-02 | Full browser E2E drag-connect-save-execute | PENDING | Manual QA or Phase 16 Playwright |
| DEFER-07-03 | Server restart approval state cleanup | PENDING | Phase 13 (RES-08) |
| DEFER-07-04 | Multi-user approval flow with SSE | PENDING | Manual QA before Phase 7 complete |
| DEFER-07-05 | Real fallback chain timing < 5 seconds | PENDING | Phase 8 or targeted integration test |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM-HIGH

**Justification:**
- Sanity checks: Adequate — 12 checks covering all new components, entry points, and build artifacts; commands are exact and runnable
- Proxy metrics: Well-evidenced — all 9 metrics trace directly to ROADMAP.md success criteria; test targets come from the plan's own verify blocks; the primary risk (mocked tests not catching integration issues) is documented per metric
- Deferred coverage: Partial but honest — the 5 deferred items cover the most important real-world risks (security injection, browser rendering, restart recovery, SSE timing, real fallback latency); each has a `validates_at` reference and a fallback plan

**What this evaluation CAN tell us:**
- Whether the safe expression evaluator handles all required operator categories correctly (P1)
- Whether conditional branch routing correctly skips non-matching paths in a unit test DAG (P2)
- Whether the approval gate pause/resume/reject mechanism works within a single process without restart (P3)
- Whether DB persistence of approval state works correctly (P4)
- Whether all API endpoints are registered and routable (P5)
- Whether per-node retry with all 3 backoff strategies works correctly (P6)
- Whether agent nodes call OrchestrationService (not stub) with correct routing rule logic (P7, mocked)
- Whether the Phase 7 backend is complete with 16+ tests covering all 6 WF requirements (P8)
- Whether a 2+ node workflow can be executed end-to-end via the API (P9, mocked subprocess)
- Whether the frontend builds without type errors and existing tests pass (S11, S12)

**What this evaluation CANNOT tell us:**
- Whether the expression evaluator is resistant to injection attacks (deferred to DEFER-07-01 — security review needed before merge)
- Whether the VueFlow canvas drag-and-drop actually works in a real browser with the new node types (deferred to DEFER-07-02 — needs browser environment)
- Whether server restart correctly cleans up pending approval states in practice (deferred to DEFER-07-03 — requires process-level restart)
- Whether the ApprovalModal actually appears in the browser when a pending_approval SSE event arrives (deferred to DEFER-07-04 — requires running server + browser)
- Whether the fallback chain failover is actually < 5 seconds with real API rate limits (deferred to DEFER-07-05 — mocks cannot validate timing)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
