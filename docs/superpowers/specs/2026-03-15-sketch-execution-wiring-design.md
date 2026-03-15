# Sketch Execution Wiring — Design Spec

## Problem

The Sketch panel classifies and routes prompts but never executes them. After routing, sketches sit in `status='routed'` indefinitely. Additionally, no test entities (product, project, team, super agent) exist by default, so routing has nothing to target.

## Goal

Wire the full flow: User prompt in Sketch → classify → route → execute on a super agent's persistent session → stream response back to Sketch panel in real-time → user can continue conversation in the Playground.

## Entity Hierarchy

```
Product → Project → Team (via project_teams) → SuperAgent (via team_members) → Session
```

All links must exist before a sketch can execute.

---

## Section 1: Test Data Seeding

Create `backend/scripts/seed_test_entities.py` — idempotent script that creates:

| Entity | Name | Key Fields |
|--------|------|------------|
| Product | "Agented Platform" | `id: prod-agented` |
| Project | "Agented" | `id: proj-agented`, `product_id: prod-agented`, `local_path: <repo root>` |
| Team | "Core Engineering" | `id: team-core`, linked to project via `add_team_to_project(proj-agented, team-core)` |
| SuperAgent | "Project Leader" | `id: sa-leader`, `backend_type: claude`, `team_id: team-core` |
| TeamMember | (auto) | `team_id: team-core`, `super_agent_id: sa-leader`, `role: leader` |
| Identity Docs | SOUL + IDENTITY | Describe the agent's role as project leader for the Agented platform |

Script uses raw SQL INSERTs (not the CRUD helper functions, which auto-generate IDs). Checks for existing entities before creating. Safe to run multiple times. Uses hardcoded IDs (not random-prefix convention) for reproducibility — this is intentional for test data so routing targets are predictable.

---

## Section 2: Sketch Execution Service

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

Read the super agent's `backend_type` from the database (matching what `_resolve_session` does in `super_agent_chat.py`). Do not hardcode a default backend.

### Background Thread

Extract the streaming logic from `super_agent_chat.py:_launch_background_thread` into a shared helper in `backend/app/services/streaming_helper.py`. Both `super_agent_chat.py` and `sketch_execution_service.py` import from this shared module. The helper function signature:

```python
def run_streaming_response(
    session_id: str,
    super_agent_id: str,
    backend: str,
    account_id: Optional[str],
    model: Optional[str],
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
) -> None:
```

The thread:

1. Assembles system prompt from super agent identity documents (SOUL, IDENTITY, MEMORY, ROLE)
2. Builds message history from session conversation_log
3. Calls `stream_llm_response()` from `conversation_streaming`
4. Pushes chunks via `ChatStateService` (SSE broadcast)
5. Persists assistant message via `SuperAgentSessionService.add_assistant_message()`
6. **On success:** calls `on_complete` callback → `update_sketch(sketch_id, status='completed')`
7. **On error:** calls `on_error` callback → `update_sketch(sketch_id, status='routed')` (reset for retry)

### Status Ordering

`execute_sketch` sets `status='in_progress'` **before** launching the background thread. This prevents the race condition where the thread completes before the caller sets in_progress.

### Team → SuperAgent Resolution

```python
def find_team_super_agent(team_id: str) -> Optional[str]:
    """Find the best super agent in a team. Prefers role='leader'."""
```

Queries `team_members` where `super_agent_id IS NOT NULL` for the given team. Returns leader first, otherwise first member. Requires `super_agent_id` column to exist in `team_members` (added in the team_members schema — verified present).

---

## Section 3: Route Endpoint Changes

Modify `backend/app/routes/sketches.py:route_sketch` — after routing succeeds:

```python
routing = SketchRoutingService.route(classification)

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
session_id = execute_sketch(sketch_id, super_agent_id, sketch.content)

# Store session info in routing_json for frontend
routing["session_id"] = session_id
routing["super_agent_id"] = super_agent_id
update_sketch(sketch_id, routing_json=json.dumps(routing))

return {"routing": routing, "session_id": session_id, "super_agent_id": super_agent_id}
```

Note: `execute_sketch` sets `status='in_progress'` internally. The route endpoint only updates `routing_json` after (no status change to avoid race).

---

## Section 4: Frontend Changes

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
- When routing returns `target_type: "none"`: show "No matching agent found. Create a team with a super agent first."

No new components. Reuse existing SSE infrastructure (`createAuthenticatedEventSource`).

---

## Files Modified

| File | Change |
|------|--------|
| `backend/scripts/seed_test_entities.py` | **New** — idempotent test data seeder |
| `backend/app/services/sketch_execution_service.py` | **New** — execute_sketch(), find_team_super_agent() |
| `backend/app/routes/sketches.py` | Modify route_sketch to call execute_sketch after routing |
| `backend/app/services/streaming_helper.py` | **New** — `run_streaming_response()` extracted from `super_agent_chat.py` |
| `backend/app/routes/super_agent_chat.py` | Refactor `_launch_background_thread` to use shared `run_streaming_response` |
| `frontend/src/composables/useSketchChat.ts` | Add SSE streaming after route, expose session info |
| `frontend/src/views/SketchChatPage.vue` | Show streaming response, "Continue in Playground" link, no-target message |

## Files Not Modified

- No schema changes (routing_json already stores arbitrary JSON)
- No migration needed
- No new API endpoints (reuse existing SSE stream endpoint)

## Status Flow

```
draft → classified → routed → in_progress → completed
                       ↑                        │
                       └── (on error, reset) ────┘
```
