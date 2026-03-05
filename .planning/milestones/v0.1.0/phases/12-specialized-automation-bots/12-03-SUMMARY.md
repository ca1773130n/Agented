---
phase: 12-specialized-automation-bots
plan: "03"
subsystem: specialized-bots-api-frontend
tags: [api-routes, frontend, search-ui, sidebar, fts5]
dependency_graph:
  requires: ["12-01", "12-02"]
  provides: ["specialized-bot-status-api", "specialized-bot-health-api", "execution-search-ui"]
  affects: ["frontend-navigation", "admin-routes"]
tech_stack:
  added: []
  patterns: ["APIBlueprint admin route", "specializedBotApi frontend module", "FTS5 snippet v-html rendering"]
key_files:
  created:
    - backend/app/routes/specialized_bots.py
    - frontend/src/services/api/specialized-bots.ts
    - frontend/src/views/ExecutionSearchPage.vue
  modified:
    - backend/app/routes/__init__.py
    - frontend/src/services/api/types.ts
    - frontend/src/services/api/index.ts
    - frontend/src/router/routes/misc.ts
    - frontend/src/components/layout/AppSidebar.vue
decisions:
  - "Standalone sidebar button for Execution Search (not expandable group) since it's a single destination"
  - "Search functions included in specializedBotApi (not separate module) per plan guidance"
  - "v-html for FTS5 snippets with XSS safety note since content is from our own database"
metrics:
  duration: "14min"
  completed: "2026-03-05"
---

# Phase 12 Plan 03: Specialized Bot API Routes & Search UI Summary

Backend API routes for specialized bot status/health, frontend API client with TypeScript types, and ExecutionSearchPage with BM25-ranked search results and sidebar navigation.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Specialized bot API routes and frontend API client | 38714ef | specialized_bots.py, specialized-bots.ts, types.ts |
| 2 | ExecutionSearchPage view with search UI and navigation | 1af2c7c | ExecutionSearchPage.vue, misc.ts, AppSidebar.vue |

## Implementation Details

### Task 1: API Routes & Frontend Client

- Created `GET /admin/specialized-bots/status` returning availability of all 7 predefined bots (trigger_exists, skill_file_exists, trigger_source, enabled)
- Created `GET /admin/specialized-bots/health` returning gh_authenticated, osv_scanner_available, search_index_count
- Blueprint registered with 120/minute rate limit in admin_blueprints
- Frontend `specializedBotApi` with getStatus, getHealth, searchLogs, getSearchStats
- TypeScript types: SpecializedBotStatus, SpecializedBotHealth, ExecutionSearchResult, ExecutionSearchResponse, ExecutionSearchStats

### Task 2: Search UI & Navigation

- ExecutionSearchPage with text search input, optional trigger ID filter, and search button
- Results display: trigger name, status badge (color-coded), date, execution ID, and highlighted FTS5 snippets
- Three UI states: initial prompt, loading spinner, no results with suggestion, result list with count
- FTS5 `<mark>` tags rendered via `v-html` with XSS safety comment
- Route registered at `/execution-search` (lazy-loaded)
- Sidebar: standalone nav button with search icon in History section, between Triggers and Usage groups

## Verification Results

- `just build`: PASS (frontend builds without TypeScript errors)
- `cd frontend && npm run test:run`: PASS (409/409 tests)
- `cd backend && uv run pytest`: 712 passed, 1 pre-existing failure (test_post_execution_hooks.py - unrelated)
- Route registration: confirmed via grep
- Sidebar link: confirmed via grep

## Deviations from Plan

### Minor Adjustments

**1. [Plan Adjustment] No expandedSections entry for execution search**
- Plan mentioned adding `executionSearch` to `expandedSections` and `isExecutionSearchActive()` check
- Since the nav item is a standalone button (not an expandable group with submenu), these are unnecessary
- Active state handled directly via `currentRouteName === 'execution-search'`

**2. [Plan Adjustment] No DefaultLayout wrapper**
- Plan mentioned using DefaultLayout, but no such component exists in the codebase
- Followed existing view pattern (ExecutionHistory.vue) with AppBreadcrumb and PageHeader instead

## Self-Check: PASSED
