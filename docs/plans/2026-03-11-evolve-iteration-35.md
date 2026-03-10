# Evolve Iteration 35: Execution Service Refactoring + Test Fixes

**Date:** 2026-03-11
**Status:** Complete

---

## Summary

Evolve iteration 35 implemented 3 remaining work items from the product-ideation backlog (27 of 30 were already done in prior iterations). The primary change was refactoring `execution_service.py` into three focused modules, plus adding a conditional trigger rules feature and frontend improvements.

The refactoring broke 18 backend tests and 1 frontend build due to stale `@patch` targets and an unused import. This document covers both the evolve changes and the manual fixes applied to restore a green build.

---

## Changes Made by Evolve

### 1. Execution Service Refactoring

Extracted three new modules from `backend/app/services/execution_service.py`:

| New Module | Responsibility | Key Functions/Classes |
|---|---|---|
| `execution_retry.py` | Retry scheduling, persistence, restoration | `ExecutionRetryManager` (class with `schedule_retry`, `restore_pending_retries`, `get_pending_retries`) |
| `execution_runner.py` | Subprocess execution, streaming, budget monitoring | `stream_pipe()`, `budget_monitor()`, `clone_repos()`, `fetch_pr_diff()`, `build_subprocess_env()` |
| `trigger_dispatcher.py` | Webhook/GitHub event dispatching, payload matching | `dispatch_webhook_event()`, `dispatch_github_event()`, `dispatch_pr_comment_commands()`, `match_payload()` |

`execution_service.py` remains the public facade — all existing `ExecutionService.*` call sites continue to work via thin delegation methods and backward-compat aliases.

### 2. Conditional Trigger Rules Feature

- New backend: `backend/app/db/trigger_conditions.py`, `backend/app/routes/trigger_conditions.py`
- New frontend: `frontend/src/views/ConditionalTriggerRulesPage.vue`, `frontend/src/services/api/trigger-conditions.ts`

### 3. Frontend Improvements

- Various composable improvements and new test files

---

## Test/Build Fixes (Manual)

### Problem

The evolve refactoring moved functions to new modules but did not update `@patch()` targets in tests. Python's `unittest.mock.patch` must target the module where a name is **looked up at runtime**, not where it was originally defined.

### Frontend Fix

**File:** `frontend/src/views/ConditionalTriggerRulesPage.vue`
- Removed unused `ConditionItem` type import causing `TS6133` build error

### Backend Test Fixes

Four test files required `@patch` path updates:

#### `tests/test_execution_service.py`
| Old Path | New Path |
|---|---|
| `app.services.execution_service.get_webhook_triggers` | `app.services.trigger_dispatcher.get_webhook_triggers` |
| `app.services.execution_service.check_and_insert_dedup_key` | `app.services.trigger_dispatcher.check_and_insert_dedup_key` |
| `app.services.execution_service.get_triggers_by_trigger_source` | `app.services.trigger_dispatcher.get_triggers_by_trigger_source` |

#### `tests/test_rate_limit_service.py`
| Old Path | New Path |
|---|---|
| `app.services.execution_service.delete_pending_retry` | `app.services.execution_retry.delete_pending_retry` |
| `app.services.execution_service.upsert_pending_retry` | `app.services.execution_retry.upsert_pending_retry` |
| `app.services.execution_service.get_all_pending_retries` | `app.services.execution_retry.get_all_pending_retries` |
| `app.services.execution_service.AuditLogService` | `app.services.audit_log_service.AuditLogService` |
| `app.services.execution_service.ExecutionLogService` | `app.services.execution_log_service.ExecutionLogService` |
| `app.services.execution_service.random.uniform` | `app.services.execution_retry.random.uniform` |

#### `tests/test_execution_error_paths.py`
| Old Path | New Path |
|---|---|
| `app.services.execution_service.RateLimitService.check_stderr_line` | `app.services.execution_runner.RateLimitService.check_stderr_line` |
| `app.services.execution_service.upsert_pending_retry` | `app.services.execution_retry.upsert_pending_retry` |
| `app.services.execution_service.delete_pending_retry` | `app.services.execution_retry.delete_pending_retry` |
| `app.services.execution_service.get_all_pending_retries` | `app.services.execution_retry.get_all_pending_retries` |
| `app.services.execution_service.get_webhook_triggers` | `app.services.trigger_dispatcher.get_webhook_triggers` |
| `app.services.execution_service.BudgetService` (in budget_monitor tests) | `app.services.execution_runner.BudgetService` |
| `app.services.execution_service.ExecutionLogService` (in stream_pipe/budget tests) | `app.services.execution_runner.ExecutionLogService` |
| `app.services.execution_service.AuditLogService` (in retry scheduling tests) | `app.services.audit_log_service.AuditLogService` |
| `app.services.execution_service.ExecutionLogService` (in retry scheduling tests) | `app.services.execution_log_service.ExecutionLogService` |

#### `tests/test_concurrent_operations.py`
| Old Path | New Path |
|---|---|
| `app.services.execution_service.ExecutionLogService` (in stream_pipe test) | `app.services.execution_runner.ExecutionLogService` |
| `app.services.execution_service.AuditLogService` (in retry test) | `app.services.audit_log_service.AuditLogService` |
| `app.services.execution_service.upsert_pending_retry` | `app.services.execution_retry.upsert_pending_retry` |

### Key Insight: Lazy Imports Require Special Handling

`execution_retry.py` uses **lazy imports** for `AuditLogService` and `ExecutionLogService` (imported inside `schedule_retry()` method body). This means:

- Patching at `app.services.execution_retry.AuditLogService` **fails** — the module-level attribute doesn't exist until the method runs
- Must patch at the **definition module**: `app.services.audit_log_service.AuditLogService`

---

## Verification

```
Backend:  2575 passed (2 pre-existing flaky failures in test_secret_vault.py unrelated to these changes)
Frontend: Build successful, all type checks pass
```
