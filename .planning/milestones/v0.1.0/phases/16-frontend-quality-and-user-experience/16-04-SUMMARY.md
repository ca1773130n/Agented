---
phase: 16-frontend-quality-and-user-experience
plan: 04
subsystem: frontend-tests
tags: [vitest, vue-test-utils, error-boundary, error-handler, use-event-source, sidebar]
depends_on: ["16-01", "16-02"]
provides:
  - Unit tests for ErrorBoundary component (onErrorCaptured, recovery, error isolation)
  - Unit tests for centralized error-handler (formatApiError, handleApiError, STATUS_MAP)
  - Unit tests for useEventSource composable (lifecycle, cleanup, event registration, autoConnect)
  - Integration tests for sidebar loading coordination and retrySidebarSection

key-files:
  created:
    - frontend/src/components/base/__tests__/ErrorBoundary.test.ts
    - frontend/src/services/__tests__/error-handler.test.ts
    - frontend/src/composables/__tests__/useEventSource.test.ts
    - frontend/src/views/__tests__/AppErrorHandling.test.ts

key-decisions:
  - "Used synchronous setupState access ($.setupState) for ErrorBoundary tests to avoid happy-dom patchBlockChildren limitation"
  - "Checked hasError immediately after mount() without await — onErrorCaptured fires synchronously during mount"
  - "Used vi.mock on services/api/client for useEventSource tests with mock EventSource factory"
  - "Used createSidebarCoordinator helper mirroring App.vue logic without mounting full component"

duration: ~20min
completed: 2026-03-04
---

# Phase 16 Plan 04: Unit Tests for Foundation Components Summary

Wrote comprehensive unit tests for all components and utilities introduced in Plans 01 and 02: ErrorBoundary, error-handler, useEventSource, and App-level sidebar coordination.

## Performance

- **Tasks:** 3/3 completed
- **Test files created:** 4
- **New tests added:** 65 (8 + 25 + 19 + 13)
- **Total test suite after:** 409/409 passing

## Accomplishments

### Task 1: ErrorBoundary and error-handler tests

**`ErrorBoundary.test.ts`** (8 tests):
- Normal rendering without errors
- `onErrorCaptured` sets `hasError = true` when child lifecycle throws
- Error message recorded in `errorMessage`
- Custom `fallbackTitle` prop respected
- Default `fallbackTitle` is "Something went wrong"
- `recover()` resets `hasError`, clears `errorMessage`, increments `recoveryKey`
- Error isolation from parent (does not propagate)
- Fallback container has `role="alert"` attribute

**`error-handler.test.ts`** (25 tests):
- `it.each` for all 9 STATUS_MAP entries (401, 403, 404, 409, 422, 429, 500, 503, 0/TIMEOUT)
- Server message inclusion when different from generic HTTP status
- Redundant server message exclusion
- Unknown status codes fall back to `ERR-{status}`
- Actionable suggestions included for known codes
- `handleApiError` with `ApiError`: uses `formatApiError`, calls `showToast('error')`
- `handleApiError` with `Error`: ERR-UNKNOWN code, preserves message
- `handleApiError` with non-Error: uses fallback message, ERR-UNKNOWN
- Return value always equals what was passed to `showToast`

### Task 2: useEventSource composable tests

**`useEventSource.test.ts`** (19 tests):
- Initial idle status
- No auto-connect by default
- `autoConnect: true` triggers `createAuthenticatedEventSource` on mount
- Status transitions: idle → connecting → open (via onopen) / error (via onerror) / closed (via close())
- Named event listeners registered via `events` map
- Reconnection cleanup: first source is closed before second is created
- Automatic cleanup on component unmount (via `onUnmounted`)
- Function-form URL (getter function evaluated on connect)
- `onOpen` callback invoked when connection opens
- `onError` callback invoked with the error event
- `sourceFactory` option bypasses `createAuthenticatedEventSource`
- Error status when neither `url` nor `sourceFactory` provided
- `getSource()` returns active source or null
- `onMessage` property assigned to source

### Task 3: App-level error handling and sidebar retry tests

**`AppErrorHandling.test.ts`** (13 tests):
- `sidebarLoading` lifecycle: starts `true`, becomes `false` after `Promise.allSettled`
- Per-section error tracking: 2 of 7 sections fail → only those 2 have error messages
- `Promise.allSettled` independence: failing sections don't block successful ones
- Non-Error rejection stored as string
- `retrySidebarSection('teams')` calls only the `teams` loader
- Error isolation: retrying one section doesn't affect other sections' errors
- Retry failure stores new error message
- Error cleared before loader runs (enabling loading state during retry)
- No-op when key not found in loaders
- `handleApiError` invokes `showToast` with `'error'` type
- Return value is the formatted error string that would be stored in `sidebarErrors`
- ApiError produces non-empty ERR-{status} message
- Generic Error produces ERR-UNKNOWN message

## Task Commits

1. **Task 1: ErrorBoundary and error-handler tests** — `1d59d36` (test)
2. **Task 2: useEventSource composable tests** — `d7a45a9` (test)
3. **Task 3: Sidebar coordination and retry tests** — `60b5dba` (test)

## Decisions Made

### 1. Synchronous setupState access for ErrorBoundary tests

**Finding:** In happy-dom, Vue's `patchBlockChildren` fails asynchronously when the `v-if`/`v-else` boundary in ErrorBoundary tries to reconcile after `onErrorCaptured` fires — the child component's vnode has a corrupt `.el` reference from the lifecycle error.

**Decision:** Access `wrapper.vm.$.setupState` directly (not DOM assertions) and check state synchronously — `onErrorCaptured` fires synchronously during `mount()`, so `hasError` is already `true` before `mount()` returns. Never `await` after mounting a ThrowingComponent; unmount immediately after assertions to cancel pending Vue re-renders.

### 2. Mock EventSource factory pattern for useEventSource tests

**Finding:** `createAuthenticatedEventSource` makes real network requests and uses fetch-event-source internals.

**Decision:** Mock the entire `services/api/client` module with `vi.mock`. Create a `createMockSource()` factory returning a mock with `.onopen`, `.onerror`, `.onmessage` properties and `_triggerOpen()` / `_triggerError()` helpers. This mirrors the `AuthenticatedEventSource` interface without any network I/O.

### 3. Logic-level helper instead of full App.vue mount for sidebar tests

**Finding:** `App.vue` imports router, health API, version API, sidebar, and all entity APIs. Mounting it in tests requires extensive mocking of all dependencies.

**Decision:** Extract the sidebar coordination logic (sidebarLoading, sidebarErrors, loadSidebarData, retrySidebarSection) into a `createSidebarCoordinator()` test helper. This mirrors the App.vue implementation exactly but is framework-agnostic, making tests fast and focused on the coordination behavior.

## Verification Results

- Frontend tests: 409/409 passed (33 test files)
- Frontend production build: PASSED (vue-tsc + vite build)
- ErrorBoundary.test.ts: 8 tests (all behavioral — onErrorCaptured, recovery, isolation)
- error-handler.test.ts: 25 tests (all STATUS_MAP entries covered via it.each)
- useEventSource.test.ts: 19 tests (full lifecycle + cleanup + edge cases)
- AppErrorHandling.test.ts: 13 tests (sidebar coordination + retry + handleApiError integration)

## Self-Check: PASSED

- All 4 test files exist at the specified paths
- All 3 task commits verified (1d59d36, d7a45a9, 60b5dba)
- 409/409 frontend tests pass with zero failures and zero unhandled errors
- Frontend production build succeeds
- Summary file created at phase directory
