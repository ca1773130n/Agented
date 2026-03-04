---
phase: 16-frontend-quality-and-user-experience
plan: 02
subsystem: ui
tags: [vue, composables, sse, eventsource, refactoring]

requires:
  - phase: none
    provides: existing SSE consumer composables
provides:
  - Shared useEventSource composable for SSE connection lifecycle
  - Refactored useConversation, useAiChat, useProjectSession to use shared SSE composable
affects: [any future SSE consumers, composable patterns]

tech-stack:
  added: []
  patterns: [useEventSource composable pattern for SSE lifecycle delegation]

key-files:
  created:
    - frontend/src/composables/useEventSource.ts
  modified:
    - frontend/src/composables/useConversation.ts
    - frontend/src/composables/useAiChat.ts
    - frontend/src/composables/useProjectSession.ts

key-decisions:
  - "Extended plan's URL-only interface to support sourceFactory for API modules that manage EventSource creation internally"
  - "Kept onUnmounted in useAiChat and useProjectSession for non-SSE cleanup (heartbeat timers, allMode reset, state reset)"

patterns-established:
  - "useEventSource composable: shared SSE lifecycle with sourceFactory or URL, events map, auto-unmount cleanup"
  - "Consumer composables delegate SSE connect/close/status to useEventSource while retaining protocol-specific parsing"

duration: 5min
completed: 2026-03-04
---

# Phase 16 Plan 02: Shared useEventSource Composable Summary

**Extracted shared SSE lifecycle composable eliminating duplicated connection boilerplate across three consumers while preserving all protocol-specific event parsing.**

## Performance

- **Duration:** 5m 23s
- **Started:** 2026-03-04T01:17:56Z
- **Completed:** 2026-03-04T01:23:19Z
- **Tasks:** 2 completed
- **Files modified:** 4

## Accomplishments

- Created `useEventSource` composable with reactive SSEStatus, connect/close/getSource interface, sourceFactory support, named event registration, and automatic onUnmounted cleanup
- Refactored `useConversation` to delegate SSE lifecycle to useEventSource, removing direct AuthenticatedEventSource management and manual cleanup
- Refactored `useAiChat` to delegate SSE lifecycle while preserving state_delta seq tracking, heartbeat watchdog, and allMode interception
- Refactored `useProjectSession` to delegate SSE lifecycle while preserving output/complete/error callback dispatch and error counting
- All 344 frontend tests pass, production build succeeds with zero type errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Create useEventSource composable** - `aafd243` (feat)
2. **Task 2: Refactor SSE consumers to delegate to useEventSource** - `eb533e4` (feat)

## Files Created/Modified

- `frontend/src/composables/useEventSource.ts` - Shared SSE lifecycle composable wrapping createAuthenticatedEventSource with reactive status, connect/close/getSource, event registration, and auto-cleanup
- `frontend/src/composables/useConversation.ts` - Replaced direct api.stream() and manual addEventListener with useEventSource sourceFactory and events map
- `frontend/src/composables/useAiChat.ts` - Replaced superAgentSessionApi.chatStream() with useEventSource; preserved heartbeat watchdog and allMode
- `frontend/src/composables/useProjectSession.ts` - Replaced grdApi.streamSession() with useEventSource; preserved error counting and callback dispatch

## Decisions Made

1. **sourceFactory pattern instead of URL-only** - The plan specified `url: string | (() => string)` for useEventSource, but the actual codebase has API modules (e.g., `superAgentSessionApi.chatStream()`, `grdApi.streamSession()`) that call `createAuthenticatedEventSource` internally and return the source. Added `sourceFactory: () => AuthenticatedEventSource` option so consumers can delegate to their existing API layer without restructuring the API modules.

2. **Separate onUnmounted for non-SSE cleanup** - useAiChat needs heartbeat timer cleanup and allMode reset on unmount; useProjectSession needs state reset on unmount. These are separate from SSE cleanup and require their own onUnmounted hooks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added sourceFactory option to UseEventSourceOptions**
- **Found during:** Task 1 (Create useEventSource composable)
- **Issue:** Plan's URL-only interface assumed consumers call createAuthenticatedEventSource directly, but all three consumers use API module functions (api.stream, chatStream, streamSession) that internally create the EventSource
- **Fix:** Added `sourceFactory?: () => AuthenticatedEventSource` option alongside `url`, making both patterns supported
- **Files modified:** frontend/src/composables/useEventSource.ts
- **Verification:** All three consumers successfully refactored using sourceFactory; TypeScript passes; build succeeds
- **Committed in:** aafd243

---

**Total deviations:** 1 auto-fixed (Rule 3)
**Impact on plan:** Minimal -- the interface is a superset of what the plan specified. URL-based creation still works for future consumers.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- useEventSource composable is available for any future SSE consumers
- All existing SSE consumers are refactored and backward-compatible
- No blockers for subsequent plans in Phase 16

## Self-Check: PASSED

- All 4 files exist (1 created, 3 modified)
- Both task commits found (aafd243, eb533e4)
- Summary file exists
- Frontend build passes with zero errors
- 344/344 frontend tests pass
