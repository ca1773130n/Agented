# Evaluation Plan: Phase 01 — Web UI Roadmapping Feature

**Designed:** 2026-02-28
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Full-stack web feature integration — PTY session management, SSE streaming, Vue 3 SPA routing, SQLite schema migration
**Reference materials:** 01-RESEARCH.md, 01-CONTEXT.md, 01-01-PLAN.md through 01-05-PLAN.md, .planning/codebase/TESTING.md

---

## Evaluation Overview

This phase adds a dedicated GRD Planning page to the Agented web UI across five sequential plans in three waves. The feature integrates deeply with existing infrastructure: `ProjectSessionManager` (PTY sessions), `GrdSyncService` (file-to-DB sync), and the existing GRD API routes. Because over 80% of the required infrastructure already exists in the codebase, evaluation focuses on correctness of integration wiring, not invention of new mechanisms.

This is a web feature phase, not an ML/R&D phase. There are no paper metrics, no benchmark datasets, and no statistical targets. Quality metrics are defined by the product requirements: all 17 planning commands must be invokable from the UI, the planning page must render with correct data, and the background auto-initialization must track state reliably. The five plans deliver in three waves, each buildable independently within wave constraints, with earlier waves establishing infrastructure consumed by later waves.

The evaluation is designed around three primary risks: (1) type or integration errors that surface only at build time or in the browser, (2) race conditions in the session-completion DB sync sequence, and (3) silent failure of background auto-initialization. Proxy metrics target these risks directly with automated checks that can run in a CI environment without a live backend.

There are no available benchmarks for this phase — BENCHMARKS.md is initialized but empty, which is appropriate for a web feature phase. Success criteria come entirely from the phase requirements and research recommendations.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| `just build` exits 0 (vue-tsc + vite) | CLAUDE.md verification protocol | TypeScript type errors cannot be caught by unit tests alone — this is mandatory per project rules |
| `uv run pytest` all pass | CLAUDE.md verification protocol | Existing tests must not regress — schema migrations and new imports must not break the 40+ existing test files |
| `npm run test:run` all pass | CLAUDE.md verification protocol | Frontend unit tests must not regress |
| GrdPlanningService imports cleanly | 01-01-PLAN.md task verify | New module must be importable without errors before any integration |
| `grd_init_status` column exists in schema | 01-01-PLAN.md must_haves | DB migration correctness — required field for all subsequent plans |
| New endpoints respond to curl | 01-01-PLAN.md verification L2 | API surface is reachable from the frontend |
| TypeScript compiles for composable and routes | 01-02-PLAN.md task verify | Composable and route must type-check even before the view component exists |
| Planning page renders at /projects/:id/planning | 01-03-PLAN.md verification L2 | Core deliverable — page must load without errors |
| Command buttons dispatch POST to /planning/invoke | 01-03-PLAN.md verification L2 | Commands must reach the backend when clicked |
| `auto_init_project` and `sync_on_session_complete` methods exist | 01-04-PLAN.md task verify | Background orchestration methods must be present |
| Planning button visible on ProjectDashboard | 01-05-PLAN.md verification L2 | Navigation entry point must be correct and correctly ordered |
| GRD settings tab renders at /settings#grd | 01-05-PLAN.md verification L2 | Settings entry point must be reachable |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 9 | Build correctness, module imports, test regression, structural invariants |
| Proxy (L2) | 8 | API surface, UI rendering, data loading, command dispatch, navigation |
| Deferred (L3) | 6 | Full end-to-end GRD sessions, cross-browser behavior, concurrent isolation |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

All sanity checks are executable without a running backend, without live PTY sessions, and without the Claude CLI installed.

### S1: Frontend Build — TypeScript Type Check + Vite Bundle

- **What:** The full production build must complete without errors. `vue-tsc` catches interface mismatches between composables, API types, and component props that unit tests do not surface.
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented && just build`
- **Expected:** Exit code 0. No `error TS` lines in output. Vite bundle output shows all chunks built successfully.
- **Failure means:** A type error exists in the new code — composable return type mismatch, missing prop definition, incorrect API response type, or lazy route import issue. Fix before declaring any plan complete.

### S2: Backend Test Suite — No Regressions

- **What:** All existing backend tests must pass after schema changes, new imports, and route additions. The `isolated_db` fixture auto-migrates, so `grd_init_status` column migration must be idempotent.
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest -x`
- **Expected:** All tests pass. Zero failures, zero errors. The `-x` flag stops at first failure to surface issues immediately.
- **Failure means:** A migration is non-idempotent, a new import introduces a circular dependency, or a new route registration conflicts with an existing blueprint. The most likely failure point is `migrations.py` — the `ALTER TABLE` idiom must use `try/except` to be idempotent.

### S3: Frontend Test Suite — No Regressions

- **What:** All existing Vitest unit tests must pass after extending `MilestoneOverview.vue`, modifying `SettingsPage.vue`, and adding new routes.
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/frontend && npm run test:run`
- **Expected:** All tests pass. No existing test failures.
- **Failure means:** A component modification broke an existing behavior. The highest-risk modification is `MilestoneOverview.vue` (extended with `phaseCommand` emit and phase action buttons) — any prop signature change or template restructuring could break existing tests if they assert on DOM structure.

### S4: GrdPlanningService Module Import

- **What:** The new Python service module must be importable without errors — no missing dependencies, no circular imports, correct class structure.
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.services.grd_planning_service import GrdPlanningService; print('OK'); print([m for m in dir(GrdPlanningService) if not m.startswith('_')])"`
- **Expected:** Prints `OK` followed by a list that includes `invoke_command`, `get_active_planning_session`, `get_init_status`, `unregister_session`, `auto_init_project`.
- **Failure means:** Import error (circular dependency, missing module) or method not defined. Diagnose with full traceback.

### S5: GrdSyncService New Method Exists

- **What:** The `sync_on_session_complete` method added to `GrdSyncService` must be present and importable.
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.services.grd_sync_service import GrdSyncService; assert hasattr(GrdSyncService, 'sync_on_session_complete'), 'Method missing'; print('sync_on_session_complete: OK')"`
- **Expected:** Prints `sync_on_session_complete: OK`
- **Failure means:** Method was not added to the service, or was added under a different name. Check 01-04-PLAN.md task 1 step 2.

### S6: DB Schema Contains grd_init_status Column

- **What:** The `projects` table schema must include `grd_init_status TEXT DEFAULT 'none'`. Both the `CREATE TABLE` statement in `schema.py` and the `ALTER TABLE` migration in `migrations.py` must be consistent.
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.database import init_db, get_connection; import tempfile, os; f = tempfile.mktemp(suffix='.db'); os.environ['DB_PATH_OVERRIDE']='ignored'; exec(open('app/config.py').read() if False else ''); from app import config; config.DB_PATH = f; init_db(); conn = __import__('sqlite3').connect(f); cols = [r[1] for r in conn.execute('PRAGMA table_info(projects)').fetchall()]; print('grd_init_status in schema:', 'grd_init_status' in cols); conn.close()"`
- **Expected:** Prints `grd_init_status in schema: True`
- **Failure means:** Migration was not applied or column name is wrong. Simplest check: `grep -n "grd_init_status" backend/app/db/schema.py backend/app/db/migrations.py` — must appear in both files.

### S7: Planning Route Registered in Frontend Router

- **What:** The route `/projects/:projectId/planning` must be present in the project routes file with the correct name `project-planning`.
- **Command:** `grep -n "project-planning" /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/router/routes/projects.ts`
- **Expected:** At least one matching line containing `name: 'project-planning'` or the route path string.
- **Failure means:** Route was not registered. Frontend navigation will 404. Add route per 01-02-PLAN.md task 2 step 3.

### S8: usePlanningSession Composable Exists with Required Exports

- **What:** The composable file must exist and export a function with the expected return shape. TypeScript compilation (S1) validates types, but this check confirms the file exists and has the function declaration.
- **Command:** `grep -n "export function usePlanningSession\|invokeCommand\|sendAnswer\|stopSession\|clearOutput\|outputLines\|currentQuestion" /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/composables/usePlanningSession.ts`
- **Expected:** All six names appear in the file output.
- **Failure means:** Composable was not fully implemented. Cross-check with 01-02-PLAN.md task 1 return type spec.

### S9: No NaN / Undefined in API Type Definitions

- **What:** The `PlanningStatus` interface and `InvokePlanningCommandRequest` type must be present in the types file.
- **Command:** `grep -n "PlanningStatus\|InvokePlanningCommandRequest\|grd_init_status" /Users/edward.seo/dev/private/project/harness/Agented/frontend/src/services/api/types.ts`
- **Expected:** At least three matching lines, including the interface definitions.
- **Failure means:** Types were not added. The composable will use implicit `any`, and contract mismatches will not be caught at compile time.

**Sanity gate:** ALL nine sanity checks must pass. Any failure blocks progression to proxy evaluation and marks the phase incomplete.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of feature correctness. These require a running backend and browser, but do not require live PTY sessions with the Claude CLI.

**IMPORTANT:** Proxy metrics are NOT validated substitutes for full end-to-end evaluation. A check that "the planning page renders" does not confirm that GRD commands execute successfully. Treat all proxy results with appropriate skepticism.

### P1: Backend Planning Endpoints Respond Correctly

- **What:** The two new planning API endpoints are reachable, return correct content types, and handle both valid and invalid project IDs gracefully.
- **How:** Start the dev backend and send HTTP requests via curl or httpx.
- **Command:**
  ```bash
  # Start backend: just dev-backend (in a separate terminal)

  # Test status endpoint with a non-existent project (expect 404 or error response)
  curl -s -o /dev/null -w "%{http_code}" http://localhost:20000/api/projects/proj-fake99/planning/status

  # Test invoke endpoint with missing command (expect 422 validation error)
  curl -s -X POST http://localhost:20000/api/projects/proj-fake99/planning/invoke \
    -H "Content-Type: application/json" \
    -d '{}' -w "\nHTTP %{http_code}\n"

  # Test invoke endpoint with valid command body (expect session_id or project-not-found error)
  curl -s -X POST http://localhost:20000/api/projects/proj-fake99/planning/invoke \
    -H "Content-Type: application/json" \
    -d '{"command": "map-codebase"}' -w "\nHTTP %{http_code}\n"
  ```
- **Target:** Status endpoint returns HTTP 404 or a JSON `{"error": "..."}` (not 500). Invoke endpoint with missing `command` returns HTTP 422. Invoke endpoint with valid body returns HTTP 200 (with `{"error": "Project not found"}`) or 500 only if ProjectSessionManager is not initialized in test context.
- **Evidence:** Endpoint correctness directly verifiable from API surface — no correlation assumptions needed.
- **Correlation with full metric:** HIGH — if the endpoints do not respond correctly, the frontend cannot function regardless of UI implementation.
- **Blind spots:** Does not confirm PTY session creation works (requires Claude CLI). Does not confirm SSE streaming delivers events. Does not confirm single-session enforcement triggers correctly.
- **Validated:** No — awaiting deferred validation at integration testing.

### P2: Planning Page Renders at Correct Route

- **What:** Navigating to `/projects/{projectId}/planning` renders the `ProjectPlanningPage` without JavaScript errors, shows the split-layout structure (left panel + right panel), and displays the MilestoneOverview component.
- **How:** Navigate to the route in a browser with dev backend + dev frontend running. Inspect browser console for errors.
- **Command:**
  ```
  1. Start: just dev-backend && just dev-frontend (separate terminals)
  2. Navigate to http://localhost:3000/projects/{valid-project-id}/planning
  3. Open browser DevTools > Console
  4. Verify: no red errors, page shows split layout with milestone section on left
  5. Open DevTools > Network — confirm GET requests to /api/projects/{id}/planning/status, /api/projects/{id}/milestones, /api/projects/{id}/phases, /api/projects/{id}/plans
  ```
- **Target:** Page renders without `[Vue warn]` or `Uncaught TypeError` in console. Network tab shows 4 API requests on load. Left panel is visible with milestone overview structure. Right session panel is hidden (no active session).
- **Evidence:** Render without errors is a necessary condition for feature completeness — page crash disqualifies the wave.
- **Correlation with full metric:** MEDIUM — page rendering does not confirm SSE streaming, command dispatch, or question widget interaction.
- **Blind spots:** Does not test data loading with actual milestones (requires a project with synced GRD state). Does not test command invocation. Does not test session panel interaction.
- **Validated:** No — awaiting deferred validation at full user walkthrough.

### P3: PlanningCommandBar Shows All 17 Commands in 4 Groups

- **What:** The command bar renders all 17 GRD planning commands organized into the 4 specified categories (Project Setup, Phase Management, Research & Analysis, Requirements).
- **How:** On the Planning page, inspect the rendered DOM for command group headings and command buttons.
- **Command:**
  ```
  1. Navigate to /projects/{id}/planning
  2. Open DevTools > Elements
  3. Count: group headings (expect 4), command buttons (expect 17)
  4. Verify group labels: "Project Setup", "Phase Management", "Research & Analysis", "Requirements"
  5. Verify command buttons include: map-codebase, new-milestone, long-term-roadmap,
     add-phase, remove-phase, insert-phase, discuss-phase, plan-phase,
     survey, deep-dive, feasibility, assess-baseline, compare-methods, list-phase-assumptions,
     requirement, plan-milestone-gaps, complete-milestone
  ```
- **Target:** 4 group headings visible. 17 command buttons visible and labeled correctly.
- **Evidence:** 01-03-PLAN.md task 2 specifies the exact command list and category mapping — this check directly validates the requirement.
- **Correlation with full metric:** MEDIUM — button presence does not confirm that clicking a button dispatches the correct command to the backend.
- **Blind spots:** Does not confirm buttons are wired to `invokeCommand`. Does not confirm command names passed to backend match GRD skill invocation format.
- **Validated:** No — awaiting deferred validation.

### P4: Command Dispatch Reaches Backend (Network Check)

- **What:** Clicking a command button in PlanningCommandBar sends a POST to `/api/projects/{id}/planning/invoke` with the correct `command` field in the request body.
- **How:** Open DevTools > Network, click a command button, inspect the outgoing POST request.
- **Command:**
  ```
  1. Navigate to /projects/{id}/planning
  2. Open DevTools > Network, filter by XHR
  3. Click "Map Codebase" button in PlanningCommandBar
  4. Inspect the POST request to /api/projects/{id}/planning/invoke
  5. Verify request body: {"command": "map-codebase"}
  6. Verify response is received (any HTTP status — project may not exist or Claude may not be installed)
  ```
- **Target:** POST request fired with correct URL and body. `command` field matches expected GRD command name.
- **Evidence:** Direct verification of the frontend-to-backend wire — the most critical integration point between Plan 02 (composable) and Plan 03 (view).
- **Correlation with full metric:** HIGH — if dispatch is wrong, no GRD commands work regardless of UI quality.
- **Blind spots:** Does not confirm the command runs successfully (Claude CLI must be available for that).
- **Validated:** No — awaiting deferred validation.

### P5: grd_init_status Transitions Correctly for Local Path Project

- **What:** Creating a project with a `local_path` that has an existing `.planning/` directory should trigger immediate sync and transition `grd_init_status` to `ready`. Creating a project with a `local_path` that has no `.planning/` should set status to `initializing`.
- **How:** Use the backend API to create projects and poll the status endpoint.
- **Command:**
  ```bash
  # Test Case A: local_path WITH existing .planning/
  curl -s -X POST http://localhost:20000/admin/projects \
    -H "Content-Type: application/json" \
    -d '{"name": "test-grd-eval", "local_path": "/path/to/repo/with/planning"}'
  # Extract project_id from response, then:
  sleep 3
  curl -s http://localhost:20000/api/projects/{project_id}/planning/status

  # Test Case B: local_path WITHOUT .planning/
  curl -s -X POST http://localhost:20000/admin/projects \
    -H "Content-Type: application/json" \
    -d '{"name": "test-no-planning", "local_path": "/tmp/empty-test-dir"}'
  # Extract project_id, then poll:
  curl -s http://localhost:20000/api/projects/{project_id}/planning/status
  ```
- **Target:** Case A — after 3 seconds, `grd_init_status` is `"ready"`. Case B — immediately after creation, `grd_init_status` is `"initializing"`.
- **Evidence:** 01-04-PLAN.md verification L2 specifies this exact test. Status transitions are the primary mechanism for user feedback during auto-initialization.
- **Correlation with full metric:** MEDIUM — status field correctness does not confirm the actual sync ran successfully (requires verifying DB records match files).
- **Blind spots:** Does not confirm `grd_milestones` / `grd_phases` tables were populated. Does not test GitHub clone → auto-init path (deferred). Does not verify Claude CLI availability.
- **Validated:** No — awaiting deferred validation.

### P6: Planning Button Appears on ProjectDashboard, Left of Management

- **What:** The "Planning" button is visible on the project dashboard page, positioned to the left of the "Management" button, with an appropriate init status badge.
- **How:** Navigate to the project dashboard in the browser.
- **Command:**
  ```
  1. Navigate to http://localhost:3000/projects/{valid-project-id}
  2. Inspect the action buttons area
  3. Verify: "Planning" button is present
  4. Verify: "Planning" button appears LEFT of "Management" button in DOM order and visual layout
  5. Verify: Clicking "Planning" navigates to /projects/{id}/planning
  6. Verify: Badge shows current grd_init_status (none, initializing, ready, or failed)
  ```
- **Target:** Planning button exists and is ordered before Management button. Navigation works. Badge reflects status.
- **Evidence:** CONTEXT.md locked decision: "Entry point: 'Planning' button on project dashboard, placed left of the existing 'Management' button." This is a hard requirement, not a soft preference.
- **Correlation with full metric:** HIGH — if navigation entry point is missing, users cannot reach the Planning page without typing the URL.
- **Blind spots:** Does not test the polling behavior when status is `initializing`. Does not test toast notification on completion.
- **Validated:** No — awaiting deferred validation.

### P7: GRD Settings Tab Renders at /settings#grd

- **What:** The Settings page has a "GRD Planning" tab that renders the `GrdSettings` component with toggle controls for auto-init, sync behavior, and verification level selector.
- **How:** Navigate to the settings page and click the GRD tab.
- **Command:**
  ```
  1. Navigate to http://localhost:3000/settings#grd
  2. Verify: "GRD Planning" tab button is visible in the tab bar
  3. Verify: Tab is active when URL hash is #grd
  4. Verify: Three settings sections render: "Project Initialization", "Sync Behavior", "Default Verification Level"
  5. Click "Save Settings" — verify success toast appears
  ```
- **Target:** Tab renders, all three sections visible, save action shows toast.
- **Evidence:** 01-05-PLAN.md task 2 specifies the component structure and tab registration. This validates the full SettingsPage → GrdSettings component integration.
- **Correlation with full metric:** MEDIUM — settings save does not verify that the settings actually affect backend behavior (deferred).
- **Blind spots:** Does not verify that settings are persisted beyond page reload. Does not verify that `autoInitEnabled=false` actually prevents auto-init in the backend.
- **Validated:** No — awaiting deferred validation.

### P8: Session-Completion Sync Order (Structural Check)

- **What:** Verify structurally that the sync call is placed BEFORE the `complete` event broadcast in `ProjectSessionManager._handle_session_exit()`. This is the race condition prevention from RESEARCH.md Pitfall 2.
- **How:** Inspect the source code for ordering of the sync call vs. broadcast call.
- **Command:**
  ```bash
  grep -n "sync_on_session_complete\|GrdPlanningService.unregister_session\|_broadcast.*complete\|complete.*_broadcast" \
    /Users/edward.seo/dev/private/project/harness/Agented/backend/app/services/project_session_manager.py
  ```
- **Target:** The line number for `sync_on_session_complete` or `GrdSyncService` call is LESS THAN the line number for the `_broadcast` call with the `complete` event in `_handle_session_exit()`.
- **Evidence:** RESEARCH.md Pitfall 2 explicitly documents the race condition: "Run GrdSyncService.sync_project() synchronously in _handle_session_exit() BEFORE broadcasting the complete event." The 01-04-PLAN.md task 1 step 3 specifies insertion point as "just above" the broadcast.
- **Correlation with full metric:** HIGH — this ordering is non-negotiable for data consistency.
- **Blind spots:** Does not test runtime behavior — only structural ordering. Actual race behavior requires a real PTY session to validate.
- **Validated:** No — awaiting deferred validation.

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring live PTY sessions, the Claude CLI, or extended integration testing not available during automated phase checks.

### D1: All 17 Planning Commands Execute End-to-End — DEFER-01-01

- **What:** Each of the 17 GRD planning commands (`map-codebase`, `new-milestone`, `complete-milestone`, `add-phase`, `remove-phase`, `insert-phase`, `discuss-phase`, `plan-phase`, `long-term-roadmap`, `survey`, `deep-dive`, `feasibility`, `assess-baseline`, `compare-methods`, `list-phase-assumptions`, `plan-milestone-gaps`, `requirement`) can be invoked from the Planning page UI, produces an active PTY session, streams output to the session panel, and exits cleanly.
- **How:** Walk through each command on a real project with the Claude CLI installed and GRD plugin configured. Note commands that require interactive question/answer (e.g., `discuss-phase`, `plan-phase`) and verify question widgets appear and answer submission works.
- **Why deferred:** Requires `claude` CLI installed with the GRD plugin, a real project with a valid `.planning/` directory, and a PTY session that can run to completion — none of which are reliably available in automated CI.
- **Validates at:** Manual integration walkthrough — no specific future phase; this is a human validation step after Phase 01 is fully deployed.
- **Depends on:** Claude CLI installed, GRD plugin configured, at least one Agented project with a local git clone.
- **Target:** All 17 commands launch a session (session_id returned). At least 14/17 (80%) complete without errors. 3/17 may require follow-up iteration. Interactive commands (discuss-phase, plan-phase, survey, deep-dive) show question widgets when the AI asks a question.
- **Risk if unmet:** If fewer than 14/17 commands work, the core feature objective is not met. The most likely failures are: (a) PTY question detection mismatch (RESEARCH.md Pitfall 5), (b) ANSI code corruption in session output (Pitfall 1). Budget 2-3 days of iteration on the `ProjectSessionManager` question detection middleware.

### D2: Interactive Question/Answer Round-Trip — DEFER-01-02

- **What:** When a GRD command prompts an interactive question (`AskUserQuestion` tool call or CLI prompt pattern), the `PlanningSessionPanel` renders a question widget, and submitting an answer via `sendAnswer()` correctly resumes the PTY session.
- **How:** Trigger `discuss-phase` or `plan-phase` on a real project. Wait for the question widget to appear. Submit an answer. Verify the session continues and produces more output.
- **Why deferred:** Requires live PTY session with GRD-aware Claude session. The question detection pattern may differ between `SetupExecutionService` (subprocess mode) and `ProjectSessionManager` (PTY mode) — RESEARCH.md Open Question 1 explicitly flags this as unresolved.
- **Validates at:** Manual integration walkthrough after Phase 01 deployment.
- **Depends on:** D1 command execution working, Claude CLI in PTY mode producing `AskUserQuestion`-style output that `_try_parse_interaction()` can detect.
- **Target:** Question widget appears for at least 2 interactive commands. Answer submission unblocks session. Session completes after answer.
- **Risk if unmet:** Interactive commands do not function. Users must use CLI for any command requiring question/answer. Fallback: raw text input from the session panel (users type directly into the PTY, bypassing the question widget). Budget 1-2 days to port question detection into `ProjectSessionManager._reader_loop()` if needed.

### D3: Background Auto-Init Full Lifecycle (GitHub Repo Clone) — DEFER-01-03

- **What:** Creating a project with a GitHub repo URL triggers auto-init after the clone completes. `grd_init_status` transitions from `none` → `pending` → `initializing` → `ready` (or `failed`). The Planning page shows milestones after successful initialization.
- **How:** Create a new project in the UI with a GitHub repo URL. Monitor the Planning button badge on the dashboard as it transitions. Navigate to the Planning page after the badge shows "ready" and verify milestones are populated.
- **Why deferred:** Requires a live GitHub clone (network dependency) and the Claude CLI. The clone can take minutes for large repos. The background thread waits up to 4 minutes for clone completion before triggering init.
- **Validates at:** Manual integration walkthrough after Phase 01 deployment.
- **Depends on:** GitHub connectivity, Claude CLI, GRD plugin, a sample repository with a README.
- **Target:** Within 10 minutes of project creation, `grd_init_status` transitions to `ready` and milestones appear on the Planning page.
- **Risk if unmet:** Zero-friction onboarding does not work. Users must manually trigger `map-codebase` from the Planning page. Fallback: manual initialization via Planning page commands. Lower severity than D1 or D2.

### D4: Session-Completion DB Sync Data Accuracy — DEFER-01-04

- **What:** After a planning session completes (e.g., `plan-phase` runs and writes a PLAN.md file), the `grd_milestones`, `grd_phases`, and `grd_plans` DB tables are updated to reflect the new `.planning/` file contents, and the Planning page shows refreshed data without a manual page reload.
- **How:** Run `plan-phase 1` on a project where phase 1 has no plan. Wait for session completion. Verify the Planning page's MilestoneOverview updates to show phase 1's new plan entries. Verify the `grd_plans` table (via SQLite CLI) contains the new plan records.
- **Why deferred:** Requires a successful end-to-end GRD session write, which depends on D1 working first.
- **Validates at:** After D1 is validated.
- **Depends on:** D1 (command execution), `GrdSyncService.sync_on_session_complete()` correctly integrated into `_handle_session_exit()`.
- **Target:** `grd_plans` table contains the newly created plan record within 5 seconds of session completion. Planning page MilestoneOverview refreshes without manual reload.
- **Risk if unmet:** DB and filesystem state diverge. Users see stale milestone/phase data until manual sync. The most likely failure is the sync call placement (race condition from Pitfall 2) — caught by P8 structurally, but runtime timing may still cause issues. Budget 1 day to add a retry mechanism or explicit `sync_complete` SSE event.

### D5: Settings Persistence and Behavioral Effect — DEFER-01-05

- **What:** GRD settings saved in the settings tab are persisted across page reloads. Setting `autoInitEnabled=false` actually prevents auto-initialization when a new project is created.
- **How:** Save `autoInitEnabled=false` in GRD settings. Create a new project. Verify `grd_init_status` remains `none` rather than transitioning to `initializing`.
- **Why deferred:** Requires backend enforcement of the setting in the project creation flow. The current plan stores settings in the key-value store but does not explicitly wire `autoInitEnabled` into `GrdPlanningService.auto_init_project()`.
- **Validates at:** A future bug-fix or follow-up task — the initial implementation does not enforce this setting.
- **Depends on:** Settings API working, backend reading `grd.auto_init_enabled` from settings store before triggering auto-init.
- **Target:** When `autoInitEnabled=false`, no auto-init thread is started on project creation.
- **Risk if unmet:** The settings UI is cosmetic — toggling it has no effect. This is a known limitation of the initial implementation and is acceptable for the MVP. Budget 2-3 hours to wire the setting check into `auto_init_project()`.

### D6: Concurrent Session Enforcement — DEFER-01-06

- **What:** If two planning commands are triggered simultaneously for the same project, the second invocation returns an error response (not a new session), and only one session is active at a time.
- **How:** Use two browser tabs or rapid API calls to invoke two commands simultaneously for the same project.
- **Why deferred:** Race condition testing requires timing-sensitive concurrent requests. The in-memory `_active_planning_sessions` dict is thread-unsafe without a lock — correctness under concurrent load requires runtime validation.
- **Validates at:** Manual integration testing — requires concurrent HTTP clients.
- **Depends on:** D1 working so that real sessions can be created and tracked.
- **Target:** Second invocation returns `{"error": "Planning session already active", "session_id": "..."}`. No second PTY process is spawned.
- **Risk if unmet:** Concurrent GRD commands corrupt `.planning/` files (RESEARCH.md Pitfall 3). Mitigation: add a `threading.Lock()` to `_active_planning_sessions` access in `GrdPlanningService`. Budget 2 hours.

---

## Ablation Plan

**Purpose:** Isolate wave contributions and validate that each wave adds independent value.

### A1: Wave 1 Without Wave 2 (Backend-Only Validation)

- **Condition:** Plans 01-01 and 01-02 complete, but 01-03 (Planning page view) not yet built.
- **Expected impact:** Backend endpoints respond (P1 passes). Frontend route registered but shows placeholder page. Composable compiles (S1 passes). No visible planning UI.
- **Command:** After Wave 1, run S1–S9 and P1. Navigate to the planning route — expect a blank or placeholder page, not a crash.
- **Evidence:** Plan 01-02 explicitly notes: "navigating to the route before Plan 03 will show a blank page. This is acceptable for Wave 1 parallel execution."
- **Purpose:** Confirms Wave 1 deliverables are independently functional and do not block Wave 2.

### A2: Wave 2 Without Auto-Init (Manual Session Only)

- **Condition:** Plans 01-03 and 01-02 complete, but 01-04 (auto-init) not yet built.
- **Expected impact:** Planning page renders (P2 passes). Commands dispatch (P4 passes). grd_init_status stays at `none` (no auto-init). Users can manually invoke commands from the Planning page.
- **Command:** After Wave 2 (pre-04), create a project and verify Planning page works for manually triggered commands, even though auto-init has not run.
- **Evidence:** CONTEXT.md ablation plan item 1: "Planning page without auto-initialization — tests that manual command invocation works independently."
- **Purpose:** Confirms the Planning page feature is independently usable without the auto-init background service.

### A3: Wave 2 Without Markdown Rendering (Raw Log Fallback)

- **Condition:** If `PlanningSessionPanel.vue` is implemented with `<pre>` raw text instead of `marked + dompurify` rendering.
- **Expected impact:** Session output is legible but not formatted. Interactive question widgets still function. Core functionality preserved.
- **Command:** Inspect `PlanningSessionPanel.vue` — if `useMarkdown` composable is used, verify it's applied. If raw `<pre>` is used as fallback, confirm session functionality is not broken.
- **Evidence:** CONTEXT.md ablation plan item 2: "Planning page without AiChatPanel markdown rendering — tests that raw log display is functional as fallback."
- **Purpose:** Identifies the value added by markdown rendering vs. raw text for session output.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| CLI GRD workflow | User runs `claude -p "/grd:plan-phase 1"` in terminal | All 17 commands functional, full interactive support | Current state — this is what the web UI replaces |
| `just build` (pre-phase) | Frontend build before any changes | 0 errors, 0 warnings | CLAUDE.md verification |
| `uv run pytest` (pre-phase) | Backend tests before any changes | All pass, 0 failures | CLAUDE.md verification |
| `npm run test:run` (pre-phase) | Frontend tests before any changes | All pass, 0 failures | CLAUDE.md verification |

The target for this phase is feature parity with the CLI workflow for the 17 planning commands, accessible from the browser without terminal access.

---

## Evaluation Scripts

**Location of evaluation code:** No dedicated evaluation scripts — all checks use standard project tooling.

**How to run all Level 1 checks:**
```bash
cd /Users/edward.seo/dev/private/project/harness/Agented

# S1: Full build
just build

# S2: Backend tests
cd backend && uv run pytest -x

# S3: Frontend tests
cd frontend && npm run test:run

# S4: Service import
cd backend && uv run python -c "from app.services.grd_planning_service import GrdPlanningService; print([m for m in dir(GrdPlanningService) if not m.startswith('_')])"

# S5: Sync method
cd backend && uv run python -c "from app.services.grd_sync_service import GrdSyncService; assert hasattr(GrdSyncService, 'sync_on_session_complete'); print('OK')"

# S6: Schema column (structural grep)
grep -c "grd_init_status" backend/app/db/schema.py backend/app/db/migrations.py backend/app/db/projects.py

# S7: Route registered
grep -n "project-planning" frontend/src/router/routes/projects.ts

# S8: Composable exports
grep -n "export function usePlanningSession\|invokeCommand\|sendAnswer\|stopSession\|clearOutput\|outputLines\|currentQuestion" frontend/src/composables/usePlanningSession.ts

# S9: Types defined
grep -n "PlanningStatus\|InvokePlanningCommandRequest\|grd_init_status" frontend/src/services/api/types.ts
```

**How to run Level 2 checks:**

```bash
# Start services (separate terminals)
just dev-backend   # terminal 1
just dev-frontend  # terminal 2

# P1: Backend endpoints
curl -s http://localhost:20000/api/projects/proj-fake99/planning/status
curl -s -X POST http://localhost:20000/api/projects/proj-fake99/planning/invoke \
  -H "Content-Type: application/json" -d '{"command": "map-codebase"}'

# P8: Structural sync ordering
grep -n "sync_on_session_complete\|GrdPlanningService.unregister\|_broadcast" \
  backend/app/services/project_session_manager.py

# P2-P7: Browser-based — navigate to URLs listed in each check above
```

---

## WebMCP Tool Definitions

This phase modifies several frontend views (`ProjectPlanningPage.vue`, `ProjectDashboard.vue`, `SettingsPage.vue`, `AppSidebar.vue`) and adds new components (`PlanningCommandBar.vue`, `PlanningSessionPanel.vue`, `GrdSettings.vue`).

### Generic Checks

| Tool | Purpose | Expected |
|------|---------|----------|
| hive_get_health_status | Verify backend is responding after frontend changes | status: healthy |
| hive_check_console_errors | Verify no new JavaScript errors from frontend changes | No new errors since phase start |
| hive_get_page_info | Verify app renders correctly after changes | Page loads with expected content |

### Page-Specific Tools

| Tool | Page | Purpose | Expected |
|------|------|---------|----------|
| hive_check_planning_page_layout | /projects/:id/planning | Split layout renders with milestone overview left, session panel right | Both panels present in DOM |
| hive_check_planning_command_bar | /projects/:id/planning | Command bar shows 4 groups and 17 command buttons | 17 buttons rendered |
| hive_check_dashboard_planning_button | /projects/:id | Planning button visible, left of Management | Button present with correct order |
| hive_check_settings_grd_tab | /settings#grd | GRD settings tab renders with toggle controls | Tab active, settings form visible |

### useWebMcpTool() Definitions

```js
// Generic health checks
useWebMcpTool("hive_get_health_status", {})
useWebMcpTool("hive_check_console_errors", { since: "phase_start" })
useWebMcpTool("hive_get_page_info", {})

// Planning page layout
useWebMcpTool("hive_check_planning_page_layout", {
  url: "/projects/{projectId}/planning",
  checks: ["left-panel-visible", "milestone-overview-rendered", "right-panel-present"]
})

// Planning command bar
useWebMcpTool("hive_check_planning_command_bar", {
  url: "/projects/{projectId}/planning",
  checks: ["command-group-count:4", "command-button-count:17", "buttons-enabled-when-idle"]
})

// Dashboard planning button
useWebMcpTool("hive_check_dashboard_planning_button", {
  url: "/projects/{projectId}",
  checks: ["planning-button-exists", "planning-left-of-management", "planning-button-navigates"]
})

// Settings GRD tab
useWebMcpTool("hive_check_settings_grd_tab", {
  url: "/settings#grd",
  checks: ["grd-tab-active", "auto-init-toggle-visible", "sync-toggle-visible", "verification-level-select-visible"]
})
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Frontend build | [PASS/FAIL] | | |
| S2: Backend tests | [PASS/FAIL] | | |
| S3: Frontend tests | [PASS/FAIL] | | |
| S4: GrdPlanningService import | [PASS/FAIL] | | |
| S5: sync_on_session_complete exists | [PASS/FAIL] | | |
| S6: grd_init_status in schema | [PASS/FAIL] | | |
| S7: Planning route registered | [PASS/FAIL] | | |
| S8: usePlanningSession exports | [PASS/FAIL] | | |
| S9: API types defined | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Backend endpoints respond | 404/422/200 per spec | | [MET/MISSED] | |
| P2: Planning page renders | No JS errors, split layout | | [MET/MISSED] | |
| P3: 17 commands in 4 groups | 17 buttons, 4 groups | | [MET/MISSED] | |
| P4: Command dispatch reaches backend | POST fired with correct body | | [MET/MISSED] | |
| P5: grd_init_status transitions | `initializing` on creation | | [MET/MISSED] | |
| P6: Planning button on dashboard | Left of Management, navigates | | [MET/MISSED] | |
| P7: GRD settings tab renders | Tab active, 3 sections, save works | | [MET/MISSED] | |
| P8: Sync before broadcast (structural) | Sync line# < broadcast line# | | [MET/MISSED] | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Wave 1 without Wave 2 | Backend works, no UI crash | | |
| A2: Wave 2 without auto-init | Manual commands work | | |
| A3: Session panel without markdown | Raw text legible, questions work | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-01-01 | All 17 commands execute end-to-end | PENDING | Manual walkthrough after deployment |
| DEFER-01-02 | Interactive Q&A round-trip | PENDING | Manual walkthrough after deployment |
| DEFER-01-03 | GitHub clone → auto-init full lifecycle | PENDING | Manual walkthrough after deployment |
| DEFER-01-04 | Session-completion DB sync accuracy | PENDING | After DEFER-01-01 validated |
| DEFER-01-05 | Settings persistence and enforcement | PENDING | Follow-up task |
| DEFER-01-06 | Concurrent session enforcement | PENDING | Manual concurrency test |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM

**Justification:**

- **Sanity checks:** Adequate. Nine checks cover the key structural invariants: build correctness, test regression, module imports, DB schema, composable structure, routing, and type definitions. These are automatable and will surface the majority of integration errors.
- **Proxy metrics:** Weakly evidenced for end-to-end quality, but well-targeted for integration verification. The proxy checks confirm that the wiring is correct (endpoints exist, page renders, commands dispatch, navigation works) without being able to confirm that GRD sessions actually succeed. The honest limitation is that we cannot proxy test PTY session quality without the Claude CLI.
- **Deferred coverage:** Comprehensive for PTY session behavior, but the validation gate is a manual human walkthrough rather than an automated test. This is acceptable given the dependency on external tooling (Claude CLI + GRD plugin), but it means the deferred validations will require dedicated attention after deployment.

**What this evaluation CAN tell us:**

- Whether the code compiles and type-checks correctly (S1)
- Whether existing tests regress from schema/code changes (S2, S3)
- Whether new modules are correctly structured and importable (S4, S5, S8)
- Whether the DB schema includes the required new column (S6, S9)
- Whether the routing and API client surface is correctly wired (S7, P1, P4)
- Whether the UI renders and presents the expected structure (P2, P3, P6, P7)
- Whether the session-completion sync is correctly ordered in the source code (P8)

**What this evaluation CANNOT tell us:**

- Whether GRD commands actually run successfully in PTY sessions (requires Claude CLI + GRD plugin — DEFER-01-01)
- Whether interactive question/answer works in PTY mode vs. subprocess mode (known open question — DEFER-01-02)
- Whether the background auto-init completes for real GitHub repos (network + CLI dependency — DEFER-01-03)
- Whether `GrdSyncService.sync_project()` correctly imports specific GRD file formats written by the actual GRD plugin (requires real GRD output — DEFER-01-04)
- Whether the `_active_planning_sessions` dict is thread-safe under concurrent load (requires timing-sensitive testing — DEFER-01-06)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-02-28*
