---
phase: 01-backend-state-machine-foundation
plan: 01
subsystem: database, ui
tags: [sqlite, xstate, xstate-v5, onboarding, state-machine, health-endpoint]

requires: []
provides:
  - "app_meta table with instance_id for DB-reset detection"
  - "/health/instance-id unauthenticated endpoint"
  - "XState v5 tour state machine with complete state/transition definitions"
  - "Guard and action stubs for future implementation"
affects: [01-02, 02-welcome-page, 03-workspace-step, 04-backend-steps]

tech-stack:
  added: [xstate@5.28.0, "@xstate/vue@3.1.4"]
  patterns: ["XState v5 setup() API for type-safe machine definitions", "SQLite hex(randomblob()) UUID generation"]

key-files:
  created:
    - frontend/src/machines/tourMachine.ts
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/routes/health.py
    - frontend/package.json
    - frontend/package-lock.json

key-decisions:
  - "Used SQLite hex(randomblob()) for UUID generation instead of Python uuid module for portability"
  - "Used XState v5 setup() API with string-referenced guards/actions for type safety"
  - "Made backends a hierarchical state with claude/codex/gemini/opencode substeps"
  - "NEXT on last backend substep (opencode) handled by parent backends NEXT transition to verification"

patterns-established:
  - "app_meta key-value table for application metadata"
  - "XState v5 setup({types, guards, actions}).createMachine({}) pattern"

duration: 21min
completed: 2026-03-21
---

# Phase 01 Plan 01: Backend Instance ID + XState Tour Machine Summary

**Backend app_meta table with /health/instance-id endpoint and XState v5 state machine defining complete onboarding tour flow with hierarchical backend substeps**

## Performance

- **Duration:** 21 min
- **Started:** 2026-03-21T10:46:41Z
- **Completed:** 2026-03-21T11:08:29Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added `app_meta` table to both fresh schema and migration 96, with UUID instance_id generated via pure SQLite functions
- Created `/health/instance-id` endpoint accessible without authentication for frontend tour boot
- Defined complete XState v5 tour state machine with 10 states (including 4 hierarchical backend substeps), 6 event types, 4 guard stubs, and 3 action stubs

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend app_meta table and /health/instance-id endpoint** - `dc0b385` (feat)
2. **Task 2: Install XState v5 and define tour state machine** - `6d1f1fb` (feat)

## Files Created/Modified

- `backend/app/db/schema.py` - Added app_meta table to fresh schema with instance_id UUID
- `backend/app/db/migrations.py` - Added migration 96 (_migrate_96_app_meta) for existing databases
- `backend/app/routes/health.py` - Added /health/instance-id GET endpoint (no auth)
- `frontend/src/machines/tourMachine.ts` - XState v5 tour state machine definition
- `frontend/package.json` - Added xstate@5.28.0 and @xstate/vue@3.1.4 dependencies
- `frontend/package-lock.json` - Lockfile updated

## Decisions Made

- Used SQLite `hex(randomblob())` pattern for UUID generation in both schema and migration, avoiding Python uuid module dependency at the SQL level
- Implemented XState v5 `setup()` API with string-referenced guards/actions (not inline functions) for proper type safety and testability
- Made `backends` a compound state with `claude` as initial child, allowing independent navigation within backend substeps
- `NEXT` on the last substep (`opencode`) is handled by the parent `backends` state's NEXT transition, keeping navigation logic clean

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pre-existing test failures in `App.test.ts` (14 failures) and `WelcomePage.test.ts` (1 failure) were confirmed as pre-existing on the branch before any changes. These are due to prior uncommitted modifications to `App.vue`.
- Pre-existing backend test failure in `test_route_sketch_requires_classification` also confirmed as pre-existing (unrelated to schema/migration changes).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 02 (tests + persistence) can proceed. The machine definition is complete with all states, events, guards, and actions defined. Plan 02 will:
- Add XState actor creation and @xstate/vue integration
- Implement localStorage persistence with instanceId staleness detection
- Add comprehensive state machine transition tests

---
*Phase: 01-backend-state-machine-foundation*
*Completed: 2026-03-21*
