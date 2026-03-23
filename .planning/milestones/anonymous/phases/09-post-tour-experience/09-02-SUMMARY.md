---
phase: 09-post-tour-experience
plan: 02
subsystem: ui
tags: [vue, xstate, tour, onboarding, product, project, team, restart]

requires:
  - phase: 09-post-tour-experience/01
    provides: TourCompletionScreen.vue, useTourChecklist.ts, sidebar Setup section

provides:
  - Three new tour states (create_product, create_project, create_team) extending the onboarding flow
  - Restart Setup Guide button in General settings tab
  - Updated TourCompletionScreen and useTourChecklist with 10 total step definitions

affects: [10-integration-testing]

tech-stack:
  added: []
  patterns:
    - "Extended XState machine with optional post-setup creation steps"
    - "Restart tour via restartTour + startTour + nextStep sequence"

key-files:
  created: []
  modified:
    - frontend/src/machines/tourMachine.ts
    - frontend/src/App.vue
    - frontend/src/components/tour/TourCompletionScreen.vue
    - frontend/src/composables/useTourChecklist.ts
    - frontend/src/components/settings/GeneralSettings.vue
    - frontend/src/machines/__tests__/tourMachine.test.ts
    - frontend/src/components/tour/__tests__/TourCompletionScreen.test.ts
    - frontend/src/composables/__tests__/useTourMachine.test.ts

key-decisions:
  - "Restart button placed in GeneralSettings.vue (not SettingsPage.vue) since General tab content lives there"
  - "restartTour() + startTour() + nextStep() sequence skips welcome page for returning users"
  - "create_project route set to /products (not dynamic product URL) with graceful fallback from Phase 7"

patterns-established:
  - "Tour restart pattern: clear localStorage, reset to idle, start, skip welcome"

duration: 18min
completed: 2026-03-23
---

# Phase 9 Plan 02: Product/Project/Team Tour Steps + Restart Capability Summary

**Extended onboarding tour with 3 optional creation steps (product, project, team) and a restart button in Settings for re-running the setup guide**

## Performance

- **Duration:** 18 min
- **Started:** 2026-03-23T05:28:26Z
- **Completed:** 2026-03-23T05:46:37Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Tour machine extended from 7 states to 10 with create_product, create_project, create_team chaining verification -> complete
- App.vue TOUR_STEP_META has 10 entries, totalTourSteps updated to 7, STEP_NUMBER_MAP covers all states
- Restart Setup Guide button in GeneralSettings.vue calls restartTour + startTour + nextStep
- All tour test suites updated for new state paths (tourMachine, TourCompletionScreen, useTourMachine)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend tourMachine with product/project/team states** - `a13379f` (feat)
2. **Task 2: Restart Setup Guide in SettingsPage + test updates** - `d112b20` (feat)

## Files Created/Modified

- `frontend/src/machines/tourMachine.ts` -- Added create_product, create_project, create_team states; verification now targets create_product
- `frontend/src/App.vue` -- 3 new TOUR_STEP_META entries, STEP_NUMBER_MAP entries 5-7, totalTourSteps=7
- `frontend/src/components/tour/TourCompletionScreen.vue` -- 3 new STEP_META entries for completion screen
- `frontend/src/composables/useTourChecklist.ts` -- 3 new CHECKLIST_DEFS for sidebar checklist
- `frontend/src/components/settings/GeneralSettings.vue` -- Setup Guide card with Restart button and handleRestartTour function
- `frontend/src/machines/__tests__/tourMachine.test.ts` -- Updated navigation sequences, added tests for new states
- `frontend/src/components/tour/__tests__/TourCompletionScreen.test.ts` -- Updated allSteps array for 10 items
- `frontend/src/composables/__tests__/useTourMachine.test.ts` -- Updated complete state navigation sequence

## Decisions Made

- Restart button placed in GeneralSettings.vue rather than SettingsPage.vue because the General tab content is rendered by GeneralSettings component
- restartTour() + startTour() + nextStep() sequence used to skip the welcome page for returning users who already have API keys
- create_project route points to /products (not a dynamic product URL) since the user needs to select a product first; Phase 7 element-not-found handling provides graceful fallback

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test suites for new machine states**
- **Found during:** Task 2 (test verification)
- **Issue:** 8 tourMachine tests, 1 TourCompletionScreen test, and 1 useTourMachine test expected old state paths (verification -> complete)
- **Fix:** Updated event sequences with 3 additional NEXT/SKIP steps, added new state transition tests
- **Files modified:** tourMachine.test.ts, TourCompletionScreen.test.ts, useTourMachine.test.ts
- **Committed in:** `d112b20`

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** Expected -- test updates are necessary when extending the state machine

**Pre-existing failures:** 3 tests in App.test.ts fail (provide/inject for showToast, retrySidebarSection, refreshTriggers) -- confirmed pre-existing, unrelated to this plan's changes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 10 tour states are wired and functional
- Phase 10 integration tests can now cover the full 7-step tour flow including product/project/team
- Restart capability is testable via Settings > General > Restart Setup Guide
- Visual verification of new steps deferred to Phase 10 E2E tests

## Self-Check: PASSED

---
*Phase: 09-post-tour-experience*
*Completed: 2026-03-23*
