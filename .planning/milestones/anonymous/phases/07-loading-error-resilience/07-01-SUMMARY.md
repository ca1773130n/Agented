---
phase: 07-loading-error-resilience
plan: 01
subsystem: tour-overlay
tags: [tour, loading, resilience, mutation-observer, prefetch]
dependency_graph:
  requires: [06-navigation-controls]
  provides: [loading-timeout-fallback, scoped-mutation-observer, route-prefetch]
  affects: [TourOverlay.vue, useTourMachine.ts, App.vue]
tech_stack:
  added: []
  patterns: [scoped-mutation-observer, timeout-escalation, route-prefetch]
key_files:
  created: []
  modified:
    - frontend/src/components/tour/TourOverlay.vue
    - frontend/src/composables/useTourMachine.ts
    - frontend/src/App.vue
    - frontend/src/components/tour/__tests__/TourOverlay.test.ts
decisions:
  - Element-not-found (3s) fallback takes priority over loading timeout (5s) via v-if/v-else-if chain
  - MutationObserver scoped to #main-content with document.body fallback
  - nextTick + 100ms delay before starting observer to avoid premature observation
  - prefetchTourRoutes uses Promise.allSettled for resilient fire-and-forget
  - Retry emits from TourOverlay; App.vue handleTourRetry re-navigates to step route
metrics:
  duration: 6min
  completed: 2026-03-22
---

# Phase 7 Plan 1: Loading Timeout Fallback + Route Prefetch Summary

Tour overlay now has graceful degradation when target elements are slow to appear: a spinner escalates to Skip/Retry fallbacks, MutationObserver is scoped to the route root, and route components are prefetched at tour start.

## Task Summary

| # | Task | Commit | Key Changes |
|---|------|--------|-------------|
| 1 | Loading timeout fallback + scoped MutationObserver | c4eed7e | TourOverlay: 5s loading timeout, 3s element-not-found timeout, scoped observer on #main-content |
| 2 | Route prefetching + retry wiring + tests | 6ef01a6 | prefetchTourRoutes() in useTourMachine, handleTourRetry in App.vue, 5 new tests |

## What Was Built

**Loading timeout (OB-40):** Spinner shows immediately when target not found. After 5s without finding target, overlay shows "This page is taking longer than expected" with Skip/Retry buttons.

**Scoped MutationObserver (OB-41):** Observer watches `#main-content` (route root) instead of `document.body`. After 3s without finding element, overlay shows "We couldn't find [step title]" with Skip/Retry. The 3s fallback takes priority over the 5s fallback via v-if/v-else-if chain.

**Route prefetching (OB-42):** `prefetchTourRoutes()` fires dynamic imports for SettingsPage.vue and BackendDetailPage.vue on tour start. Called in all three tour-start locations in App.vue. Uses `Promise.allSettled` for resilience.

**Retry wiring:** TourOverlay emits `retry`; App.vue `handleTourRetry` re-navigates to the current step's route to force a fresh load.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `just build`: PASS (zero vue-tsc errors)
- `npm run test:run` on TourOverlay: 28/28 PASS (23 existing + 5 new)
- Full test suite: 3 pre-existing failures in App.test.ts (provide/inject tests unrelated to tour changes)
- `uv run pytest`: not affected (frontend-only changes)

## Self-Check: PASSED
