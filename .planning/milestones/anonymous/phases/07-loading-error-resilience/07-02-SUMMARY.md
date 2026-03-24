---
phase: 07-loading-error-resilience
plan: 02
subsystem: tour-overlay
tags: [tour, z-index, modal-coordination, provide-inject]
dependency_graph:
  requires:
    - phase: 01-backend-state-machine-foundation
      provides: z-index scale, tour overlay CSS custom properties
  provides:
    - --z-toast CSS variable above tour z-indexes
    - modalOpenDuringTour provide/inject for modal-tour coordination
    - TourOverlay isModalOpen prop with reduced-opacity dimming
  affects: [TourOverlay.vue, TourSpotlight.vue, App.vue, BackendDetailPage.vue]
tech_stack:
  added: []
  patterns: [provide-inject-modal-signal, css-variable-z-index-scale]
key_files:
  created: []
  modified:
    - frontend/src/App.vue
    - frontend/src/components/tour/TourOverlay.vue
    - frontend/src/components/tour/TourSpotlight.vue
    - frontend/src/views/BackendDetailPage.vue
key-decisions:
  - "--z-toast: 10005 placed above --z-tour-progress: 10004 in CSS scale"
  - "Modal coordination uses provide/inject pattern consistent with existing showToast"
  - "TourSpotlight reduced prop dims glow to 0.3 opacity alongside dim-fallback"
  - "BackendDetailPage watches both showAddModal and editingAccount for modal signal"
patterns-established:
  - "provide/inject modal coordination: setTourModalOpen injected by modal components"
duration: 5min
completed: 2026-03-22
---

# Phase 7 Plan 2: Toast Z-Index Fix + Modal Coordination Summary

Toast notifications now render above the tour overlay via --z-toast: 10005 CSS variable, and the tour overlay dims to 0.3 opacity when modals open during tour steps (OB-44).

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T09:52:41Z
- **Completed:** 2026-03-22T09:57:50Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Resolved deferred OB-43 toast/tour overlay z-index conflict from Phase 1 (01-02)
- Implemented modal coordination so Add Account form during tour step reduces overlay dimming
- Extended provide/inject pattern for cross-component tour-modal signaling

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix toast z-index conflict** - `ff12028` (fix)
2. **Task 2: Modal coordination overlay yield** - `b1c7189` (feat)

## Files Created/Modified

- `frontend/src/App.vue` - Added --z-toast: 10005 to :root, replaced hardcoded z-index in .toast-container, added modalOpenDuringTour ref + provide, passed isModalOpen prop to TourOverlay
- `frontend/src/components/tour/TourOverlay.vue` - Added optional isModalOpen prop with withDefaults, modal-open CSS class on dim-fallback (opacity: 0.3), passed reduced prop to TourSpotlight
- `frontend/src/components/tour/TourSpotlight.vue` - Added optional reduced prop, tour-spotlight--reduced class (opacity: 0.3)
- `frontend/src/views/BackendDetailPage.vue` - Injected setTourModalOpen, watcher on showAddModal/editingAccount signals modal state

## Decisions Made

- --z-toast: 10005 placed one above --z-tour-progress: 10004, keeping the sequential scale
- Modal coordination uses provide/inject (not event bus) consistent with existing showToast pattern
- Both showAddModal and editingAccount watched since either opens the inline form
- TourSpotlight glow also dims when modal open (reduced prop) for visual consistency
- isModalOpen defaults to false via withDefaults to avoid breaking existing tests

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `just build`: PASS (zero vue-tsc errors)
- `npm run test:run`: 992 pass, 3 pre-existing failures in App.test.ts (provide/inject tests unrelated to tour)
- `uv run pytest`: not affected (frontend-only changes)
- Grep confirms no hardcoded `z-index: 10000` in App.vue

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 7 complete. All loading/error resilience features in place:
- Plan 01: Loading timeout fallback, scoped MutationObserver, route prefetch
- Plan 02: Toast z-index fix, modal coordination during tour

Ready for Phase 8 (accessibility) or Phase 9 (persistence/analytics).

## Self-Check: PASSED

---
*Phase: 07-loading-error-resilience*
*Completed: 2026-03-22*
