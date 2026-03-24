---
phase: 03-welcome-flow-tour-entry
plan: 01
subsystem: frontend/tour
tags: [xstate, tour, welcome, onboarding]
dependency_graph:
  requires: [01-02, 02-02]
  provides: [welcome-to-tour-transition, machine-driven-overlay]
  affects: [App.vue, WelcomePage.vue]
tech_stack:
  added: []
  patterns: [computed-bridge-layer, TOUR_STEP_META-lookup]
key_files:
  created: []
  modified:
    - frontend/src/App.vue
    - frontend/src/views/WelcomePage.vue
    - frontend/src/views/__tests__/WelcomePage.test.ts
    - frontend/src/views/__tests__/App.test.ts
decisions:
  - TOUR_STEP_META as flat Record mapping machine state names to display metadata
  - Computed bridge layer in App.vue maps machine state to TourOverlay StepLike interface
  - Direct navigation from WelcomePage to /settings#general (no /?tour=start intermediate)
  - totalTourSteps hardcoded to 3 (workspace, backends, verification) pending Phase 4 enrichment
metrics:
  duration: 7min
  completed: 2026-03-22
---

# Phase 03 Plan 01: Welcome Flow Tour Entry Summary

Wire App.vue and WelcomePage.vue to the XState tour machine so first-time users flow from welcome page through API key generation into the guided tour overlay on /settings#general.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Switch App.vue from useTour to useTourMachine | 5aed6cc | frontend/src/App.vue |
| 2 | Wire WelcomePage to XState machine | 048601f | frontend/src/views/WelcomePage.vue, tests |

## What Was Built

**App.vue (Task 1):**
- Replaced `useTour` import with `useTourMachine` (XState-based singleton composable)
- Created `TOUR_STEP_META` lookup mapping machine state names (workspace, backends.claude, etc.) to `{ target, title, message, skippable, route }` objects
- Created computed bridge layer: `tourActive`, `tourStep`, `tourStepNumber`, `tourSubstepLabel`
- Added `watch` on `tour.currentStep` that auto-navigates to the correct route when machine state changes
- Updated TourOverlay template bindings to use new computed values
- Updated all `?tour=start` handlers to call `startTour()` then `nextStep()` (welcome -> workspace)

**WelcomePage.vue (Task 2):**
- Imported `useTourMachine` composable
- `beginSetup()` now calls `tourMachine.startTour()` (idle -> welcome) before showing keygen
- `continueToApp()` now calls `tourMachine.nextStep()` (welcome -> workspace) and navigates directly to `/settings#general` instead of `/?tour=start`
- Added `agented-tour-machine-state` to localStorage cleanup in `onMounted`
- Updated tests to mock useTourMachine and assert new navigation target

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated App.test.ts mock from useTour to useTourMachine**
- **Found during:** Task 2 verification
- **Issue:** App.test.ts mocked the old `useTour` composable which is no longer imported by App.vue
- **Fix:** Replaced `vi.mock('../../composables/useTour')` with `vi.mock('../../composables/useTourMachine')` matching the new API surface
- **Files modified:** frontend/src/views/__tests__/App.test.ts
- **Commit:** 048601f

### Pre-existing Test Failures (Not Caused by This Plan)

3 tests in App.test.ts (`provides showToast/retrySidebarSection/refreshTriggers`) fail with "expected 'object' to be 'function'" — confirmed pre-existing by running against the previous commit.

## Decisions Made

1. **TOUR_STEP_META as flat Record:** Maps machine state string names directly to display metadata rather than nesting by parent state. Simple and readable.
2. **Computed bridge layer:** Rather than modifying TourOverlay or useTourMachine, created App.vue-local computed properties that translate machine state to the StepLike interface TourOverlay expects.
3. **Direct navigation:** WelcomePage navigates to `/settings#general` directly instead of `/?tour=start` redirect, eliminating the intermediate dashboard flash.
4. **totalTourSteps = 3:** Hardcoded for now (workspace, backends, verification). Phase 4 will refine step content and counts.

## Verification Results

- `just build`: PASS (zero vue-tsc errors)
- `npm run test:run`: 974 passed, 3 failed (pre-existing)
- Backend: No backend files changed

## Self-Check: PASSED
