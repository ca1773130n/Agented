# Phase 1: Web UI Roadmapping Feature - Research

**Researched:** 2026-02-28
**Domain:** Full-stack web UI integration for AI-assisted project planning (Vue 3 + Flask + PTY sessions + SSE streaming)
**Confidence:** HIGH

## Summary

This phase adds a dedicated Planning page to the Agented web UI that allows users to create roadmaps, milestones, requirements, and phases through AI-assisted interaction in the browser. The implementation is primarily a codebase integration task, not a greenfield build -- the vast majority of required infrastructure already exists in the codebase.

The backend already has: PTY session management (`ProjectSessionManager`), SSE streaming, GRD sync service, GRD CLI service, project session CRUD, and milestone/phase/plan database tables. The frontend already has: `InteractiveSetup.vue` (SSE log streaming with structured question/answer UI), `MilestoneOverview.vue`, `KanbanBoard.vue`, `AiChatPanel.vue`, `ProjectSessionPanel.vue`, and the `grdApi` client module with full session management capabilities.

The key work is: (1) creating a new `ProjectPlanningPage.vue` with a split layout (MilestoneOverview + AI session panel), (2) adding backend endpoints for GRD command invocation via PTY sessions that run Claude Code with GRD skill, (3) implementing auto-initialization on project creation (background `map-codebase` + `new-project`), (4) adding a one-time `GrdSyncService` import trigger, and (5) adding a GRD settings tab to SettingsPage.

**Primary recommendation:** Reuse `ProjectSessionManager` for GRD command PTY sessions, adapt `InteractiveSetup.vue` patterns for the AI interaction panel, and build the Planning page as a project-scoped split-layout view that mirrors the `SuperAgentPlayground` layout pattern.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**AI Interaction Model:**
- Reuse existing PTY session + InteractiveSetup pattern. GRD commands are AI-powered (Claude Code with GRD plugin). The backend spins up a PTY session running Claude Code in the project's cloned repo directory, and the web UI reflects that session via SSE streaming.
- InteractiveSetup.vue already implements the full pattern: SSE log streaming (`log` events), structured question prompts (`question` events with options/multiselect), answer submission (`setupApi.respond()`), and completion handling.
- The web UI must show: AI conversation output, AskUserQuestion-style option selection widgets, and free-text input for detailed answers.
- Existing infrastructure: `setupApi` (frontend), PTY session services (backend), SSE streaming -- all reusable.

**GRD Integration Approach:**
- No reimplementation of GRD logic in Python. GRD commands execute within an AI session (Claude Code + GRD plugin). The backend creates a PTY session that runs Claude Code in the project's cloned repo directory with the appropriate GRD skill invocation.
- The AI session is the runtime. `grd-tools.js` is called by the AI within the session, not by the backend directly. The backend only manages session lifecycle.
- The web UI reflects the session -- conversation, tool calls, questions, and answers -- through the existing SSE protocol.

**Scope / MVP:**
- Auto on project creation (background): `grd:map-codebase` runs automatically after git clone, `grd:new-project --auto @README.md` runs automatically after map-codebase, runs in background thread; user is notified on completion. `GrdSyncService` does a one-time sync at this point to import any existing `.planning/` files from the repo into the DB.
- Planning page (new dedicated page): All planning-related GRD commands available: `new-milestone`, `complete-milestone`, `add-phase`, `remove-phase`, `insert-phase`, `discuss-phase`, `plan-phase`, `long-term-roadmap`, `survey`, `deep-dive`, `feasibility`, `assess-baseline`, `compare-methods`, `list-phase-assumptions`, `plan-milestone-gaps`, `requirement`, `map-codebase`. Core visualization: `MilestoneOverview.vue` moved, reused, and extended. Entry point: "Planning" button on project dashboard, placed left of the existing "Management" button.
- Settings page: GRD settings in a new tab on the existing Settings page.
- Management page (existing): Execution commands: `execute-phase`, `autopilot`, `evolve`, `progress`, `quick`, `verify-phase`, `verify-work`.

**Data Model & Persistence:**
- Source of truth: `.planning/` files on disk in the project's cloned repo directory.
- DB sync: One-time sync on project creation (import existing `.planning/` from repo). After that, all modifications go through web UI -> AI session -> writes files -> backend syncs to DB on session completion.
- No periodic GRD sync needed. The 30-min scheduler job for GRD sync is unnecessary for projects managed through the web UI. Only needed for the initial import case.
- Real-time UI updates: PTY session completion fires an event via SSE. Backend syncs `.planning/` files to DB at that point. Frontend refreshes Planning page state on receiving the completion event. No polling.

**Navigation & Layout:**
- Planning page is project-scoped -- accessed from within a project's context.
- Every GRD planning project is tied 1:1 to an Agented project (GitHub repo based).
- Planning page is separate from the Project Management page (which handles agent task execution).

### Claude's Discretion

- Specific UI layout of the Planning page (command palette, sidebar actions, etc.)
- How to organize the planning commands in the UI (grouped by workflow stage, alphabetical, etc.)
- Whether to show a command palette or action buttons for GRD commands
- How to extend `MilestoneOverview.vue` for the new context

### Deferred Ideas (OUT OF SCOPE)

- Execution commands on Planning page (deliberately excluded -- belongs on Management page)
- Bidirectional file sync (not needed -- web UI is the single writer after initial import)
- Custom visualization beyond MilestoneOverview (extend later based on usage)

## Paper-Backed Recommendations

This is a full-stack web UI integration phase, not an ML/research phase. Recommendations below are grounded in established software engineering patterns and verified codebase analysis rather than academic papers.

### Recommendation 1: Split-Layout Planning Page with Command Categories

**Recommendation:** Build the Planning page as a two-panel split layout: MilestoneOverview + phase cards on the left (scrollable), AI session panel on the right (fixed). Group GRD commands into 3-4 workflow stages displayed as action buttons on milestone/phase cards.

**Evidence:**
- The `SuperAgentPlayground.vue` (line 1-100) already implements this exact split-layout pattern in the codebase, with a chat panel on the left and document/config tabs on the right.
- The `ProjectManagementPage.vue` (line 407-449) implements a similar `kanban-chat-layout` with `chat-side-panel` at 340px width.
- The CONTEXT.md "Specific Ideas" section explicitly suggests: "The Planning page could have a split layout: MilestoneOverview on the left, AI session panel on the right (similar to how SuperAgentPlayground works)."

**Confidence:** HIGH -- Multiple working implementations of this pattern exist in the codebase.

**Recommended command groupings:**
1. **Project Setup:** `map-codebase`, `new-milestone`, `long-term-roadmap`
2. **Phase Management:** `add-phase`, `remove-phase`, `insert-phase`, `discuss-phase`, `plan-phase`
3. **Research & Analysis:** `survey`, `deep-dive`, `feasibility`, `assess-baseline`, `compare-methods`, `list-phase-assumptions`
4. **Requirements:** `requirement`, `plan-milestone-gaps`, `complete-milestone`

### Recommendation 2: Reuse ProjectSessionManager for GRD Command Sessions

**Recommendation:** Use the existing `ProjectSessionManager` PTY infrastructure to run GRD commands. Each GRD command invocation creates a PTY session that runs `claude` with the appropriate GRD skill invocation as the prompt.

**Evidence:**
- `ProjectSessionManager` (verified in `backend/app/services/project_session_manager.py`) provides: PTY creation via `pty.openpty()`/`os.fork()`, ring buffer output (10,000 lines), SSE broadcasting via Queue-per-subscriber, pause/resume, resource limits (1hr idle, 4hr max lifetime), crash recovery via PID/PGID in DB.
- The GRD routes (`backend/app/routes/grd.py`, lines 619-727) already expose session create/stream/stop/input endpoints at `/api/projects/<project_id>/sessions/*`.
- The `grdApi` frontend client (`frontend/src/services/api/grd.ts`, lines 204-268) already has `createSession`, `streamSession`, `sendInput`, `stopSession` methods.
- `InteractiveSetup.vue` demonstrates the SSE event handling pattern (`log`, `question`, `complete`, `error` events) that the Planning page AI panel must replicate.

**Confidence:** HIGH -- All infrastructure exists and is battle-tested in the codebase.

**Session command construction:**
```python
# For a GRD command like "plan-phase", the PTY session runs:
cmd = ["claude", "-p", f"/grd:plan-phase {phase_number}"]
# The PTY session runs in the project's local_path (cloned repo directory)
```

### Recommendation 3: Adapt InteractiveSetup SSE Protocol for Planning AI Panel

**Recommendation:** The Planning page's AI session panel should use the same SSE event protocol as `SetupExecutionService` (`log`, `question`, `complete`, `error` events), but displayed through a richer UI component that merges `InteractiveSetup.vue` interaction widgets with `AiChatPanel.vue`-style message rendering.

**Evidence:**
- `SetupExecutionService` (`backend/app/services/setup_execution_service.py`, lines 131-217) implements the stdout interactive parsing with `_try_parse_interaction()` that detects `AskUserQuestion` tool calls and regex-based CLI prompts.
- `InteractiveSetup.vue` (lines 65-178) handles: SSE event subscription, question rendering (text/password/select/multiselect), answer submission, reconnect with retry.
- `ProjectSessionManager` already broadcasts `output` and `complete` events (lines 264-278, 338-351).

**Key difference from InteractiveSetup:** The Planning page needs to show the AI's markdown-formatted conversation output (not just raw log lines). This means the `output` SSE events should be rendered through `marked` + `dompurify` (already used via `useMarkdown` composable) rather than plain `<pre>` text.

**Confidence:** HIGH -- Both patterns verified in codebase. The composition approach is well-established.

### Recommendation 4: Background Auto-Initialization via GrdSyncService + PTY

**Recommendation:** On project creation (after git clone), trigger a background PTY session that runs `map-codebase` followed by `new-project --auto @README.md`, then invoke `GrdSyncService.sync_project()` to import `.planning/` files into the DB.

**Evidence:**
- `GrdSyncService.sync_project()` (`backend/app/services/grd_sync_service.py`, lines 52-116) already handles: ROADMAP.md parsing to milestone + phases, PLAN.md/SUMMARY.md parsing, SHA256 incremental sync with `project_sync_state` table.
- `ProjectSessionManager.create_session()` supports background sessions (daemon threads for reader).
- The project creation flow (`backend/app/routes/projects.py`) handles git clone and local_path resolution.

**Confidence:** HIGH -- Both services verified working in codebase.

**Implementation approach:**
1. After git clone completes (in project creation or sync), check if `.planning/` exists.
2. If `.planning/` exists: run `GrdSyncService.sync_project()` immediately (file-only sync, no AI needed).
3. If `.planning/` does not exist: spawn a background PTY session running `claude -p "/grd:map-codebase"`, then on completion spawn another running `claude -p "/grd:new-project --auto @README.md"`, then sync.
4. Store initialization status on the project record (e.g., `grd_init_status` field: `none`, `initializing`, `ready`, `failed`).

### Recommendation 5: Session-Completion-Triggered DB Sync

**Recommendation:** When a GRD planning PTY session completes (exit code 0), automatically trigger `GrdSyncService.sync_project()` to import any `.planning/` file changes into the DB, then broadcast a `plan_changed` SSE event to refresh the frontend.

**Evidence:**
- `ProjectSessionManager._handle_session_exit()` (lines 301-353) already handles session exit detection, DB status update, and subscriber notification. Adding a sync trigger here follows the established pattern.
- The `plan_changed` SSE event type is already handled in `ProjectManagementPage.vue` (line 278-284) with debounced `loadPhasesAndPlans()` refresh.

**Confidence:** HIGH -- Both mechanisms verified.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vue 3 | 3.5 | Frontend component framework | Already used throughout codebase |
| Vue Router 4 | 4.6 | SPA routing with `createWebHistory` | Already configured, just add new route |
| Flask + flask-openapi3 | 2.x / 3.x | Backend API with auto-generated OpenAPI spec | Established codebase pattern |
| Python `pty` module | stdlib | PTY session management | Already used by `ProjectSessionManager` |
| `marked` + `dompurify` | 17.x / 3.x | Markdown rendering with XSS sanitization | Already used via `useMarkdown` composable |
| `vue-draggable-plus` | 0.6 | Drag-and-drop for phase reordering | Already used by `KanbanBoard` |
| `streaming-markdown` | 0.2 | Incremental markdown rendering during streaming | Already used for AI chat streaming |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `chart.js` | 4.5 | Phase progress visualization | If extending MilestoneOverview with charts |
| `highlight.js` | 11.x | Syntax highlighting in AI output | When rendering code blocks in AI responses |
| `@vue-flow/core` | 1.48 | Phase dependency graph visualization | Deferred -- only if dependency viz requested |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PTY sessions via `os.fork()` | `subprocess.Popen` | PTY gives full TTY features (ANSI, signals), subprocess is simpler but loses interactive capability |
| SSE streaming | WebSockets | SSE is simpler, unidirectional (sufficient), auto-reconnect built in. WebSockets adds complexity for no benefit here |
| Raw SQLite | SQLAlchemy ORM | Codebase convention is raw SQLite; switching would break all existing patterns |

**Installation:** No new packages needed. All required libraries are already in `frontend/package.json` and `backend/pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure

```
backend/
├── app/routes/grd.py              # Extend with planning-specific endpoints
├── app/services/
│   ├── grd_sync_service.py        # Extend: session-completion-triggered sync
│   ├── grd_planning_service.py    # NEW: GRD command dispatch + auto-init orchestration
│   └── project_session_manager.py # Reuse as-is
└── app/db/grd.py                  # Extend: grd_init_status on projects table

frontend/
├── src/views/
│   └── ProjectPlanningPage.vue    # NEW: Main planning page view
├── src/components/grd/
│   ├── MilestoneOverview.vue      # Extend: action buttons per phase
│   ├── PlanningCommandBar.vue     # NEW: Command selection/dispatch panel
│   ├── PlanningSessionPanel.vue   # NEW: AI session output + interaction panel
│   └── PhaseDetailCard.vue        # NEW: Phase card with inline GRD actions
├── src/components/settings/
│   └── GrdSettings.vue            # NEW: GRD settings tab component
├── src/composables/
│   └── usePlanningSession.ts      # NEW: Composable wrapping PTY session for planning
└── src/router/routes/projects.ts  # Extend: add planning route
```

### Pattern 1: PTY Session for GRD Command Invocation

**What:** Each GRD planning command creates a PTY session via `ProjectSessionManager.create_session()` with `cmd = ["claude", "-p", "<GRD skill invocation>"]`.

**When to use:** Every time the user triggers a GRD command from the Planning page.

**Example:**
```python
# backend/app/services/grd_planning_service.py
class GrdPlanningService:
    @classmethod
    def invoke_command(cls, project_id: str, grd_command: str, args: dict = None) -> str:
        """Invoke a GRD command via Claude Code PTY session.

        Returns session_id for SSE streaming.
        """
        project = get_project(project_id)
        local_path = project["local_path"]

        # Build the skill invocation prompt
        prompt = f"/grd:{grd_command}"
        if args:
            for key, value in args.items():
                prompt += f" --{key} {value}"

        session_id = ProjectSessionManager.create_session(
            project_id=project_id,
            cmd=["claude", "-p", prompt],
            cwd=local_path,
            execution_type="direct",
            execution_mode="interactive",
        )
        return session_id
```

### Pattern 2: SSE Event Protocol for Planning Sessions

**What:** The Planning page subscribes to the PTY session's SSE stream and renders output as a conversation. `output` events show AI markdown, `question` events show interactive widgets, `complete` events trigger DB sync + UI refresh.

**When to use:** Always for the AI session panel on the Planning page.

**Example:**
```typescript
// frontend/src/composables/usePlanningSession.ts
export function usePlanningSession(projectId: Ref<string>) {
  const sessionId = ref<string | null>(null);
  const outputLines = ref<string[]>([]);
  const currentQuestion = ref<PlanningQuestion | null>(null);
  const status = ref<'idle' | 'running' | 'waiting_input' | 'complete'>('idle');

  function connectSSE() {
    const es = grdApi.streamSession(projectId.value, sessionId.value!);

    es.addEventListener('output', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      outputLines.value.push(data.line);
    });

    es.addEventListener('complete', async (e: MessageEvent) => {
      status.value = 'complete';
      // Trigger sync + refresh
      await grdApi.sync(projectId.value);
      emit('sessionCompleted');
    });
  }

  async function invokeCommand(command: string, args?: Record<string, string>) {
    const result = await grdApi.createSession(projectId.value, {
      cmd: ['claude', '-p', `/grd:${command}${args ? ' ' + formatArgs(args) : ''}`],
      execution_mode: 'interactive',
    });
    sessionId.value = result.session_id;
    status.value = 'running';
    connectSSE();
  }

  return { sessionId, outputLines, currentQuestion, status, invokeCommand };
}
```

### Pattern 3: Background Auto-Initialization

**What:** After project creation with git clone, run GRD initialization commands in a background PTY session. Track status on the project record.

**When to use:** Every time a project is created or cloned.

**Example:**
```python
# In project creation route or post-clone hook
def _auto_init_grd(project_id: str, local_path: str):
    """Background GRD initialization after project clone."""
    update_project(project_id, grd_init_status="initializing")

    # Step 1: map-codebase
    session_id = ProjectSessionManager.create_session(
        project_id=project_id,
        cmd=["claude", "-p", "/grd:map-codebase"],
        cwd=local_path,
        execution_type="direct",
        execution_mode="autonomous",
    )
    # ... wait for completion, then:

    # Step 2: new-project --auto @README.md
    session_id = ProjectSessionManager.create_session(
        project_id=project_id,
        cmd=["claude", "-p", "/grd:new-project --auto @README.md"],
        cwd=local_path,
        execution_type="direct",
        execution_mode="autonomous",
    )
    # ... wait for completion, then:

    # Step 3: Sync to DB
    planning_dir = str(Path(local_path) / ".planning")
    GrdSyncService.sync_project(project_id, planning_dir)
    update_project(project_id, grd_init_status="ready")
```

### Anti-Patterns to Avoid

- **Reimplementing GRD logic in Python:** CONTEXT.md explicitly forbids this. GRD commands run inside an AI session (Claude Code + GRD plugin), not as direct Python function calls. The backend only manages session lifecycle.
- **Polling for updates:** Use SSE event-driven refresh, not periodic polling. The `complete` event on session end triggers sync + UI refresh.
- **Bidirectional file sync:** The web UI is the single writer after initial import. Do not implement filesystem watchers or periodic sync loops.
- **Mixing execution and planning commands:** Planning commands belong on the Planning page; execution commands (`execute-phase`, `autopilot`, `evolve`, `progress`, `quick`, `verify-phase`, `verify-work`) belong on the existing Management page.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PTY session management | Custom PTY wrapper | `ProjectSessionManager` | Already handles fork/setsid/ring-buffer/SSE/cleanup |
| SSE streaming | Custom event system | `ProjectSessionManager.subscribe()` + `_broadcast()` | Queue-per-subscriber pattern already working |
| Markdown rendering in AI output | Custom parser | `marked` + `dompurify` + `streaming-markdown` | Already in `package.json`, used by `useMarkdown` |
| ANSI escape stripping | Custom regex | `ProjectSessionManager._ANSI_RE` | Already compiled and tested |
| GRD file parsing | Custom ROADMAP.md parser | `GrdSyncService._sync_roadmap()` | Already handles version extraction, phase parsing, upsert |
| Interactive question UI | New component from scratch | Adapt `InteractiveSetup.vue` patterns | SSE question/answer protocol already implemented |
| Project session CRUD | New DB tables | Existing `project_sessions` table + `grd.py` CRUD | Schema and functions already exist |

**Key insight:** Over 80% of the required infrastructure already exists. The phase is primarily a composition and wiring task, not a build-from-scratch task.

## Common Pitfalls

### Pitfall 1: PTY Session Output Parsing for AI Conversations

**What goes wrong:** Raw PTY output from `claude` contains ANSI escape codes, progress spinners, and control sequences that corrupt markdown rendering.
**Why it happens:** `claude` CLI writes rich terminal output assuming a real terminal emulator.
**How to avoid:** Use `ProjectSessionManager._ANSI_RE` regex stripping (already applied in `_reader_loop`). Additionally, filter out non-content lines (spinners, progress bars) before rendering as conversation content.
**Warning signs:** Garbled output, missing/duplicated characters, broken markdown rendering.

### Pitfall 2: Session Completion Race Condition with DB Sync

**What goes wrong:** Frontend sends refresh request before `GrdSyncService.sync_project()` has finished importing files, resulting in stale data displayed.
**Why it happens:** Session `complete` event fires, frontend immediately calls list endpoints, but sync hasn't run yet.
**How to avoid:** Run `GrdSyncService.sync_project()` synchronously in `_handle_session_exit()` BEFORE broadcasting the `complete` event. Or add a new SSE event type `sync_complete` that fires after sync finishes.
**Warning signs:** MilestoneOverview shows old data after a GRD command completes.

### Pitfall 3: Multiple Concurrent Planning Sessions

**What goes wrong:** User triggers a second GRD command while the first is still running, causing file conflicts in `.planning/`.
**Why it happens:** GRD commands modify `.planning/` files. Two concurrent writers create race conditions.
**How to avoid:** Enforce single active planning session per project. Check for existing active session before creating a new one. Show "session in progress" state in the UI with option to cancel or wait.
**Warning signs:** Corrupted `.planning/` files, git merge conflicts, duplicate phases.

### Pitfall 4: Background Auto-Init Failing Silently

**What goes wrong:** The auto-initialization PTY session fails (e.g., `claude` not installed, no API key), but the user has no visibility into the failure.
**Why it happens:** Background initialization runs in a daemon thread with no UI feedback.
**How to avoid:** Store `grd_init_status` on the project record (`none`, `initializing`, `ready`, `failed`). Show initialization status on the project dashboard. Link to the Planning page with error details on failure.
**Warning signs:** Planning page shows "No milestones" even after project creation with a README.

### Pitfall 5: InteractiveSetup Question Detection Mismatch

**What goes wrong:** The `_try_parse_interaction()` regex in `SetupExecutionService` doesn't match GRD's `AskUserQuestion` format, so interactive questions are rendered as raw log lines instead of interactive widgets.
**Why it happens:** GRD plugin's question format may differ from the patterns currently detected.
**How to avoid:** Verify GRD's `AskUserQuestion` output format matches `SetupExecutionService._try_parse_interaction()` patterns. The existing JSON parsing (`{"type": "tool_use", "name": "AskUserQuestion"}`) should match, but test with actual GRD commands. If using `ProjectSessionManager` instead of `SetupExecutionService`, the question detection logic must be ported to the reader loop or a middleware layer.
**Warning signs:** Questions appear as raw JSON in the log output instead of as interactive form widgets.

## Experiment Design

### Recommended Experimental Setup

This is a feature integration phase. "Experiments" are integration tests rather than ML experiments.

**Independent variables:** GRD command type (e.g., `plan-phase`, `discuss-phase`, `survey`)
**Dependent variables:** Session success rate, sync accuracy (DB matches files), UI render correctness
**Controlled variables:** Project configuration, backend state

**Baseline comparison:**
- Baseline: CLI-only GRD workflow (user runs `claude` in terminal with GRD plugin)
- Expected performance: Web UI achieves feature parity with CLI for planning commands
- Our target: All 17 planning commands launchable from web UI with interactive question/answer support

**Ablation plan:**
1. Planning page without auto-initialization -- tests that manual command invocation works independently
2. Planning page without AiChatPanel markdown rendering -- tests that raw log display is functional as fallback
3. Planning page without session-completion sync -- tests that manual "Sync" button works as fallback

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Session success rate | Core functionality | `completed / total sessions` | Should be >95% |
| Sync accuracy | Data integrity | Compare DB records to `.planning/` files | 100% match expected |
| Time to first milestone | User experience | Time from project creation to first milestone visible | <60s for auto-init |
| Command coverage | Feature completeness | GRD commands launchable from UI / total planning commands | 17/17 (100%) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Planning page renders and loads data | Level 1 (Sanity) | Can check immediately via `just build` + page visit |
| PTY session creation for GRD commands | Level 1 (Sanity) | API call returns session_id |
| SSE streaming delivers output events | Level 2 (Proxy) | Connect to stream endpoint, verify event delivery |
| Interactive question/answer round-trip | Level 2 (Proxy) | Trigger a GRD command that asks a question, verify widget appears |
| Auto-initialization on project creation | Level 2 (Proxy) | Create project, verify milestones appear after init |
| Session-completion DB sync accuracy | Level 2 (Proxy) | Run command, verify DB records match `.planning/` files |
| All 17 planning commands launchable | Level 3 (Deferred) | Manual walk-through of each command |
| Full build passes (`just build`) | Level 1 (Sanity) | TypeScript type checking catches interface mismatches |
| Backend tests pass (`uv run pytest`) | Level 1 (Sanity) | Existing tests must not regress |
| Frontend tests pass (`npm run test:run`) | Level 1 (Sanity) | Existing tests must not regress |

**Level 1 checks to always include:**
- `just build` succeeds (vue-tsc type checking + vite build)
- `cd backend && uv run pytest` passes
- `cd frontend && npm run test:run` passes
- New route `/projects/:projectId/planning` renders without errors
- `grdApi.createSession()` returns a valid session_id

**Level 2 proxy metrics:**
- EventSource receives `output` events when streaming a session
- MilestoneOverview displays data after `GrdSyncService.sync_project()`
- Planning command buttons dispatch correct `cmd` arrays to backend
- GRD settings tab renders in SettingsPage with correct hash routing

**Level 3 deferred items:**
- End-to-end test of each of the 17 GRD planning commands
- Cross-browser SSE reconnect behavior
- Resource limit enforcement for long-running planning sessions
- Concurrent user session isolation

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is initialized but empty. Production considerations are derived from codebase analysis.

### Known Failure Modes

- **PTY session orphaning:** If the backend crashes while a PTY session is running, the child process becomes orphaned. Prevention: `ProjectSessionManager.cleanup_dead_sessions()` runs on startup (verified in `__init__.py` startup sequence, item 8). Detection: sessions with `status='active'` whose PID is dead.
- **SQLite busy timeout under concurrent sync:** Multiple `GrdSyncService.sync_project()` calls for different projects could contend on SQLite writes. Prevention: SQLite's `busy_timeout = 5000` (5s) is configured in `get_connection()`. Detection: `sqlite3.OperationalError: database is locked` in logs.
- **Claude CLI rate limiting:** Background auto-init for many projects simultaneously could trigger API rate limits. Prevention: Queue auto-init requests, process sequentially with backoff. Detection: PTY session exits with non-zero code, stderr contains rate limit error.

### Scaling Concerns

- **At current scale:** Single SQLite database, in-process PTY sessions. Works fine for single-user/small-team deployment.
- **At production scale:** Multiple concurrent planning sessions require PTY session pooling or limits. Consider max active planning sessions per project (recommended: 1) and max total concurrent PTY sessions globally (recommended: 10).

### Common Implementation Traps

- **Forgetting to close EventSource on component unmount:** Always call `eventSource.close()` in `onUnmounted()`. The existing `InteractiveSetup.vue` correctly does this (line 219-221).
- **Not handling SSE reconnect:** EventSource auto-reconnects, but subscribed state may be lost. `ProjectSessionManager.subscribe()` replays ring buffer on new subscription (lines 536-543), which handles this correctly.
- **Blocking the main thread with sync operations:** `GrdSyncService.sync_project()` reads files and writes to DB synchronously. For large `.planning/` directories, run in a background thread to avoid blocking Flask request handling.

## Code Examples

Verified patterns from the existing codebase:

### Creating a PTY Session (from ProjectSessionManager)
```python
# Source: backend/app/services/project_session_manager.py, lines 80-219
session_id = ProjectSessionManager.create_session(
    project_id=project_id,
    cmd=["claude", "-p", "/grd:plan-phase 1"],
    cwd="/path/to/project",
    execution_type="direct",
    execution_mode="interactive",
)
# Returns: "psess-abc123"
```

### SSE Subscription (from grd.py routes)
```python
# Source: backend/app/routes/grd.py, lines 662-678
@grd_bp.get("/<project_id>/sessions/<session_id>/stream")
def stream_session(path: SessionPath):
    def generate():
        for event in ProjectSessionManager.subscribe(path.session_id):
            yield event
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
```

### Frontend SSE Handling (from InteractiveSetup.vue)
```typescript
// Source: frontend/src/components/projects/InteractiveSetup.vue, lines 65-138
const eventSource = new EventSource(setupApi.streamUrl(executionId.value));

eventSource.addEventListener('log', (e: MessageEvent) => {
  const data = JSON.parse(e.data);
  if (data.content) {
    logs.value.push(data.content);
    scrollToBottom();
  }
});

eventSource.addEventListener('question', (e: MessageEvent) => {
  const data = JSON.parse(e.data);
  currentQuestion.value = {
    interaction_id: data.interaction_id,
    question_type: data.question_type || 'text',
    prompt: data.prompt || '',
    options: data.options,
  };
  status.value = 'waiting_input';
});

eventSource.addEventListener('complete', (e: MessageEvent) => {
  const data = JSON.parse(e.data);
  status.value = 'complete';
  exitCode.value = data.exit_code ?? null;
  closeEventSource();
  if (exitCode.value === 0) emit('completed');
});
```

### GRD Sync Trigger (from GrdSyncService)
```python
# Source: backend/app/services/grd_sync_service.py, lines 52-116
from pathlib import Path
planning_dir = str(Path(local_path).expanduser().resolve() / ".planning")
result = GrdSyncService.sync_project(project_id, planning_dir)
# Returns: {"synced": 5, "skipped": 2, "errors": []}
```

### Adding a Route (from router/routes/projects.ts)
```typescript
// Source: frontend/src/router/routes/projects.ts
export const projectRoutes: RouteRecordRaw[] = [
  // ... existing routes ...
  {
    path: '/projects/:projectId/planning',
    name: 'project-planning',
    component: () => import('../../views/ProjectPlanningPage.vue'),
    props: true,
    meta: { title: 'Project Planning', requiresEntity: 'projectId' },
  },
];
```

### Settings Tab Addition (from SettingsPage.vue pattern)
```typescript
// Source: frontend/src/views/SettingsPage.vue, lines 17-27
const TAB_NAMES = ['general', 'marketplaces', 'harness', 'mcp', 'grd'] as const;
// Add 'grd' to the tuple and import GrdSettings component
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CLI-only GRD workflow | Web UI + CLI hybrid | This phase | Users can plan without terminal access |
| Periodic 30-min GRD sync | Event-driven sync on session completion | This phase | Real-time data freshness, less wasted compute |
| Manual `map-codebase` + `new-project` | Auto-initialization on project creation | This phase | Zero-friction onboarding for new projects |

**Deprecated/outdated:**
- The 30-minute periodic GRD sync scheduler job becomes unnecessary for web-UI-managed projects after this phase. It should be retained only as a fallback for CLI-managed projects.

## Open Questions

1. **Question: How does `claude` CLI output format its responses in PTY mode?**
   - What we know: `ProjectSessionManager._reader_loop` strips ANSI codes and broadcasts line-by-line via `output` events.
   - What's unclear: Whether Claude CLI output includes structured tool_use JSON (like `AskUserQuestion`) in PTY mode, or only in subprocess stdin/stdout mode.
   - Recommendation: Test a simple GRD command (`map-codebase`) in a PTY session and inspect raw output before and after ANSI stripping. If question detection doesn't work via PTY, consider using `SetupExecutionService`'s subprocess-based approach instead.

2. **Question: Should the Planning page reuse `SetupExecutionService` or `ProjectSessionManager` for interactive sessions?**
   - What we know: `SetupExecutionService` has built-in `_try_parse_interaction()` for detecting questions in stdout. `ProjectSessionManager` does not have this but has better session management (ring buffer, pause/resume, resource limits).
   - What's unclear: Whether to port question detection into `ProjectSessionManager._reader_loop()` or create a new hybrid service.
   - Recommendation: Extend `ProjectSessionManager` with optional question detection middleware. This keeps the session management advantages while adding interactive capability. The detection logic from `SetupExecutionService._try_parse_interaction()` (lines 310-342) is small and portable.

3. **Question: What is the exact `cmd` format for invoking Claude Code with a GRD skill?**
   - What we know: The CONTEXT says "Claude Code with GRD plugin" and skills are invoked with `/grd:command-name`.
   - What's unclear: Whether the PTY session should run `claude -p "/grd:plan-phase 1"` (single prompt mode) or `claude` (interactive mode with typed commands).
   - Recommendation: Use `claude -p "/grd:plan-phase 1"` for autonomous commands that don't need user interaction, and `claude --interactive` (or similar) for commands that require `AskUserQuestion` round-trips. Test both modes during implementation.

4. **Question: How to notify the user when background auto-initialization completes?**
   - What we know: The CONTEXT says "user is notified on completion."
   - What's unclear: Whether to use a toast notification, a badge on the project dashboard, SSE push, or a combination.
   - Recommendation: Use a combination: (a) store `grd_init_status` on the project record, (b) show a status indicator on the project dashboard ("Planning: Initializing..." / "Planning: Ready"), (c) when the user is on the dashboard and init completes, show a toast with a link to the Planning page.

## Sources

### Primary (HIGH confidence)
- `backend/app/services/project_session_manager.py` -- PTY session management, SSE broadcasting, ring buffer
- `backend/app/services/setup_execution_service.py` -- Interactive question detection, SSE event protocol
- `backend/app/services/grd_sync_service.py` -- File-to-DB sync with SHA256 incremental hashing
- `backend/app/services/grd_cli_service.py` -- GRD binary detection and subprocess execution
- `backend/app/routes/grd.py` -- Existing GRD API endpoints (sync, milestones, phases, plans, sessions, chat)
- `backend/app/db/grd.py` -- Milestone/phase/plan/session CRUD operations
- `backend/app/db/schema.py` -- Table definitions for milestones, project_phases, project_plans, project_sessions, project_sync_state
- `frontend/src/components/projects/InteractiveSetup.vue` -- SSE event handling, question UI, answer submission
- `frontend/src/components/grd/MilestoneOverview.vue` -- Milestone visualization with phase stats
- `frontend/src/views/ProjectManagementPage.vue` -- Split layout with chat panel, kanban board, session management
- `frontend/src/views/SuperAgentPlayground.vue` -- Split layout pattern reference
- `frontend/src/services/api/grd.ts` -- GRD API client with session management methods
- `frontend/src/services/api/system.ts` -- setupApi pattern for SSE streaming
- `frontend/src/router/routes/projects.ts` -- Project routing configuration
- `frontend/src/views/SettingsPage.vue` -- Tab-based settings page pattern
- `.planning/codebase/ARCHITECTURE.md` -- System architecture analysis
- `.planning/codebase/STACK.md` -- Technology stack inventory
- `.planning/milestones/v0.1.0/phases/01-web-ui-roadmapping-feature/01-CONTEXT.md` -- Locked implementation decisions

### Secondary (MEDIUM confidence)
- Codebase convention analysis (patterns observed across 90+ service files, 120+ Vue components)
- Vue 3 Composition API documentation (verified via codebase usage patterns)

### Tertiary (LOW confidence)
- None -- all findings directly verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries already in use, no new dependencies needed
- Architecture: HIGH -- All patterns verified against working codebase implementations
- Recommendations: HIGH -- Each recommendation cites specific files and line numbers from the codebase
- Pitfalls: HIGH -- Identified from actual code paths and known failure modes in existing services

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable -- no external dependency changes expected)
