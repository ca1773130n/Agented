# Architecture

**Analysis Date:** 2026-02-25

## High-Level Architecture

Agented is a full-stack AI bot automation platform with a clear backend/frontend split:

```
┌─────────────────────────────────────────────────────┐
│  Browser (Vue 3 SPA)                                │
│  - Port 3000 (dev) / served from Flask (prod)       │
└─────────────────────┬───────────────────────────────┘
                      │ HTTP + SSE (proxied via Vite in dev)
                      ↓
┌─────────────────────────────────────────────────────┐
│  Flask Backend (flask-openapi3)                     │
│  - Port 20000                                       │
│  - /api/*, /admin/*, /health/*, /docs/*             │
└──────┬──────────────────────────────────────────────┘
       │
       ├── SQLite DB (backend/agented.db)
       ├── subprocess: claude / opencode / gemini / codex CLIs
       ├── APScheduler (background cron jobs)
       └── CLIProxyAPI process (OAuth proxy for Claude accounts)
```

### Communication Patterns

- **REST**: All data CRUD operations via JSON over HTTP
- **SSE (Server-Sent Events)**: Real-time log streaming for executions, project sessions, AI conversations
- **Webhooks**: Inbound triggers from GitHub events and generic JSON webhooks
- **Subprocess**: Bot execution via `claude -p`, `opencode run`, `gemini -p`, `codex exec` CLI commands

---

## Backend Architecture

### App Factory Pattern

Entry point: `backend/app/__init__.py` — `create_app()`

The factory pattern initializes services in dependency order on startup:

1. `init_db()` + `seed_predefined_triggers()` + `seed_preset_mcp_servers()` — database
2. `GrdCliService.detect_binary()` — finds GRD binary on path
3. `ModelDiscoveryService.clear_cache()` — resets model cache
4. `SchedulerService.init(app)` — APScheduler background scheduler
5. `MonitoringService.init()` — rate limit monitoring (depends on scheduler)
6. Scheduled jobs registered: session collection (10 min), repo sync (30 min), stale conversation cleanup (5 min)
7. `AgentSchedulerService.init()`, `RotationEvaluator.init()`
8. `ProjectSessionManager.cleanup_dead_sessions()` — clean stale PTY sessions
9. `WorkflowExecutionService.cleanup_stale_executions()` — recover interrupted workflows
10. `ExecutionService.restore_pending_retries()` — resume rate-limit retries across restarts
11. `AgentMessageBusService.start()` — TTL sweep worker
12. `CLIProxyManager` — kill orphan processes, refresh OAuth tokens, start proxy

All blueprints registered last via `register_blueprints(app)`.

### Route Layer

`backend/app/routes/__init__.py` registers 44+ `APIBlueprint` instances.

**Route prefix conventions:**
- `/health/*` — liveness/readiness probes (`backend/app/routes/health.py`)
- `/admin/*` — all management/configuration APIs (agents, teams, triggers, executions, etc.)
- `/api/*` — public-facing APIs
- `/` — webhook receiver (`backend/app/routes/webhook.py`)
- SPA catch-all — registered last via `app.register_blueprint(spa_bp)` using Flask's 404 handler

**Blueprint pattern:**
```python
# backend/app/routes/executions.py
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

tag = Tag(name="executions", description="Execution log operations")
executions_bp = APIBlueprint("executions", __name__, url_prefix="/admin", abp_tags=[tag])

class TriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")

@executions_bp.get("/triggers/<trigger_id>/executions")
def list_trigger_executions(path: TriggerPath):
    ...
```

Route paths use Pydantic `BaseModel` for path parameters, validated automatically by flask-openapi3.

### Service Layer

`backend/app/services/` contains 90+ service classes with stateless classmethods or singleton patterns.

**Core execution services:**

| Service | File | Responsibility |
|---------|------|----------------|
| `ExecutionService` | `execution_service.py` | Build CLI commands, spawn subprocesses, stream logs, rate-limit detection |
| `OrchestrationService` | `orchestration_service.py` | Fallback chain routing, account rotation, budget pre-checks |
| `ExecutionLogService` | `execution_log_service.py` | In-memory log buffers, SSE subscriber queues, DB persistence on finish |
| `ProcessManager` | `process_manager.py` | Subprocess tracking dict, SIGTERM/SIGKILL for cancellation |

**Background/scheduler services:**

| Service | File | Responsibility |
|---------|------|----------------|
| `SchedulerService` | `scheduler_service.py` | APScheduler wrapper, loads cron triggers and team schedules |
| `MonitoringService` | `monitoring_service.py` | Polls provider rate limit APIs, records snapshots, threshold alerts |
| `AgentSchedulerService` | `agent_scheduler_service.py` | Schedules autonomous agent executions |
| `RotationEvaluator` | `rotation_evaluator.py` | Evaluates team rotation schedules |
| `SessionCollectionService` | `session_collection_service.py` | Collects Claude session usage every 10 minutes |
| `AgentMessageBusService` | `agent_message_bus_service.py` | TTL-based agent message sweep |

**Domain services:**

| Service | File | Responsibility |
|---------|------|----------------|
| `TeamExecutionService` | `team_execution_service.py` | Multi-agent team execution coordination |
| `WorkflowExecutionService` | `workflow_execution_service.py` | DAG-based workflow execution with topological sort |
| `ProjectSessionManager` | `project_session_manager.py` | PTY-based project sessions |
| `CLIProxyManager` | `cliproxy_manager.py` | Manages global CLIProxyAPI OAuth proxy process |
| `BackendService` | `backend_service.py` | AI backend configuration (Claude, OpenCode, Gemini, Codex) |
| `BudgetService` | `budget_service.py` | Token usage budget enforcement |
| `RateLimitService` | `rate_limit_service.py` | Rate limit detection and cooldown tracking |
| `AuditLogService` | `audit_log_service.py` | Structured audit event logging |
| `GrdSyncService` | `grd_sync_service.py` | Syncs GRD planning data between filesystem and DB |
| `SkillDiscoveryService` | `skill_discovery_service.py` | Discovers Claude skills on filesystem |

**Service patterns:**
```python
# Class-level state with threading.Lock (common pattern)
class ExecutionLogService:
    _log_buffers: Dict[str, List[LogLine]] = {}
    _subscribers: Dict[str, List[Queue]] = {}
    _lock = threading.Lock()

    @classmethod
    def start_execution(cls, ...) -> str: ...
    @classmethod
    def append_log(cls, execution_id: str, ...) -> None: ...
```

### Database Layer

`backend/app/db/` — Raw SQLite via `sqlite3` module. No ORM.

**Key files:**

| File | Responsibility |
|------|----------------|
| `connection.py` | `get_connection()` context manager — opens connection, sets `row_factory=sqlite3.Row`, enables foreign keys and busy timeout |
| `schema.py` | `create_fresh_schema()` — all `CREATE TABLE` and `CREATE INDEX` statements for fresh database |
| `migrations.py` | `init_db()`, incremental schema migrations, `seed_predefined_triggers()`, `seed_preset_mcp_servers()`, `auto_register_project_root()` |
| `ids.py` | Prefixed ID generators — `generate_trigger_id()`, `generate_agent_id()`, etc. |
| `__init__.py` | Barrel re-export of all public DB functions |
| Domain modules | `agents.py`, `backends.py`, `budgets.py`, `triggers.py`, `teams.py`, `projects.py`, `plugins.py`, `workflows.py`, etc. |

**Connection pattern:**
```python
# backend/app/db/connection.py
from contextlib import contextmanager

@contextmanager
def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
    finally:
        conn.close()
```

All queries open and close their own connection per operation. No connection pooling.

**ID convention:** `{prefix}-{6-char-random}` — e.g., `trigger-abc123`, `agent-xyz789`, `team-def456`. Prefixes: `bot-`, `agent-`, `conv-`, `team-`, `prod-`, `proj-`, `plug-`, `skill-`, `sess-`, `wf-`, `phase-`, `plan-`.

**Schema overview (key tables):**
- `triggers` — webhook/schedule/github triggers
- `execution_logs` — trigger execution history with stdout/stderr logs
- `agents` — AI agents with capabilities and configuration
- `teams` — multi-agent teams with topology
- `projects` — workspace projects linked to GitHub repos
- `plugins` — reusable plugin components
- `workflows` — DAG workflow definitions and executions
- `backends` — AI backend accounts (Claude Code, OpenCode, etc.)
- `budget_limits` / `token_usage` — spend tracking and enforcement
- `agent_conversations` / `design_conversations` — AI conversation threads
- `monitoring_snapshots` — rate limit and usage history
- `grd_milestones` / `grd_phases` / `grd_plans` — GRD project planning data

### Model Layer

`backend/app/models/` — Pydantic v2 models for request/response validation only (not DB models).

One file per domain: `agent.py`, `team.py`, `trigger.py`, `plugin.py`, `workflow.py`, etc.

---

## Frontend Architecture

### Entry Point

`frontend/src/main.ts` — creates Vue app, attaches router, mounts to `#app`.

`frontend/src/App.vue` — root component that:
- Provides `showToast` via Vue `provide`/`inject` (global toast system)
- Loads sidebar data (triggers, projects, products, teams, plugins, backends)
- Renders `AppSidebar` + `<router-view>` with layout switching (`isFullBleed`)
- Registers WebMCP generic tools on mount

### Routing

`frontend/src/router/index.ts` — `createRouter` with `createWebHistory`. Routes split by domain:

| Route File | Domain |
|------------|--------|
| `routes/dashboard.ts` | Main dashboards |
| `routes/agents.ts` | Agent management |
| `routes/teams.ts` | Team management |
| `routes/products.ts` | Product/org management |
| `routes/projects.ts` | Project management |
| `routes/plugins.ts` | Plugin management |
| `routes/skills.ts` | Skills management |
| `routes/workflows.ts` | Workflow builder |
| `routes/mcpServers.ts` | MCP server management |
| `routes/superAgents.ts` | Super agent playground |
| `routes/triggers.ts` | Trigger/bot management |
| `routes/settings.ts` | Settings |
| `routes/misc.ts` | Audit, security, execution history |

**Navigation Guards** (`frontend/src/router/guards.ts`):
- Sets `document.title` from `route.meta.title`
- Validates entity IDs for routes with `meta.requiresEntity` (e.g., `teamId`, `agentId`)
- Entity validation cached 5 minutes to avoid repeated API calls
- Fails open on network errors (allows navigation, lets component handle errors)
- Redirects to `not-found` for invalid/missing entity IDs

### State Management

No state management library. Pattern: component-local `ref`/`reactive`.

- **Sidebar data**: Loaded in `App.vue` and passed down via props
- **Toast system**: `provide('showToast', showToast)` in `App.vue`, consumed via `useToast()` composable
- **Entity state**: Each view component manages its own data loading with `onMounted`

### Composables

`frontend/src/composables/` — Vue 3 composables for reusable stateful logic:

| Composable | File | Responsibility |
|------------|------|----------------|
| `useConversation` | `useConversation.ts` | Generic AI conversation (hook/command/rule/plugin design flows) |
| `useAiChat` | `useAiChat.ts` | Super agent SSE chat with `state_delta` protocol, reconnect watchdog |
| `useProjectSession` | `useProjectSession.ts` | PTY-based project session lifecycle |
| `useTeamCanvas` | `useTeamCanvas.ts` | Team topology canvas interactions |
| `useWorkflowCanvas` | `useWorkflowCanvas.ts` | Workflow DAG canvas interactions |
| `useWorkflowExecution` | `useWorkflowExecution.ts` | Workflow run state and SSE streaming |
| `useAllMode` | `useAllMode.ts` | "All mode" multi-backend response aggregation |
| `useOrgCanvas` | `useOrgCanvas.ts` | Organization hierarchy canvas |
| `usePagination` | `usePagination.ts` | Generic pagination |
| `useListFilter` | `useListFilter.ts` | Generic list filtering |
| `useMarkdown` | `useMarkdown.ts` | Markdown rendering |
| `useSidebarCollapse` | `useSidebarCollapse.ts` | Sidebar mobile/collapse state |
| `useUnsavedGuard` | `useUnsavedGuard.ts` | Warn on unsaved changes before navigation |

### API Client

`frontend/src/services/api/` — domain-specific API modules:

- `client.ts` — base `apiFetch()` with 30s timeout, 3-retry exponential backoff for 429/502/503/504
- `types.ts` — all TypeScript types (~37k lines)
- Domain modules: one file per domain (e.g., `triggers.ts`, `agents.ts`, `teams.ts`, `grd.ts`)
- `index.ts` — barrel re-export of all API objects and types

**API pattern:**
```typescript
// frontend/src/services/api/triggers.ts
export const triggerApi = {
  list: () => apiFetch<{ triggers: Trigger[] }>('/admin/triggers'),
  get: (id: string) => apiFetch<Trigger>(`/admin/triggers/${id}`),
  create: (data: Partial<Trigger>) => apiFetch<Trigger>('/admin/triggers', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Trigger>) => apiFetch<Trigger>(`/admin/triggers/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: string) => apiFetch<void>(`/admin/triggers/${id}`, { method: 'DELETE' }),
};
```

SSE endpoints use `new EventSource(url)` directly in composables, not `apiFetch`.

### Layout System

Three layout wrappers in `frontend/src/layouts/`:

- `DefaultLayout.vue` — standard padded content area
- `FullBleedLayout.vue` — no padding (for canvas/workflow views); activated via `route.meta.fullBleed = true`
- `EntityLayout.vue` — handles loading/error states with retry/back actions; exposes `entity` and `reload` via slot

### Component Organization

`frontend/src/components/` organized by domain:

| Directory | Contents |
|-----------|----------|
| `layout/` | `AppSidebar.vue` (only file — handles all navigation) |
| `base/` | Reusable UI primitives (modals, buttons, inputs) |
| `ai/` | AI chat panel components |
| `canvas/` | Graph canvas components (team topology, workflow DAG) |
| `grd/` | GRD planning UI (KanbanBoard, KanbanColumn, MilestoneOverview) |
| `monitoring/` | Usage/rate limit charts |
| `triggers/` | Trigger management components |
| `teams/` | Team management components |
| `plugins/` | Plugin components |
| `projects/` | Project management components |
| `workflow/` | Workflow node components |
| `super-agents/` | Super agent session components |
| `sessions/` | Session history/log components |
| `security/` | Security audit components |

---

## Data Flow Patterns

### Webhook → Bot Execution Flow

```
1. POST /  (webhook.py)
   └── ExecutionService.dispatch_webhook_event(payload, raw_payload, signature_header)
       ├── HMAC signature validation (if webhook_secret configured)
       ├── Match payload against webhook triggers (keyword/field matching)
       └── OrchestrationService.execute_with_fallback(trigger, message_text, event, "webhook")
           ├── BudgetService.check_budget() — pre-flight budget check
           ├── get_fallback_chain() — find configured fallback accounts
           └── ExecutionService.run_trigger(trigger, message_text, event, trigger_type)
               ├── Clone GitHub repos (if path_type == "github")
               ├── Render prompt template (replace {message}, {paths}, {pr_url}, etc.)
               ├── ExecutionLogService.start_execution() — create DB record + SSE broadcast
               ├── ExecutionService.build_command() → ["claude", "-p", prompt, ...]
               ├── subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
               ├── ProcessManager.register(execution_id, process, trigger_id)
               ├── Thread: _stream_pipe(stdout) → ExecutionLogService.append_log() → SSE broadcast
               ├── Thread: _stream_pipe(stderr) → rate limit detection
               ├── Thread: _budget_monitor() → periodic budget check, kills process if exceeded
               └── ExecutionLogService.finish_execution() — flush logs to DB, broadcast complete
```

### SSE Streaming

**Execution logs:**
```
GET /admin/executions/{id}/stream
└── ExecutionLogService.subscribe(execution_id)
    ├── Replay buffered log lines (up to SSE_REPLAY_LIMIT=500)
    └── Block on Queue.get() → yield SSE events
        Events: "log" | "status" | "complete"
```

**AI Conversation (Super Agents):**
```
EventSource → /admin/super-agents/{id}/sessions/{sess_id}/stream
└── state_delta protocol: named SSE events with seq-based ordering
    Events: "message" | "content_delta" | "tool_call" | "finish" | "status_change" | "error" | "full_sync"
    Reconnect: Last-Event-ID header → server replays from that seq
```

### Scheduled Trigger Flow

```
APScheduler (CronTrigger)
└── SchedulerService._run_scheduled_trigger(trigger_id)
    └── OrchestrationService.execute_with_fallback(trigger, "", None, "schedule")
        └── [same as webhook flow above]
```

### GitHub PR Review Flow

```
POST /github/webhook  (github_webhook.py)
└── ExecutionService.dispatch_github_event(payload, headers)
    ├── Validate GitHub webhook signature (X-Hub-Signature-256)
    ├── Match PR events to triggers
    └── OrchestrationService.execute_with_fallback(trigger, message_text, pr_event, "github")
```

### Workflow DAG Execution

```
WorkflowExecutionService.start_execution(workflow_id, execution_id)
└── Parse DAG graph → topological sort (graphlib.TopologicalSorter)
    └── For each node in order:
        ├── trigger → ExecutionService.run_trigger()
        ├── skill → shell command via subprocess
        ├── command → configured command execution
        ├── agent → AgentSchedulerService dispatch
        ├── script → inline script via subprocess
        ├── conditional → evaluate condition, pick branch
        └── transform → data transformation
    └── WorkflowMessage envelopes route I/O between nodes
```

---

## Key Design Decisions

### 1. Raw SQLite — No ORM
**Decision:** Direct `sqlite3` with `row_factory=sqlite3.Row`. No SQLAlchemy.
**Rationale:** Simplicity. All queries are hand-written SQL in domain-specific DB modules.
**Trade-off:** No query builder, no migration framework. Migrations are hand-written in `backend/app/db/migrations.py`.

### 2. In-Memory Log Streaming via Queues
**Decision:** `ExecutionLogService` buffers logs in memory (`Dict[str, List[LogLine]]`) and distributes to SSE subscribers via `threading.Queue`.
**Rationale:** Sub-millisecond fan-out to multiple clients without extra infrastructure.
**Trade-off:** Logs lost if server crashes mid-execution (final flush to DB on completion only). SSE_REPLAY_LIMIT (500 lines) caps reconnect replay.

### 3. Subprocess CLI Execution
**Decision:** Bot execution by spawning `claude -p`, `opencode run`, `gemini -p`, or `codex exec` as subprocesses.
**Rationale:** Reuses existing CLI tooling without API integration overhead; supports multiple AI providers.
**Trade-off:** Requires CLI tools installed on server. Process lifetime managed via `ProcessManager` with PGID-based kill.

### 4. Fallback Chain + Account Rotation
**Decision:** `OrchestrationService` routes executions through configurable fallback chains of AI backend accounts, rotating on rate limits with exponential backoff retries (persisted to DB).
**Rationale:** Maximizes availability when individual accounts hit rate limits.

### 5. No Frontend State Management Library
**Decision:** Component-local `ref`/`reactive` + `provide`/`inject` for cross-cutting concerns.
**Rationale:** Avoids Vuex/Pinia complexity for a data-fetch-and-display application pattern.
**Trade-off:** Sidebar entity lists are loaded in `App.vue` and some duplication exists between `App.vue` global state and per-view local state.

### 6. SPA via 404 Handler
**Decision:** `spa_bp` intercepts Flask's 404 errors (not a catch-all route) and serves `index.html` for non-API paths.
**Rationale:** Avoids interfering with HTTP method handling on API routes (e.g., still returns 405 for wrong methods on real API endpoints).

### 7. flask-openapi3 (Not vanilla Flask)
**Decision:** Uses `OpenAPI()` app factory and `APIBlueprint` instead of `Flask()` and `Blueprint`.
**Rationale:** Auto-generates OpenAPI spec and Swagger UI at `/docs`. Pydantic models for path/query/body validation.

---

*Architecture analysis: 2026-02-25*
