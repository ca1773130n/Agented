---
phase: 15-code-consistency-standards
plan: 01
subsystem: backend-services
tags: [config-constants, id-generation, logging, code-quality]
dependency_graph:
  requires: []
  provides:
    - centralized-config-constants
    - id-generation-factory
    - service-logger-declarations
  affects:
    - backend/app/config.py
    - backend/app/db/ids.py
    - backend/app/services/*.py
tech_stack:
  added: []
  patterns:
    - "generate_id(prefix, length) factory pattern for all entity IDs"
    - "app.config as single source of truth for shared numeric constants"
    - "logging.getLogger(__name__) as module-level logger in all service files"
key_files:
  created: []
  modified:
    - backend/app/config.py
    - backend/app/db/ids.py
    - backend/app/db/viewer_comments.py
    - backend/app/routes/super_agents.py
    - backend/app/services/execution_service.py
    - backend/app/services/execution_log_service.py
    - backend/app/services/budget_service.py
    - backend/app/services/github_service.py
    - backend/app/services/super_agent_session_service.py
    - backend/app/services/team_execution_service.py
    - backend/app/services/harness_loader_service.py
    - backend/app/services/audit_service.py
    - "backend/app/services/*.py (32 files for logger declarations)"
decisions:
  - "Config constants grouped by domain (execution, SSE, process, budget, GitHub)"
  - "generate_id() factory uses secrets.choice() matching existing ids.py pattern"
  - "Class-level constants in services kept as aliases to config imports for backward compat"
  - "import logging placed among stdlib imports; logger after all imports"
metrics:
  duration: "26min"
  completed: "2026-03-06"
---

# Phase 15 Plan 01: Backend Foundation for Code Consistency

Centralized magic numbers into config.py named constants, consolidated ID generation into a generate_id() factory, and replaced all print() calls in services with structured logger usage.

## Task Summary

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Centralize config constants and consolidate ID factory | 3febe39 | Extended config.py with 15 named constants; added generate_id() factory to ids.py; fixed 3 rogue random.choices() |
| 2 | Replace print() with structured logger across all services | e99ee1b | Replaced 7 print() calls with logger.error(); added logger declarations to 32 service files |

## Changes Made

### Task 1: Config Constants + ID Factory

**Part A (CON-07) -- Config constants:** Extended `backend/app/config.py` with named constants grouped by domain:
- Execution: EXECUTION_TIMEOUT_DEFAULT/MIN/MAX, MAX_RETRY_ATTEMPTS, MAX_RETRY_DELAY, WEBHOOK_DEDUP_WINDOW
- SSE: SSE_REPLAY_LIMIT, SSE_KEEPALIVE_TIMEOUT, STALE_EXECUTION_THRESHOLD
- Process management: THREAD_JOIN_TIMEOUT, SIGTERM_GRACE_SECONDS, OUTPUT_RING_BUFFER_SIZE
- Budget: DEFAULT_5H_TOKEN_LIMIT, DEFAULT_WEEKLY_TOKEN_LIMIT
- GitHub: CLONE_TIMEOUT, GIT_OP_TIMEOUT

Updated 6 service files to import constants from config.py instead of defining local copies.

**Part B (CON-04) -- ID factory:** Added `generate_id(prefix, length)` factory function to `backend/app/db/ids.py` using `secrets.choice()`. Refactored all 26+ entity generator functions to one-line wrappers. Fixed 3 rogue `random.choices()` calls:
- `backend/app/routes/super_agents.py` -- replaced with `generate_message_id()`
- `backend/app/services/team_execution_service.py` -- replaced with `generate_id("team-exec-", 8)`
- `backend/app/db/viewer_comments.py` -- replaced with `generate_comment_id()` from ids.py

### Task 2: Structured Logger Replacement

**CON-01 -- print() replacement:** Replaced 7 print() calls with `logger.error()` using `%s` format strings:
- 6 in `harness_loader_service.py` (import failure logging for agents, skills, hooks, commands, teams)
- 1 in `audit_service.py` (audit index rebuild error)

Added `import logging` and `logger = logging.getLogger(__name__)` to all 32 service files that were missing logger declarations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added generate_comment_id() to ids.py and fixed viewer_comments.py**
- **Found during:** Task 1
- **Issue:** viewer_comments.py had a rogue `random.choices()` call not listed in the plan (only super_agents.py and team_execution_service.py were listed)
- **Fix:** Added COMMENT_ID_PREFIX/LENGTH constants and generate_comment_id() to ids.py, updated viewer_comments.py to use it
- **Files modified:** backend/app/db/ids.py, backend/app/db/viewer_comments.py
- **Commit:** 3febe39

## Verification Results

- Zero `print()` calls in `backend/app/services/` (grep verified)
- Zero `random.choices()` calls outside `ids.py` (grep verified)
- `generate_id()` factory function present in ids.py (grep verified)
- Config imports work: `from app.config import EXECUTION_TIMEOUT_DEFAULT, SSE_REPLAY_LIMIT, MAX_RETRY_ATTEMPTS` returns OK
- `generate_id('test-', 6)` produces valid IDs
- Backend tests: 1447 passed, 1 pre-existing failure (test_import_error_handled_gracefully -- unrelated to changes)
- Ruff lint/format: all modified files pass

## Self-Check: PASSED

- [x] backend/app/config.py exists with named constants
- [x] backend/app/db/ids.py has generate_id() factory
- [x] Commit 3febe39 exists
- [x] Commit e99ee1b exists
- [x] All 32 service files have logger declarations
- [x] Zero print() calls in services
- [x] Zero random.choices() outside ids.py
