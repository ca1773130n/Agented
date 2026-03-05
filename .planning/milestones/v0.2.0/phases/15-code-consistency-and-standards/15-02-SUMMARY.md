---
phase: 15-code-consistency-standards
plan: 02
subsystem: frontend
tags: [type-safety, composables, typescript, refactoring]
dependency_graph:
  requires: [15-01]
  provides: [useAsyncState-composable, unified-type-system]
  affects: [frontend-components, frontend-services, frontend-composables]
tech_stack:
  added: []
  patterns: [unknown-catch-narrowing, eslint-disable-justification, typed-event-handlers]
key_files:
  created:
    - frontend/src/composables/useAsyncState.ts
  modified:
    - frontend/src/composables/useSketchChat.ts
    - frontend/src/composables/useStreamingGeneration.ts
    - frontend/src/composables/useCanvasLayout.ts
    - frontend/src/layouts/EntityLayout.vue
    - frontend/src/services/api/backends.ts
    - frontend/src/components/sketches/SketchClassification.vue
    - frontend/src/components/sketches/SketchRouting.vue
    - frontend/src/components/canvas/TeamCanvas.vue
    - frontend/src/components/canvas/CanvasSidebar.vue
    - frontend/src/components/canvas/OrgCanvas.vue
    - frontend/src/components/canvas/AgentDetailPanel.vue
    - frontend/src/components/projects/ProjectTeamCanvas.vue
    - frontend/src/components/base/DataTable.vue
    - frontend/src/components/monitoring/MonitoringSection.vue
    - frontend/src/components/monitoring/TokenUsageChart.vue
    - frontend/src/components/monitoring/CombinedUsageChart.vue
    - frontend/src/components/monitoring/RemainingTimeChart.vue
    - frontend/src/components/monitoring/RotationTimelineChart.vue
    - frontend/src/components/monitoring/BudgetLimitForm.vue
    - frontend/src/components/analytics/CostTrendChart.vue
    - frontend/src/components/analytics/BotEffectivenessChart.vue
    - frontend/src/components/analytics/SuccessRateChart.vue
    - frontend/src/components/analytics/ExecutionVolumeChart.vue
    - frontend/src/components/triggers/ExecutionLogViewer.vue
    - frontend/src/views/SuperAgentsPage.vue
    - frontend/src/views/HooksPage.vue
    - frontend/src/views/RulesPage.vue
    - frontend/src/views/CommandsPage.vue
    - frontend/src/views/TeamsPage.vue
    - frontend/src/views/WorkflowsPage.vue
    - frontend/src/views/AIBackendsPage.vue
    - frontend/src/views/PluginsPage.vue
    - frontend/src/views/ProjectsPage.vue
    - frontend/src/views/ProductsPage.vue
    - frontend/src/views/AgentsPage.vue
    - frontend/src/views/McpServersPage.vue
    - frontend/src/views/BackendDetailPage.vue
    - frontend/src/views/ExecutionHistory.vue
    - frontend/src/views/ExploreMcpServers.vue
    - frontend/src/views/ExploreSuperAgents.vue
    - frontend/src/views/AgentDesignPage.vue
    - frontend/src/views/TeamBuilderPage.vue
    - frontend/src/views/ProjectDashboard.vue
    - frontend/src/views/SketchChatPage.vue
decisions:
  - "ChatMessage interface removed from useSketchChat.ts; ConversationMessage from types.ts used as canonical type"
  - "DataTable.vue retains any[] for items prop with eslint-disable -- generic component accepting any shape"
  - "Chart.js callbacks retain any with eslint-disable justifications -- library types are overly complex"
  - "Vue Flow event handlers retain any with eslint-disable -- library event types are dynamic"
  - "MonitoringSection monitoring window objects retain any with eslint-disable -- variable shape from backend API"
  - "Test files not targeted for any removal -- acceptable in test context per plan guidance"
metrics:
  duration: 17min
  completed: "2026-03-06"
---

# Phase 15 Plan 02: Frontend Type Consolidation and useAsyncState Composable

Consolidated duplicate ChatMessage into canonical ConversationMessage type, eliminated TypeScript any from 45 component and service files, and created a shared useAsyncState composable for consistent async lifecycle management.

## Task Results

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | Consolidate ChatMessage and eliminate TypeScript any | b2cba61 | Done |
| 2 | Create useAsyncState composable | eda726c | Done |

## Changes Made

### Task 1: Type Consolidation and any Elimination

**ChatMessage removal (CON-08):**
- Removed `ChatMessage` interface definition from `useSketchChat.ts`
- Changed `messages` ref type from `ChatMessage[]` to `ConversationMessage[]`
- Updated `SketchChatPage.vue` to pass messages directly (no mapping needed)
- Zero ChatMessage references remain (verified by grep)

**TypeScript any elimination (CON-08):**
- Replaced 40+ `catch (e: any)` patterns with `catch (e: unknown)` and `instanceof Error` narrowing across all views and components
- Replaced 12+ unnecessary `(x: any) => x.id` lambda type annotations with type inference in WebMCP page tools modal actions
- Added proper types for canvas components: `Agent`, `SuperAgent`, `TeamMember`, `TopologyConfig`
- Created `SketchClassificationData` and `SketchRoutingData` interfaces replacing `Record<string, any>`
- Typed `checkRateLimits` return type to include `needs_login` and `account_id` fields
- Changed `useStreamingGeneration` generic default from `any` to `unknown`
- Replaced `Record<string, any>` with `Record<string, number>` in `useCanvasLayout.ts`
- Used `EffortLevel` and `Agent['backend_type']` casts instead of `as any` in `AgentDesignPage.vue`
- Typed `ExploreSuperAgents.vue` with `MarketplaceSearchResult` instead of `any[]`
- Typed `ProjectDashboard.vue` and related components with `TeamMember[]` instead of `any[]`

**Justified exceptions (with eslint-disable):**
- `DataTable.vue` items/row-click: Generic component requires any for polymorphic usage
- Chart.js tooltip callbacks (6 files): Library callback types are overly complex
- Vue Flow event handlers (3 files): Library event types are dynamic
- Monitoring window objects (MonitoringSection.vue): Variable shape from backend API

### Task 2: useAsyncState Composable (CON-09)

- Created `frontend/src/composables/useAsyncState.ts` with generic `UseAsyncStateReturn<T>` interface
- Provides `data`, `isLoading`, `error` refs and `execute()` function
- Uses `unknown` catch type with `instanceof Error` narrowing (matches CON-08 pattern)
- Infrastructure for future composable adoption; no existing composables refactored (per plan)
- SSE setup code confirmed already centralized via `createAuthenticatedEventSource` (no duplication to fix)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed MonitoringSection eslint-disable comment breaking code**
- **Found during:** Task 1
- **Issue:** `replace_all` for `(win: any)` placed eslint-disable comments mid-expression, breaking `=== windowType` onto comment line
- **Fix:** Used `eslint-disable-next-line` on separate line above the expression
- **Files modified:** `MonitoringSection.vue`
- **Commit:** b2cba61

**2. [Rule 1 - Bug] Fixed DataTable Record<string, unknown> breaking consumers**
- **Found during:** Task 1 verification
- **Issue:** Changing DataTable items from `any[]` to `Record<string, unknown>[]` caused type errors in SecurityDashboard, TeamsSummaryDashboard, and UsageHistoryPage
- **Fix:** Reverted to `any[]` with eslint-disable justification -- DataTable is a generic component
- **Files modified:** `DataTable.vue`
- **Commit:** b2cba61

## Verification

- `grep -rn 'interface ChatMessage' frontend/src/` returns empty (zero definitions)
- `cd frontend && npm run build` passes (vue-tsc + vite, zero errors)
- `cd frontend && npm run test:run` passes (409 tests, 33 test files)
- `test -f frontend/src/composables/useAsyncState.ts` succeeds

## Self-Check: PASSED

- [x] frontend/src/composables/useAsyncState.ts exists
- [x] Commit b2cba61 exists (Task 1)
- [x] Commit eda726c exists (Task 2)
- [x] Zero ChatMessage interface definitions
- [x] Frontend builds with zero errors
- [x] All 409 frontend tests pass
