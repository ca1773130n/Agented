---
phase: 13-execution-resilience-infrastructure
plan: 01
subsystem: execution-resilience
tags: [circuit-breaker, retry, transient-errors, fault-tolerance]
dependency_graph:
  requires: []
  provides: [CircuitBreakerService, circuit_breakers-table, transient-error-classification]
  affects: [OrchestrationService, ExecutionService]
tech_stack:
  added: []
  patterns: [circuit-breaker-pattern, per-backend-locks, sqlite-persistence]
key_files:
  created:
    - backend/app/services/circuit_breaker_service.py
    - backend/app/db/circuit_breakers.py
    - backend/tests/test_circuit_breaker.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/services/orchestration_service.py
    - backend/app/services/execution_service.py
decisions:
  - "Per-backend threading.Lock with _ensure_breaker internal method to avoid reentrant lock deadlocks"
  - "Non-transient patterns checked first (higher specificity) before transient patterns"
  - "CIRCUIT_BREAKER_OPEN status added to ExecutionStatus enum for explicit fast-fail signaling"
  - "Transient failure detection in _stream_pipe only records first match per execution to avoid spam"
metrics:
  duration: 14min
  completed: 2026-03-05
---

# Phase 13 Plan 01: Circuit Breaker Service & Transient Retry Summary

Per-backend circuit breaker state machine with SQLite persistence, transient error classification, and OrchestrationService integration for cascading failure prevention.

## Task Completion

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | Circuit breaker service with SQLite persistence | 574945b | Done |
| 2 | Integrate with orchestration and extend transient retry | c470103 | Done |
| - | Ruff formatting | f43799a | Done |

## What Was Built

### CircuitBreakerService (backend/app/services/circuit_breaker_service.py)

Three-state circuit breaker (Nygard 2018) per backend type (claude, opencode, gemini, codex):

- **CLOSED**: Normal operation. Failures increment `fail_count`. After `fail_max` (5) consecutive transient failures, transitions to OPEN.
- **OPEN**: Fast-fail all requests via `can_execute() -> False`. After `reset_timeout` (60s), transitions to HALF_OPEN.
- **HALF_OPEN**: Allow one trial request. Success -> CLOSED, failure -> OPEN.

Thread safety via per-backend `threading.Lock` instances with a separate `_ensure_breaker()` internal method to avoid reentrant lock deadlocks.

### Transient Error Classification

`is_transient_error()` classifies errors by three signals:
1. **Exception type**: `subprocess.TimeoutExpired` = transient; `FileNotFoundError` = non-transient
2. **Stderr patterns**: connection refused/timeout/502/503/overloaded = transient; auth errors/command not found = non-transient
3. **Exit codes**: 127 (command not found), 126 (permission denied) = non-transient

### SQLite Persistence (backend/app/db/circuit_breakers.py)

- `circuit_breakers` table with `backend_type` PK, state, fail/success counts, last_failure_time
- Migration v73 for existing databases
- On server restart: stale OPEN breakers with elapsed timeout auto-reset to CLOSED

### OrchestrationService Integration

- Checks `CircuitBreakerService.can_execute()` before dispatching to each backend in fallback chain
- Skips backends with OPEN breakers, tries next chain entry
- Records `record_success()` / `record_failure()` after execution
- New `CIRCUIT_BREAKER_OPEN` status when all backends are circuit-broken

### ExecutionService Extension

- `_stream_pipe()` now detects transient failure patterns in stderr (beyond rate limits)
- `was_transient_failure()` method for post-execution transient error checking
- `_transient_failure_detected` dict tracks first transient error per execution

## Experiment Results

### Parameters

| Parameter | Value |
|-----------|-------|
| fail_max | 5 |
| reset_timeout | 60s |
| success_threshold | 1 |
| transient_patterns | 13 regex patterns |
| non_transient_patterns | 10 regex patterns |

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| circuit_breaker_transition_accuracy | N/A (no breaker) | 100% | 100% (9/9 transition tests pass) | PASS |
| transient_error_classification_accuracy | N/A | 0 false positives | 0 false positives (22 pattern tests) | PASS |
| state_persistence_round_trip | N/A | Survives restart | Verified (5 persistence tests) | PASS |

### Test Coverage

48 tests covering:
- 9 state transition scenarios (CLOSED->OPEN, OPEN->HALF_OPEN, HALF_OPEN->CLOSED, etc.)
- 12 transient error patterns (parametrized)
- 10 non-transient error patterns (parametrized)
- 5 SQLite persistence scenarios including restart recovery
- 2 concurrency tests (multi-threaded failures, mixed operations)
- 3 admin visibility tests

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed reentrant lock deadlock in CircuitBreakerService**
- **Found during:** Task 1
- **Issue:** `record_failure()` acquired the per-backend lock then called `get_breaker()` which also tried to acquire the same lock, causing deadlock
- **Fix:** Introduced `_ensure_breaker()` internal method (lock-free) called by all public methods that already hold the lock
- **Files modified:** backend/app/services/circuit_breaker_service.py
- **Commit:** 574945b

## Self-Check: PASSED

All 7 key files exist. All 3 commits verified. 48/48 tests pass. 1263/1264 existing tests pass (1 pre-existing failure in test_post_execution_hooks unrelated to this plan).
