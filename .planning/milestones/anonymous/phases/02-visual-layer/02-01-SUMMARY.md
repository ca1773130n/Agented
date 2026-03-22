---
phase: 02-visual-layer
plan: 01
subsystem: ui
tags: [floating-ui, css-custom-properties, spotlight, tour, vue3]

requires:
  - phase: 01-backend-state-machine-foundation
    provides: tour z-index CSS custom properties in App.vue :root
provides:
  - TourSpotlight.vue component with box-shadow dimming and CSS transitions
  - TourOverlay.vue refactored to orchestrator pattern with ResizeObserver
  - Tour visual CSS custom properties (overlay-dim, glow-color, transition-speed, etc.)
  - @floating-ui/vue dependency ready for tooltip positioning
affects: [02-visual-layer plan 02 (tooltip + progress bar), 04-step-definitions, 07-polish]

tech-stack:
  added: ["@floating-ui/vue@^1.1.11"]
  patterns: ["box-shadow dimming for spotlight overlay", "CSS custom properties for all tour visual values", "ResizeObserver for content reflow tracking", "component extraction (orchestrator + specialist)"]

key-files:
  created:
    - frontend/src/components/tour/TourSpotlight.vue
    - frontend/src/components/tour/__tests__/TourSpotlight.test.ts
  modified:
    - frontend/src/App.vue
    - frontend/src/components/tour/TourOverlay.vue
    - frontend/src/components/tour/__tests__/TourOverlay.test.ts
    - frontend/package.json
    - frontend/package-lock.json

key-decisions:
  - "CSS custom property padding reads from --tour-spotlight-padding with fallback to 8px"
  - "Glow animation uses opacity-based box-shadow (fixed shadow, animated opacity) per Research Pitfall 6"
  - "Accent color switched from indigo (#6366f1) to --accent-cyan to match app design language"
  - "TourSpotlight uses v-if on targetRect internally rather than parent controlling visibility"

patterns-established:
  - "Static analysis test: read .vue source, extract <style> block, grep for hardcoded values"
  - "Orchestrator + specialist component pattern for tour layers"

duration: 4min
completed: 2026-03-22
---

# Phase 02 Plan 01: Spotlight Extraction and CSS Custom Properties Summary

**TourSpotlight component extracted with box-shadow dimming, zero hardcoded colors/z-index, ResizeObserver reflow tracking, and @floating-ui/vue installed for Plan 02 tooltip**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-22T02:37:00Z
- **Completed:** 2026-03-22T02:41:06Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- Installed @floating-ui/vue and defined 7 tour CSS custom properties in App.vue :root
- Extracted TourSpotlight.vue with box-shadow dimming, position: fixed, CSS transitions, and performance-optimized glow animation
- Refactored TourOverlay.vue to slim orchestrator with ResizeObserver for content reflow detection
- Replaced all hardcoded color and z-index values in both tour components with CSS custom properties
- Added 9 new TourSpotlight tests including static analysis checks for hardcoded values

## Task Commits

Each task was committed atomically:

1. **Task 1: Install @floating-ui/vue and define CSS custom properties** - `3ca46a5` (chore)
2. **Task 2: Create TourSpotlight and refactor TourOverlay** - `f57c111` (feat)

## Files Created/Modified

- `frontend/src/components/tour/TourSpotlight.vue` - Spotlight component with box-shadow dimming, CSS custom properties only
- `frontend/src/components/tour/TourOverlay.vue` - Refactored to orchestrator; delegates spotlight, adds ResizeObserver
- `frontend/src/components/tour/__tests__/TourSpotlight.test.ts` - 9 tests: rendering, styles, glow, static analysis
- `frontend/src/components/tour/__tests__/TourOverlay.test.ts` - Updated for refactored structure, added TourSpotlight child test
- `frontend/src/App.vue` - Added 7 tour visual CSS custom properties
- `frontend/package.json` - Added @floating-ui/vue dependency
- `frontend/package-lock.json` - Updated lockfile

## Decisions Made

- Used `--accent-cyan` as primary tour accent color (replacing old indigo `#6366f1`) to match app design language
- Glow animation uses fixed box-shadow with CSS var colors rather than animating the shadow spread value (avoids paint thrashing per Research Pitfall 6)
- TourSpotlight reads padding from `--tour-spotlight-padding` CSS custom property with fallback, keeping the value configurable
- Static analysis test pattern: read component source, extract style block, regex for hardcoded values — catches regressions at test time

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing test failures in `frontend/src/views/__tests__/App.test.ts` (3 tests about `injectedRefresh` type). These are unrelated to tour components and existed before this plan. No regressions introduced.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- @floating-ui/vue is installed and ready for Plan 02 tooltip component
- TourSpotlight provides `targetRect` prop interface that tooltip will also use
- CSS custom properties are in place for tooltip and progress bar styling
- TourOverlay orchestrator pattern is ready to add TourTooltip and TourProgressBar as additional children

## Self-Check: PASSED

- [x] `frontend/src/components/tour/TourSpotlight.vue` exists
- [x] `frontend/src/components/tour/__tests__/TourSpotlight.test.ts` exists
- [x] Commit `3ca46a5` exists
- [x] Commit `f57c111` exists
- [x] Zero hardcoded colors in tour component style blocks
- [x] Zero hardcoded z-index in tour component style blocks
- [x] ResizeObserver present in TourOverlay
- [x] `just build` passes
- [x] All tour tests pass (26/26)

---
*Phase: 02-visual-layer*
*Completed: 2026-03-22*
