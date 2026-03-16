# Team-Aware Sketch Execution & Multi-Agent Collaboration

## Problem

When a sketch is routed to a team, `execute_sketch()` picks only the team leader and runs a single session. The leader agent has no knowledge of its teammates, cannot delegate work via the mailbox, and team members are never woken up. The mailbox system (`AgentMessageBusService`, `agent_messages` table, frontend inbox) exists but is completely disconnected from sketch execution.

Result: The leader agent simulates collaboration (e.g., "@Seraph — Pull the full paper...") but no real messages are sent and no team member sessions start.

## Solution

Wire team context into the leader's execution, parse @mentions from the leader's response to trigger real mailbox messages, start delegate sessions for mentioned team members, and show collaboration progress in the frontend.

## Design

### 1. Team-Aware Sketch Execution (Backend)

**File: `backend/app/services/sketch_execution_service.py`**

#### New function: `get_team_context(team_id) -> dict`

Query `team_members` table for all super agents in the team. Return:
```python
{
  "team_id": str,
  "members": [
    { "super_agent_id": str, "name": str, "role": str, "layer": str, "description": str }
  ]
}
```

SQL: `SELECT tm.super_agent_id, tm.name, tm.role, tm.layer, tm.description, sa.name as agent_name FROM team_members tm JOIN super_agents sa ON tm.super_agent_id = sa.id WHERE tm.team_id = ? AND tm.super_agent_id IS NOT NULL`

#### Modified: `execute_sketch(sketch_id, super_agent_id, content, team_id=None)`

When `team_id` is provided:
1. Call `get_team_context(team_id)` to get team roster
2. Build team context preamble:
   ```
   [TEAM CONTEXT]
   You are the team leader. Your team members are:
   - {name} (role: {role}, layer: {layer}) — {description}
   ...
   To delegate work to a team member, mention them with @Name and describe their task.
   The system will automatically send your instructions via mailbox and start their session.
   [END TEAM CONTEXT]
   ```
3. Prepend team context to the sketch content sent to the leader's session
4. After `run_streaming_response()` completes (via the existing callback), call `process_delegations()`
5. Store team_id and delegation state in `routing_json`

#### New function: `process_delegations(sketch_id, leader_agent_id, leader_response, team_context)`

1. Parse `@Name` mentions from leader_response using regex: `@(\w+)[\s—\-:]+(.+?)(?=@\w+|$)` (with re.DOTALL)
2. Match each name against team_context members (case-insensitive)
3. For each matched member:
   a. Send mailbox message via `AgentMessageBusService.send_message()`:
      - `from_agent_id`: leader's super_agent_id
      - `to_agent_id`: member's super_agent_id
      - `message_type`: 'request'
      - `priority`: 'high'
      - `subject`: f"Sketch delegation: {sketch_title}"
      - `content`: the extracted task text for this member
      - `ttl_seconds`: 3600
   b. Call `execute_delegate()` for each member
   c. Append delegation info to sketch's `routing_json.delegations[]`

#### New function: `execute_delegate(sketch_id, super_agent_id, task_content, leader_agent_id)`

1. `get_or_create_session(super_agent_id)`
2. Build delegate prompt:
   ```
   [DELEGATION FROM TEAM LEADER]
   You have been assigned this task by your team leader.
   Original sketch: {original_sketch_content}

   Your specific assignment:
   {task_content}

   Complete your task and your response will be sent back to the team leader via mailbox.
   [END DELEGATION]
   ```
3. Send message to session, launch `run_streaming_response()` in background thread
4. On completion callback:
   a. Send `response` message back to leader via mailbox
   b. Update `routing_json.delegations[].status` to 'completed'
   c. Check if all delegations complete → if so, update sketch status to 'completed'

### 2. Route Endpoint Changes

**File: `backend/app/routes/sketches.py`**

Modify `POST /admin/sketches/{id}/route`:
- When routing result `target_type == 'team'`, pass `team_id` to `execute_sketch()`
- Include `delegations: []` in the initial routing response (populated later)
- Add new endpoint: `GET /admin/sketches/{id}/delegations` to poll delegation status

### 3. New Sketch Status

Add `collaborating` to the sketch status enum. Transition: `in_progress` (leader executing) → `collaborating` (delegates executing) → `completed`.

Update `sketch_execution_service.py` callbacks to set `collaborating` when `process_delegations()` starts delegates.

### 4. Frontend Changes

**File: `frontend/src/composables/useSketchChat.ts`**

New refs:
```typescript
const delegations = ref<Array<{
  agentId: string;
  agentName: string;
  role: string;
  status: 'pending' | 'in_progress' | 'completed';
  taskSummary: string;
  content: string;
  sessionId?: string;
}>>([]);
```

After routing response:
- If `routing.delegations` exists, populate `delegations` ref
- Poll `GET /admin/sketches/{id}/delegations` every 3 seconds while status is `collaborating`
- For each delegation with a sessionId, optionally open SSE stream for real-time content

New function: `loadDelegations(sketchId)` — fetches current delegation state.

**File: `frontend/src/views/SketchChatPage.vue`**

Add "Team Collaboration" section after the streaming response area:
```html
<div v-if="delegations.length > 0" class="delegations-section">
  <h4>Team Collaboration</h4>
  <div v-for="d in delegations" :key="d.agentId" class="delegation-card">
    <div class="delegation-header">
      <span class="agent-name">{{ d.agentName }}</span>
      <span class="agent-role">{{ d.role }}</span>
      <StatusBadge :status="d.status" />
    </div>
    <p class="task-summary">{{ d.taskSummary }}</p>
    <div v-if="d.content" class="delegate-response">{{ d.content }}</div>
    <router-link v-if="d.sessionId && d.status === 'completed'"
      :to="{ name: 'super-agent-playground', params: { superAgentId: d.agentId } }">
      View in Playground
    </router-link>
  </div>
</div>
```

Styling: Use existing card/badge patterns from the design system. Delegation cards use `var(--bg-secondary)` background, status badges reuse existing `StatusBadge` component.

### 5. Sketch API Extension

**File: `frontend/src/services/api/sketches.ts`**

Add:
```typescript
getDelegations(sketchId: string): Promise<{ delegations: Delegation[] }>
```

**File: `backend/app/routes/sketches.py`**

Add:
```python
@bp.get('/<sketch_id>/delegations')
def get_delegations(sketch_id):
    sketch = get_sketch(sketch_id)
    routing = json.loads(sketch['routing_json'] or '{}')
    return {"delegations": routing.get("delegations", [])}
```

## Files Modified

- `backend/app/services/sketch_execution_service.py` — Team context, delegation parsing, delegate execution
- `backend/app/routes/sketches.py` — Pass team_id, new delegations endpoint
- `frontend/src/composables/useSketchChat.ts` — Delegation refs, polling, streams
- `frontend/src/views/SketchChatPage.vue` — Delegation UI section
- `frontend/src/services/api/sketches.ts` — getDelegations API call

## Files NOT Modified

- `backend/app/services/agent_message_bus_service.py` — Used as-is
- `backend/app/services/sketch_routing_service.py` — Used as-is
- `backend/app/services/super_agent_session_service.py` — Used as-is
- Message schema / DB tables — No changes needed

## Error Handling

- If @mention doesn't match any team member: log warning, skip (don't fail the sketch)
- If delegate session fails to start: mark delegation as 'error', don't block other delegates
- If all delegates timeout (TTL expires): mark sketch as 'completed' with partial results
- If leader response has no @mentions: sketch completes normally (no collaboration phase)
