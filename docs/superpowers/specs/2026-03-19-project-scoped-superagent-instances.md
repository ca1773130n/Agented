# Project-Scoped SuperAgent & Team Instances

## Problem

SuperAgents are singletons with no project binding. They have no working directory — CLI subprocesses inherit the Flask server's cwd. Sessions have no project context. When an SA is assigned to multiple projects via teams, all work happens in the same global context with no filesystem isolation. This makes SA sessions meaningless for project-specific work.

## Solution

Transform SuperAgents and Teams into **templates** that get **instanced per project**. Each SA instance gets its own git worktree from the project repo. Sessions belong to instances, not templates. Two chat modes route through different backends: management (CLIProxy, fast, with project context in system prompt) and work (CLI subprocess with `cwd`).

## Design

### 1. Data Model

#### Templates (existing tables, unchanged)

`super_agents` — SA template (Neo, Trinity, etc.). Identity, description, backend_type, documents. No schema changes.

`teams` — Team template. Structure, topology, member roles. No schema changes.

#### New Tables

**`project_sa_instances`**

```sql
CREATE TABLE project_sa_instances (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    template_sa_id TEXT NOT NULL REFERENCES super_agents(id),
    worktree_path TEXT,
    default_chat_mode TEXT NOT NULL DEFAULT 'management' CHECK(default_chat_mode IN ('management', 'work')),
    config_overrides TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, template_sa_id)
);
CREATE INDEX idx_psa_project ON project_sa_instances(project_id);
CREATE INDEX idx_psa_template ON project_sa_instances(template_sa_id);
```

Fields:
- `id`: prefixed `psa-` + 6-char random suffix (same length as other entity IDs)
- `project_id`: the project this instance belongs to
- `template_sa_id`: the SA template this was created from
- `worktree_path`: absolute path to the git worktree for this instance (NULL if worktree creation failed)
- `default_chat_mode`: default mode for new messages when no per-message override is sent. The per-message `chat_mode` field always takes precedence over this default.
- `config_overrides`: JSON for future per-project specialization (nullable)

**`project_team_instances`**

```sql
CREATE TABLE project_team_instances (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    template_team_id TEXT NOT NULL REFERENCES teams(id),
    config_overrides TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, template_team_id)
);
CREATE INDEX idx_pti_project ON project_team_instances(project_id);
```

Fields:
- `id`: prefixed `pti-` + 6-char random suffix
- `project_id`: the project this team instance belongs to
- `template_team_id`: the team template this was created from
- `config_overrides`: JSON for future per-project team specialization (nullable)

#### New ID Constants (`ids.py`)

```python
PSA_ID_PREFIX = "psa-"
PSA_ID_LENGTH = 6

PTI_ID_PREFIX = "pti-"
PTI_ID_LENGTH = 6
```

Plus `generate_psa_id()`, `generate_pti_id()`, and collision-safe `_get_unique_*` variants following the existing pattern.

#### Modified Tables

**`super_agent_sessions`** — add column:

```sql
ALTER TABLE super_agent_sessions ADD COLUMN instance_id TEXT REFERENCES project_sa_instances(id) ON DELETE SET NULL;
CREATE INDEX idx_sas_instance ON super_agent_sessions(instance_id);
```

When `instance_id` is set, the session is project-scoped. When NULL, legacy behavior (global SA session).

### 2. Instance Lifecycle

#### Creation — via `POST /admin/projects/:project_id/instances`

This is the **sole entry point** for instance creation. The existing `project_teams` assignment action is modified to call this endpoint after inserting the `project_teams` row. This avoids two separate creation paths.

Steps (wrapped in a single database transaction):

1. Create a `project_team_instance` row
2. For each member in the template team's `team_members`:
   a. Create a `project_sa_instance` row (skip if one already exists for this project + SA combo via `INSERT OR IGNORE` on the UNIQUE constraint)
   b. Create a git worktree (outside the transaction — filesystem ops are not transactional). On failure: log error, leave `worktree_path = NULL`, continue to next member.
3. After the transaction commits, create worktrees for successfully inserted instances.
4. Create an initial persistent session for each SA instance with `instance_id` set.

If the transaction fails (e.g. FK violation), no rows are committed — no partial state.

Worktree creation:
```bash
git -C {project_local_path} worktree add \
    .worktrees/{sa_name_lowercase} \
    -b instance/{psa_id}
```

Branch name uses the instance ID (not project_id + sa_name) to guarantee uniqueness and avoid collisions with existing GRD or manual worktrees. The `.worktrees/` directory is used (same convention as the superpowers worktree skill — already `.gitignore`d in projects that use it).

**Worktree limit:** The `WorktreeService.DEFAULT_LIMIT` (5) is too low for teams. `InstanceService` creates worktrees directly via `git worktree add` (not through `WorktreeService`) since instance worktrees are long-lived and managed separately from ephemeral GRD worktrees.

#### Manager SA

When a project has `manager_super_agent_id` set, that SA also gets instanced for the project — created by `InstanceService.ensure_manager_instance(project_id)`, called from the project update endpoint when `manager_super_agent_id` changes. This instance is not tied to a `project_team_instance`.

#### Deletion — via `DELETE /admin/projects/:project_id/instances/:instance_id`

1. Call `SuperAgentSessionService.end_session(session_id)` for each active session on the instance. This cleans up both the DB status and the in-memory `_active_sessions` dict.
2. Remove the git worktree via `git worktree remove --force {worktree_path}`.
3. Delete the `project_sa_instances` row. `ON DELETE SET NULL` on `super_agent_sessions.instance_id` preserves session history with a NULL instance.

For manager SA instances: deletion happens when `manager_super_agent_id` is cleared or changed on the project, via `InstanceService.cleanup_manager_instance(project_id, old_sa_id)`.

For team removal: when a team is removed from a project via `project_teams`, delete the `project_team_instance` row and all its SA instances (loop through instances, call the deletion flow above for each).

### 3. Chat Mode & Streaming Routing

#### Two modes

- **`management`** — fast, conversational. Uses CLIProxyAPI (existing routing: proxy → LiteLLM → CLI fallback). System prompt gets project context injected. For standups, planning, status discussions.
- **`work`** — execution-oriented. Forces CLI subprocess path with `cwd=worktree_path`. Both `_stream_via_cli` and `_stream_via_opencode_cli` receive the `cwd` parameter. For coding, research, file changes.

#### Mode resolution chain

Per-message `chat_mode` field takes precedence. Fallback:

```
1. message.chat_mode (from request body)     → if set, use it
2. instance.default_chat_mode (from DB)      → if instance_id is set
3. 'management'                              → global default
```

#### Request body change

`ChatSendRequest` in `super_agent_chat.py` adds a new field alongside the existing `mode` field (which controls `single`/`all`/`compound` dispatch — unrelated):

```python
class ChatSendRequest(BaseModel):
    content: str
    backend: str = "auto"
    account_id: Optional[str] = None
    model: Optional[str] = None
    mode: str = "single"                          # existing — dispatch mode
    chat_mode: Optional[str] = None               # NEW — 'management' or 'work'
```

The `mode` field is dispatch mode (unchanged). The `chat_mode` field is the streaming routing mode (new). No naming collision.

#### Streaming path changes

`run_streaming_response` signature:

```python
def run_streaming_response(
    session_id, super_agent_id, backend,
    account_id=None, model=None,
    on_complete=None, on_error=None,
    cwd=None,          # NEW — worktree path for work mode
    chat_mode=None,    # NEW — 'management' or 'work'
):
```

`stream_llm_response` signature adds `cwd` and `chat_mode`:

```python
def stream_llm_response(messages, model=None, ..., cwd=None, chat_mode=None):
```

Routing logic at the top of `stream_llm_response`:

```python
# Work mode: force CLI subprocess with cwd
if chat_mode == 'work' and cwd:
    if effective_backend == 'opencode':
        yield from _stream_via_opencode_cli(messages, resolved_model, cwd=cwd)
    else:
        yield from _stream_via_cli(messages, resolved_model, cwd=cwd)
    return

# Management mode or no cwd: existing routing (CLIProxy → LiteLLM → CLI fallback)
# ... existing code unchanged ...
```

Both `_stream_via_cli` and `_stream_via_opencode_cli` add `cwd` parameter:

```python
def _stream_via_cli(messages, model, cwd=None):
    # ...
    proc = subprocess.Popen(cmd, stdout=..., stderr=..., cwd=cwd)
```

#### `_resolve_session` changes for `psa-` IDs

When the endpoint receives a `psa-` prefixed ID as `super_agent_id`:

```python
def _resolve_session(data, super_agent_id, session_id):
    session = get_super_agent_session(session_id)
    # ...

    # Resolve instance if psa- prefix
    instance = None
    if super_agent_id.startswith("psa-"):
        instance = get_project_sa_instance(super_agent_id)
        if not instance:
            return {"error_response": error_response("NOT_FOUND", "Instance not found", ...)}
        # Use the template SA for backend resolution
        sa = get_super_agent(instance["template_sa_id"])
        effective_backend = sa.get("backend_type") or "claude"
    else:
        sa = get_super_agent(super_agent_id)
        effective_backend = (sa.get("backend_type") if sa else None) or "claude"

    # Resolve chat_mode
    chat_mode = data.get("chat_mode")
    if not chat_mode and instance:
        chat_mode = instance.get("default_chat_mode", "management")

    # Resolve cwd for work mode
    cwd = instance["worktree_path"] if instance and chat_mode == "work" else None

    return {
        "session": session,
        "effective_backend": effective_backend,
        "instance": instance,
        "chat_mode": chat_mode,
        "cwd": cwd,
        # ... existing fields ...
    }
```

#### System prompt injection

`assemble_system_prompt` signature adds `chat_mode` and `instance_id`:

```python
@classmethod
def assemble_system_prompt(cls, super_agent_id, session_id, chat_mode=None, instance_id=None):
```

When `instance_id` is set, resolve the instance and project:

```python
if instance_id:
    instance = get_project_sa_instance(instance_id)
    project = get_project(instance["project_id"])
    # Append project context block (see Section 3 of design)
```

The `chat_mode` parameter is passed from the caller (`_launch_background_thread` or `run_streaming_response`) — it is NOT stored on the session. Each message can have a different mode.

#### Session restore on startup

`SuperAgentSessionService.restore_active_sessions()` must load `instance_id` from the DB and store it in the in-memory `_active_sessions` dict:

```python
for row in get_active_sessions_list():
    cls._active_sessions[row["id"]] = {
        "super_agent_id": row["super_agent_id"],
        "instance_id": row.get("instance_id"),  # NEW — preserve project context
        # ... existing fields ...
    }
```

This ensures project context survives server restarts.

### 4. Migration of Existing Data

All in a single versioned migration function. Worktree creation is handled by a separate startup hook (not in the migration itself, since migrations run inside a DB transaction and should not do filesystem I/O).

**Migration (DB only):**

1. Create `project_sa_instances` and `project_team_instances` tables
2. Add `instance_id` column to `super_agent_sessions`
3. For each SA that has active sessions:
   - Find the most associated project: first check `projects.manager_super_agent_id = sa.id`, then check `project_teams` → `team_members` → `super_agent_id`. If multiple projects match, use the most recently updated one.
   - If no project association found, find the first project in the DB (projects are ordered by `created_at`). If no projects exist at all, skip — instance stays NULL.
   - Create a `project_sa_instance` row with `worktree_path = NULL` (worktrees created at startup)
   - Set `instance_id` on all sessions for that SA+project combo
4. For each existing `project_teams` row, create a `project_team_instance` and corresponding `project_sa_instance` rows (idempotent via UNIQUE constraint)

**Startup hook (after migration):**

In `_init_database()`, after migrations run, call `InstanceService.ensure_worktrees()` which:
- Queries all `project_sa_instances` where `worktree_path IS NULL`
- For each, attempts to create a git worktree
- Updates `worktree_path` on success

### 5. API Changes

#### New endpoints

`POST /admin/projects/:project_id/instances` — sole entry point for instance creation.
- Body: `{ team_id: string }` or `{ super_agent_id: string }` (for manager SA)
- Creates `project_team_instance` + `project_sa_instance` rows, worktrees, initial sessions
- Returns: `{ team_instance_id, sa_instances: [{ id, template_sa_id, worktree_path, session_id }] }`

`GET /admin/projects/:project_id/instances` — list all SA instances for a project.
- Returns instances with template SA info (name, description, backend_type) joined

`GET /admin/projects/:project_id/instances/:instance_id` — instance detail.
- Returns instance + template info + active sessions

`DELETE /admin/projects/:project_id/instances/:instance_id` — remove instance.
- Ends sessions, removes worktree, deletes row

#### Modified endpoints

`POST /admin/super-agents/:id/sessions/:sid/chat` — add `chat_mode` field to `ChatSendRequest`. When `:id` starts with `psa-`, resolve via `get_project_sa_instance` → template SA for backend/model. Pass `cwd` and `chat_mode` through to `run_streaming_response`.

`GET /admin/super-agents/:id/sessions` — when `:id` starts with `psa-`, query sessions with `instance_id = :id` instead of `super_agent_id = :id`.

`POST /admin/sketches/:id/route` — routing resolves against `project_sa_instances` for the sketch's project. `SketchRoutingService.route()` receives `project_id`, queries instances instead of global SAs.

#### Backward compatibility

- `sa-` prefixed IDs: existing behavior unchanged (template/legacy path)
- `psa-` prefixed IDs: resolved via `project_sa_instances` table, template SA looked up via `template_sa_id`
- Sessions with `instance_id = NULL`: legacy behavior, no project context

### 6. Frontend Changes

#### Playground page

- SA selector becomes project-scoped. Opening a project shows its SA instances.
- "Management / Work" toggle in chat header. Switches `chat_mode` per message.
- Session list shows sessions for the project instance, not the global SA.

#### Project dashboard

- "Active Sessions" shows sessions from `project_sa_instances` for that project.
- "Chat" button routes to the instance's playground with `?session=` param.
- Team section shows the project team instance's members (resolved from template).

#### Sidebar

- Under each project, show its instanced SAs as collapsible sub-items.
- Clicking an SA under a project goes to that instance's playground.

#### Global SA templates page

- Existing `/super-agents` page becomes template management.
- Shows templates only, not instances.
- "Instances" column shows which projects have instances of this SA.

#### Sketch panel

- Routing targets `project_sa_instances` for the sketch's project, not global SAs.

### 7. Error Handling

- If git worktree creation fails (repo not cloned, disk full): log error, create instance with `worktree_path = NULL`. Instance works in management mode only; work mode returns a user-facing error: "Worktree not available. Run instance setup or use management mode."
- If worktree path becomes invalid (deleted externally): detect on next `work` mode chat, attempt re-create via `InstanceService.ensure_worktree(instance_id)`, log warning.
- If project `local_path` is not set: skip worktree creation, instance works in management mode only.
- Instance creation is idempotent: `UNIQUE(project_id, template_sa_id)` prevents duplicates. `INSERT OR IGNORE` used in the creation loop.
- Instance deletion calls `SuperAgentSessionService.end_session()` for each active session before DB deletion, ensuring in-memory state is cleaned up.
- Migration failure: if any step fails, the migration aborts (existing `RuntimeError` pattern). Partial state is not committed.

## Files Modified

- `backend/app/db/schema.py` — add `project_sa_instances` and `project_team_instances` tables
- `backend/app/db/migrations.py` — add migration for new tables, `instance_id` column, data migration
- `backend/app/db/ids.py` — add `psa-`/`pti-` ID constants (6-char suffix) and generators
- `backend/app/db/project_sa_instances.py` — CRUD for SA instances (new file)
- `backend/app/db/project_team_instances.py` — CRUD for team instances (new file)
- `backend/app/db/super_agent_sessions.py` — support `instance_id` in queries
- `backend/app/models/project_instances.py` — Pydantic request/response models (new file)
- `backend/app/routes/project_instances.py` — instance API endpoints (new file)
- `backend/app/routes/__init__.py` — register new blueprint
- `backend/app/routes/super_agent_chat.py` — add `chat_mode` to `ChatSendRequest`, resolve `psa-` IDs, pass `cwd`/`chat_mode`
- `backend/app/routes/sketches.py` — route to project SA instances
- `backend/app/services/instance_service.py` — instance creation/deletion with worktree management (new file)
- `backend/app/services/super_agent_session_service.py` — add `instance_id` to in-memory state, project context in system prompt, `chat_mode`/`instance_id` params on `assemble_system_prompt`
- `backend/app/services/streaming_helper.py` — add `cwd` and `chat_mode` params, pass to `stream_llm_response`
- `backend/app/services/conversation_streaming.py` — add `cwd`/`chat_mode` to `stream_llm_response`, work-mode routing, pass `cwd` to both `_stream_via_cli` and `_stream_via_opencode_cli`
- `backend/app/services/sketch_execution_service.py` — resolve instance for sketch execution, pass `cwd`
- `backend/app/services/sketch_routing_service.py` — route within project instances
- `backend/app/__init__.py` — call `InstanceService.ensure_worktrees()` at startup
- `frontend/src/services/api/types/project-instances.ts` — TypeScript types (new file)
- `frontend/src/services/api/project-instances.ts` — API client (new file)
- `frontend/src/services/api/index.ts` — export new API + types
- `frontend/src/views/SuperAgentPlayground.vue` — management/work toggle, project-scoped sessions
- `frontend/src/views/ProjectDashboard.vue` — show project SA instances
- `frontend/src/components/layout/AppSidebar.vue` — project-scoped SA navigation
- `frontend/src/router/routes/superAgents.ts` — instance routes

## Files NOT Modified

- `backend/app/db/super_agents.py` — template table unchanged
- `backend/app/db/teams.py` — template table unchanged
- `backend/app/db/team_members.py` — template membership unchanged
- `backend/app/services/worktree_service.py` — not used for instance worktrees (different lifecycle)
