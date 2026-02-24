# Miscellaneous Feature Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 4 improvements: SSE heartbeat reconnect, structured trace logging, execution log full-text search, and canvas export (PNG/JSON).

**Architecture:** Minimal targeted changes — each task touches only the files described, no cross-cutting refactors. Backend changes use existing patterns (Flask routes, logging module, SQLite). Frontend changes use Vue 3 Composition API and add html-to-image for canvas export.

**Tech Stack:** Flask/Python backend, Vue 3 + TypeScript frontend, Vitest tests, html-to-image for PNG export.

---

### Task 1: SSE Heartbeat — execution log service

**Files:**
- Modify: `backend/app/services/execution_log_service.py:233-234`

**Step 1: Replace bare keepalive comment with timestamped heartbeat comment**

In `subscribe()`, change the `Empty` timeout handler from:
```python
yield ": keepalive\n\n"
```
To:
```python
yield f": heartbeat {datetime.datetime.now().isoformat()}\n\n"
```

This makes the comment carry a timestamp so operators can see when the last heartbeat was sent in logs/traces.

**Step 2: Run backend tests**

```bash
cd backend && uv run pytest -x -q
```

Expected: all pass.

**Step 3: Commit**

```bash
git add backend/app/services/execution_log_service.py
git commit -m "fix: add timestamp to SSE keepalive comment in execution log stream"
```

---

### Task 2: SSE Heartbeat — chat state service + client-side watchdog

**Files:**
- Modify: `backend/app/services/chat_state_service.py:179`
- Modify: `frontend/src/composables/useAiChat.ts`

**Step 1: Add timestamp to chat heartbeat comment**

In `chat_state_service.py`, change:
```python
yield ": heartbeat\n\n"
```
To:
```python
import datetime  # already imported at top
yield f": heartbeat {datetime.datetime.now().isoformat()}\n\n"
```

**Step 2: Add reconnect watchdog to useAiChat.ts**

After `let eventSource: EventSource | null = null;`, add:

```typescript
// Watchdog: reconnect if no SSE activity for 65 s (server heartbeat is 30 s)
// SSE comment keepalives are NOT visible to EventSource; we reset the watchdog
// on every *named* event. If the connection goes stale without an error event
// (e.g., silent proxy timeout), the watchdog forces a reconnect.
// Reconnect protocol:
//   1. close old EventSource
//   2. call connectStream() — EventSource auto-sends Last-Event-ID header
//   3. server replays missed events from last_seq
const HEARTBEAT_TIMEOUT_MS = 65_000
let _heartbeatTimer: ReturnType<typeof setTimeout> | null = null

function _resetHeartbeat() {
  if (_heartbeatTimer) clearTimeout(_heartbeatTimer)
  _heartbeatTimer = setTimeout(() => {
    if (sessionId.value && eventSource) {
      console.warn('[useAiChat] No SSE activity for 65 s — reconnecting')
      connectStream()
    }
  }, HEARTBEAT_TIMEOUT_MS)
}

function _clearHeartbeat() {
  if (_heartbeatTimer) {
    clearTimeout(_heartbeatTimer)
    _heartbeatTimer = null
  }
}
```

In `connectStream()`, after setting up event listeners, call `_resetHeartbeat()`.

In the `state_delta` listener, call `_resetHeartbeat()` at the top of the handler (so any real event resets the watchdog).

In `closeStream()`, call `_clearHeartbeat()`.

In `cleanup()`, call `_clearHeartbeat()`.

**Step 3: Run frontend tests**

```bash
cd frontend && npm run test:run
```

Expected: all pass.

**Step 4: Commit**

```bash
git add backend/app/services/chat_state_service.py frontend/src/composables/useAiChat.ts
git commit -m "feat: add SSE heartbeat timestamps and client-side reconnect watchdog"
```

---

### Task 3: Structured logging with trace IDs

**Files:**
- Modify: `backend/app/services/execution_service.py`

**Step 1: Add trace-ID aware logger factory**

Near the top of `execution_service.py` (after `logger = logging.getLogger(__name__)`), add:

```python
def _trace_logger(execution_id: str) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that prefixes every log record with the execution trace ID."""
    return logging.LoggerAdapter(logger, {"trace_id": execution_id})
```

**Step 2: Wire trace_id into the log formatter (optional but complete)**

This is only needed if you want the trace_id to appear in output. Add a note:
```
# To surface trace_id in output, configure the root logger format to include %(trace_id)s
# e.g. logging.basicConfig(format='[%(trace_id)s] %(levelname)s %(message)s')
# The adapter safely provides trace_id='' when not set via LoggerAdapter defaults.
```

**Step 3: Use trace logger in _run_execution**

Find the main execution-running method (likely `_run_execution` or similar). Replace bare `logger.info(...)` / `logger.error(...)` calls inside the per-execution branch with:

```python
tlog = _trace_logger(execution_id)
tlog.info("Starting subprocess: %s", command)
# ... replace other logger.* calls within the execution scope ...
tlog.info("Execution finished with exit_code=%s", exit_code)
```

**Step 4: Run backend tests**

```bash
cd backend && uv run pytest -x -q
```

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/services/execution_service.py
git commit -m "feat: add structured trace logging via LoggerAdapter in execution service"
```

---

### Task 4: Full-text search over execution logs

**Files:**
- Modify: `backend/app/routes/executions.py`

**Step 1: Add ?q= search to get_execution endpoint**

Replace the `get_execution` handler body with:

```python
@executions_bp.get("/executions/<execution_id>")
def get_execution(path: ExecutionPath):
    """Get a single execution with full logs. Supports ?q= to filter log lines."""
    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND

    q = request.args.get("q", "").strip()
    if q:
        execution = dict(execution)  # shallow copy — don't mutate cached object
        q_lower = q.lower()
        for field in ("stdout_log", "stderr_log"):
            raw = execution.get(field) or ""
            matched = [line for line in raw.splitlines() if q_lower in line.lower()]
            execution[field] = "\n".join(matched)
        execution["log_search_query"] = q
        execution["log_match_count"] = sum(
            len((execution.get(f) or "").splitlines()) for f in ("stdout_log", "stderr_log")
        )

    return execution, HTTPStatus.OK
```

**Step 2: Run backend tests**

```bash
cd backend && uv run pytest -x -q
```

Expected: all pass.

**Step 3: Commit**

```bash
git add backend/app/routes/executions.py
git commit -m "feat: add ?q= full-text search filter for execution log lines"
```

---

### Task 5: Canvas export — install html-to-image

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install html-to-image**

```bash
cd frontend && npm install html-to-image
```

**Step 2: Verify package.json updated**

Check that `html-to-image` appears in dependencies.

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add html-to-image dependency for canvas PNG export"
```

---

### Task 6: Canvas export — CanvasToolbar buttons

**Files:**
- Modify: `frontend/src/components/canvas/CanvasToolbar.vue`

**Step 1: Add export emits and buttons**

Add `export-png` and `export-json` to the `defineEmits` block.

Before the Save button separator, add:

```html
<div class="toolbar-separator"></div>
<button class="toolbar-btn" title="Export as PNG" @click="$emit('export-png')">
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <rect x="1" y="1" width="14" height="14" rx="2"/>
    <path d="M1 10l4-4 3 3 3-4 4 5"/>
  </svg>
  PNG
</button>
<button class="toolbar-btn" title="Export topology as JSON" @click="$emit('export-json')">
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4 2H2a1 1 0 00-1 1v10a1 1 0 001 1h2"/>
    <path d="M12 2h2a1 1 0 011 1v10a1 1 0 01-1 1h-2"/>
    <line x1="5" y1="8" x2="11" y2="8"/>
  </svg>
  JSON
</button>
```

**Step 2: Commit**

```bash
git add frontend/src/components/canvas/CanvasToolbar.vue
git commit -m "feat: add export PNG/JSON buttons to canvas toolbar"
```

---

### Task 7: Canvas export — implement handlers in TeamCanvas

**Files:**
- Modify: `frontend/src/components/canvas/TeamCanvas.vue`

**Step 1: Add import and handlers**

At the top of the script, add:
```typescript
import { toPng } from 'html-to-image'
```

Add two functions:

```typescript
async function handleExportPng() {
  const el = document.querySelector<HTMLElement>('.team-flow')
  if (!el) return
  try {
    const dataUrl = await toPng(el)
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = `team-${props.team?.name || 'canvas'}.png`
    a.click()
  } catch (e) {
    showToast('Failed to export PNG', 'error')
  }
}

function handleExportJson() {
  const payload = {
    team_id: props.team?.id,
    team_name: props.team?.name,
    topology: props.team?.topology,
    nodes: nodes.value.map(n => ({ id: n.id, type: n.type, position: n.position, data: n.data })),
    edges: edges.value.map(e => ({ id: e.id, source: e.source, target: e.target, data: e.data })),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `team-${props.team?.name || 'canvas'}.json`
  a.click()
  URL.revokeObjectURL(url)
}
```

**Step 2: Wire handlers to CanvasToolbar**

In the template, add `@export-png="handleExportPng"` and `@export-json="handleExportJson"` to `<CanvasToolbar>`.

**Step 3: Run frontend tests**

```bash
cd frontend && npm run test:run
```

Expected: all pass.

**Step 4: Commit**

```bash
git add frontend/src/components/canvas/TeamCanvas.vue
git commit -m "feat: implement canvas export as PNG and JSON in TeamCanvas"
```

---

### Final: Verify all tests pass

```bash
cd backend && uv run pytest -q
cd frontend && npm run test:run
```
