# Coding Conventions

**Analysis Date:** 2026-02-25

---

## Python Coding Style

### Formatting

- **Formatter:** Black `26.1.0` with `line-length = 100`, `target-version = ["py310"]`
- **Linter:** Ruff with `select = ["E", "F", "I"]` and `ignore = ["E501", "E402"]`
- Run formatting: `cd backend && uv run black .`
- Lines up to 100 characters are acceptable; Black enforces this automatically

### Naming

- Functions: `snake_case` — e.g., `add_agent()`, `get_all_agents()`, `delete_team_agent_assignment()`
- Classes: `PascalCase` — e.g., `AgentService`, `AgentCreationStatus`, `PaginationQuery`
- Constants: `UPPER_SNAKE_CASE` — e.g., `VALID_BACKENDS`, `PREDEFINED_TRIGGER_IDS`, `TRIGGER_ID_PREFIX`
- Module-level loggers: `logger = logging.getLogger(__name__)` at the top of each file
- Private helpers: underscore-prefixed — e.g., `_get_unique_agent_id()`, `_parse_agent_json_fields()`

### Imports

- Standard library imports first, then third-party, then local (enforced by Ruff `I` rules)
- Use `from http import HTTPStatus` rather than raw integer status codes
- Relative imports within `app/` — e.g., `from ..models.common import PaginationQuery`
- Avoid star imports everywhere

### Type Hints

- Use `Optional[str]` and `List[dict]` from `typing` (Python 3.10 target)
- Return type annotations on all service methods: `-> Tuple[dict, HTTPStatus]`
- DB functions annotate return types: `-> Optional[str]`, `-> bool`, `-> List[dict]`

---

## API Design Patterns

### Blueprint Registration

Each domain gets its own `APIBlueprint` in `backend/app/routes/<domain>.py`:

```python
from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="agents", description="Agent management operations")
agents_bp = APIBlueprint("agents", __name__, url_prefix="/admin/agents", abp_tags=[tag])
```

All blueprints are registered in `backend/app/routes/__init__.py` via `app.register_api(bp)`.
The SPA catch-all blueprint is registered **last** with `app.register_blueprint(spa_bp)`.

### Route Prefix Conventions

- Management/admin routes: `/admin/<entity>/` — e.g., `/admin/agents/`, `/admin/teams/`
- Public API routes: `/api/<domain>/` — e.g., `/api/projects/<id>/sync`, `/api/webhooks/github/`
- Health: `/health/`

### Path Parameter Models

Path parameters are declared as Pydantic models with `Field`:

```python
class AgentPath(BaseModel):
    agent_id: str = Field(..., description="Agent ID")

@agents_bp.get("/<agent_id>")
def get_agent_detail(path: AgentPath):
    ...
```

### Query Parameter Models

Pagination uses a shared `PaginationQuery` from `backend/app/models/common.py`:

```python
class PaginationQuery(BaseModel):
    limit: Optional[int] = Field(None, ge=1, le=500)
    offset: Optional[int] = Field(None, ge=0)

@agents_bp.get("/")
def list_agents(query: PaginationQuery):
    result, status = AgentService.list_agents(limit=query.limit, offset=query.offset or 0)
    return result, status
```

### Request Body Handling

Routes read JSON bodies via `request.get_json()` and pass raw dicts to service layer:

```python
@agents_bp.post("/")
def create_agent():
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = AgentService.create_agent(data)
    return result, status
```

### Response Format

- Success responses: return plain dict + `HTTPStatus` enum (e.g., `HTTPStatus.OK`, `HTTPStatus.CREATED`)
- Error responses: `{"error": "<message>"}` dict + appropriate `HTTPStatus` code
- List responses always include `total_count` alongside the item array
- Standard response models in `backend/app/models/common.py`: `ErrorResponse`, `MessageResponse`

### Route Handler Responsibility

Route handlers are thin — they validate that a body exists, extract data, delegate to service, and return. No business logic in route handlers.

---

## Service Layer Patterns

Services are static-method classes in `backend/app/services/`:

```python
class AgentService:
    @staticmethod
    def list_agents(limit: Optional[int] = None, offset: int = 0) -> Tuple[dict, HTTPStatus]:
        total_count = count_agents()
        agents = get_all_agents(limit=limit, offset=offset)
        return {"agents": agents, "total_count": total_count}, HTTPStatus.OK

    @staticmethod
    def get_agent_detail(agent_id: str) -> Tuple[dict, HTTPStatus]:
        agent = get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND
        return agent, HTTPStatus.OK
```

Services return `(dict, HTTPStatus)` tuples that routes return directly. No exceptions propagated to the route layer.

---

## Database Access Patterns

### Connection Manager

All DB access uses the `get_connection()` context manager from `backend/app/db/connection.py`:

```python
from .connection import get_connection

with get_connection() as conn:
    cursor = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    return dict(row) if row else None
```

The connection enables foreign keys, sets `busy_timeout = 5000`, and uses `sqlite3.Row` factory so columns are accessible by name.

### CRUD Function Structure

DB functions in `backend/app/db/<entity>.py` follow a consistent pattern:
- `add_<entity>(...)` — returns the new ID string or `None` on `IntegrityError`
- `get_<entity>(id)` — returns `dict` or `None`
- `get_all_<entity>(limit, offset)` — returns `List[dict]`
- `count_<entity>()` — returns `int`
- `update_<entity>(id, **kwargs)` — returns `bool`
- `delete_<entity>(id)` — returns `bool`

### Update Pattern

Updates build a dynamic `SET` clause using explicit `None` checks:

```python
def update_agent(agent_id: str, name: str = None, ...):
    updates = []
    values = []
    if name is not None:
        updates.append("name = ?")
        values.append(name)
    # ...
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(agent_id)
    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0
```

### Row-to-Dict Conversion

Always convert `sqlite3.Row` to dict immediately: `dict(row)` or `[dict(row) for row in cursor.fetchall()]`.

### DB Path Configuration

The DB path is read from `app.config.DB_PATH` at runtime (not at import time), allowing tests to patch it via `monkeypatch.setattr("app.config.DB_PATH", ...)`.

---

## ID Generation Conventions

All entity IDs are defined in `backend/app/db/ids.py`. Format: `<prefix>-<random_lowercase_alnum>`.

| Entity | Prefix | Random Length | Example |
|--------|--------|---------------|---------|
| Trigger | `trig-` | 6 | `trig-abc123` |
| Agent | `agent-` | 6 | `agent-abc123` |
| Conversation | `conv-` | 8 | `conv-abc12345` |
| Team | `team-` | 6 | `team-abc123` |
| Product | `prod-` | 6 | `prod-abc123` |
| Project | `proj-` | 6 | `proj-abc123` |
| Plugin | `plug-` | 6 | `plug-abc123` |
| Super Agent | `super-` | 6 | `super-abc123` |
| Session | `sess-` | 8 | `sess-abc12345` |
| Workflow | `wf-` | 6 | `wf-abc123` |
| Workflow Execution | `wfx-` | 8 | `wfx-abc12345` |
| Sketch | `sketch-` | 6 | `sketch-abc123` |
| Milestone | `ms-` | 6 | `ms-abc123` |
| Phase | `phase-` | 6 | `phase-abc123` |
| Plan | `plan-` | 6 | `plan-abc123` |
| Project Session | `psess-` | 8 | `psess-abc12345` |

Each entity also has a collision-safe `_get_unique_<entity>_id(conn)` variant that loops until a non-colliding ID is found. Always use the collision-safe variants when inserting into the database.

Predefined trigger IDs use the legacy `bot-` prefix (`bot-security`, `bot-pr-review`) to preserve historical records.

---

## Error Handling Patterns

### Flask Global Handlers

Registered in `backend/app/__init__.py`:
- 404 → `{"error": "Not found"}`
- 405 → `{"error": "Method not allowed"}`
- 413 → `{"error": "Payload too large"}`
- 500 → `{"error": "Internal server error"}`
- `sqlite3.OperationalError` → 503 `{"error": "Service temporarily unavailable"}`

### Service Layer

Services never raise exceptions to routes. They catch database errors locally and return `({"error": "..."}, HTTPStatus.INTERNAL_SERVER_ERROR)` tuples.

### DB Layer

DB functions catch `sqlite3.IntegrityError` and return `None` to signal failure without propagating.

---

## Pydantic Model Conventions

Models live in `backend/app/models/<entity>.py`. Three types of models exist:
1. **Entity models** (e.g., `Agent`) — full representation with `id`, `created_at`, `updated_at`
2. **Request models** (e.g., `CreateAgentRequest`, `UpdateAgentRequest`) — body validation; all update fields are `Optional`
3. **Response models** (e.g., `AgentListResponse`, `CreateAgentResponse`) — typed return shapes

Use `str(Enum)` for string enums:

```python
class EffortLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"
```

Use `Field` with `pattern` for ID fields that must match a prefix:

```python
id: str = Field(..., pattern=r"^agent-[a-z0-9-]+$", examples=["agent-abc123"])
```

---

## TypeScript / Vue Coding Style

### Language

TypeScript throughout. All `.vue` files use `<script setup lang="ts">`. All type imports use `import type { ... }`.

### Vue Component Structure

Components use Composition API with `<script setup>`. Props use TypeScript generic syntax (not `defineProps({})` with object config):

```vue
<script setup lang="ts">
defineProps<{
  label: string;
  variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'violet';
}>();
</script>
```

Emits follow the same pattern:

```typescript
const emit = defineEmits<{
  sort: [field: string];
  'row-click': [item: T];
}>();
```

### State Management

No Vuex/Pinia. All state is component-local using `ref` and `reactive`. Cross-cutting concerns use `provide`/`inject`:

- `showToast` — provided by `App.vue`, consumed via `useToast()` composable
- `refreshTriggers` — provided by `App.vue` for sidebar sync

### Composables

Composables live in `frontend/src/composables/`. Naming: `use<PascalCase>`. They return typed objects:

```typescript
// frontend/src/composables/useDataPage.ts
export function useDataPage<T>(options: UseDataPageOptions<T>): UseDataPageReturn<T> { ... }
```

Common composables used in view pages:
- `useListFilter` — client-side search/sort with `localStorage` persistence
- `usePagination` — page/size state with `localStorage` persistence
- `useDataPage` — combines loading, `useListFilter`, and `usePagination`
- `useToast` — typed access to injected `showToast`
- `useStreamingGeneration` — SSE-based streaming log display
- `useFocusTrap` — modal accessibility

### API Client

All API calls go through `frontend/src/services/api/client.ts` via `apiFetch<T>()`. Domain modules (e.g., `frontend/src/services/api/agents.ts`) export typed API objects:

```typescript
export const agentApi = {
  list: () => apiFetch<{ agents: Agent[]; total_count: number }>('/admin/agents'),
  get: (id: string) => apiFetch<Agent>(`/admin/agents/${id}`),
  create: (data: CreateAgentRequest) => apiFetch<{ agent_id: string }>('/admin/agents', {
    method: 'POST', body: JSON.stringify(data),
  }),
};
```

All types are declared in `frontend/src/services/api/types.ts` and re-exported from `frontend/src/services/api/index.ts`.

`apiFetch` includes:
- 30-second request timeout via `AbortController`
- Exponential backoff retry on 429, 502, 503, 504
- `Retry-After` header parsing for 429 responses

SSE connections use `createBackoffEventSource()` from `client.ts`, which adds reconnection backoff and backpressure queue.

### CSS Conventions

- BEM-style CSS with `ds-` prefix for design system components: `ds-page-header`, `ds-status-badge`, `ds-status-success`
- Scoped styles on all components using `<style scoped>`
- CSS custom properties defined in `App.vue` for the dark theme: `var(--text-primary)`, `var(--accent-emerald)`, `var(--accent-crimson-dim)`

### Component Organization

```
frontend/src/components/
  base/          — shared UI primitives (PageHeader, StatusBadge, DataTable, etc.)
  ai/            — AI chat and streaming components
  canvas/        — team/workflow canvas components
  grd/           — GRD project management components
  layout/        — AppSidebar and layout shell
  monitoring/    — charts and monitoring widgets
  triggers/      — trigger-specific modals/viewers
  teams/         — team-specific components
  ...            — one directory per domain
```

---

## Schema Conventions

### Database Schema

Schema is defined in `backend/app/db/schema.py` (`create_fresh_schema()`). New tables/columns are added via migration functions appended to `backend/app/db/migrations.py`.

- All timestamps use `TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- Foreign keys use `ON DELETE CASCADE` for child records, `ON DELETE SET NULL` for optional references
- Boolean-like fields stored as `INTEGER` (`0`/`1`) not `BOOLEAN`
- JSON array fields stored as `TEXT` (serialize/deserialize in service layer)
- All entity tables have `TEXT PRIMARY KEY` (except junction tables which use `INTEGER AUTOINCREMENT`)

---

*Conventions analysis: 2026-02-25*
