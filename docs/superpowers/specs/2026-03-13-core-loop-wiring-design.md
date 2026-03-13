# Core Loop Wiring: Project-Centric Execution via Super Agents

**Date**: 2026-03-13
**Status**: Draft
**Approach**: End-to-end thin slice (Approach B)

## Problem

The Agented platform has ~172 frontend views but only ~30 are fully functional. The core user journey — creating agents, assigning them to teams, connecting teams to projects, triggering execution, and seeing results — is fragmented. Key pieces (super agent sessions, mailboxing, scheduling) exist as working backend services but aren't wired through the UI or to each other.

## Execution Model

Three execution layers, each with distinct characteristics:

| Layer | Nature | Trigger | Session |
|-------|--------|---------|---------|
| **Bot** | Stateless CLI invocation | Webhook, GitHub, schedule, manual | None (fire-and-forget) |
| **Super Agent** | Persistent session via cliproxy/PTY | Trigger dispatch, schedule, bot output, user chat | Long-lived, pausable |
| **Agent** | Subagent definition | Spawned by super agent or user | Ephemeral, scoped to parent |

### Entity Relationships

```
Project (repo, config)
  └── Team (leader + members)
        ├── Super Agent A (leader) — persistent session, mailbox
        ├── Super Agent B (member) — persistent session, mailbox
        └── Agent definitions (subagent specs, spawnable by any super agent)
```

- **Teams** are groups of **super agents** (leader + members), all with persistent sessions
- Super agents communicate via **mailbox messaging** (inbox/outbox, priority, TTL, SSE delivery)
- **Agents** are definitions (role, skills, system prompt) spawned as subagents by super agents or users
- **Bots** remain the lightweight stateless trigger-to-CLI path
- The platform abstracts across backends (claude, opencode, etc.) — not tied to Claude Code's native teammate feature

### Trigger Flow

```
Trigger paths into the project:
  ┌─ Webhook/GitHub event ─┐
  ├─ Cron schedule ────────┤──→ Dispatcher ──→ Routes to:
  ├─ Manual (user click) ──┤       │            ├─ Bot (existing, stateless CLI)
  └─ Bot output ───────────┘       │            └─ Super Agent session (NEW)
                                   │
User chat UI ──────────────────────┘──→ Super Agent session directly
```

Super agent session flow:
1. Session created (or existing resumed)
2. Prompt delivered (trigger payload rendered into message)
3. Super agent processes, optionally:
   - Spawns agent definitions as subagents
   - Messages teammate super agents via mailbox
4. Results stream back via SSE
5. Execution logged to execution_logs

## What Already Works

| Feature | Service/File | Status |
|---------|-------------|--------|
| CLIProxyManager | `cliproxy_manager.py` | Persistent sessions, OAuth, auto-refresh |
| PtyService | `pty_service.py` | Interactive CLI with TTY support |
| Super agent session lifecycle | `super_agent_session_service.py` | Create, send, pause, resume, end, SSE stream |
| Mailboxing | `agent_message_bus_service.py`, `messages.py` | Inbox/outbox, SSE delivery, prompt injection, broadcast |
| Team → super agent assignment | `teams.py` DB functions | Super agents assignable as members/leaders |
| APScheduler cron triggers | `scheduler_service.py` | Daily/weekly/monthly cron, fires bot executions |
| Execution log streaming | `execution_service.py` | SSE streaming, FTS5 search |
| Bot trigger dispatch | `trigger_dispatcher.py` | Webhook/GitHub event matching to bots |

## What Needs to Be Built

### 1. Database Migration

**Triggers table** — add super agent dispatch support:
```sql
ALTER TABLE triggers ADD COLUMN super_agent_id TEXT REFERENCES super_agents(id);
ALTER TABLE triggers ADD COLUMN dispatch_type TEXT DEFAULT 'bot'
  CHECK(dispatch_type IN ('bot', 'super_agent'));
```

**Execution logs table** — unify bot and super agent execution history:
```sql
ALTER TABLE execution_logs ADD COLUMN session_id TEXT REFERENCES super_agent_sessions(id);
ALTER TABLE execution_logs ADD COLUMN source_type TEXT DEFAULT 'bot'
  CHECK(source_type IN ('bot', 'super_agent', 'user_chat'));
```

4 new columns across 2 existing tables. No new tables needed.

**Note on `trigger_id` nullability**: The existing `execution_logs.trigger_id` is `NOT NULL`. For `source_type='user_chat'` executions (no trigger involved), a synthetic trigger record is not needed — instead, make `trigger_id` nullable in the migration:
```sql
-- SQLite doesn't support ALTER COLUMN, so trigger_id stays as-is for existing rows.
-- New inserts with source_type='user_chat' pass trigger_id=NULL.
-- Application-level validation enforces: trigger_id required when source_type IN ('bot', 'super_agent').
```

**Note on SQLite FK constraints**: `ALTER TABLE ADD COLUMN` with `REFERENCES` is syntactically valid but SQLite does not enforce FKs on columns added via ALTER. Referential integrity is enforced at the application level in the CRUD functions.

**Note on FTS5**: The existing `execution_logs_fts` virtual table and its sync triggers only index `stdout_log`, `stderr_log`, and `prompt`. No FTS5 changes needed for the new columns.

### 2. Super Agent Session Service Update

Add a `get_or_create_session(super_agent_id)` method to `SuperAgentSessionService`:
- Query for an existing session with status `active` or `paused` for this super_agent_id
- If found and `paused`, call `resume_session()`; return it
- If found and `active`, return it
- If none found, call `create_session()`; return it
- If `create_session` fails due to `MAX_CONCURRENT_SESSIONS` (10, global limit), raise a specific `SessionLimitError` that the dispatcher can handle (log error, mark execution as failed)

**Known constraint**: The 10-session limit is global across all super agents. Under heavy scheduling + manual chat, this could be exhausted. Acceptable for the thin slice; future work can add per-super-agent limits or dynamic pool sizing.

### 3. Dispatcher Routing (`trigger_dispatcher.py`)

The existing bot dispatch path uses `ExecutionQueueService.enqueue()` for async queued execution. The super agent path bypasses the queue since super agent sessions are persistent and long-lived — they don't fit the fire-and-forget queue model.

```python
def dispatch_event(trigger, payload):
    if trigger.dispatch_type == 'bot':
        # Existing path — async via execution queue
        ExecutionQueueService.enqueue(trigger, payload)
    elif trigger.dispatch_type == 'super_agent':
        # New path — direct session dispatch (no queue)
        try:
            session = SuperAgentSessionService.get_or_create_session(trigger.super_agent_id)
            rendered_prompt = ExecutionService.render_prompt(trigger.prompt_template, payload)
            SuperAgentSessionService.send_message(session.id, rendered_prompt)
            log_execution(trigger, session, source_type='super_agent')
        except SessionLimitError:
            log_execution_failed(trigger, reason='session_limit_exceeded')
```

**Template rendering**: Reuses the existing placeholder substitution from `ExecutionService` (`{paths}`, `{message}`, `{pr_url}`, etc.) — no new rendering mechanism needed.

**Relationship between `team_id` and `super_agent_id` on triggers**: The existing `team_id` column on triggers identifies which team "owns" the trigger for organizational purposes. The new `super_agent_id` identifies the specific super agent to dispatch to. They are complementary: `team_id` is optional grouping metadata; `super_agent_id` is the dispatch target when `dispatch_type='super_agent'`. A trigger with `dispatch_type='bot'` ignores `super_agent_id`.

### 4. Scheduler Update (`scheduler_service.py`)

Both the scheduler and the webhook dispatcher use the same dispatch routing logic. The scheduler's `_execute_trigger()` calls the dispatch function directly (synchronous, in the scheduler thread). The webhook dispatcher enqueues via `ExecutionQueueService`. For super agent dispatch, both paths use the same direct session dispatch (Section 3) — no queue involvement.

- `dispatch_type == 'bot'` → existing bot execution path (scheduler: direct, webhook: queued)
- `dispatch_type == 'super_agent'` → direct session dispatch (both scheduler and webhook)

### 5. Pydantic Model Changes

**`app/models/trigger_models.py`** — Add to `CreateTriggerRequest` and `UpdateTriggerRequest`:
```python
dispatch_type: str = "bot"  # "bot" or "super_agent"
super_agent_id: Optional[str] = None  # Required when dispatch_type="super_agent"
```

Add to trigger response model:
```python
dispatch_type: str
super_agent_id: Optional[str]
```

**Execution log response models** — Add:
```python
session_id: Optional[str]
source_type: str  # "bot", "super_agent", "user_chat"
```

### 6. Project Dashboard (`/projects/:projectId`)

Currently partial. Becomes the central hub with four panels:

**Teams panel**: Shows assigned teams with their super agents. Status indicators (active session, idle, paused). Click super agent → opens chat/session view.

**Triggers panel**: Lists project triggers. Create/edit trigger with `dispatch_type` selector (bot or super agent). If super agent, dropdown picks from project's teams' super agents.

**Sessions panel**: Live view of active super agent sessions across project's teams. Current task, message count. Click → session detail with SSE log stream.

**Execution history**: Existing, enhanced with `source_type` badge (bot / super_agent / user_chat) for unified view.

### 7. Team Dashboard (`/teams/:teamId`)

Currently partial. Wire these features:

**Members list**: Already shows super agents. Add session status indicator and "Chat" button per super agent.

**Mailbox view**: Wire existing `MessageInbox` and `MessageThread` components (in `src/components/super-agents/`) to `/admin/super-agents/:id/messages/*` endpoints. Show recent messages between team's super agents.

**Team trigger**: Wire UI to configure team's `trigger_source` and `trigger_config`. Show scheduled runs.

### 8. Super Agent Chat

The chat functionality currently lives in `src/composables/useAiChat.ts` and is embedded in views like `SuperAgentPlayground.vue`. Extract or extend this into a reusable chat component that can be embedded in the project dashboard and team dashboard. Wire it to:
- `POST /admin/super-agents/:id/sessions` — create session
- `POST /admin/super-agents/:id/sessions/:sid/message` — send prompt
- `GET /admin/super-agents/:id/sessions/:sid/stream` — SSE response stream

Accessible from: project dashboard (teams panel), team dashboard (member chat button), super agent detail page.

### 9. Scheduling Dashboard (`/dashboards/scheduling`)

Currently a UI shell. Wire to show:
- All scheduled triggers across projects, grouped by project
- Next run time, last run result, dispatch type (bot/super_agent)
- Create/edit with basic cron expression input
- Pause/resume individual schedules

Uses existing `SchedulerService` status endpoint + trigger CRUD.

### 10. Execution Logging

Super agent session output flows into `execution_logs`:
- `session_id` links to `super_agent_sessions`
- `source_type` distinguishes bot / super_agent / user_chat
- Same FTS5 search, SSE streaming, and filtering as bot executions

## Deferred

These are explicitly out of scope for the thin slice:

- **Multi-backend abstraction** — first slice uses whatever backend the super agent is configured with
- **Cross-team communication** — mailboxing works within a team first
- **Agent spawning UI** — super agents spawn subagents via their session; no dedicated management UI
- **Workflow builder integration** — workflows remain a separate system
- **~100 UI shell views** not part of the core loop
- **VisualCronWizard** full implementation — basic cron input first
- **Advanced scheduling** — dependency-aware, optimizer, smart suggestions
- **Collaborative features** — real-time multi-user viewing
- **Integration wiring** — Slack, GitHub Actions, ticketing remain shells

## Success Criteria

1. Create a project with a GitHub repo
2. Create a team with 2 super agents (leader + member)
3. Assign team to project
4. Create a trigger on the project that dispatches to the leader super agent
5. Fire the trigger (manually, via webhook, or on schedule)
6. Super agent session starts, processes the prompt, results appear in execution history
7. Open the project dashboard, chat with a super agent directly
8. Super agents can message each other via mailbox within the team
9. Schedule a trigger, see it in the scheduling dashboard, watch it fire on cron

## Component Inventory

### Backend Changes
| File | Change |
|------|--------|
| `app/db/migrations.py` | Add 4 columns to triggers and execution_logs, make trigger_id nullable |
| `app/db/triggers.py` | Add `session_id` and `source_type` to execution log insert/query functions |
| `app/services/super_agent_session_service.py` | Add `get_or_create_session()` method, `SessionLimitError` |
| `app/services/trigger_dispatcher.py` | Add dispatch_type routing to super agent sessions |
| `app/services/scheduler_service.py` | Add super agent dispatch path in `_execute_trigger()` |
| `app/routes/triggers.py` | Accept `super_agent_id` and `dispatch_type` in create/update |
| `app/models/trigger_models.py` | Add `dispatch_type`, `super_agent_id` to request/response models |

### Frontend Changes
| Component | Change |
|-----------|--------|
| `views/projects/ProjectDashboard.vue` | Add teams, triggers, sessions, execution panels |
| `views/teams/TeamDashboard.vue` | Wire member status, chat button, mailbox |
| `composables/useAiChat.ts` | Extract reusable chat component for super agent sessions |
| `views/dashboards/SchedulingDashboard.vue` | Wire to scheduler status + trigger CRUD |
| `views/triggers/TriggerManagement.vue` | Add dispatch_type selector and super agent picker |
| `views/executions/ExecutionHistory.vue` | Add source_type badge/filter |
| `components/super-agents/MessageInbox.vue` | Wire to `/admin/super-agents/:id/messages/*` |
| `components/super-agents/MessageThread.vue` | Wire to `/admin/super-agents/:id/messages/*` |
| `services/api.ts` | Add super agent session and message API functions |

### Tests
| File | Coverage |
|------|----------|
| `backend/tests/test_trigger_dispatch_super_agent.py` | Dispatcher routing for dispatch_type='super_agent' |
| `backend/tests/test_scheduler_super_agent.py` | Scheduler firing super agent triggers |
| `backend/tests/test_session_get_or_create.py` | get_or_create_session logic, session limit error |
| `backend/tests/test_execution_log_source_type.py` | Execution logs with session_id and source_type |
| `frontend/src/tests/project-dashboard.test.ts` | Project dashboard panels render and wire to APIs |
| `frontend/src/tests/team-dashboard-chat.test.ts` | Team dashboard chat button and mailbox wiring |
| `frontend/src/tests/scheduling-dashboard.test.ts` | Scheduling dashboard lists triggers, shows status |

### Known Constraints
- **10-session global limit**: `MAX_CONCURRENT_SESSIONS = 10` is shared across all super agents. Acceptable for thin slice.
- **In-memory session state**: `SuperAgentSessionService._active_sessions` is lost on server restart. `restore_active_sessions()` recovers from DB on startup, but trigger events during restart window may be lost. Acceptable for thin slice; future work can add a persistent dispatch queue.
