---
phase: 01-web-ui-roadmapping-feature
wave: all
plans_reviewed: [01-01, 01-02, 01-03, 01-04, 01-05]
timestamp: 2026-02-28T02:30:00+09:00
blockers: 0
warnings: 3
info: 6
verdict: warnings_only
---

# Code Review: Phase 01 (Web UI Roadmapping Feature)

## Verdict: WARNINGS ONLY

All five plans executed to completion with no missing tasks and no critical defects. The implementation faithfully follows the plan specifications, CONTEXT.md locked decisions, and research pitfall guidance. Three warnings identified: an untracked file referenced by committed code, undocumented extra endpoints beyond plan scope, and lack of thread-safety on the planning session tracker. Six informational findings noted.

## Stage 1: Spec Compliance

### Plan Alignment

**Plan 01-01 (Backend GRD Planning Service & Schema)**

All plan tasks executed and verified:

- Task 1: `GrdPlanningService` created at `/Users/edward.seo/dev/private/project/harness/Agented/backend/app/services/grd_planning_service.py` (275 lines). All four required methods present: `invoke_command`, `get_active_planning_session`, `unregister_session`, `get_init_status`. Class-level `_active_planning_sessions` dict implemented. Commit `5274f3f`.
- Task 2: `grd_init_status TEXT DEFAULT 'none'` column added to schema (line 320 of `schema.py`), migration v54 added to `migrations.py` (idempotent ALTER TABLE), `update_project()` extended with `grd_init_status` parameter, two planning endpoints added to `grd.py`. Commit `5431eef`.

| Finding | Severity |
|---------|----------|
| W1: Commit `5431eef` adds significantly more than the two planning endpoints specified in plan. Additional endpoints include `create_phase`, `create_plan`, `update_plan`, `delete_plan`, `project_chat`, `project_chat_stream`, plus associated models (`CreatePlanBody`, `UpdatePlanBody`, `ProjectChatBody`, `CreatePhaseBody`). These ~350 extra lines in `grd.py` are not documented in SUMMARY.md or the plan. | WARNING |

SUMMARY.md for 01-01 states "Deviations: None" but the commit scope is materially larger than planned.

**Plan 01-02 (Frontend Composable & Route)**

All plan tasks executed and verified:

- Task 1: `usePlanningSession` composable at `/Users/edward.seo/dev/private/project/harness/Agented/frontend/src/composables/usePlanningSession.ts` (208 lines, meets min_lines: 100). All required exports present: `sessionId`, `outputLines`, `status`, `currentQuestion`, `exitCode`, `invokeCommand`, `sendAnswer`, `stopSession`, `clearOutput`. SSE event handling for `message`, `output`, `question`, `complete`, `error` implemented. EventSource cleanup on `onUnmounted()`. Auto-reconnect with 3-error circuit breaker. Commit `f7f988a`.
- Task 2: `grdApi` extended with `invokePlanningCommand()` (line 283) and `getPlanningStatus()` (line 297). `PlanningStatus` and `InvokePlanningCommandRequest` types added to `types.ts`. Route registered at `/projects/:projectId/planning` with name `project-planning`. Minimal `ProjectPlanningPage.vue` placeholder created (correctly noted as deviation in SUMMARY). Commit `9c15c68`.

No issues found. Deviation (placeholder view) properly documented.

**Plan 01-03 (Planning Page UI Components)**

All three tasks executed and verified:

- Task 1: `ProjectPlanningPage.vue` at `/Users/edward.seo/dev/private/project/harness/Agented/frontend/src/views/ProjectPlanningPage.vue` (284 lines, meets min_lines: 200). Split layout implemented. Commit `31c9c69`.
- Task 2: `PlanningCommandBar.vue` (201 lines, meets min_lines: 80) with 17 commands in 4 groups exactly matching the plan specification. `MilestoneOverview.vue` extended with `phaseCommand` emit and per-phase action buttons (Discuss, Plan, Research). Commit `f2a7927`.
- Task 3: `PlanningSessionPanel.vue` (519 lines, meets min_lines: 150) with markdown rendering via `renderMarkdown()` (marked + dompurify), question widgets for select/multiselect/text/password, status bar, Stop/Clear actions, auto-scroll via `useAutoScroll`. Commit `e68c3bb`.

No issues found. All artifacts meet or exceed min_lines requirements.

**Plan 01-04 (Backend Auto-Init & Session-Completion Sync)**

Both tasks executed and verified:

- Task 1: `auto_init_project()` method added (line 162). `_run_init_session()` helper with 2s polling and 10-minute timeout. `sync_on_session_complete()` added to `GrdSyncService`. Session-completion hook wired into `ProjectSessionManager._handle_session_exit()` -- sync call at lines 341-365, broadcast at line 370 (sync correctly BEFORE broadcast per RESEARCH.md Pitfall 2). Commit `2254293`.
- Task 2: Auto-init wired into `projects.py` `create_project()` route. Local path projects trigger immediately (line 116), GitHub projects use clone-wait thread (line 134). Response includes `grd_init_status`. Commit `6a0f441`.

No issues found.

**Plan 01-05 (Navigation & GRD Settings)**

Both tasks executed and verified:

- Task 1: Planning button added to `ProjectDashboard.vue` at line 386, LEFT of Management button at line 393 (per CONTEXT.md locked decision). Init status badge with initializing/ready/failed states. Polling via 5s interval with watch-based lifecycle. Toast notifications on status transitions. Commit `41ee2c5`.
- Task 2: `GrdSettings.vue` (145 lines, meets min_lines: 50). `SettingsPage.vue` extended with `grd` tab. `AppSidebar.vue` updated with planning link. Commit `bcc1626`.

No issues found.

### Research Methodology

N/A -- no research references in plans. KNOWHOW.md, LANDSCAPE.md, and PAPERS.md are all initialized but empty (appropriate for a web feature phase).

### Context Decision Compliance

All locked decisions from CONTEXT.md verified:

1. **"No reimplementation of GRD logic in Python"** -- `GrdPlanningService` only manages session lifecycle, delegates to Claude CLI PTY sessions. Confirmed in docstring and implementation.
2. **"Reuse existing PTY session + InteractiveSetup pattern"** -- `usePlanningSession.ts` follows `useProjectSession.ts` and `InteractiveSetup.vue` patterns. `GrdPlanningService.invoke_command()` uses `get_handler("direct")`.
3. **"Planning button on project dashboard, placed left of the existing Management button"** -- Confirmed in template: Planning at line 386, Management at line 393.
4. **"GRD settings in a new tab on the existing Settings page"** -- `SettingsPage.vue` has `grd` in `TAB_NAMES` array, `GrdSettings` component renders on tab selection.

Deferred ideas verified NOT implemented:

- Execution commands (`execute-phase`, `autopilot`, `evolve`, `progress`) -- not present in `PlanningCommandBar.vue` or `ProjectPlanningPage.vue`.
- `@vue-flow/core` graph visualization -- not imported anywhere in new code.
- Bidirectional file sync -- not implemented.

No issues found.

### Known Pitfalls (KNOWHOW.md)

N/A -- KNOWHOW.md is initialized but empty. Phase-specific pitfalls from RESEARCH.md were addressed:

- Pitfall 2 (Session Completion Race Condition): Sync call placed BEFORE broadcast in `_handle_session_exit()` (lines 341-365 before line 370).
- Pitfall 4 (Background Auto-Init Failing Silently): Status tracked via `grd_init_status` column with `failed` terminal state.
- EventSource cleanup on unmount: `onUnmounted(closeEventSource)` at line 195 of `usePlanningSession.ts`.

### Eval Coverage

EVAL.md (`01-EVAL.md`) is comprehensive with 9 sanity checks, 8 proxy metrics, and 6 deferred validations.

All sanity checks (S1-S9) can be computed from the implementation:

- S4 (`GrdPlanningService` import): methods `invoke_command`, `get_active_planning_session`, `get_init_status`, `unregister_session`, `auto_init_project` all present.
- S6 (schema column): `grd_init_status` appears in `schema.py` (line 320), `migrations.py` (line 2961), `projects.py` (line 67).
- S7 (route): `project-planning` registered in `projects.ts` (line 33).
- S8 (composable): all six named exports present.
- S9 (types): `PlanningStatus` and `InvokePlanningCommandRequest` at lines 1152 and 1157 of `types.ts`.

No issues found.

## Stage 2: Code Quality

### Architecture

Implementation follows existing project patterns consistently:

- **Backend**: `GrdPlanningService` uses the classmethod singleton pattern matching `GrdSyncService` and `ExecutionLogService`. Database functions follow the `update_project()` kwargs pattern. Routes use `APIBlueprint` with Pydantic models per `flask-openapi3` conventions. Migration uses the try/except ALTER TABLE idiom.
- **Frontend**: Composable follows `useProjectSession.ts` pattern. API methods follow `apiFetch<T>()` pattern in `grdApi`. Route registered in `projectRoutes` with lazy import. Components use scoped CSS with dark theme variables (`--bg-secondary`, `--text-primary`, etc.).

| Finding | Severity |
|---------|----------|
| W2: `backend/app/services/project_chat_service.py` (172 lines) is present as an untracked file in the working directory but is imported by committed code in `grd.py` (line 468, lazy import inside `project_chat` endpoint). While this import is lazy and won't cause import-time failures, the `project_chat` and `project_chat_stream` endpoints in committed `grd.py` will fail at runtime with `ImportError` if the file is not committed. This file is not part of any Phase 01 plan. | WARNING |
| I1: The extra endpoints in `grd.py` (CRUD for phases/plans, project chat) appear to be useful supporting functionality for the planning page but were not specified in any plan. They are well-structured and follow existing patterns. | INFO |

### Reproducibility

N/A -- no experimental code. This is a web feature implementation.

### Documentation

| Finding | Severity |
|---------|----------|
| I2: `GrdPlanningService` docstring correctly references the locked decision about no Python reimplementation of GRD logic. Good practice. | INFO |
| I3: `usePlanningSession.ts` includes JSDoc comments describing each method's purpose and its relationship to the backend patterns. | INFO |
| I4: The `_run_init_session` method assumes success when `info is None` (line 263: `return True  # Session cleaned up, assume success`). While this matches the plan specification, a comment explaining WHY this assumption is safe (or noting it as a known limitation) would improve maintainability. | INFO |

### Deviation Documentation

**Plan 01-01 SUMMARY.md:**

States "Deviations: None" but commit `5431eef` includes ~350 lines of additional endpoints (`create_phase`, `create_plan`, `update_plan`, `delete_plan`, `project_chat`, `project_chat_stream`) beyond the two planning endpoints specified in the plan. SUMMARY key_files lists only the expected files and does not mention the extra endpoints.

| Finding | Severity |
|---------|----------|
| W3: SUMMARY.md for Plan 01-01 does not document the significant additional scope (CRUD endpoints, project chat endpoints) added to `grd.py` beyond the two planning endpoints specified in the plan. These additions are not harmful but represent undocumented deviation from plan scope. | WARNING |

**Plan 01-02 SUMMARY.md:**

Deviation (placeholder `ProjectPlanningPage.vue`) properly documented with reasoning. Matches actual git history.

**Plan 01-03 SUMMARY.md:**

States "Deviations: None." Git history confirms three clean commits matching task descriptions exactly. Accurate.

**Plan 01-04 SUMMARY.md:**

Key decisions documented. `key_files` section matches actual files modified in commits `2254293` and `6a0f441`. Accurate.

**Plan 01-05 SUMMARY.md:**

Key decisions documented. Files modified match. Accurate.

| Finding | Severity |
|---------|----------|
| I5: The `_active_planning_sessions` dict in `GrdPlanningService` is accessed from multiple threads (Flask request handlers, background init thread, session-completion hook in `ProjectSessionManager`) without a `threading.Lock`. Python's GIL provides some protection for simple dict operations, but this is not guaranteed for all dict mutation patterns. EVAL.md correctly identifies this as DEFER-01-06. | INFO |
| I6: All five SUMMARY.md files follow a consistent format with frontmatter, task descriptions, deviations section, and verification results. Good documentation hygiene. | INFO |

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| W1 | WARNING | 1 | Plan Alignment | Plan 01-01 commit `5431eef` adds ~350 lines of extra endpoints (CRUD + project chat) beyond the two planning endpoints specified. Undocumented scope expansion. |
| W2 | WARNING | 2 | Architecture | `project_chat_service.py` is untracked but imported by committed `grd.py` code. Runtime `ImportError` will occur when `project_chat` endpoints are called. |
| W3 | WARNING | 2 | Deviation Docs | Plan 01-01 SUMMARY states "Deviations: None" despite significantly larger commit scope than planned. |
| I1 | INFO | 2 | Architecture | Extra endpoints in `grd.py` are well-structured and follow existing patterns. |
| I2 | INFO | 2 | Documentation | Service docstrings correctly reference locked CONTEXT.md decisions. |
| I3 | INFO | 2 | Documentation | Composable includes good JSDoc documentation. |
| I4 | INFO | 2 | Documentation | `_run_init_session` assumes success when session info is None -- comment explaining reasoning would help. |
| I5 | INFO | 2 | Architecture | `_active_planning_sessions` dict accessed from multiple threads without lock. Acceptable for MVP; identified in EVAL.md DEFER-01-06. |
| I6 | INFO | 2 | Deviation Docs | SUMMARY files follow consistent format across all five plans. |

## Recommendations

**W1 + W3 (Undocumented scope expansion in Plan 01-01):** Update `01-01-SUMMARY.md` to document the additional CRUD and project chat endpoints added to `grd.py`. Even if these were useful and desirable, plan summaries should accurately reflect what was built. This is a documentation fix, not a code fix.

**W2 (Untracked `project_chat_service.py`):** Either commit the file (it supports the project chat endpoints already in committed `grd.py`) or remove the project chat endpoints from `grd.py` if they are not intended for this phase. The current state will cause runtime errors when those endpoints are called. Recommended action: `git add backend/app/services/project_chat_service.py` and commit it with a descriptive message.

---

*Review by: Claude (grd-reviewer)*
*Review date: 2026-02-28*
