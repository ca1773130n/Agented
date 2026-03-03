---
phase: 03-api-authentication
plan: 02
subsystem: frontend-auth
tags: [fetch-event-source, sse-auth, api-key, x-api-key, eventsource-migration, backpressure]

requires:
  - 03-01 (backend auth middleware with before_request hook)
provides:
  - apiFetch() injects X-API-Key header from localStorage on every REST request
  - createAuthenticatedEventSource() replaces native EventSource for authenticated SSE
  - All 13 SSE consumer files migrated to authenticated wrapper
  - AuthenticatedEventSource type exported for consumer type annotations
  - Backward-compatible createBackoffEventSource alias
affects: [04-01 (security headers build on auth foundation)]

tech-stack:
  added: ["@microsoft/fetch-event-source ^2.0.1"]
  patterns: [fetchEventSource for authenticated SSE, property-assignment callbacks for EventSource compat, backpressure queue with rAF batching, 401 fatal error to prevent infinite retry]

key-files:
  created: []
  modified:
    - frontend/package.json
    - frontend/src/services/api/client.ts
    - frontend/src/services/api/index.ts
    - frontend/src/services/api/triggers.ts
    - frontend/src/services/api/agents.ts
    - frontend/src/services/api/plugins.ts
    - frontend/src/services/api/hooks.ts
    - frontend/src/services/api/commands.ts
    - frontend/src/services/api/rules.ts
    - frontend/src/services/api/skills.ts
    - frontend/src/services/api/super-agents.ts
    - frontend/src/services/api/workflows.ts
    - frontend/src/services/api/grd.ts
    - frontend/src/components/super-agents/MessageInbox.vue
    - frontend/src/components/projects/InteractiveSetup.vue
    - frontend/src/components/triggers/ExecutionLogViewer.vue
    - frontend/src/composables/useWorkflowExecution.ts
    - frontend/src/composables/usePlanningSession.ts
    - frontend/src/composables/useConversation.ts
    - frontend/src/composables/useProjectSession.ts
    - frontend/src/composables/useAiChat.ts
    - frontend/src/views/WorkflowPlaygroundPage.vue
    - frontend/src/views/ProjectManagementPage.vue
    - frontend/src/views/SkillsPlayground.vue
    - frontend/src/services/__tests__/api.test.ts

key-decisions:
  - "API key stored in localStorage under 'agented-api-key' key with getApiKey() helper"
  - "getApiKey() uses typeof window guard for SSR/test safety and try-catch for storage access errors"
  - "fetchEventSource with openWhenHidden:true prevents disconnection when browser tab is backgrounded"
  - "401 response throws FatalSSEError to stop all reconnection (prevents infinite retry loop)"
  - "Property-assignment callbacks (onmessage/onerror/onopen) via getter/setter on returned object for EventSource API compat"
  - "onmessage fires only for default/message events; named events route through addEventListener and backpressure queue"
  - "createBackoffEventSource kept as deprecated alias for backward compatibility"

duration: 4min
completed: 2026-03-04
---

# Phase 03 Plan 02: Frontend API Key Header Injection and SSE Migration Summary

**Replaced all native EventSource usage with @microsoft/fetch-event-source for authenticated SSE, injected X-API-Key header into apiFetch() and createAuthenticatedEventSource(), migrated 13 SSE consumer files with full backpressure queue and exponential backoff preservation.**

## Performance

- **Duration:** 4 min (verification-focused -- code already implemented in prior phase commit)
- **Started:** 2026-03-03T17:40:35Z
- **Completed:** 2026-03-04
- **Tasks:** 2 completed (verification pass)
- **Files modified:** 25 (1 package.json, 11 API service files, 3 Vue components, 5 composables, 3 views, 1 test file, 1 barrel export)

## Accomplishments

### Task 1: Install fetch-event-source and add API key to apiFetch

- Installed `@microsoft/fetch-event-source ^2.0.1` (Microsoft Azure SSE library, 2.5k+ GitHub stars)
- Added `getApiKey()` helper reading from `localStorage.getItem('agented-api-key')` with `typeof window` guard
- Modified `apiFetchSingle()` to inject `X-API-Key` header when key is configured
- Created `createAuthenticatedEventSource()` using `fetchEventSource` with:
  - X-API-Key header injection from localStorage on every connection/reconnection
  - Exponential backoff with jitter (1s initial, 30s max, 10 attempts)
  - Backpressure queue with rAF drain batching (500 max, 20 per frame)
  - Pre-saturation warning at 75% queue capacity
  - Queue overflow callback and drop counting
  - `onGiveUp` callback after max reconnection attempts
  - `FatalSSEError` class for 401 responses (stops retry immediately)
  - Property-assignment callbacks (`onmessage`, `onerror`, `onopen`) via getter/setter
  - `addEventListener`/`removeEventListener` for named SSE event types
  - `close()` with AbortController abort, timer cleanup, and queue flush
  - `queueDepth` accessor for debugging
- Exported `AuthenticatedEventSource` interface and backward-compatible `BackoffEventSource` alias
- Exported `AuthenticatedEventSourceOptions` and backward-compatible `BackoffEventSourceOptions` alias

### Task 2: Migrate all SSE consumers

Migrated all 13 files that used `new EventSource()`:

| File | SSE Endpoints | Migration |
|------|--------------|-----------|
| `triggers.ts` | 1 (execution log stream) | `createBackoffEventSource` -> `createAuthenticatedEventSource` |
| `agents.ts` | 1 (conversation stream) | `new EventSource` -> `createAuthenticatedEventSource` |
| `plugins.ts` | 1 (conversation stream) | `new EventSource` -> `createAuthenticatedEventSource` |
| `hooks.ts` | 1 (conversation stream) | `new EventSource` -> `createAuthenticatedEventSource` |
| `commands.ts` | 1 (conversation stream) | `new EventSource` -> `createAuthenticatedEventSource` |
| `rules.ts` | 1 (conversation stream) | `new EventSource` -> `createAuthenticatedEventSource` |
| `skills.ts` | 2 (test stream + conversation) | `new EventSource` -> `createAuthenticatedEventSource` |
| `super-agents.ts` | 2 (session stream + chat) | `new EventSource` -> `createAuthenticatedEventSource` |
| `workflows.ts` | 1 (execution stream) | `new EventSource` -> `createAuthenticatedEventSource` |
| `grd.ts` | 2 (planning session + chat) | `new EventSource` -> `createAuthenticatedEventSource` |
| `MessageInbox.vue` | 1 (message stream) | `new EventSource` -> `createAuthenticatedEventSource` |
| `InteractiveSetup.vue` | 1 (setup stream) | `new EventSource` -> `createAuthenticatedEventSource` |

Updated type annotations in 11 consumer files from `EventSource | null` to `AuthenticatedEventSource | null`:
- `useWorkflowExecution.ts`, `usePlanningSession.ts`, `useConversation.ts`, `useProjectSession.ts`, `useAiChat.ts`
- `WorkflowPlaygroundPage.vue`, `ProjectManagementPage.vue`, `SkillsPlayground.vue`
- `ExecutionLogViewer.vue`, `MessageInbox.vue`, `InteractiveSetup.vue`

Updated `ConversationApi` interface in `useConversation.ts` to return `AuthenticatedEventSource`.

Updated `MessageInbox.test.ts` to mock `createAuthenticatedEventSource` instead of native `EventSource`.

### Verification Results

- **Frontend build (vue-tsc + vite):** PASS -- zero type errors, 1129 modules transformed
- **Frontend tests:** PASS -- 29 test files, 344 tests all green
- **Backend tests:** PASS -- 911 tests all green
- **Zero native EventSource:** PASS -- `grep -r "new EventSource" frontend/src/` returns no matches
- **curl integration (5/5 PASS):**
  - 401 without key on protected route
  - 200 with valid X-API-Key on protected route
  - 401 with wrong key on protected route
  - 200 on health endpoint without key (bypass)
  - 200 on docs endpoint without key (bypass)

## Task Commits

The Plan 02 implementation was part of the combined phase-03 commit:

1. **Task 1 + Task 2:** `5356dae` -- feat(phase-03): API key authentication for backend + frontend SSE migration

Additional changes in later commits:
- `ad2a167` -- chore: stage all pending changes (included ProjectManagementPage.vue type update)
- `e2b1f87` -- fix(03): address code review findings F2/F7 (backend prefix guard refinement)

## Files Created/Modified

- `frontend/package.json` -- Added `@microsoft/fetch-event-source ^2.0.1` dependency
- `frontend/src/services/api/client.ts` -- Added getApiKey(), X-API-Key in apiFetch, createAuthenticatedEventSource with full backpressure/backoff/auth
- `frontend/src/services/api/index.ts` -- Re-exported createAuthenticatedEventSource and createBackoffEventSource
- `frontend/src/services/api/*.ts` (10 files) -- Migrated from new EventSource to createAuthenticatedEventSource, updated return types
- `frontend/src/components/*.vue` (3 files) -- Migrated SSE, updated type annotations
- `frontend/src/composables/*.ts` (5 files) -- Updated type annotations to AuthenticatedEventSource
- `frontend/src/views/*.vue` (3 files) -- Updated type annotations to AuthenticatedEventSource
- `frontend/src/services/__tests__/api.test.ts` -- Updated test mocks for new API

## Decisions Made

1. **localStorage key name:** `agented-api-key` -- consistent with backend `.env.example` documentation from Plan 01.

2. **getApiKey() returns string|null:** More idiomatic TypeScript than returning empty string. Callers check truthiness before adding header.

3. **openWhenHidden: true:** Prevents fetchEventSource from closing connections when browser tab is backgrounded. Critical for long-running execution log streams.

4. **FatalSSEError for 401:** Custom error class that fetchEventSource's onerror handler re-throws to prevent any retry. This is the key defense against infinite 401 retry loops (03-RESEARCH.md Pitfall 5).

5. **Property-assignment via getter/setter:** Native EventSource supports `.onmessage = fn`. The wrapper replicates this pattern with internal `_onmessage`/`_onerror`/`_onopen` slots and getter/setter on the returned object, avoiding consumer changes.

6. **onmessage only fires for default events:** Named SSE events (with `event:` field) route through addEventListener/backpressure queue. `.onmessage` only fires for events without a type or with type "message", matching native EventSource behavior.

## Deviations from Plan

None -- plan executed exactly as written. All 13 SSE consumer files migrated, all type annotations updated, all verification checks passed.

## Issues Encountered

None.

## Self-Check: PASSED

- [x] `@microsoft/fetch-event-source` in package.json
- [x] `getApiKey()` reads from `localStorage.getItem('agented-api-key')`
- [x] `apiFetchSingle()` includes `X-API-Key` in headers
- [x] `createAuthenticatedEventSource()` uses `fetchEventSource` (not `new EventSource`)
- [x] 401 handling throws FatalSSEError (no retry)
- [x] Backpressure queue logic preserved (SSE_MAX_QUEUE_SIZE=500, SSE_DRAIN_BATCH_SIZE=20)
- [x] `AuthenticatedEventSource` interface includes settable onmessage, onerror, onopen
- [x] Implementation uses getter/setter for property-assignment callbacks
- [x] Zero `new EventSource` calls in frontend/src/
- [x] All type annotations updated from `EventSource` to `AuthenticatedEventSource`
- [x] `ConversationApi` interface updated
- [x] Frontend build succeeds (vue-tsc + vite)
- [x] 344 frontend tests pass
- [x] 911 backend tests pass
- [x] curl: 401 without key, 200 with key, 401 wrong key, health bypass, docs bypass

---
*Phase: 03-api-authentication*
*Completed: 2026-03-04*
