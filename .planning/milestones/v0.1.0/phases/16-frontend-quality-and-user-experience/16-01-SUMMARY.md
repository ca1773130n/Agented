---
phase: 16-frontend-quality-and-user-experience
plan: 01
subsystem: frontend-error-handling
tags: [error-boundary, api-errors, sidebar-loading, toast-notifications]
dependency_graph:
  requires: []
  provides: [error-boundary, centralized-error-handler, sidebar-loading-coordination]
  affects: [App.vue, main.ts, AppSidebar.vue]
tech_stack:
  added: []
  patterns: [onErrorCaptured, Promise.allSettled, per-section-error-tracking]
key_files:
  created:
    - frontend/src/components/base/ErrorBoundary.vue
    - frontend/src/services/api/error-handler.ts
  modified:
    - frontend/src/App.vue
    - frontend/src/main.ts
    - frontend/src/components/layout/AppSidebar.vue
decisions:
  - Used onErrorCaptured with return false to prevent SPA crashes from child component rendering errors
  - Typed handleApiError showToast param with ToastType union for strict TS compatibility
  - loadVersion included in Promise.allSettled but silently degrades (does not throw) by design
  - Section error indicators placed at nav-section-label level with per-key retry buttons
metrics:
  duration: 6min
  completed: 2026-03-04
---

# Phase 16 Plan 01: Error Boundary, API Error Handler, and Sidebar Loading Summary

ErrorBoundary component with onErrorCaptured recovery, centralized API error handler with 9 status code mappings and toast integration, and Promise.allSettled sidebar loading coordination with per-section error tracking and retry.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create ErrorBoundary component and centralized error handler | 295af15 | ErrorBoundary.vue, error-handler.ts |
| 2 | Wire ErrorBoundary in App.vue and coordinate sidebar loading | 2213655 | App.vue, main.ts, AppSidebar.vue, error-handler.ts |

## Implementation Details

### ErrorBoundary.vue
- Vue 3 component using `onErrorCaptured` lifecycle hook
- Returns `false` from error handler to stop propagation and prevent SPA crash
- Recovery mechanism: increments `recoveryKey` ref to force child subtree re-creation via `:key` binding
- Styled fallback UI consistent with existing ErrorState.vue design (crimson icon, dark theme variables)

### error-handler.ts
- `STATUS_MAP` covers 9 HTTP status codes: 0 (timeout), 401, 403, 404, 409, 422, 429, 500, 503
- Each mapping provides: error code (ERR-xxx), user-friendly message, and suggested action
- `formatApiError()`: builds formatted string with optional server message detail
- `handleApiError()`: shows toast notification and returns formatted string for local error state
- Toast callback typed with ToastType union for strict TypeScript compatibility

### App.vue Changes
- Imported ErrorBoundary and handleApiError
- Wrapped `<router-view>` with `<ErrorBoundary>` (sidebar and toasts remain outside)
- Replaced 7 independent `loadX()` calls with `Promise.allSettled` via `loadSidebarData()`
- Added `sidebarLoading` ref (true during loading) and `sidebarErrors` ref (per-section error tracking)
- `retrySidebarSection(key)` clears error and re-runs only the failed section's loader
- Replaced all `console.warn('[Sidebar] Failed to load...')` with `handleApiError()` toast calls
- Each loader now re-throws after handling error so Promise.allSettled can track rejections

### AppSidebar.vue Changes
- Added `sidebarLoading` and `sidebarErrors` props with defaults
- Added `retrySidebarSection` emit
- Loading spinner shown at top of sidebar when `sidebarLoading` is true (CSS animated border spinner)
- Inline error indicators with warning icon and Retry button at section headers (Watch Tower, Organization, Forge, System)
- Scoped styles for spinner animation and error badge/retry button

### main.ts Changes
- Added `app.config.errorHandler` for defense-in-depth logging of uncaught Vue errors

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TypeScript type incompatibility in handleApiError**
- **Found during:** Task 2 verification
- **Issue:** `showToast` parameter typed as `(msg: string, type: string) => void` was incompatible with App.vue's `showToast` which uses `ToastType` union. TypeScript's parameter contravariance correctly flagged this.
- **Fix:** Changed `handleApiError` parameter to `(msg: string, type: 'success' | 'error' | 'info' | 'infrastructure') => void` matching the ToastType union.
- **Files modified:** frontend/src/services/api/error-handler.ts
- **Commit:** 2213655

## Verification Results

- Frontend production build: PASSED (vue-tsc + vite build)
- Frontend tests: 344/344 passed (29 test files)
- ErrorBoundary.vue exists with onErrorCaptured: PASSED
- error-handler.ts exports formatApiError and handleApiError: PASSED
- App.vue imports ErrorBoundary and wraps router-view: PASSED
- App.vue uses Promise.allSettled for sidebar loading: PASSED
- main.ts sets app.config.errorHandler: PASSED
- No console.warn Sidebar Failed calls remain: PASSED (0 matches)
- AppSidebar.vue has sidebarLoading prop and v-if directive: PASSED

## Self-Check: PASSED

All created files exist, all commits verified, all modified files accounted for.
