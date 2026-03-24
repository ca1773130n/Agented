---
phase: 01-backend-state-machine-foundation
plan: 02
subsystem: ui, state-management
tags: [xstate, vue-composable, persistence, localStorage, z-index, onboarding]

requires:
  - "XState v5 tour machine definition (01-01)"
  - "/health/instance-id endpoint (01-01)"
provides:
  - "useTourMachine composable with persistence, instance_id validation, and guard checks"
  - "z-index CSS custom properties for tour overlay layering"
affects: [02-welcome-page, 03-workspace-step, 04-backend-steps]

tech-stack:
  added: []
  patterns: ["Singleton XState actor with Vue shallowRef reactivity", "Async guard-check-then-advance for sync XState guards", "localStorage persistence with schema version migration"]

key-files:
  created:
    - frontend/src/composables/useTourMachine.ts
  modified:
    - frontend/src/App.vue

key-decisions:
  - "Singleton actor pattern — shared across all components, survives route changes"
  - "Schema version 1 with discard-on-mismatch for future migration safety"
  - "Async guard checks run in composable, not in machine — keeps machine definition pure"
  - "Toast container z-index conflict noted (hardcoded 10000) — deferred to Phase 7"

duration: 4min
completed: 2026-03-21
---

# Phase 01 Plan 02: Vue Composable with Persistence and Z-Index Scale Summary

**Singleton XState actor composable persisting tour state to localStorage with instance_id staleness detection and five-level z-index CSS scale for tour overlay layering**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-21T11:11:02Z
- **Completed:** 2026-03-21T11:14:50Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments

- Created `useTourMachine` composable wrapping XState v5 actor with localStorage persistence on every state transition
- Implemented instance_id validation (fetches `/health/instance-id`, clears state on mismatch)
- Schema version validation (discards snapshots with mismatched version)
- Async guard-check-then-advance pattern: queries `/api/settings` and `/admin/backends` to auto-skip completed steps
- Exposed full reactive API: state, context, isActive, currentStep, canGoBack, canGoForward, event senders, clearTourState, checkAndAutoAdvance
- Added five z-index CSS custom properties to App.vue `:root` (--z-tour-overlay through --z-tour-progress)

## Task Commits

1. **Task 1: useTourMachine composable** - `1a08b87` (feat)
2. **Task 2: z-index CSS custom properties** - `689406b` (feat)

## Files Created/Modified

- `frontend/src/composables/useTourMachine.ts` - New composable with persistence, validation, and reactive state
- `frontend/src/App.vue` - Added five --z-tour-* CSS custom properties to :root

## Decisions Made

- Used singleton actor pattern (single `sharedActor` instance) to avoid multiple XState actors competing for the same localStorage key and to persist state across Vue Router navigation
- Schema version starts at 1 with discard-on-mismatch strategy — simpler than migration logic, acceptable because tour restart is not disruptive
- Guard checks implemented entirely in composable via `checkAndAutoAdvance()` rather than modifying the machine definition with `invoke` blocks — keeps tourMachine.ts a pure state chart
- Toast container has hardcoded `z-index: 10000` which equals `--z-tour-overlay` — noted as Phase 7 concern per plan instructions (do not change existing values)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pre-existing test failures in App.test.ts (14 failures) and WelcomePage.test.ts (1 failure) remain from prior branch changes — confirmed pre-existing in 01-01 SUMMARY.

## Self-Check: PASSED

- [x] `frontend/src/composables/useTourMachine.ts` exists
- [x] `frontend/src/App.vue` contains --z-tour-overlay, --z-tour-spotlight, --z-tour-tooltip, --z-tour-controls, --z-tour-progress
- [x] Commits 1a08b87 and 689406b exist in git log
- [x] `just build` passes
- [x] TypeScript compiles without errors

---
*Phase: 01-backend-state-machine-foundation*
*Completed: 2026-03-21*
