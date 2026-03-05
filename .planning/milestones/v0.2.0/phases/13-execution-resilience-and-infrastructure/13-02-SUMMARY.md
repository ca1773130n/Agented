---
phase: 13-execution-resilience-infrastructure
plan: 02
subsystem: execution-queue
tags: [execution-queue, concurrency-control, sqlite-backed, dispatcher, admin-api]
dependency_graph:
  requires: [CircuitBreakerService, circuit_breakers-table]
  provides: [ExecutionQueueService, execution_queue-table, queue-admin-api]
  affects: [ExecutionService, OrchestrationService, TeamExecutionService]
tech_stack:
  added: []
  patterns: [sqlite-backed-queue, background-dispatcher, per-trigger-concurrency, cas-status-update]
key_files:
  created:
    - backend/app/db/execution_queue.py
    - backend/app/services/execution_queue_service.py
    - backend/tests/test_execution_queue.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/services/execution_service.py
    - backend/app/__init__.py
    - backend/app/routes/executions.py
    - backend/tests/test_trigger_team_integration.py
decisions:
  - "Queue dispatcher polls every 1 second with threading.Event.wait for clean shutdown"
  - "Per-trigger queue depth capped at 100 with QueueFullError exception"
  - "CAS (compare-and-swap) status updates prevent dispatch races between threads"
  - "Stale dispatching entries reset to pending on server restart for crash recovery"
  - "Team-mode and direct-mode triggers both route through the queue uniformly"
metrics:
  duration: 13min
  completed: 2026-03-05
---

# Phase 13 Plan 02: Execution Queue Service Summary

SQLite-backed execution queue with per-trigger concurrency caps, background dispatcher thread, and admin queue visibility API -- replacing fire-and-forget thread dispatch for durable execution management.

## Task Completion

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | Create execution queue DB module and queue service with dispatcher | 2191c8a | Done |
| 2 | Integrate queue with dispatch flow and add admin API endpoints | 2a51800 | Done |

## What Was Built

### Execution Queue DB Module (backend/app/db/execution_queue.py)

SQLite CRUD operations for the `execution_queue` table:
- `enqueue_execution()` -- insert pending entry with qe- prefixed ID
- `get_pending_entries()` -- FIFO ordered (priority DESC, created_at ASC)
- `update_entry_status()` -- CAS-based status transitions
- `count_active_for_trigger()` -- dispatching count per trigger
- `get_queue_depth()` -- pending count (global or per-trigger)
- `get_queue_summary()` -- per-trigger pending/dispatching counts
- `cancel_pending_entries()` -- bulk cancel with optional trigger filter
- `cleanup_completed_entries()` -- age-based cleanup for old entries
- `reset_stale_dispatching()` -- crash recovery for stuck entries

### ExecutionQueueService (backend/app/services/execution_queue_service.py)

Background dispatcher with concurrency control:
- **Dispatcher thread**: polls every 1 second, dispatches up to 10 entries per batch
- **Per-trigger concurrency**: configurable caps (default 1), excess entries wait in queue
- **Circuit breaker integration**: checks `CircuitBreakerService.can_execute()` before dispatch
- **Queue depth cap**: 100 pending entries per trigger, raises `QueueFullError` (HTTP 429)
- **Stale recovery**: on startup, resets entries stuck in "dispatching" back to "pending"
- **Execution delegation**: dispatches to OrchestrationService or TeamExecutionService based on trigger config

### Dispatch Flow Integration

Replaced direct `threading.Thread` spawns in `ExecutionService`:
- `dispatch_webhook_event()` now calls `ExecutionQueueService.enqueue()` instead of spawning threads
- `dispatch_github_event()` now calls `ExecutionQueueService.enqueue()` instead of spawning threads
- Dedup and HMAC checks still run BEFORE enqueue (at intake, not dispatch)
- Team dispatch (via team_id) handled by the queue dispatcher, not at enqueue time

### Admin API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/executions/queue` | GET | Per-trigger pending/dispatching counts |
| `/admin/executions/queue/<trigger_id>` | GET | Queue depth for specific trigger |
| `/admin/executions/queue/<trigger_id>` | DELETE | Cancel all pending entries for trigger |
| `/admin/executions/retries` | GET | Pending rate-limit retries from DB |

### Schema & Migration

- `execution_queue` table with indexes on status, trigger_id+status, priority+created_at
- Migration v74 for existing databases

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated team integration tests for queue-based dispatch**
- **Found during:** Task 2
- **Issue:** Three existing tests in test_trigger_team_integration.py asserted direct calls to TeamExecutionService.execute_team and OrchestrationService.execute_with_fallback, which no longer happen because dispatch routes through the queue
- **Fix:** Updated tests to assert ExecutionQueueService.enqueue is called instead
- **Files modified:** backend/tests/test_trigger_team_integration.py
- **Commit:** 2a51800

## Test Coverage

23 tests covering:
- 9 DB CRUD operations (enqueue, FIFO, priority, CAS, active count, depth, summary, cancel, stale recovery)
- 8 service-level tests (enqueue, max depth rejection, concurrency cap, dispatcher, circuit breaker, FIFO dispatch, restart recovery, cap config)
- 5 API endpoint tests (queue status, trigger depth, cancel, retries empty, retries populated)
- 1 pre-existing test suite regression check (all pass)

## Self-Check: PASSED
