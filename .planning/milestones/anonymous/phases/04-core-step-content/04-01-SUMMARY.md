---
phase: 04-core-step-content
plan: 01
subsystem: ui
tags: [xstate, tour, vue, state-machine]

requires:
  - phase: 01-backend-state-machine-foundation
    provides: XState tour machine with backends hierarchical state
  - phase: 03-welcome-flow-tour-entry
    provides: TOUR_STEP_META, STEP_NUMBER_MAP, route watcher in App.vue
provides:
  - monitoring state in tour machine between backends and verification
  - complete TOUR_STEP_META with 7 entries for all machine states
  - corrected target selectors for verification, OpenCode, and monitoring
  - monitoring guard check and auto-advance logic
affects: [05-substep-navigation, 06-accessibility, 10-integration-testing]

tech-stack:
  added: []
  patterns: [monitoring guard check via /api/monitoring/config]

key-files:
  created: []
  modified:
    - frontend/src/machines/tourMachine.ts
    - frontend/src/App.vue
    - frontend/src/composables/useTourMachine.ts
    - frontend/src/views/BackendDetailPage.vue
    - frontend/src/machines/__tests__/tourMachine.test.ts
    - frontend/src/composables/__tests__/useTourMachine.test.ts

key-decisions:
  - "Monitoring step targets token-monitoring card on /settings#general"
  - "Verification step targets harness-plugins card on /settings#harness (not harness-status on /plugins)"
  - "OpenCode substep targets opencode-info note (not add-account-btn which is hidden via v-if)"
  - "Monitoring guard checks /api/monitoring/config endpoint for enabled field"

patterns-established:
  - "Hash-based routing: routeHash field in TOUR_STEP_META for settings tabs"

duration: 11min
completed: 2026-03-22
---

# Phase 04 Plan 01: Core Step Content Summary

**Tour machine expanded to 4 core steps with monitoring state, corrected selectors for verification/OpenCode, and guard-based auto-advance for monitoring configuration.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-22T04:15:15Z
- **Completed:** 2026-03-22T04:26:07Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added monitoring state to tour machine between backends and verification, completing the 4-step core flow (workspace, backends, monitoring, verification)
- Fixed verification step to target harness-plugins on /settings#harness instead of harness-status on /plugins
- Fixed OpenCode substep to target the visible opencode-info note instead of the hidden add-account-btn
- Added monitoring configuration guard check and auto-advance in useTourMachine
- Updated all test files to account for new monitoring state (977 tests passing, 3 pre-existing failures in App.test.ts)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add monitoring state to tourMachine** - `28793c6` (feat)
2. **Task 2: Update TOUR_STEP_META, step numbering, selectors, and guard checks** - `536d208` (feat)

## Files Created/Modified

- `frontend/src/machines/tourMachine.ts` - Added monitoring state, isMonitoringConfigured guard, updated backends/verification transitions
- `frontend/src/App.vue` - Added monitoring to TOUR_STEP_META, fixed verification/OpenCode entries, updated STEP_NUMBER_MAP and totalTourSteps to 4
- `frontend/src/composables/useTourMachine.ts` - Added monitoringConfigured guard check via /api/monitoring/config, monitoring auto-advance
- `frontend/src/views/BackendDetailPage.vue` - Added data-tour="opencode-info" to opencode note div
- `frontend/src/machines/__tests__/tourMachine.test.ts` - Updated all transition expectations for monitoring state, added monitoring-specific tests
- `frontend/src/composables/__tests__/useTourMachine.test.ts` - Updated complete state navigation sequence for monitoring

## Decisions Made

- Monitoring step targets the token-monitoring card on /settings#general (GeneralSettings.vue already has this data-tour attribute)
- Verification step changed from /plugins to /settings#harness, targeting harness-plugins card (HarnessSettings.vue already has this attribute)
- OpenCode substep targets opencode-info note instead of add-account-btn which is hidden with `v-if="!isOpenCode"`
- Guard checks /api/monitoring/config (existing endpoint) for `enabled` field to determine if monitoring is configured

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing tests for monitoring state**
- **Found during:** Task 2
- **Issue:** tourMachine.test.ts and useTourMachine.test.ts had hardcoded navigation sequences expecting backends -> verification without monitoring
- **Fix:** Updated toVerification sequence to go through toMonitoring, updated all assertions for opencode NEXT/SKIP -> monitoring, verification BACK -> monitoring, skip-all path with extra monitoring SKIP, and completedSteps accumulation
- **Files modified:** frontend/src/machines/__tests__/tourMachine.test.ts, frontend/src/composables/__tests__/useTourMachine.test.ts
- **Verification:** 977 tests passing (3 pre-existing App.test.ts failures unrelated to tour)
- **Committed in:** 536d208 (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test bug fix)
**Impact on plan:** None - test updates were necessary consequence of machine state changes

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tour machine now has all 4 core steps with correct transitions
- All TOUR_STEP_META entries have valid routes, hashes, and target selectors
- All data-tour attributes verified to exist on their target DOM elements
- Ready for Plan 04-02 (route watcher and additional content work if applicable)

## Self-Check: PASSED

- frontend/src/machines/tourMachine.ts: FOUND
- frontend/src/App.vue: FOUND
- frontend/src/composables/useTourMachine.ts: FOUND
- frontend/src/views/BackendDetailPage.vue: FOUND
- Commit 28793c6: FOUND
- Commit 536d208: FOUND
- All data-tour selectors verified present in target files

---
*Phase: 04-core-step-content*
*Completed: 2026-03-22*
