# System Error Logging, Dashboard & Autofix

## Problem

Agented has no persistent error logging. Backend logs go to stderr only and vanish on restart. Frontend errors appear as transient toasts that auto-dismiss before users can read them. When something breaks (CLIProxyAPI down, bad API key, runtime exceptions), there's no way to review what happened, and every fix requires manual investigation.

## Solution

Three-layer system: (1) persistent error capture from both backend and frontend, (2) an autofix engine with predefined operations for known errors and an agent fallback for novel ones, (3) a dashboard page to view errors, fix attempts, and trigger retries.

## Design

### 1. Error Logging Infrastructure

#### Backend File Logging

**File: `backend/app/logging_config.py`**

Add `RotatingFileHandler` inside `configure_logging()` alongside the existing `StreamHandler(sys.stderr)`. The function already calls `root.handlers.clear()` before adding handlers, so the file handler is added right after the stderr handler in the same function:
- Path: `backend/data/logs/agented.log`
- Max size: 10MB, 5 backup files
- Same JSON formatter as stderr output
- Create `data/logs/` directory at the top of `configure_logging()` if missing via `os.makedirs(..., exist_ok=True)`

#### New DB Table: `system_errors`

```sql
CREATE TABLE system_errors (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL CHECK(source IN ('backend', 'frontend')),
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT,
    request_id TEXT,
    context_json TEXT,
    error_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'investigating', 'fixed', 'ignored')),
    fix_attempt_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_system_errors_status ON system_errors(status);
CREATE INDEX idx_system_errors_hash ON system_errors(error_hash);
CREATE INDEX idx_system_errors_timestamp ON system_errors(timestamp DESC);
```

Fields:
- `id`: prefixed `err-` + 6-char random suffix
- `source`: `backend` or `frontend`
- `category`: `cli_error`, `proxy_error`, `streaming_error`, `runtime_error`, `frontend_error`, `db_error`
- `context_json`: JSON with relevant IDs — `{ agent_id, session_id, sketch_id, url, component }` etc.
- `error_hash`: SHA256 of `category + normalized_message` (variable parts like IDs/timestamps stripped) for dedup

#### Error Capture Points

**Backend** — Add error capture calls in:
- `conversation_streaming.py`: `_stream_via_cli`, `_stream_via_proxy`, `_stream_via_litellm` error paths
- `sketch_execution_service.py`: `execute_sketch`, `execute_delegate` error callbacks
- `streaming_helper.py`: `run_streaming_response` exception handler
- Flask global error handlers in `create_app()`: 500, `sqlite3.OperationalError`

Each capture point calls a new `capture_error()` function:
```python
def capture_error(
    category: str,
    message: str,
    stack_trace: str = None,
    request_id: str = None,
    context: dict = None,
) -> Optional[str]:
    """Persist error to system_errors table and trigger autofix. Returns error ID."""
```

**Frontend** — Two capture mechanisms:
1. Global `app.config.errorHandler` in `App.vue` — catches unhandled Vue errors
2. Enhanced `handleApiError()` in `error-handler.ts` — reports API errors

Both POST to `POST /admin/system/errors` with `{ source: 'frontend', category, message, stack_trace, context_json }`.

#### API Endpoints

**File: `backend/app/routes/system.py`** — New blueprint `system_bp` at `/admin/system`

- `GET /admin/system/errors` — List errors with filters: `status`, `category`, `source`, `since` (ISO timestamp), `search` (text match), `limit`, `offset`. Returns `{ errors: [...], total_count: int }`.
- `POST /admin/system/errors` — Frontend error reporting. Body: `{ source, category, message, stack_trace?, context_json? }`. Returns `{ error_id }`.
- `GET /admin/system/errors/<error_id>` — Single error with fix attempts joined.
- `PATCH /admin/system/errors/<error_id>` — Update status. Body: `{ status }`.
- `POST /admin/system/errors/<error_id>/retry-fix` — Re-trigger autofix for this error.
- `GET /admin/system/logs` — Tail recent log file. Query: `lines` (default 100, max 1000 — server-validated). Returns `{ lines: [...] }`. Reads from end of file only to avoid loading the full 10MB log.

### 2. Autofix Engine

**File: `backend/app/services/autofix_service.py`**

#### Dedup Layer

When `capture_error()` is called:
1. Compute `error_hash` from `category + message_template` (regex-strip UUIDs, timestamps, file paths)
2. Query `system_errors` for same `error_hash` with `timestamp > now - 60s` and `status != 'ignored'`
3. If found: insert error record but skip autofix trigger
4. If not found: insert error record, trigger autofix

#### Tier 1 — Predefined Safe Operations

A `FIX_REGISTRY` dict maps error patterns (regex on `category:message`) to fix functions:

```python
FIX_REGISTRY = {
    r"proxy_error:.*Could not connect.*8317": fix_cliproxy_not_running,
    r"proxy_error:.*Invalid API key": fix_cliproxy_auth,
    r"cli_error:.*rate.limit|429": fix_rate_limited,
    r"cli_error:.*exit code 1": fix_cli_config,
    r"db_error:.*database is locked": fix_db_locked,
    r"streaming_error:.*session.*stale": fix_stale_session,
}
```

Each fix function signature:
```python
def fix_cliproxy_not_running(error: dict) -> dict:
    """Returns { success: bool, action_taken: str }"""
```

Example implementations:
- `fix_cliproxy_not_running`: Run `subprocess.Popen(["cliproxyapi"])`, wait 2s, health check port 8317
- `fix_cliproxy_auth`: Re-read global config key, update `~/.cli-proxy-api/config.yaml`, health check
- `fix_rate_limited`: Call `BackendService.get_accounts(backend_id)` to find an alternate account where `rate_limited_until` is null or expired, then call `BackendService.set_default_account(backend_id, account_id)` to rotate. If no alternate account is available, report failure.
- `fix_db_locked`: Retry the original DB write with exponential backoff (3 attempts, 0.1s/0.5s/2s delays). Uses `get_connection()` for a fresh connection each retry.
- `fix_stale_session`: Delete the `super_agent_sessions` row for the session_id in the error's `context_json`, then call `SuperAgentSessionService.get_or_create_session(super_agent_id)` to create a fresh one. The `super_agent_id` and `session_id` are extracted from `context_json`.

#### Tier 2 — Agent Investigation

When no Tier 1 pattern matches:

1. Get or create session for `sa-system`
2. Build investigation prompt:
   ```
   [SYSTEM ERROR - AUTOFIX REQUEST]
   An error occurred in the Agented platform that needs investigation.

   Error ID: {error_id}
   Category: {category}
   Message: {message}
   Stack Trace: {stack_trace}
   Context: {context_json}
   Recent Related Logs: {last_20_log_lines_matching_request_id_or_last_50_lines_if_no_request_id}

   Investigate this error. You have access to the Agented codebase at the current working directory.
   Diagnose the root cause, apply a fix if possible, and report what you did.
   [END SYSTEM ERROR]
   ```
3. Send to session, launch `run_streaming_response()`
4. On completion: parse response, update fix attempt status

#### New DB Table: `fix_attempts`

```sql
CREATE TABLE fix_attempts (
    id TEXT PRIMARY KEY,
    error_id TEXT NOT NULL REFERENCES system_errors(id),
    tier INTEGER NOT NULL CHECK(tier IN (1, 2)),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'success', 'failed')),
    action_taken TEXT,
    agent_session_id TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_fix_attempts_error_id ON fix_attempts(error_id);
```

#### Autofix Flow

```
capture_error() called
  → compute error_hash
  → INSERT into system_errors
  → dedup check (same hash in last 60s?)
    → yes: skip autofix
    → no: trigger_autofix(error_id)

trigger_autofix(error_id)
  → check status != 'ignored'
  → INSERT fix_attempt (status='pending')
  → UPDATE system_errors SET status='investigating'
  → match against FIX_REGISTRY
    → match found (Tier 1):
        → UPDATE fix_attempt SET status='running', tier=1
        → execute fix function
        → UPDATE fix_attempt SET status=success/failed, action_taken, completed_at
    → no match (Tier 2):
        → UPDATE fix_attempt SET status='running', tier=2
        → send to sa-system agent session
        → on_complete: UPDATE fix_attempt SET status=success/failed, action_taken, completed_at
  → UPDATE system_errors SET status='fixed'/'new' based on result
```

### 3. System Agent

**Seeded on startup** in `create_app()` alongside predefined bots. Uses a fixed hardcoded ID (same pattern as `bot-security` and `bot-pr-review` — intentionally not auto-generated). The `sa-` prefix matches existing super agent IDs (`sa-neo`, `sa-trinity`, etc.):
- `id`: `sa-system` (fixed, not generated — checked for existence before insert)
- `name`: "System"
- `description`: "Automated error diagnosis and repair agent for the Agented platform"
- `backend_type`: `claude`
- Not added to any team — operates independently

System prompt focuses on:
- Understanding Agented architecture (Flask + Vue + SQLite + CLIProxyAPI)
- Reading error context, logs, and source files
- Editing config files, restarting services, fixing code
- Reporting diagnosis and verification of fix

### 4. Error Dashboard

**New route: `/admin/system/errors`** — `SystemErrorsPage.vue`

#### Layout
Full-width table with filter bar at top. Row click opens detail panel on right (same pattern as SketchChatPage info panel).

#### Table Columns
- Timestamp (relative, e.g., "2m ago")
- Source (badge: `backend` / `frontend`)
- Category (badge by type)
- Message (truncated to ~80 chars)
- Status (badge: new/investigating/fixed/ignored)
- Fix (Tier badge + result icon)

#### Filter Bar
- Status dropdown: All / New / Investigating / Fixed / Ignored
- Category dropdown: All / cli_error / proxy_error / streaming_error / runtime_error / frontend_error / db_error
- Source dropdown: All / Backend / Frontend
- Time range: Last Hour / Last Day / Last Week / All
- Search text input

#### Detail Panel (on row click)
- Full error message
- Stack trace (collapsible, monospace `<pre>`)
- Context: linked agent/session/sketch IDs (clickable `<router-link>`)
- Request ID
- Fix attempts list: tier badge, action taken, result, timestamp
- Action buttons: "Retry Fix" (re-triggers autofix), "Ignore" (marks ignored, suppresses future autofix for this hash)

#### Real-time Updates
- Poll `GET /admin/system/errors?status=new&since={last_poll}` every 10 seconds when dashboard is open
- Sidebar nav badge showing count of `status=new` errors (poll every 30 seconds globally)

#### Toast Enhancement

**File: `frontend/src/App.vue`**

- Error toast auto-dismiss extended from current duration to 8 seconds
- Error toasts include a "View Details" link that navigates to `/admin/system/errors?highlight={error_id}`

**File: `frontend/src/services/api/error-handler.ts`**

- `handleApiError()` enhanced to POST error to backend before showing toast
- Toast message includes the error ID for cross-reference

### 5. Frontend API Extension

**File: `frontend/src/services/api/system.ts`** — Add to existing file (already exports `healthApi`, `versionApi`, `utilityApi`, `settingsApi`, `setupApi`)

```typescript
export const systemApi = {
  listErrors: (params?) => apiFetch('/admin/system/errors', ...),
  getError: (id) => apiFetch(`/admin/system/errors/${id}`),
  reportError: (data) => apiFetch('/admin/system/errors', { method: 'POST', ... }),
  updateError: (id, data) => apiFetch(`/admin/system/errors/${id}`, { method: 'PATCH', ... }),
  retryFix: (id) => apiFetch(`/admin/system/errors/${id}/retry-fix`, { method: 'POST' }),
  getLogs: (lines?) => apiFetch(`/admin/system/logs?lines=${lines}`),
};
```

**File: `frontend/src/services/api/types/system.ts`** — New file in existing `types/` directory (follows convention: `sketches.ts`, `teams.ts`, etc.)

```typescript
export type ErrorSource = 'backend' | 'frontend';
export type ErrorCategory = 'cli_error' | 'proxy_error' | 'streaming_error' | 'runtime_error' | 'frontend_error' | 'db_error';
export type ErrorStatus = 'new' | 'investigating' | 'fixed' | 'ignored';
export type FixTier = 1 | 2;
export type FixStatus = 'pending' | 'running' | 'success' | 'failed';

export interface SystemError {
  id: string;
  timestamp: string;
  source: ErrorSource;
  category: ErrorCategory;
  message: string;
  stack_trace?: string;
  request_id?: string;
  context_json?: string;
  error_hash: string;
  status: ErrorStatus;
  fix_attempt_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface FixAttempt {
  id: string;
  error_id: string;
  tier: FixTier;
  status: FixStatus;
  action_taken?: string;
  agent_session_id?: string;
  started_at: string;
  completed_at?: string;
  created_at?: string;
}
```

## Files Modified

- `backend/app/logging_config.py` — Add RotatingFileHandler inside configure_logging()
- `backend/app/__init__.py` — Seed sa-system agent, register system blueprint
- `backend/app/db/schema.py` — Add system_errors and fix_attempts tables
- `backend/app/db/migrations.py` — Add numbered migrations for system_errors and fix_attempts tables
- `backend/app/db/system_errors.py` — CRUD for system_errors and fix_attempts (new file)
- `backend/app/services/autofix_service.py` — Autofix engine (new file)
- `backend/app/services/error_capture.py` — capture_error() utility (new file)
- `backend/app/services/conversation_streaming.py` — Add capture_error calls
- `backend/app/services/sketch_execution_service.py` — Add capture_error calls
- `backend/app/services/streaming_helper.py` — Add capture_error calls
- `backend/app/routes/system.py` — System API endpoints (new file)
- `backend/app/models/system.py` — Pydantic models for system endpoints (new file)
- `frontend/src/App.vue` — Global error handler, toast duration
- `frontend/src/services/api/system.ts` — Add systemApi to existing file
- `frontend/src/services/api/types/system.ts` — System types (new file in existing types/ dir)
- `frontend/src/services/api/error-handler.ts` — Enhanced to report errors
- `frontend/src/views/SystemErrorsPage.vue` — Error dashboard (new file)
- `frontend/src/composables/useSystemErrors.ts` — Dashboard composable (new file)
- `frontend/src/router/` — Add system errors route

## Files NOT Modified

- `backend/app/services/agent_message_bus_service.py` — Used as-is
- `backend/app/services/super_agent_session_service.py` — Used as-is
- `backend/app/db/connection.py` — Used as-is

## Error Handling

- If `capture_error()` itself fails (e.g., DB locked), log to stderr and continue — never crash the main request
- If Tier 1 fix fails, update fix_attempt as failed, leave error as `new` for retry
- If Tier 2 agent session fails to start, mark fix_attempt as failed, don't block
- If frontend can't POST error report (network down), log to console only
- Dedup window (60s) prevents fix storms from cascading failures
- Errors with status `ignored` never trigger autofix
