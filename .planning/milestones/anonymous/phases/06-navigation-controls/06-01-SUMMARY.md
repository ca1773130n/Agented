---
phase: 06-navigation-controls
plan: 01
subsystem: ui
tags: [vue, tour, progress-bar, skip-confirmation]

requires:
  - phase: 05-form-field-guidance
    provides: TourProgressBar with step counter, substep label, skip/next buttons
provides:
  - Step title display in progress bar left section
  - Skip confirmation dialog for significant tour steps
  - isSignificantStep helper for conditional confirmation
affects: [06-02, 10-integration-testing]

tech-stack:
  added: []
  patterns: [inline-confirmation-pattern, significant-step-gating]

key-files:
  created: []
  modified:
    - frontend/src/components/tour/TourProgressBar.vue
    - frontend/src/components/tour/TourOverlay.vue
    - frontend/src/components/tour/__tests__/TourProgressBar.test.ts

key-decisions:
  - "Combined Tasks 1 and 2 implementation in TourProgressBar since both add props to same component"
  - "Skip confirmation uses inline replace pattern (v-if/v-else) not modal overlay"
  - "isSignificantStep uses hardcoded title set ['AI Backend Accounts'] — extensible for Phase 9"
  - "Confirm button styled with accent-crimson border to signal destructive action"

patterns-established:
  - "Inline confirmation: replace action buttons with confirm/cancel row using v-if/v-else"
  - "Significant step gating: isSignificantStep() checks step title against allow-list"

duration: 5min
completed: 2026-03-22
---

# Phase 06 Plan 01: Step Title + Skip Confirmation Summary

**Progress bar now shows step title above counter and requires confirmation before skipping significant steps like AI Backend Accounts**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T09:00:07Z
- **Completed:** 2026-03-22T09:05:07Z
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- Step title renders above step counter in restructured column layout with meta row
- Skip confirmation inline dialog replaces action buttons for significant steps (skipNeedsConfirm=true)
- 5 new tests covering title display, direct skip, confirmation flow, confirm action, and cancel action
- All 16 TourProgressBar tests pass; build clean with zero TypeScript errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Add stepTitle prop, skip confirmation, and title display** - `56b2a9f` (feat)
2. **Task 2: Add tests for step title and skip confirmation** - `1b3a776` (test)

## Files Created/Modified

- `frontend/src/components/tour/TourProgressBar.vue` - Added stepTitle and skipNeedsConfirm props, restructured left section to column layout with title + meta row, added inline skip confirmation UI with confirm/cancel buttons
- `frontend/src/components/tour/TourOverlay.vue` - Added isSignificantStep helper, passes step-title and skip-needs-confirm props to TourProgressBar
- `frontend/src/components/tour/__tests__/TourProgressBar.test.ts` - Added stepTitle and skipNeedsConfirm to baseProps, added 5 new tests for title rendering and confirmation flow

## Decisions Made

- Combined both plan tasks into a single component update since stepTitle and skipNeedsConfirm are both new props on the same component — split commits by feat vs test
- Skip confirmation uses inline replacement (v-if/v-else on tour-skip-confirm vs tour-actions) rather than a modal, keeping the interaction lightweight and in-context
- isSignificantStep checks step.title against a hardcoded set rather than a step property, keeping the StepLike interface unchanged
- confirmingSkip state resets via watch on skippable and stepTitle props to prevent stale confirmation when step changes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added baseProps updates to Task 1 commit**
- **Found during:** Task 1 build verification
- **Issue:** Build failed because existing tests lacked new required props stepTitle and skipNeedsConfirm
- **Fix:** Added stepTitle and skipNeedsConfirm to baseProps in TourProgressBar.test.ts as part of Task 1
- **Files modified:** frontend/src/components/tour/__tests__/TourProgressBar.test.ts
- **Verification:** `just build` passed after fix
- **Committed in:** 56b2a9f (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3)
**Impact on plan:** Minimal — moved baseProps update from Task 2 into Task 1 to unblock build

## Issues Encountered

Pre-existing failures in App.test.ts (3 tests about provide/inject) unrelated to this plan — caused by prior uncommitted changes to App.vue on the branch.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TourProgressBar accepts stepTitle and skipNeedsConfirm props — ready for Phase 06 Plan 02
- isSignificantStep helper extensible for additional step titles in future phases
- All tour component tests pass; build clean

## Self-Check: PASSED

- [x] TourProgressBar.vue exists
- [x] TourOverlay.vue exists
- [x] TourProgressBar.test.ts exists
- [x] Commit 56b2a9f found
- [x] Commit 1b3a776 found
