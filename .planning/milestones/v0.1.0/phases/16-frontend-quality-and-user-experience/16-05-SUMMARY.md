---
phase: 16-frontend-quality-and-user-experience
plan: 05
subsystem: frontend-error-handling
tags: [handleApiError, toast-notifications, EntityLayout, LoadingState, ErrorState]
dependency_graph:
  requires: [16-01]
  provides: [consistent-api-error-toasts, sketch-chat-loading-states]
  affects:
    - frontend/src/views/AgentDesignPage.vue
    - frontend/src/views/AuditDetail.vue
    - frontend/src/views/BackendDetailPage.vue
    - frontend/src/views/GenericTriggerDashboard.vue
    - frontend/src/views/GenericTriggerHistory.vue
    - frontend/src/views/McpServerDetailPage.vue
    - frontend/src/views/PluginDetailPage.vue
    - frontend/src/views/ProductSettingsPage.vue
    - frontend/src/views/ProjectPlanningPage.vue
    - frontend/src/views/ProjectSettingsPage.vue
    - frontend/src/views/SkillDetailPage.vue
    - frontend/src/views/SuperAgentPlayground.vue
    - frontend/src/views/TeamBuilderPage.vue
    - frontend/src/views/TeamDashboard.vue
    - frontend/src/views/TeamSettingsPage.vue
    - frontend/src/views/WorkflowBuilderPage.vue
    - frontend/src/views/SketchChatPage.vue
tech_stack:
  added: []
  patterns: [handleApiError, useToast, LoadingState, ErrorState, try-catch-rethrow]
key_files:
  modified:
    - frontend/src/views/AgentDesignPage.vue
    - frontend/src/views/AuditDetail.vue
    - frontend/src/views/BackendDetailPage.vue
    - frontend/src/views/GenericTriggerDashboard.vue
    - frontend/src/views/GenericTriggerHistory.vue
    - frontend/src/views/McpServerDetailPage.vue
    - frontend/src/views/PluginDetailPage.vue
    - frontend/src/views/ProductSettingsPage.vue
    - frontend/src/views/ProjectPlanningPage.vue
    - frontend/src/views/ProjectSettingsPage.vue
    - frontend/src/views/SkillDetailPage.vue
    - frontend/src/views/SuperAgentPlayground.vue
    - frontend/src/views/TeamBuilderPage.vue
    - frontend/src/views/TeamDashboard.vue
    - frontend/src/views/TeamSettingsPage.vue
    - frontend/src/views/WorkflowBuilderPage.vue
    - frontend/src/views/SketchChatPage.vue
decisions:
  - EntityLayout views only get handleApiError + re-throw -- no LoadingState/ErrorState added (EntityLayout already provides these natively)
  - GenericTriggerHistory and SuperAgentPlayground lacked useToast; both now import it alongside handleApiError
  - ProjectPlanningPage already had a try/catch with basic showToast call; replaced with handleApiError for structured error formatting
  - SketchChatPage uses useSketchChat composable which swallows errors into error.value; loadInitialData uses Promise.all + finally for isLoading tracking; loadError set by checking error.value post-call (no double-toast)
  - AgentCreateWizard, PluginDesignPage, SkillCreateWizard verified -- useConversation.startConversation() already has internal try/catch with toast; no changes needed
  - WorkflowPlaygroundPage verified -- no onMounted and no blocking initial API fetch; left unchanged
metrics:
  duration: ~15min
  completed: 2026-03-04
---

# Phase 16 Plan 05: Consistent Error Handling with Toast Notifications Summary

Added handleApiError toast notifications to all 16 EntityLayout views and full loading/error state coverage to SketchChatPage (the only non-EntityLayout view with a blocking initial API fetch).

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add handleApiError to 16 EntityLayout views | 9f8cc08 | 16 view files |
| 2 | Audit and add loading/error states to 5 non-EntityLayout views | c465db7 | SketchChatPage.vue |

## Implementation Details

### Task 1: EntityLayout Views (16 files)

The pattern applied to all 16 views:

```typescript
async function loadXxx() {
  try {
    const data = await api.get(id.value);
    // ... set refs ...
    return data;
  } catch (err) {
    handleApiError(err, showToast, 'Failed to load {entity}');
    throw err; // Re-throw so EntityLayout displays its error UI
  }
}
```

**Views that required useToast added:**
- `GenericTriggerHistory.vue` -- had no useToast import at all
- `SuperAgentPlayground.vue` -- had no useToast import at all

**Views with pre-existing try/catch updated:**
- `ProjectPlanningPage.vue` -- had `showToast('Failed to load planning data', 'error')` replaced with `handleApiError(err, showToast, 'Failed to load planning data')` for structured error formatting

All other 13 views had their loadEntity functions wrapped with new try/catch blocks calling handleApiError before re-throwing.

**Invariant maintained:**
- No EntityLayout view gained LoadingState, ErrorState, or a separate isLoading ref
- EntityLayout continues to provide inline error UI and retry natively
- The re-throw after handleApiError is essential for EntityLayout to show its error UI

### Task 2: Non-EntityLayout Views (5 views assessed)

**SketchChatPage.vue** -- Full loading/error pattern added:
- Added `isLoading = ref(true)` and `loadError = ref<string | null>(null)`
- Added `LoadingState` and `ErrorState` component imports
- Added `handleApiError` import
- Created `loadInitialData()` wrapping `Promise.all([loadProjects(), loadSketches()])` with finally-based isLoading tracking
- Since `useSketchChat` composable swallows errors into `error.value` (not throws), `loadError` is set by checking `error.value` after the calls complete. The existing `error` watcher already shows toasts, avoiding double-notification.
- Template wrapped: `<LoadingState v-if="isLoading">` / `<ErrorState v-else-if="loadError" @retry="loadInitialData">` / `<div v-else class="sketch-chat-page">`

**AgentCreateWizard, PluginDesignPage, SkillCreateWizard** -- Verified and left unchanged:
- All three call `conversation.startConversation()` in onMounted (fire-and-forget, not awaited)
- `useConversation.startConversation()` has a full try/catch internally that shows toast notifications on both `ApiError` and generic Error types
- No additional error handling needed

**WorkflowPlaygroundPage** -- Verified and left unchanged:
- Zero `onMounted` calls (confirmed by grep)
- No blocking initial API fetch -- page renders immediately with interactive AI chat interface

## Verification Results

- Frontend tests: 409/409 passed (33 test files)
- Frontend production build: PASSED (vue-tsc + vite build)
- All 16 EntityLayout views import handleApiError: PASSED
- No EntityLayout view imports LoadingState: PASSED (grep returns zero matches)
- SketchChatPage imports LoadingState, ErrorState, and handleApiError: PASSED
- WorkflowPlaygroundPage has zero onMounted calls: PASSED
- All views use useToast() composable (not raw inject): PASSED

## Self-Check: PASSED

All 17 modified files exist, both commits verified, pattern applied correctly to all targets.
