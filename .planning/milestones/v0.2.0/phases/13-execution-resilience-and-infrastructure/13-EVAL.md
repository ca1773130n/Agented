# Evaluation Plan: Phase 13 — Execution Resilience & Infrastructure

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Methods evaluated:** Circuit breaker (Nygard 2018), exponential backoff with full jitter (AWS 2024), SQLite-backed execution queue (persist-queue pattern), SIGSTOP/SIGCONT pause/resume (POSIX), HMAC-SHA256 webhook validation (webhooks.fyi)
**Reference research:** `.planning/milestones/v0.1.0/phases/13-execution-resilience-infrastructure/13-RESEARCH.md`
**Plans covered:** 13-01 (circuit breaker + retry), 13-02 (execution queue), 13-03 (pause/resume + bulk cancel), 13-04 (webhook validation + persistence + analytics)

---

## Evaluation Overview

Phase 13 is a pure infrastructure hardening phase. There is no machine learning or novel algorithm being evaluated — the success criteria are behavioral: does the system correctly enforce state machines, signal processes, persist data, reject invalid requests, and bound resource usage? All methods implemented are canonical, well-established patterns (Nygard 2018, AWS backoff guidance, POSIX signals) applied to the existing Flask/SQLite/subprocess architecture.

The primary evaluation challenge is that most behaviors require either subprocess-level interaction (pause/resume needs a real running subprocess) or time-dependent state transitions (circuit breaker recovery timeout, retry backoff curves). Unit tests with mocking cover the state machine logic completely. Integration-level behaviors — whether SIGSTOP actually suspends a real `claude` CLI subprocess, whether the queue handles hundreds of concurrent enqueues gracefully under SQLite WAL contention — must be deferred to manual integration testing and load testing.

No external benchmarks exist for this phase (BENCHMARKS.md is empty). Targets are derived from the phase requirements (RES-01 through RES-09) and the existing codebase baseline (940 passing tests, fire-and-forget thread dispatch with no concurrency control, per-trigger HMAC validation without consolidation).

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|-----------------|
| Circuit breaker state transition correctness | RES-01; Nygard (2018) Ch.5; 13-RESEARCH.md#recommendation-1 | Directly measures the core safety property — fast-fail on N failures |
| Transient error classification accuracy | RES-02; AWS (2024) backoff guidance; 13-RESEARCH.md#recommendation-2 | Misclassification causes either missed retries or breaker trips on permanent errors |
| Concurrency cap enforcement | RES-03; 13-RESEARCH.md#recommendation-3 | Unbounded concurrency is the primary resource exhaustion risk |
| Queue FIFO ordering | RES-03; persist-queue architecture | FIFO is the fairness guarantee for dispatch |
| Queue persistence across restart | RES-04; 13-RESEARCH.md#recommendation-3 | Survival across restart is the defining requirement for RES-04 |
| SIGSTOP/SIGCONT signal delivery | RES-05; Python subprocess docs; POSIX | Pause/resume correctness depends on correct signal targeting |
| Bulk cancel completeness and timing | RES-06; 13-RESEARCH.md#recommendation-5 | Cancel within 5 seconds is the stated requirement |
| HMAC 403 rejection rate | RES-07; webhooks.fyi; 13-RESEARCH.md#recommendation-5 | Security property: invalid signatures must be rejected before any processing |
| Execution log persistence (no TTL) | RES-08 | Default-unlimited retention is explicitly required |
| Workflow analytics query correctness | RES-09 | Per-node status must be accurate for analytics to be useful |
| Regression: existing test suite | Baseline (940 tests) | Zero regressions is a hard requirement for all 4 plans |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 12 checks | Basic functionality, format, and existence verification |
| Proxy (L2) | 11 metrics | Automated unit/integration tests approximating real quality |
| Deferred (L3) | 5 validations | Require real subprocess execution, load, or real webhook providers |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: No regression — existing test suite passes
- **What:** All 940 pre-existing tests continue to pass after phase 13 changes
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest -x -q 2>&1 | tail -5`
- **Expected:** `940 passed` (or higher if phase adds tests) with no failures
- **Failure means:** A regression was introduced in existing execution, webhook, trigger, or workflow logic. Must investigate before proceeding.

### S2: CircuitBreakerService class exists with required interface
- **What:** The three required public methods exist on CircuitBreakerService
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.circuit_breaker_service import CircuitBreakerService; assert hasattr(CircuitBreakerService, 'can_execute'); assert hasattr(CircuitBreakerService, 'record_success'); assert hasattr(CircuitBreakerService, 'record_failure'); print('OK')"`
- **Expected:** `OK`
- **Failure means:** CircuitBreakerService was not created or is missing core methods. Plan 13-01 incomplete.

### S3: circuit_breakers table exists in schema
- **What:** The circuit_breakers SQLite table is defined in the schema and created on DB init
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.db.connection import get_connection; from app import create_app; app = create_app(); ctx = app.app_context(); ctx.push(); conn = next(get_connection()); cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='circuit_breakers'\"); assert cur.fetchone() is not None, 'table missing'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** DB migration for circuit_breakers was not applied. Plan 13-01 incomplete.

### S4: ExecutionQueueService class exists with required interface
- **What:** Queue service has enqueue, start_dispatcher, and stop_dispatcher methods
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.execution_queue_service import ExecutionQueueService; assert hasattr(ExecutionQueueService, 'enqueue'); assert hasattr(ExecutionQueueService, 'start_dispatcher'); assert hasattr(ExecutionQueueService, 'stop_dispatcher'); print('OK')"`
- **Expected:** `OK`
- **Failure means:** ExecutionQueueService was not created or is missing core methods. Plan 13-02 incomplete.

### S5: execution_queue table exists in schema
- **What:** The execution_queue SQLite table is defined and created on DB init
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.db.connection import get_connection; from app import create_app; app = create_app(); ctx = app.app_context(); ctx.push(); conn = next(get_connection()); cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='execution_queue'\"); assert cur.fetchone() is not None, 'table missing'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** DB migration for execution_queue was not applied. Plan 13-02 incomplete.

### S6: Queue depth admin API returns valid JSON
- **What:** GET /admin/executions/queue returns JSON with expected shape (not 404 or 500)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app import create_app; app = create_app(); client = app.test_client(); r = client.get('/admin/executions/queue'); assert r.status_code == 200, f'got {r.status_code}'; import json; body = json.loads(r.data); assert 'queue' in body or 'total_pending' in body, f'unexpected body: {body}'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** Admin queue endpoint missing or broken. Plan 13-02 incomplete.

### S7: ProcessManager.pause and ProcessManager.resume methods exist
- **What:** ProcessManager has pause and resume classmethods
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.process_manager import ProcessManager; assert callable(getattr(ProcessManager, 'pause', None)); assert callable(getattr(ProcessManager, 'resume', None)); print('OK')"`
- **Expected:** `OK`
- **Failure means:** Pause/resume was not added to ProcessManager. Plan 13-03 incomplete.

### S8: Pause/resume API endpoints return correct status codes for non-existent execution
- **What:** POST /admin/executions/<unknown_id>/pause and /resume return 404 (not 500)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app import create_app; app = create_app(); client = app.test_client(); r = client.post('/admin/executions/exec-zzzzzz/pause'); assert r.status_code == 404, f'pause got {r.status_code}'; r2 = client.post('/admin/executions/exec-zzzzzz/resume'); assert r2.status_code == 404, f'resume got {r2.status_code}'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** Endpoints not registered or error handling broken. Plan 13-03 incomplete.

### S9: WebhookValidationService class exists with required interface
- **What:** WebhookValidationService has validate_signature, validate_webhook, and validate_github methods
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.webhook_validation_service import WebhookValidationService; assert hasattr(WebhookValidationService, 'validate_signature'); assert hasattr(WebhookValidationService, 'validate_webhook'); assert hasattr(WebhookValidationService, 'validate_github'); print('OK')"`
- **Expected:** `OK`
- **Failure means:** WebhookValidationService was not created or is missing core methods. Plan 13-04 incomplete.

### S10: Invalid HMAC returns 403 on webhook endpoint
- **What:** A webhook POST with a wrong signature header returns 403, not 200
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app import create_app; app = create_app(); client = app.test_client(); headers = {'X-Webhook-Signature': 'sha256=badbadbadbad', 'Content-Type': 'application/json'}; r = client.post('/api/webhooks/trigger-000000', data=b'{\"test\": 1}', headers=headers); print('status:', r.status_code); assert r.status_code in (403, 404), f'expected 403 or 404 for unknown trigger, got {r.status_code}'"`
- **Expected:** `status: 403` (or 404 if trigger does not exist — 403 must appear before trigger lookup for a trigger with a configured webhook secret)
- **Failure means:** Webhook validation service not integrated into the route. Plan 13-04 incomplete. Note: test with a real trigger that has a configured webhook secret for a clean 403 assertion.

### S11: Execution logs persist without TTL by default
- **What:** The scheduler does not call delete_old_execution_logs when EXECUTION_LOG_RETENTION_DAYS is unset or 0
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.scheduler_service import SchedulerService; import inspect; src = inspect.getsource(SchedulerService); assert 'EXECUTION_LOG_RETENTION_DAYS' in src or 'retention' in src.lower(), 'retention config not found in scheduler'; print('retention config present in scheduler')"`
- **Expected:** `retention config present in scheduler`
- **Failure means:** Scheduler still unconditionally deletes execution logs. RES-08 violated. Plan 13-04 incomplete.

### S12: "paused" status is a valid execution state
- **What:** The execution state enum/class includes "paused" and "pause_timeout"
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.execution_service import ExecutionStatus; states = [s.value if hasattr(s, 'value') else s for s in ExecutionStatus]; assert 'paused' in states, f'paused not in {states}'; print('OK')"`
- **Expected:** `OK`
- **Failure means:** ExecutionStatus was not extended with paused state. Plan 13-03 incomplete.

**Sanity gate:** ALL sanity checks must pass. Any failure blocks progression.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of quality/performance via automated tests.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full integration testing. Results should be treated as evidence of correctness, not proof.

### P1: Circuit breaker state transitions — all 5 transition paths tested
- **What:** The circuit breaker correctly transitions through CLOSED->OPEN->HALF_OPEN->CLOSED and the regression path HALF_OPEN->OPEN
- **How:** Run the circuit breaker unit test suite
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_circuit_breaker.py -v 2>&1 | tail -20`
- **Target:** All test cases pass, including at minimum: CLOSED->OPEN (5 failures), OPEN fast-fail, OPEN->HALF_OPEN (timeout elapsed), HALF_OPEN->CLOSED (success), HALF_OPEN->OPEN (failure). Minimum 10 test cases.
- **Evidence:** Nygard (2018) defines the three-state circuit breaker; these are the canonical transition tests. 13-RESEARCH.md Verification Strategy directly calls out these transitions as Level 1 checks. 13-01-PLAN.md Task 2 specifies the same test cases.
- **Correlation with full metric:** HIGH — state transition unit tests are the complete specification for a pure state machine
- **Blind spots:** Tests use mocked time or short timeouts; real-world concurrency under load not tested
- **Validated:** No — awaiting deferred integration validation (DEFER-13-01)

### P2: Transient error classification accuracy
- **What:** Errors that should trip the circuit breaker (502, 503, timeout, connection refused) are classified as transient; permanent errors (FileNotFoundError, bad prompt exit code 1) are classified as non-transient
- **How:** Unit tests covering the `is_transient_error()` classification function with representative error samples
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_circuit_breaker.py -v -k "transient or classification" 2>&1`
- **Target:** 100% correct classification for all documented transient and non-transient patterns. Zero false positives (non-transient errors tripping the breaker).
- **Evidence:** 13-RESEARCH.md Pitfall 1 explicitly warns that misclassification causes the breaker to stay OPEN incorrectly. The excluded-exception design is from PyBreaker documentation and Nygard (2018) Ch.5.
- **Correlation with full metric:** HIGH — classification is deterministic; unit tests cover the full input space
- **Blind spots:** Real subprocess error messages may have variations not covered by the pattern list; production stderr from claude/opencode CLI may differ from patterns tested
- **Validated:** No — awaiting deferred validation against real CLI error output (DEFER-13-02)

### P3: Concurrency cap enforcement — at most N executions run simultaneously
- **What:** When concurrency cap is set to K for a trigger, at most K executions dispatch concurrently even if N > K entries are queued
- **How:** Unit tests that enqueue N items for a trigger with cap=K, then verify active count never exceeds K
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_execution_queue.py -v -k "concurrency or cap" 2>&1`
- **Target:** Tests demonstrate cap=1 enforced (default), cap=2 enforced, and excess entries remain in "pending" state until a slot opens
- **Evidence:** 13-RESEARCH.md Recommendation 3 identifies unbounded concurrency as the primary resource exhaustion risk. 13-02-PLAN.md Task 2 specifies this as a test case.
- **Correlation with full metric:** MEDIUM — unit tests mock ExecutionService.run_trigger; real subprocess resource usage not measured
- **Blind spots:** Dispatcher timing jitter could allow brief over-subscription if polling interval aligns with multiple entries becoming eligible simultaneously
- **Validated:** No — awaiting deferred load test (DEFER-13-03)

### P4: Queue FIFO ordering — entries dispatched in enqueue order
- **What:** When N executions are queued, they are dispatched in the order they were enqueued (FIFO within same priority)
- **How:** Enqueue entries A, B, C and verify dispatch order matches insertion order
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_execution_queue.py -v -k "fifo or order" 2>&1`
- **Target:** Dispatch order matches insertion order for all test cases
- **Evidence:** FIFO is the fairness guarantee stated in RES-03. 13-02-PLAN.md specifies `ORDER BY priority DESC, created_at ASC` in the queue SELECT.
- **Correlation with full metric:** HIGH — FIFO ordering is deterministic and fully testable in unit context
- **Blind spots:** Concurrent insertion from multiple threads could cause non-deterministic ordering within the same millisecond; not tested
- **Validated:** No

### P5: Queue persistence across simulated restart
- **What:** Pending queue entries survive a simulated server restart (stale "dispatching" recovery returns them to "pending")
- **How:** Insert queue entries, mark one as "dispatching" (simulating an in-flight restart), call start_dispatcher() with recovery, verify "dispatching" entry is reset to "pending"
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_execution_queue.py -v -k "restart or recovery or persist" 2>&1`
- **Target:** Stale "dispatching" entries are recovered to "pending" state after restart; "pending" entries remain available for dispatch
- **Evidence:** RES-04 explicitly requires survival across restart. 13-02-PLAN.md Task 2 specifies this test case.
- **Correlation with full metric:** MEDIUM — simulated restart (re-calling start_dispatcher in the same process) approximates but does not fully replicate an actual server restart
- **Blind spots:** Actual restart resets in-memory state entirely (ProcessManager._processes, CircuitBreakerService._breakers); simulated test does not exercise this full reset path
- **Validated:** No — awaiting deferred real-restart test (DEFER-13-04)

### P6: Pause/resume API — correct state transitions and 409 on invalid state
- **What:** Pause endpoint transitions "running" -> "paused" (200); returns 409 if execution is not running. Resume endpoint transitions "paused" -> "running" (200); returns 409 if not paused.
- **How:** Mock ProcessManager SIGSTOP/SIGCONT; test API routes with synthetic execution records in DB
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_pause_cancel.py -v 2>&1`
- **Target:** All test cases pass, including: pause on running (200), pause on non-running (409), resume on paused (200), resume on non-paused (409), pause on non-existent (404). Minimum 10 test cases.
- **Evidence:** RES-05 specifies pause/resume without data loss; CAS-based state transition is required (13-RESEARCH.md Pitfall 5). 13-03-PLAN.md Task 2 specifies these test cases.
- **Correlation with full metric:** MEDIUM — status code tests verify state machine logic, but the actual SIGSTOP signal delivery to the subprocess is mocked
- **Blind spots:** Whether SIGSTOP actually suspends a long-running `claude` subprocess without data loss is NOT verified by these unit tests
- **Validated:** No — awaiting deferred subprocess integration test (DEFER-13-05)

### P7: Bulk cancel terminates matching executions
- **What:** POST /admin/executions/bulk-cancel with trigger_id filter cancels all running executions for that trigger; the response reports per-execution success/failure
- **How:** Create synthetic running execution records, call bulk cancel, verify status updates
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_pause_cancel.py -v -k "bulk" 2>&1`
- **Target:** 100% of matching executions report cancelled in the response body; no non-matching executions are cancelled
- **Evidence:** RES-06 requires individual + bulk cancel. 13-03-PLAN.md specifies trigger_id and execution_ids filter support.
- **Correlation with full metric:** MEDIUM — mocked ProcessManager; real subprocess termination not tested
- **Blind spots:** Race condition between bulk cancel and natural completion (both updating the same record) is tested with CAS but not with real concurrency
- **Validated:** No

### P8: HMAC validation — valid signatures pass, invalid signatures return 403
- **What:** WebhookValidationService.validate_signature returns True for correct HMAC; webhook routes return 403 for invalid/missing/wrong-prefix signatures
- **How:** Unit tests with computed HMAC against known secret and payload; route tests via Flask test client
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_webhook_validation.py -v 2>&1`
- **Target:** 12+ test cases covering: valid sha256, invalid sha256, valid sha1 (legacy), missing header, wrong prefix, timestamp within tolerance, timestamp outside tolerance, 403 via route
- **Evidence:** RES-07 requires SHA-256 default with 403 rejection. webhooks.fyi specifies `hmac.compare_digest` for timing-safe comparison (already used in codebase). 13-04-PLAN.md Task 1 specifies these test cases.
- **Correlation with full metric:** HIGH — HMAC validation is deterministic; unit tests cover the complete validation logic
- **Blind spots:** Replay protection uses timestamp comparison, not nonce tracking — a replay within the 5-minute window with the same timestamp is not detected
- **Validated:** No

### P9: Duplicate HMAC implementations removed
- **What:** The old `ExecutionService._verify_webhook_hmac` and standalone `verify_github_signature` are removed; only `WebhookValidationService` handles HMAC validation
- **How:** Grep the backend service/route files for the old function names
- **Command:** `grep -r "_verify_webhook_hmac\|verify_github_signature" /Users/neo/Developer/Projects/Agented/backend/app/ --include="*.py" | grep -v "test_" | grep -v "__pycache__"`
- **Target:** Zero matches in non-test service/route files (the functions are deleted, not just unused)
- **Evidence:** 13-04-PLAN.md explicitly requires removing both old implementations and updating callers. Consolidation is the stated goal of RES-07.
- **Correlation with full metric:** HIGH — grep is a direct check for the target property
- **Blind spots:** Functions could be commented out rather than removed; grep would still find them
- **Validated:** No

### P10: Workflow analytics queries return correct aggregates
- **What:** `get_workflow_node_analytics()` returns per-node success/failure counts that match seeded test data; `get_workflow_execution_timeline()` returns nodes in chronological order
- **How:** Unit tests with isolated_db fixture seeded with known workflow execution records
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_execution_persistence.py -v 2>&1`
- **Target:** Analytics counts match seeded data exactly; timeline ordering is correct; zero-data case returns empty results (not errors)
- **Evidence:** RES-09 requires per-node status for analytics. 13-04-PLAN.md Task 2 specifies these analytics functions.
- **Correlation with full metric:** MEDIUM — aggregation SQL correctness is testable, but performance at scale (thousands of records) is not
- **Blind spots:** GROUP BY queries may have subtle rounding or type-coercion issues not caught by small test datasets
- **Validated:** No — awaiting deferred scale test (DEFER-13-05)

### P11: Execution log retention disabled by default
- **What:** When EXECUTION_LOG_RETENTION_DAYS is not set or is 0, the scheduler does not run the delete_old_execution_logs job
- **How:** Unit test that verifies scheduler job is skipped under default config
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_execution_persistence.py -v -k "retention or ttl or cleanup" 2>&1`
- **Target:** Test confirms the scheduled cleanup does not fire when retention is disabled (default)
- **Evidence:** RES-08 requires "no TTL limitation". Current codebase runs `delete_old_execution_logs(days=30)` daily via scheduler. 13-04-PLAN.md Task 2 requires making this opt-in.
- **Correlation with full metric:** HIGH — the behavior is deterministic and directly testable
- **Blind spots:** Config value could be read at different points; if scheduler reads it on startup and caches it, runtime changes would not take effect
- **Validated:** No

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring real subprocess execution, load testing, or production integration.

### D1: Real AI backend failure simulation — DEFER-13-01
- **What:** Circuit breaker correctly fast-fails, then auto-recovers, when the actual `claude` or `opencode` CLI is unavailable or returns transient errors
- **How:** Temporarily rename the claude binary, fire 5 execution requests, verify breaker opens; restore the binary, wait for recovery timeout, fire 1 request, verify breaker transitions to HALF_OPEN then CLOSED
- **Why deferred:** Requires a real `claude` CLI installation and is destructive (binary rename); not safe to run in standard CI
- **Validates at:** Manual integration testing after phase 13 completion
- **Depends on:** claude CLI installed in the test environment; ability to simulate backend unavailability
- **Target:** Breaker opens after exactly 5 transient failures; recovers to CLOSED within 65 seconds (reset_timeout=60 + margin)
- **Risk if unmet:** Transient error classification may miss real CLI error patterns; breaker could trip on non-transient errors in production. Mitigation: review `_is_transient_error()` against actual CLI output from a live run.
- **Fallback:** If real CLI test is not feasible, manually inspect stderr patterns from 3 recent failed executions and verify they match the classifier patterns.

### D2: Transient error classification against real CLI output — DEFER-13-02
- **What:** The stderr patterns used in `is_transient_error()` match the actual error output from `claude`/`opencode` CLI when they encounter connection failures, rate limits, and 502/503 errors
- **How:** Collect real stderr output from failed executions (from existing execution_logs table) and verify the patterns match
- **Why deferred:** Requires production or staging execution history showing actual transient failures
- **Validates at:** After 2 weeks of production operation with phase 13 deployed
- **Depends on:** Deployed phase 13 + production traffic generating transient failures
- **Target:** All transient failures in the first 2 weeks of production operation are correctly classified and retried; zero instances of non-transient errors triggering retry
- **Risk if unmet:** Silent retry storms if non-transient errors are misclassified. Detection: monitor retry count in pending_retries table; alert if a single execution has >5 retry attempts.
- **Fallback:** Add an explicit "transient error patterns" config variable that operators can extend without code changes.

### D3: Queue under load — sustained webhook burst — DEFER-13-03
- **What:** The execution queue correctly handles 50+ concurrent webhook arrivals without SQLite lock errors, 5xx responses on the webhook endpoint, or queue corruption
- **How:** Load test: fire 50 concurrent HTTP POST requests to a test webhook trigger, measure response time distribution and error rate
- **Why deferred:** Requires load testing infrastructure and a running server; cannot be run in unit test context
- **Validates at:** Manual load test session after phase 13 completion (schedule as ad-hoc test)
- **Depends on:** Running server with WAL-mode SQLite and execution queue service active
- **Target:** P95 webhook response time < 100ms (queue insert only); zero 5xx errors; zero SQLite "database is locked" errors in server logs; queue depth visible and accurate in admin API
- **Risk if unmet:** High-volume webhook sources (GitHub org webhooks) could cause SQLite contention. Mitigation: WAL mode (already configured) should handle ~100 writes/second; contention at >100/s would require a separate queue database file.
- **Fallback:** If contention is observed, split execution_queue into its own SQLite file (separate from main DB).

### D4: Real restart survival — pending queue entries and retry queue — DEFER-13-04
- **What:** Pending queue entries and scheduled retries are actually recovered after a full server restart (not just a simulated in-process restart)
- **How:** (1) Create 3 pending queue entries via webhook calls, (2) stop the Flask server (`kill -9`), (3) restart the server, (4) verify all 3 entries are dispatched within 10 seconds of restart
- **Why deferred:** Requires starting and stopping a real server process; not runnable in unit test context
- **Validates at:** Manual integration test after phase 13 completion
- **Depends on:** Full server running with execution_queue and pending_retries tables populated
- **Target:** 100% of pre-restart pending entries are dispatched after restart; no entries are lost or duplicated
- **Risk if unmet:** Operators would lose queued executions on any server restart or deploy. Mitigation: the queue table is persistent by design; loss indicates a bug in the stale-recovery logic in `start_dispatcher()`.
- **Fallback:** Add a startup log message showing how many pending entries were recovered.

### D5: Real SIGSTOP/SIGCONT against long-running subprocess — DEFER-13-05
- **What:** Pausing and resuming an actual running `claude` subprocess via SIGSTOP/SIGCONT does not lose output, corrupt state, or cause the process to exit unexpectedly
- **How:** (1) Start a long-running execution (a prompt that takes >60 seconds), (2) call POST /admin/executions/<id>/pause, (3) verify status changes to "paused", (4) wait 5 seconds, (5) call resume, (6) verify execution completes successfully with full output
- **Why deferred:** Requires a real `claude` CLI execution long enough to pause; cannot be mocked
- **Validates at:** Manual integration testing after phase 13 completion
- **Depends on:** claude CLI installed; a long-running prompt available for testing; SIGSTOP support on the OS (confirmed macOS/Darwin 25.3.0)
- **Target:** Execution completes successfully after pause/resume cycle; all log lines before pause and after resume are present; no duplicate or missing output lines
- **Risk if unmet:** SIGSTOP could cause the subprocess to deadlock (unlikely on macOS with stdio pipes) or the resume could cause double-logging (likely if the pipe buffer is replayed). Mitigation: test on a short execution first (< 5 second task) before testing on long-running tasks.
- **Fallback:** If SIGSTOP causes issues with pipe buffering, implement pause as a "drain and hold" mechanism instead: read and buffer remaining pipe output, then stop the process.

---

## Ablation Plan

**Purpose:** Isolate component contributions and verify architectural decisions.

### A1: Circuit breaker per-backend vs. global
- **Condition:** Remove per-backend isolation — use a single global circuit breaker instead
- **Expected impact:** A failure in one backend (e.g., claude) would block executions for all other backends (opencode, gemini). This is explicitly documented as an anti-pattern in 13-RESEARCH.md.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_circuit_breaker.py -v -k "per_backend or isolation" 2>&1`
- **Evidence:** 13-RESEARCH.md Anti-Patterns: "Global circuit breaker: Each backend type must have its own breaker."

### A2: Queue with vs. without concurrency cap (fire-and-forget baseline)
- **Condition:** Remove concurrency cap — dispatch all pending entries immediately (return to pre-phase-13 behavior)
- **Expected impact:** All N enqueued executions would start simultaneously, each spawning a subprocess. Under burst conditions this creates resource exhaustion.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_execution_queue.py -v -k "concurrency" 2>&1`
- **Evidence:** 13-RESEARCH.md Recommendation 3: "Prevents resource exhaustion from concurrent bot executions."

### A3: CAS vs. non-CAS status update for pause (race condition demonstration)
- **Condition:** Replace `update_execution_status_cas(execution_id, "paused", expected_status="running")` with a plain `update_execution_status(execution_id, "paused")` that does not check current status
- **Expected impact:** A pause request arriving after natural completion would incorrectly mark the execution as "paused" even though it has already finished
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_pause_cancel.py -v -k "cas or race" 2>&1`
- **Evidence:** 13-RESEARCH.md Pitfall 5: "Bulk Cancellation Race with Normal Completion" and existing `update_execution_status_cas()` in `db/triggers.py`.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views. Phase 13 adds backend-only services (circuit_breaker_service.py, execution_queue_service.py, webhook_validation_service.py, process_manager.py extensions) and admin API endpoints with no corresponding frontend UI changes.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Existing test suite | 940 backend tests before phase 13 | 940 passed, 0 failed | `uv run pytest -q` pre-phase |
| No circuit breaker | Current behavior: all failures handled by rate-limit retry only | N/A — no fast-fail exists | Codebase analysis (13-RESEARCH.md) |
| No concurrency limit | Current behavior: unlimited concurrent subprocess spawns | Unbounded | Codebase analysis |
| Per-trigger HMAC only | Current behavior: two separate HMAC implementations, no consolidation | 2 implementations | `grep -r "verify_hmac\|verify_github_signature"` |
| 30-day execution log TTL | Current behavior: `delete_old_execution_logs(days=30)` runs daily | 30-day hard limit | `scheduler_service.py` |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_circuit_breaker.py      (Plan 13-01: circuit breaker unit tests)
backend/tests/test_execution_queue.py      (Plan 13-02: queue unit tests)
backend/tests/test_pause_cancel.py         (Plan 13-03: pause/resume/bulk-cancel tests)
backend/tests/test_webhook_validation.py   (Plan 13-04: HMAC validation tests)
backend/tests/test_execution_persistence.py (Plan 13-04: persistence and analytics tests)
```

**How to run sanity checks only:**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest -x -q --ignore=tests/integration 2>&1 | tail -5
```

**How to run phase 13 tests only:**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_circuit_breaker.py tests/test_execution_queue.py tests/test_pause_cancel.py tests/test_webhook_validation.py tests/test_execution_persistence.py -v 2>&1
```

**How to run full evaluation (all tests):**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest -q 2>&1 | tail -10
```

**How to check for removed duplicate HMAC implementations:**
```bash
grep -r "_verify_webhook_hmac\|verify_github_signature" /Users/neo/Developer/Projects/Agented/backend/app/ --include="*.py" | grep -v "__pycache__"
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: No regression | [PASS/FAIL] | | |
| S2: CircuitBreakerService interface | [PASS/FAIL] | | |
| S3: circuit_breakers table | [PASS/FAIL] | | |
| S4: ExecutionQueueService interface | [PASS/FAIL] | | |
| S5: execution_queue table | [PASS/FAIL] | | |
| S6: Queue admin API | [PASS/FAIL] | | |
| S7: ProcessManager pause/resume | [PASS/FAIL] | | |
| S8: Pause/resume 404 on unknown | [PASS/FAIL] | | |
| S9: WebhookValidationService interface | [PASS/FAIL] | | |
| S10: Invalid HMAC returns 403 | [PASS/FAIL] | | |
| S11: Retention config in scheduler | [PASS/FAIL] | | |
| S12: paused state in ExecutionStatus | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: CB state transitions (10+ tests) | All pass | | [MET/MISSED] | |
| P2: Transient error classification | 100% accuracy | | [MET/MISSED] | |
| P3: Concurrency cap enforcement | cap=1 and cap=2 pass | | [MET/MISSED] | |
| P4: Queue FIFO ordering | Order preserved | | [MET/MISSED] | |
| P5: Queue restart persistence | Stale recovery works | | [MET/MISSED] | |
| P6: Pause/resume state machine (10+ tests) | All pass | | [MET/MISSED] | |
| P7: Bulk cancel matching executions | 100% of matches cancelled | | [MET/MISSED] | |
| P8: HMAC valid/invalid (12+ tests) | All pass | | [MET/MISSED] | |
| P9: Duplicate HMAC removed | 0 grep hits | | [MET/MISSED] | |
| P10: Workflow analytics correctness | Aggregates match seed data | | [MET/MISSED] | |
| P11: Execution retention disabled by default | No cleanup when default config | | [MET/MISSED] | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Per-backend CB isolation | Per-backend tests pass | | |
| A2: Concurrency cap vs. fire-and-forget | Cap enforcement verified | | |
| A3: CAS vs. non-CAS on pause | CAS prevents race condition | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-13-01 | Real AI backend failure simulation | PENDING | Manual integration test post-phase-13 |
| DEFER-13-02 | Transient error patterns vs. real CLI output | PENDING | 2 weeks post-deployment |
| DEFER-13-03 | Queue under 50+ concurrent webhook burst | PENDING | Manual load test post-phase-13 |
| DEFER-13-04 | Real server restart survival | PENDING | Manual integration test post-phase-13 |
| DEFER-13-05 | Real SIGSTOP/SIGCONT on live subprocess | PENDING | Manual integration test post-phase-13 |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 12 checks covering all 4 plans' primary artifacts and APIs; every check has an exact command
- Proxy metrics: Well-evidenced — all 11 proxy metrics trace to specific requirements (RES-01 through RES-09), research citations (Nygard 2018, AWS 2024, webhooks.fyi), or plan specifications (13-01-PLAN.md through 13-04-PLAN.md); correlation strength documented for each
- Deferred coverage: Comprehensive — the 5 deferred items cover all cases where subprocess-level or load-level behavior cannot be mocked: real CLI error patterns, real signal delivery, real SQLite contention under load, real restart recovery

**What this evaluation CAN tell us:**
- Whether the circuit breaker state machine is implemented correctly per Nygard (2018) specification
- Whether the execution queue correctly enforces FIFO and concurrency caps in unit context
- Whether HMAC validation is correct and properly integrated (consolidating both old implementations)
- Whether pause/resume state transitions use CAS correctly to prevent races
- Whether workflow analytics SQL queries return accurate aggregates for known data sets
- Whether zero regressions were introduced across the existing 940-test suite

**What this evaluation CANNOT tell us:**
- Whether SIGSTOP/SIGCONT works correctly on real `claude`/`opencode` subprocess output pipes (deferred to DEFER-13-05)
- Whether the transient error classifier handles all real-world CLI error message variations (deferred to DEFER-13-02)
- Whether the SQLite queue holds up under high-concurrency webhook bursts without lock contention (deferred to DEFER-13-03)
- Whether pending queue entries survive a real server kill-and-restart scenario (deferred to DEFER-13-04)
- Whether the circuit breaker correctly auto-recovers from a real AI backend outage (deferred to DEFER-13-01)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
