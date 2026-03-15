# Sketch Execution Wiring — Design Spec

## Problem

The Sketch panel classifies and routes prompts but never executes them. After routing, sketches sit in `status='routed'` indefinitely. Additionally, no teams or super agents exist by default, so routing has nothing to target.

## Goal

Wire the full flow: User prompt in Sketch → classify → route (scoped to selected project) → execute on a super agent's persistent session → stream response back to Sketch panel in real-time → user can continue conversation in the Playground.

## Entity Hierarchy

```
Product → Project → Team (via project_teams) → SuperAgent (via team_members) → Session
```

All links must exist before a sketch can execute.

---

## Section 1: Bundled Teams & Super Agents

Seed 5 teams and 17 super agents on DB initialization (same pattern as predefined triggers). Marked with `source='bundle'` so the UI can display them as "Bundled Example".

### Schema Change

Add `source` column to `super_agents` table:

```sql
ALTER TABLE super_agents ADD COLUMN source TEXT DEFAULT 'ui_created';
```

Teams already have `source TEXT DEFAULT 'ui_created'`.

### Teams

| Team | Leader | Members | Description |
|------|--------|---------|-------------|
| Matrix Command | Morpheus | Oracle, Architect | Vision, coordination, architecture |
| Matrix Development | Trinity | Apoc, Switch, Tank | Backend, frontend, integration |
| Matrix Research | Neo | Niobe, Ghost, Seraph | Experiments, data, papers |
| Matrix Operations | Keymaker | Mouse, Merovingian | Problem solving, analysis, knowledge |
| Matrix QA | Dozer | Smith, Cypher | Defense, test attacks, security attacks |

### Super Agents (17)

| Name | Role | Layer | Team |
|------|------|-------|------|
| **Morpheus** | Visionary — goal decomposition, task assignment, strategic planning | Command | Matrix Command (leader) |
| **Oracle** | Coordinator — bottleneck detection, progress monitoring, escalation | Command | Matrix Command |
| **Architect** | System Designer — architecture, ADRs, structural guidelines | Command | Matrix Command |
| **Trinity** | Lead Developer — task distribution, core logic, code review | Development | Matrix Development (leader) |
| **Apoc** | Backend Engineer — APIs, database, server logic | Development | Matrix Development |
| **Switch** | Frontend Engineer — UI components, styling, client optimization | Development | Matrix Development |
| **Tank** | Integration Engineer — CI/CD, external services, DevOps | Development | Matrix Development |
| **Neo** | Lead Researcher — research direction, PoC, breakthrough solutions | Research | Matrix Research (leader) |
| **Niobe** | Experiment Conductor — A/B tests, ablation studies, benchmarking | Research | Matrix Research |
| **Ghost** | Data Engineer — dataset conversion, preprocessing pipelines | Research | Matrix Research |
| **Seraph** | Paper Researcher — paper analysis, SOTA tracking, priority ranking | Research | Matrix Research |
| **Keymaker** | Problem Solver & Repo Gardener — root cause analysis, cleanup | Operations | Matrix Operations (leader) |
| **Mouse** | Analyst & Visualizer — metrics, dashboards, reports | Operations | Matrix Operations |
| **Merovingian** | Knowledge Manager — code tracking, indexing, impact analysis | Operations | Matrix Operations |
| **Dozer** | Protector (Blue Team) — security patches, defensive patterns | QA | Matrix QA (leader) |
| **Smith** | Test Attacker (Red Team) — edge cases, failing tests, coverage gaps | QA | Matrix QA |
| **Cypher** | Security Attacker (Red Team) — OWASP scanning, vulnerability PoCs | QA | Matrix QA |

### Identity Documents

Each super agent gets two identity documents (SOUL + IDENTITY) defined inline in `bundle_seeds.py` as string constants. Content is derived from the reference files at `~/Developer/Projects/Agented/temp_bundles/superagents/` (not shipped with the app — used only as source material during development). The SOUL doc contains the agent's quote, role description, and layer. The IDENTITY doc contains responsibilities, input/output, guidelines, and communication patterns.

### Seeding Implementation

Create `backend/app/db/bundle_seeds.py` with:

```python
BUNDLED_TEAMS = [...]      # 5 team definitions with source='bundle'
BUNDLED_SUPER_AGENTS = [...] # 17 super agent definitions with source='bundle'
BUNDLED_DOCUMENTS = [...]  # 34 identity documents (SOUL + IDENTITY per agent)

def seed_bundled_teams_and_agents():
    """Idempotent seed — inserts if not exists, skips if present."""
```

Called from `init_db()` in `backend/app/db/schema.py` after table creation (same as `seed_predefined_triggers`).

### Frontend: Bundled Badge

Teams and super agents with `source='bundle'` display a small "Bundled" badge in the UI (list views and detail pages). Not editable-locked — users can modify them if desired.

### Project Assignment

Users assign bundled teams to their projects from the existing project dashboard (ProjectTeamsSection). No new UI needed for assignment — the teams just appear in the available teams list.

---

## Section 2: Project-Scoped Routing

### `SketchRoutingService.route()` Changes

Currently `route()` searches all super agents and teams globally. Add a `project_id` parameter to scope the search:

```python
@classmethod
def route(cls, classification: dict, project_id: str = None) -> dict:
```

When `project_id` is provided:
1. Query `project_teams` → `teams` to get teams assigned to the project
2. Query `team_members` where `super_agent_id IS NOT NULL` for those teams to get scoped super agents
3. Only search within those scoped teams and agents (same keyword matching logic)
4. If no match within project scope, return `target_type: "none"`

These queries are written inline in `route()` using raw SQL (consistent with the rest of the routing service). No new DB helper functions needed.

When `project_id` is `None`, fall back to global search (backward compatible).

### Route Endpoint

Pass the sketch's `project_id` through to the routing service:

```python
sketch = get_sketch(sketch_id)
classification = sketch["classification_json"]
routing = SketchRoutingService.route(classification, project_id=sketch.get("project_id"))
```

---

## Section 3: Sketch Execution Service

Create `backend/app/services/sketch_execution_service.py` with one public function:

```python
def execute_sketch(sketch_id: str, super_agent_id: str, content: str) -> str:
    """
    Execute a routed sketch on a super agent session.
    Returns session_id.

    1. Set sketch status to 'in_progress' (before launching thread to avoid race)
    2. Resolve backend_type from super agent record (not hardcoded)
    3. get_or_create_session(super_agent_id)
    4. SuperAgentSessionService.send_message(session_id, content)
    5. Launch background thread for LLM streaming
    """
```

### Backend Resolution

Read the super agent's `backend_type` from the database (matching what `_resolve_session` does in `super_agent_chat.py`). Do not hardcode a default backend. `account_id` and `model` default to `None` (sketch execution uses the super agent's defaults).

### Background Thread

Extract the streaming logic from `super_agent_chat.py:_launch_background_thread` into a shared helper in `backend/app/services/streaming_helper.py`. Both `super_agent_chat.py` and `sketch_execution_service.py` import from this shared module. The helper function signature:

```python
def run_streaming_response(
    session_id: str,
    super_agent_id: str,
    backend: str,
    account_id: Optional[str] = None,
    model: Optional[str] = None,
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
) -> None:
```

The helper owns the full streaming loop including SSE delta pushing:

1. Assembles system prompt from super agent identity documents (SOUL, IDENTITY, MEMORY, ROLE)
2. Builds message history from session conversation_log
3. Calls `stream_llm_response()` from `conversation_streaming`
4. Pushes `content_delta` chunks via `ChatStateService.push_delta()` (SSE broadcast)
5. Pushes `finish` and `status_change` events via `ChatStateService.push_status()`
6. Persists assistant message via `SuperAgentSessionService.add_assistant_message()`
7. Calls `update_backend_last_used()` to track backend usage
8. **On success:** calls `on_complete` callback → `update_sketch(sketch_id, status='completed')`
9. **On error:** calls `on_error` callback → `update_sketch(sketch_id, status='classified')` (reset to allow re-routing via the existing Route button)

### Error Recovery

On error, status resets to `classified` (not `routed`) so the existing "Route Sketch" button re-enables. The SSE stream sends an error event that the frontend displays as an error message in the chat. User can click "Route Sketch" again to retry.

### Status Ordering

`execute_sketch` sets `status='in_progress'` **before** launching the background thread. This prevents the race condition where the thread completes before the caller sets in_progress.

### Team → SuperAgent Resolution

```python
def find_team_super_agent(team_id: str) -> Optional[str]:
    """Find the best super agent in a team. Prefers role='leader'."""
```

Queries `team_members` where `super_agent_id IS NOT NULL` for the given team. Returns leader first, otherwise first member. Requires `super_agent_id` column to exist in `team_members` (added in the team_members schema — verified present).

---

## Section 4: Route Endpoint Changes

Modify `backend/app/routes/sketches.py:route_sketch` — after routing succeeds:

```python
routing = SketchRoutingService.route(classification, project_id=sketch.get("project_id"))

if routing["target_type"] == "super_agent":
    super_agent_id = routing["target_id"]
elif routing["target_type"] == "team":
    super_agent_id = find_team_super_agent(routing["target_id"])
else:
    # No target — update sketch status and return
    update_sketch(sketch_id, status='routed', routing_json=json.dumps(routing))
    return {"routing": routing}

if not super_agent_id:
    update_sketch(sketch_id, status='routed', routing_json=json.dumps(routing))
    return {"routing": routing}

# Execute (sets status='in_progress' internally before launching thread)
session_id = execute_sketch(sketch_id, super_agent_id, sketch["content"])

# Store session info in routing_json for frontend
routing["session_id"] = session_id
routing["super_agent_id"] = super_agent_id
update_sketch(sketch_id, routing_json=json.dumps(routing))

return {"routing": routing, "session_id": session_id, "super_agent_id": super_agent_id}
```

Note: `execute_sketch` sets `status='in_progress'` internally. The route endpoint only updates `routing_json` after (no status change to avoid race).

---

## Section 5: Frontend Changes

### `useSketchChat.ts`

After `routeSketch()` returns with `session_id` and `super_agent_id`:

1. Open SSE connection to `/admin/super-agents/{super_agent_id}/sessions/{session_id}/chat/stream`
2. Stream `content_delta` chunks into the Sketch chat as an assistant message (real-time)
3. On SSE error or disconnect: show error message in chat, do not attempt reconnection (user can re-submit)
4. When stream ends normally, mark the sketch conversation as complete
5. Expose `session_id` and `super_agent_id` for the "Continue in Playground" link

### `SketchChatPage.vue`

- During streaming: show the LLM response assembling in real-time (same UX as Playground)
- After completion: show a "Continue in Playground →" link pointing to `/super-agents/{super_agent_id}/playground` (navigates to the super agent's playground page; session auto-loads as the most recent)
- When routing returns `target_type: "none"`: show "No matching agent found. Assign a team with super agents to this project first."

### Bundled Badge (list views)

Teams list and super agents list: show a small "Bundled" tag next to items where `source === 'bundle'`. Use the existing tag/badge pattern from the codebase. No blocking behavior — bundled items are fully editable.

No new components. Reuse existing SSE infrastructure (`createAuthenticatedEventSource`).

---

## Files Modified

| File | Change |
|------|--------|
| `backend/app/db/bundle_seeds.py` | **New** — bundled teams, super agents, identity documents, seed function |
| `backend/app/db/schema.py` | Add `source` column to `super_agents`, call `seed_bundled_teams_and_agents()` from `init_db()` |
| `backend/app/db/migrations.py` | Migration to add `source` column to existing `super_agents` table |
| `backend/app/services/sketch_execution_service.py` | **New** — execute_sketch(), find_team_super_agent() |
| `backend/app/services/sketch_routing_service.py` | Add `project_id` parameter to `route()`, scope search to project teams |
| `backend/app/services/streaming_helper.py` | **New** — `run_streaming_response()` extracted from `super_agent_chat.py` |
| `backend/app/routes/sketches.py` | Modify route_sketch to pass project_id and call execute_sketch after routing |
| `backend/app/routes/super_agent_chat.py` | Refactor `_launch_background_thread` to use shared `run_streaming_response` |
| `frontend/src/composables/useSketchChat.ts` | Add SSE streaming after route, expose session info |
| `frontend/src/views/SketchChatPage.vue` | Show streaming response, "Continue in Playground" link, no-target message |

## Status Flow

```
draft → classified → routed → in_progress → completed
             ↑                      │
             └── (on error, reset) ─┘
```
