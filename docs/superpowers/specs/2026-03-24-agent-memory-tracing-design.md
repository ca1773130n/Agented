# Agent Memory & Tracing System Design

**Date**: 2026-03-24
**Status**: Approved (autonomous)
**Inspired by**: Mastra AI (`@mastra/memory`, `@mastra/observability`)

## Overview

Add two major subsystems to Agented, adapted from Mastra's architecture to our Python/Flask/SQLite stack:

1. **Agent Memory** — Thread-based message persistence, working memory (structured scratchpad), and FTS5-based semantic recall across agent sessions
2. **Structured Tracing** — Typed span hierarchy for agent executions with storage, query API, and frontend viewer

## 1. Agent Memory System

### 1.1 Architecture

```
┌─────────────────────────────────────────────────────┐
│ Agent Execution Flow                                │
│                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌───────────┐ │
│  │ Input    │───>│ Memory       │───>│ LLM Call  │ │
│  │ Message  │    │ Processors   │    │ (CLI)     │ │
│  └──────────┘    │              │    └─────┬─────┘ │
│                  │ 1. History   │          │       │
│                  │ 2. Semantic  │          ▼       │
│                  │ 3. Working   │    ┌───────────┐ │
│                  └──────┬───────┘    │ Output    │ │
│                         │            │ Processors│ │
│                         │            │           │ │
│                         │            │ 1. Save   │ │
│                         │            │ 2. Index  │ │
│                         │            │ 3. Update │ │
│                         │            └─────┬─────┘ │
│                         ▼                  ▼       │
│                  ┌──────────────────────────────┐  │
│                  │ SQLite Storage               │  │
│                  │ - memory_threads             │  │
│                  │ - memory_messages            │  │
│                  │ - memory_messages_fts        │  │
│                  │ - agent_working_memory       │  │
│                  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 1.2 Data Model

#### memory_threads
Conversation threads that group messages. Each agent run can belong to a thread.

```sql
CREATE TABLE memory_threads (
    id TEXT PRIMARY KEY,              -- 'thrd-' + 6-char random
    resource_id TEXT NOT NULL,        -- owner entity (agent_id, bot_id, or user identifier)
    resource_type TEXT NOT NULL DEFAULT 'agent',  -- 'agent', 'bot', 'user'
    title TEXT,
    metadata TEXT,                    -- JSON object for arbitrary metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_memory_threads_resource ON memory_threads(resource_id, resource_type);
```

#### memory_messages
Individual messages within threads.

```sql
CREATE TABLE memory_messages (
    id TEXT PRIMARY KEY,              -- 'msg-' + 8-char random
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL,               -- 'user', 'assistant', 'system', 'tool'
    content TEXT NOT NULL,
    type TEXT DEFAULT 'text',         -- 'text', 'tool_call', 'tool_result'
    metadata TEXT,                    -- JSON: tool_name, execution_id, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES memory_threads(id) ON DELETE CASCADE
);
CREATE INDEX idx_memory_messages_thread ON memory_messages(thread_id, created_at);
```

#### memory_messages_fts (FTS5)
Full-text search over message content for semantic recall.

```sql
CREATE VIRTUAL TABLE memory_messages_fts USING fts5(
    content,
    content='memory_messages',
    content_rowid='rowid',
    tokenize='porter unicode61'
);
-- Sync triggers (INSERT/UPDATE/DELETE) like execution_logs_fts
```

#### agent_working_memory
Persistent structured scratchpad per agent or per thread.

```sql
CREATE TABLE agent_working_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,          -- agent_id or thread_id
    entity_type TEXT NOT NULL,        -- 'agent' or 'thread'
    content TEXT NOT NULL,            -- JSON or Markdown content
    template TEXT,                    -- optional template definition
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_id, entity_type)
);
```

### 1.3 Service Layer

**`AgentMemoryService`** (`backend/app/services/agent_memory_service.py`):

```python
class AgentMemoryService:
    # Thread management
    create_thread(resource_id, resource_type, title, metadata) -> dict
    get_thread(thread_id) -> dict
    list_threads(resource_id, resource_type, limit, offset) -> list
    delete_thread(thread_id) -> bool

    # Message management
    save_messages(thread_id, messages: list[dict]) -> list[dict]
    get_messages(thread_id, limit, before_id) -> list[dict]

    # Semantic recall (FTS5-based)
    recall(thread_id, query, top_k=5, message_range=1) -> list[dict]

    # Working memory
    get_working_memory(entity_id, entity_type) -> dict
    update_working_memory(entity_id, entity_type, content, template) -> dict

    # Memory context builder (for injection into agent prompts)
    build_memory_context(agent_id, thread_id, user_message) -> str
```

### 1.4 Integration with Agent Execution

When `AgentService.run_agent()` is called:
1. Find or create a thread for the agent + optional session context
2. Call `AgentMemoryService.build_memory_context()` which:
   - Loads last N messages from thread (message history)
   - Searches FTS5 for semantically relevant past messages (semantic recall)
   - Loads working memory for the agent
   - Formats all into a context block prepended to the prompt
3. After execution completes, save the user message + assistant response to the thread
4. If the response contains working memory updates, persist them

### 1.5 Memory Configuration per Agent

Add `memory_config` JSON column to the `agents` table:

```json
{
    "enabled": true,
    "last_messages": 10,
    "semantic_recall": {
        "enabled": true,
        "top_k": 5,
        "message_range": 1
    },
    "working_memory": {
        "enabled": true,
        "scope": "agent",
        "template": "# Agent Notes\n- **Current Task**:\n- **Key Facts**:\n- **Preferences**:"
    }
}
```

### 1.6 API Routes

**`/admin/agents/<agent_id>/memory`** — Agent memory management:
- `GET /admin/agents/<agent_id>/memory/threads` — List threads
- `POST /admin/agents/<agent_id>/memory/threads` — Create thread
- `GET /admin/agents/<agent_id>/memory/threads/<thread_id>` — Get thread + messages
- `DELETE /admin/agents/<agent_id>/memory/threads/<thread_id>` — Delete thread
- `GET /admin/agents/<agent_id>/memory/threads/<thread_id>/messages` — List messages (paginated)
- `POST /admin/agents/<agent_id>/memory/threads/<thread_id>/messages` — Add messages
- `GET /admin/agents/<agent_id>/memory/recall?q=<query>&thread_id=<id>` — Semantic recall
- `GET /admin/agents/<agent_id>/memory/working` — Get working memory
- `PUT /admin/agents/<agent_id>/memory/working` — Update working memory
- `PUT /admin/agents/<agent_id>/memory/config` — Update memory config

## 2. Structured Tracing System

### 2.1 Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Agent/Bot Execution                                     │
│                                                         │
│  TracingService.start_trace(type=AGENT_RUN)             │
│  ├── span: AGENT_RUN (root)                             │
│  │   ├── attributes: agent_id, prompt, model            │
│  │   │                                                  │
│  │   ├── span: PROMPT_BUILD                             │
│  │   │   └── memory retrieval, template rendering       │
│  │   │                                                  │
│  │   ├── span: EXECUTION (CLI subprocess)               │
│  │   │   ├── attributes: command, backend_type          │
│  │   │   ├── span: TOOL_CALL (if detected in output)    │
│  │   │   │   └── tool_name, input, output               │
│  │   │   └── span: TOOL_CALL ...                        │
│  │   │                                                  │
│  │   └── span: MEMORY_SAVE                              │
│  │       └── messages saved, working memory updated     │
│  │                                                      │
│  TracingService.end_trace()                              │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ SQLite Storage                                          │
│ - traces (root trace records)                           │
│ - trace_spans (individual spans with hierarchy)         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Data Model

#### traces
Root trace records. One per agent run / bot execution.

```sql
CREATE TABLE traces (
    id TEXT PRIMARY KEY,              -- 'trc-' + 8-char random
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,        -- 'agent', 'bot', 'trigger'
    entity_id TEXT NOT NULL,
    execution_id TEXT,                -- links to execution_logs
    status TEXT DEFAULT 'running',    -- 'running', 'completed', 'error'
    input TEXT,                       -- JSON: the input/prompt
    output TEXT,                      -- JSON: the final output
    metadata TEXT,                    -- JSON: tags, custom data
    error_message TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_traces_entity ON traces(entity_type, entity_id);
CREATE INDEX idx_traces_execution ON traces(execution_id);
CREATE INDEX idx_traces_started ON traces(started_at DESC);
```

#### trace_spans
Individual spans within a trace. Supports parent-child hierarchy.

```sql
CREATE TABLE trace_spans (
    id TEXT PRIMARY KEY,              -- 'span-' + 8-char random
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,              -- NULL for root span
    name TEXT NOT NULL,
    span_type TEXT NOT NULL,          -- see Span Types below
    status TEXT DEFAULT 'running',    -- 'running', 'completed', 'error'
    input TEXT,                       -- JSON
    output TEXT,                      -- JSON
    attributes TEXT,                  -- JSON: type-specific attributes
    metadata TEXT,                    -- JSON
    error_message TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    FOREIGN KEY (trace_id) REFERENCES traces(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_span_id) REFERENCES trace_spans(id) ON DELETE SET NULL
);
CREATE INDEX idx_trace_spans_trace ON trace_spans(trace_id, started_at);
CREATE INDEX idx_trace_spans_parent ON trace_spans(parent_span_id);
CREATE INDEX idx_trace_spans_type ON trace_spans(span_type);
```

### 2.3 Span Types

Adapted from Mastra's 16 types to what's relevant for Agented:

| SpanType | Description | Key Attributes |
|----------|-------------|----------------|
| `AGENT_RUN` | Root span for agent execution | agent_id, prompt, model, max_steps |
| `BOT_RUN` | Root span for bot/trigger execution | trigger_id, trigger_type, backend_type |
| `TEAM_RUN` | Root span for team orchestration | team_id, topology |
| `PROMPT_BUILD` | Prompt construction phase | template_vars, snippets_used, memory_injected |
| `EXECUTION` | CLI subprocess execution | command, exit_code, backend_type |
| `TOOL_CALL` | Tool invocation within execution | tool_name, tool_input, tool_output, success |
| `MEMORY_RECALL` | Memory retrieval operation | query, results_count, recall_type |
| `MEMORY_SAVE` | Memory persistence operation | messages_saved, working_memory_updated |
| `BUDGET_CHECK` | Budget verification | monthly_limit, current_spend, allowed |
| `RETRY` | Retry attempt after rate limit | attempt, cooldown_seconds, reason |
| `GENERIC` | Custom/miscellaneous span | (arbitrary attributes) |

### 2.4 Service Layer

**`TracingService`** (`backend/app/services/tracing_service.py`):

```python
class TracingService:
    # Trace lifecycle
    start_trace(name, entity_type, entity_id, execution_id, input, metadata) -> Trace
    end_trace(trace_id, status, output, error_message) -> None

    # Span lifecycle
    start_span(trace_id, name, span_type, parent_span_id, input, attributes) -> Span
    end_span(span_id, status, output, error_message) -> None
    update_span(span_id, attributes, metadata) -> None

    # Query API
    list_traces(entity_type, entity_id, limit, offset, status) -> list
    get_trace(trace_id) -> dict  # includes all spans as tree
    get_trace_timeline(trace_id) -> list  # flat ordered list of spans
    search_traces(query, entity_type, date_range) -> list

    # Statistics
    get_trace_stats(entity_id, entity_type, date_range) -> dict
```

### 2.5 Integration Points

1. **ExecutionService.run_trigger()** — Wrap entire execution in a trace
2. **AgentService.run_agent()** — Create AGENT_RUN trace with child spans for prompt build, execution, memory ops
3. **ExecutionLogService** — Link traces to execution logs via `execution_id`
4. **BudgetService** — Add BUDGET_CHECK span
5. **ExecutionRetryManager** — Add RETRY spans

### 2.6 API Routes

**`/admin/traces`** — Trace browsing and query:
- `GET /admin/traces` — List traces (filterable by entity, status, date range)
- `GET /admin/traces/<trace_id>` — Get trace with full span tree
- `GET /admin/traces/<trace_id>/timeline` — Get flat timeline view
- `GET /admin/traces/stats` — Aggregate statistics
- `GET /admin/agents/<agent_id>/traces` — Agent-specific traces
- `DELETE /admin/traces/<trace_id>` — Delete a trace

## 3. Frontend Components

### 3.1 Memory Views
- **Agent Memory Tab** — New tab on agent detail page showing threads, messages, working memory
- **Thread List** — Sortable list of conversation threads with message counts and last activity
- **Thread Detail** — Scrollable message view with role badges (user/assistant/system/tool)
- **Working Memory Editor** — Inline editor for viewing/editing working memory content
- **Memory Config Panel** — Settings for message history count, semantic recall, working memory template

### 3.2 Trace Views
- **Traces List Page** — Filterable list of all traces with status, duration, entity info
- **Trace Detail Page** — Hierarchical span tree with expandable nodes showing:
  - Span type icon/badge
  - Duration bar (waterfall chart)
  - Input/output JSON viewers
  - Attributes panel
  - Error details
- **Agent Trace Tab** — Agent-specific trace history on agent detail page

## 4. Implementation Phases

### Phase 1: Agent Memory Foundation
- Database schema (memory_threads, memory_messages, memory_messages_fts, agent_working_memory)
- Migration in schema.py
- AgentMemoryService (CRUD, recall, working memory)
- DB layer functions in `backend/app/db/agent_memory.py`
- Pydantic models in `backend/app/models/agent_memory.py`
- API routes in `backend/app/routes/agent_memory.py`
- Integration into AgentService.run_agent() for auto-save
- Add memory_config column to agents table
- Backend tests

### Phase 2: Structured Tracing
- Database schema (traces, trace_spans)
- TracingService with span lifecycle management
- DB layer in `backend/app/db/tracing.py`
- Pydantic models in `backend/app/models/tracing.py`
- API routes in `backend/app/routes/tracing.py`
- Integration into ExecutionService, AgentService
- Backend tests

### Phase 3: Semantic Recall + Memory Pipeline
- FTS5 sync triggers for memory_messages
- Recall algorithm using FTS5 ranking
- Memory context builder for prompt injection
- Memory processor pipeline (ordered: history -> recall -> working memory)
- Integration tests with agent execution flow

### Phase 4: Frontend
- Vue components for memory views (thread list, thread detail, working memory editor)
- Vue components for trace views (trace list, trace detail with span tree)
- New tabs on agent detail page
- API integration in services/api/
- Frontend tests

## 5. Design Decisions

1. **SQLite FTS5 over vector DB** — Agented uses SQLite throughout. FTS5 provides good-enough semantic search without adding a vector DB dependency. Can upgrade to sqlite-vec later.

2. **Thread-based model** — Matches Mastra's thread/resource pattern. Threads group messages logically. Resources (agents) own threads.

3. **Working memory as structured text** — Markdown template approach (like Mastra) is simpler than schema-based for our use case. Agents update it via natural language.

4. **Traces separate from execution_logs** — execution_logs captures raw stdout/stderr. Traces capture structured semantic information about what happened. They link via execution_id.

5. **Span types adapted for CLI execution** — Mastra's types are for in-process LLM calls. Ours are adapted for subprocess-based CLI tool execution.

6. **No Observational Memory in v1** — OM requires background LLM calls (Observer/Reflector agents). Deferred to a future phase.
