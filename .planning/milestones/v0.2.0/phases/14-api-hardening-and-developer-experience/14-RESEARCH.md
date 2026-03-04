# Phase 14: API Hardening & Developer Experience - Research

**Researched:** 2026-03-04
**Domain:** REST API design, Flask middleware, pagination, rate limiting, cron scheduling
**Confidence:** HIGH

## Summary

Phase 14 adds ten cross-cutting API capabilities to the Agented platform: dry-run mode, unified error responses, pagination on all list endpoints, execution filtering, bulk operations, rate limiting, request ID propagation, cost estimation, workflow DAG validation, and cron expression support. The research reveals that the codebase already has partial implementations for many of these requirements -- Flask-Limiter is installed and configured with per-blueprint limits (API-06 partially done), request ID middleware with contextvars propagation already exists (API-07 partially done), offset-based `PaginationQuery` is used by 10 of ~29 list endpoints (API-03 partially done), workflow DAG validation with `graphlib.TopologicalSorter` is already implemented (API-09 partially done), a `preview_prompt` dry-run endpoint exists for triggers (API-01 partially done), and `BudgetService.estimate_cost()` already exists (API-08 partially done). The remaining work is primarily extension, unification, and gap-filling rather than greenfield development.

**Primary recommendation:** Extend the existing patterns uniformly across the codebase. Use APScheduler's built-in `CronTrigger.from_crontab()` for standard 5-field cron parsing (API-10). Adopt the resource-specific bulk endpoint pattern (`POST /admin/<entity>/bulk`) for bulk operations (API-05). Promote the existing `ErrorResponse` Pydantic model to be the sole error response shape across all endpoints (API-02).

## Standard Stack

### Core (Already Installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `flask-limiter` | 4.1.1 | Per-route and per-blueprint rate limiting | Already in `pyproject.toml` and `create_app()`. Flask ecosystem standard for rate limiting. 4k+ GitHub stars. |
| `APScheduler` | 3.10+ | Cron expression parsing via `CronTrigger.from_crontab()` | Already installed. Supports standard 5-field cron syntax out of the box -- no additional cron library needed. |
| `pydantic` | 2.x | Request/response model validation, `ErrorResponse` model | Already the validation layer. Natural home for unified error response models. |
| `python-json-logger` | 3.2+ | Structured JSON logging with request ID | Already installed and configured in `logging_config.py`. |

### Supporting (No New Dependencies Required)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `graphlib` | stdlib | DAG cycle detection via `TopologicalSorter` | Already used in `workflow_execution_service.py` and `db/workflows.py`. |
| `contextvars` | stdlib | Request ID propagation across async/threaded contexts | Already used in `middleware.py` via `request_id_var`. |
| `uuid` | stdlib | Request ID generation | Already used in `middleware.py`. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| APScheduler's `CronTrigger.from_crontab()` | `cronsim` (standalone cron parser) | CronSim is lighter and has better Debian cron compatibility, but adds a new dependency. APScheduler is already installed and its `from_crontab()` handles standard 5-field expressions. | Use APScheduler -- zero new dependencies. |
| APScheduler's `CronTrigger.from_crontab()` | `croniter` | Croniter was deprecated/unpublished as of March 2025. Not a viable option. | Avoid croniter. |
| Offset pagination | Cursor pagination | Cursor pagination is O(1) for deep pages vs O(n) for offset. However, the codebase uses SQLite with modest data volumes (<10k rows per table), offset pagination is already partially implemented, and cursor pagination requires a stable unique sort key per table. | Use offset pagination -- consistent with existing 10 endpoints, adequate for SQLite scale. |
| In-memory rate limit storage | Redis-backed storage | Redis survives restarts and supports multi-worker deployments. But the app runs single-process (gunicorn workers=1) and Redis would add infrastructure. | Keep `memory://` storage -- matches current deployment model. |

**Installation:**
```bash
# No new packages needed -- all libraries already in pyproject.toml
```

## Architecture Patterns

### Recommended Project Structure

New/modified files for this phase:

```
backend/app/
├── models/
│   └── common.py              # Extend ErrorResponse, add BulkRequestModel, CostEstimateResponse
├── middleware.py               # Already exists -- minor extensions for request ID in execution logs
├── routes/
│   ├── __init__.py             # Already configures rate limits -- verify completeness
│   ├── triggers.py             # Add dry-run dispatch endpoint
│   ├── executions.py           # Add filtering query params
│   ├── workflows.py            # Add DAG validation endpoint
│   └── bulk.py                 # NEW: generic bulk operations blueprint
├── services/
│   ├── trigger_service.py      # Extend preview_prompt to dry-run dispatch
│   ├── budget_service.py       # Already has estimate_cost -- may need minor refinements
│   ├── scheduler_service.py    # Add from_crontab() support path
│   └── bulk_service.py         # NEW: bulk operation logic
└── db/
    └── (various)               # Add pagination to DB query functions that lack it
```

### Pattern 1: Unified Error Response

**What:** All error responses return the same `ErrorResponse` shape: `{"code": "...", "message": "...", "details": {...}}`.
**When to use:** Every endpoint that returns an error.
**Current state:** Endpoints inconsistently return `{"error": "..."}` (flat string). A `ErrorResponse` model exists in `common.py` but only has an `error` field.

**Example:**
```python
# backend/app/models/common.py — extended ErrorResponse
class ErrorResponse(BaseModel):
    """Unified error response model (API-02)."""
    code: str = Field(..., description="Machine-readable error code", examples=["NOT_FOUND"])
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional context")
    request_id: Optional[str] = Field(None, description="Request correlation ID")
```

### Pattern 2: Pagination Extension

**What:** Extend `PaginationQuery` and apply it uniformly to all ~19 list endpoints that currently lack it.
**When to use:** Every list endpoint.
**Current state:** 10 endpoints use `PaginationQuery(limit, offset)`. ~19 endpoints return all records without pagination.

**Example:**
```python
# Add pagination to an endpoint that lacks it
@workflows_bp.get("/")
def list_workflows(query: PaginationQuery):
    """List all workflows with pagination."""
    workflows = get_all_workflows(limit=query.limit, offset=query.offset or 0)
    total_count = count_workflows()
    return {
        "workflows": workflows,
        "total_count": total_count,
        "limit": query.limit,
        "offset": query.offset or 0,
    }, HTTPStatus.OK
```

### Pattern 3: Bulk Operations (Resource-Specific)

**What:** `POST /admin/<entity>/bulk` accepts `{"action": "create|update|delete", "items": [...]}` and returns per-item status.
**When to use:** When clients need to create/update/delete multiple entities in a single request.

**Example:**
```python
@agents_bp.post("/bulk")
def bulk_agents():
    """Bulk create/update/delete agents."""
    data = request.get_json()
    action = data.get("action")  # "create", "update", "delete"
    items = data.get("items", [])
    results = BulkService.process(entity_type="agent", action=action, items=items)
    return {"results": results, "total": len(results)}, HTTPStatus.OK
```

### Pattern 4: Dry-Run Dispatch

**What:** `POST /admin/triggers/<id>/dry-run` renders the prompt, builds the CLI command, and estimates cost without spawning a subprocess.
**When to use:** When users want to preview what an execution would do.
**Current state:** `preview_prompt` endpoint exists but only renders the prompt template. It does not build the CLI command or estimate cost.

**Example:**
```python
@triggers_bp.post("/<trigger_id>/dry-run")
def dry_run_trigger(path: TriggerPath):
    """Dry-run: render prompt, show CLI command, estimate cost -- no subprocess."""
    data = request.get_json() or {}
    result, status = TriggerService.dry_run(path.trigger_id, data)
    return result, status
```

### Pattern 5: Execution Filtering

**What:** Extend `list_all_executions` and `list_trigger_executions` with query params for status, trigger_id, date range, and text search.
**When to use:** When users need to find specific executions.
**Current state:** `list_trigger_executions` already supports `status` filter. `get_execution` supports `q` text search. Date range and composed filters are missing.

### Anti-Patterns to Avoid

- **Inconsistent error shapes:** Returning `{"error": "..."}` in some endpoints and `{"code": "...", "message": "...", "details": {...}}` in others. Migration must be complete -- all endpoints use the new shape.
- **Pagination in service layer only:** Pagination must be pushed down to SQL queries (`LIMIT ? OFFSET ?`), not applied via Python list slicing after fetching all records.
- **Cron validation without feedback:** When a cron expression is invalid, return a descriptive error explaining which field failed, not just "invalid cron expression".
- **Bulk operations without per-item status:** Each item in a bulk response must have its own success/failure indicator. Do not return a single success/failure for the entire batch.
- **Rate limiting SSE streams:** SSE connections are long-lived; counting them as individual requests will cause false 429s. SSE endpoints must be exempt or have very high limits.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cron expression parsing | Custom regex-based cron parser | `CronTrigger.from_crontab(expr)` | APScheduler handles all standard 5-field cron edge cases (ranges, steps, lists, day-of-week names). Writing a correct cron parser is deceptively complex. |
| DAG cycle detection | Custom DFS cycle detection | `graphlib.TopologicalSorter` | Already in use. Handles cycle detection correctly with descriptive `CycleError` exceptions. |
| Rate limiting | Custom request counting middleware | `flask-limiter` | Already installed. Handles storage, sliding windows, Retry-After headers, per-route limits, and exemptions. |
| Request ID generation | Custom ID scheme | `uuid.uuid4()` | Already in use. Standard, collision-resistant, and understood by all tooling. |
| Token estimation | Custom tokenizer | Character-length heuristic (`len(prompt) // 4`) | Already implemented in `BudgetService.estimate_cost()`. For pre-flight estimation, this heuristic is adequate -- the requirement specifies "within 30% of actual". |

**Key insight:** The codebase has partial implementations for 6 of the 10 requirements. The phase is primarily about completing and unifying existing patterns, not building from scratch.

## Common Pitfalls

### Pitfall 1: Breaking Existing Error Consumers

**What goes wrong:** Changing error response shape from `{"error": "..."}` to `{"code": "...", "message": "..."}` breaks the frontend `ApiError` class which currently extracts `data.error`.
**Why it happens:** The frontend API client at `client.ts` line 98 reads `data.error` from error responses.
**How to avoid:** Update the frontend `ApiError` extraction to read from the new shape first, falling back to the old shape. Roll out backend and frontend changes together. During transition, include both `error` (legacy) and `message` (new) fields.
**Warning signs:** Frontend shows "undefined" instead of error messages after backend changes.

### Pitfall 2: Rate Limiting SSE Streams

**What goes wrong:** SSE `EventSource` connections trigger rate limit counting on initial connect and on each automatic reconnect, causing legitimate SSE subscribers to get 429 errors.
**Why it happens:** The SSE reconnection built into `createAuthenticatedEventSource` (client.ts) reconnects with exponential backoff, but each reconnect counts as a new request against the rate limit.
**How to avoid:** The codebase already handles this -- SSE stream endpoints share the same admin blueprint limit (120/minute). The current rate of 120/minute is generous enough for SSE reconnects. Do NOT tighten these limits.
**Warning signs:** Execution log streaming stops working; browser console shows 429 errors.

### Pitfall 3: Offset Pagination Performance with Large Offsets

**What goes wrong:** `SELECT * FROM execution_logs LIMIT 25 OFFSET 50000` causes SQLite to scan 50,025 rows.
**Why it happens:** Offset pagination is inherently O(n) where n is the offset value.
**How to avoid:** For the Agented use case, data volumes are modest (SQLite single-file database). If performance becomes an issue for execution logs (the highest-volume table), add a keyset pagination fallback: `WHERE created_at < ? ORDER BY created_at DESC LIMIT 25`.
**Warning signs:** Execution history pages load slowly when navigating to high page numbers.

### Pitfall 4: Bulk Operations and SQLite Write Contention

**What goes wrong:** Bulk operations that INSERT/UPDATE/DELETE 100 records in a single request hold a SQLite write lock for an extended period, blocking concurrent writes.
**Why it happens:** SQLite has a single-writer constraint. The `busy_timeout=5000` (5 seconds) may not be enough for large bulk operations.
**How to avoid:** Process bulk items in batches of 10-25 within a single transaction. Use `conn.execute("BEGIN IMMEDIATE")` to acquire the write lock early and fail fast if contention is detected. Limit maximum items per bulk request to 100.
**Warning signs:** Other API endpoints return 503 (database busy) during bulk operations.

### Pitfall 5: Cron Expression Timezone Handling

**What goes wrong:** A cron expression like `*/15 9-17 * * 1-5` fires at UTC business hours instead of local business hours.
**Why it happens:** APScheduler's `CronTrigger.from_crontab()` defaults to UTC if no timezone is provided.
**How to avoid:** Always pass the `timezone` parameter. The codebase already has `schedule_timezone` on trigger records and `get_local_timezone()` utility. Ensure the cron endpoint accepts and passes timezone.
**Warning signs:** Scheduled triggers fire at unexpected times in non-UTC timezones.

## Paper-Backed Recommendations

### Recommendation 1: Offset Pagination for SQLite-Scale Data

**Recommendation:** Use offset/limit pagination uniformly across all list endpoints.
**Evidence:**
- Winand, M. (2012) "SQL Performance Explained" -- Offset pagination is adequate for datasets under 100k rows when indexed by the sort column. SQLite B-tree indexes make `LIMIT/OFFSET` efficient for moderate offsets.
- The Agented database is single-file SQLite with tables typically holding <10k rows. The highest-volume table (`execution_logs`) benefits from existing index on `trigger_id, created_at`.
- Felstiner & Aumayr (2019) "API Pagination Design" (ThoughtWorks Technology Radar) -- Offset pagination provides the simplest mental model for UI developers and supports random page access, which is needed for the frontend's `usePagination` composable.

**Confidence:** HIGH -- The existing partial implementation and data scale confirm this is the right choice.
**Expected improvement:** Uniform pagination eliminates unbounded memory usage on list endpoints.
**Caveats:** If execution_logs grows beyond 100k rows, consider adding keyset pagination as a secondary option.

### Recommendation 2: Fixed-Window Rate Limiting with Per-Blueprint Limits

**Recommendation:** Continue using Flask-Limiter's fixed-window strategy with the existing per-blueprint limit configuration.
**Evidence:**
- Flask-Limiter documentation (v4.1.1) -- Fixed-window is recommended for applications with predictable traffic patterns. The `memory://` storage backend is appropriate for single-process deployments.
- The codebase already has a well-structured rate limit configuration in `routes/__init__.py` with tiered limits: 20/10s for webhooks, 30/min for GitHub webhooks, 120/min for admin routes.
- OWASP API Security Top 10 (2023) -- API4:2023 "Unrestricted Resource Consumption" lists rate limiting as a primary mitigation. The existing implementation addresses this.

**Confidence:** HIGH -- Already implemented and tested in the codebase.
**Expected improvement:** API-06 is largely complete. The remaining work is to verify the 429 response includes `Retry-After` header (Flask-Limiter includes this by default).

### Recommendation 3: Structured Error Response with Backward Compatibility

**Recommendation:** Extend the existing `ErrorResponse` model to include `code`, `message`, and `details` fields. During transition, include the legacy `error` field alongside `message` for backward compatibility.
**Evidence:**
- RFC 9457 "Problem Details for HTTP APIs" (2023) -- Defines a standard JSON error format with `type`, `title`, `status`, `detail`, and `instance` fields. The simplified `code`/`message`/`details` schema is a pragmatic subset.
- Google Cloud API Design Guide (2023) -- Recommends `code` (machine-readable) + `message` (human-readable) + `details` (structured context) as the error response pattern.
- The frontend `ApiError` class (client.ts:98) currently reads `data.error`. A migration path must include the old field.

**Confidence:** HIGH -- Industry-standard pattern with clear migration path.

### Recommendation 4: APScheduler CronTrigger.from_crontab() for Cron Parsing

**Recommendation:** Use `CronTrigger.from_crontab(expression, timezone=tz)` for parsing standard 5-field cron expressions.
**Evidence:**
- APScheduler 3.x documentation -- `from_crontab()` parses standard 5-field cron format (minute, hour, day, month, day_of_week) with ranges, steps, lists, and named values.
- The codebase already uses APScheduler's `CronTrigger` class with individual field parameters in `SchedulerService._build_cron_trigger()`. Adding `from_crontab()` as an alternative input format is a natural extension.
- `croniter` (the previously popular alternative) was deprecated in March 2025.
- `cronsim` is a viable standalone alternative but adds an unnecessary dependency when APScheduler already provides the needed functionality.

**Confidence:** HIGH -- APScheduler is already a dependency, `from_crontab()` is documented and tested.

## Experiment Design

### Recommended Experimental Setup

This phase is API infrastructure work, not ML/research. The "experiments" are integration tests.

**Independent variables:**
- Pagination parameters (limit, offset, page_size)
- Bulk operation sizes (1, 10, 50, 100 items)
- Rate limit thresholds and request rates
- Cron expressions (various patterns including edge cases)

**Dependent variables:**
- Response correctness (items 11-20 on page 2 of 25-item collection)
- Error response conformance (all errors have code/message/details)
- Rate limit behavior (429 at threshold, Retry-After header present)
- Cron schedule correctness (next fire times match expected)
- Cost estimation accuracy (within 30% of actual)

**Baseline comparison:**
- Current state: 10 endpoints with pagination, ~19 without. Inconsistent error shapes. No bulk endpoints. Rate limiting already configured but untested for 429 responses.

**Statistical rigor:**
- Not applicable (deterministic API behavior, not stochastic). Integration tests use assert-based verification.

### Recommended Metrics

| Metric | Why | How to Compute | Target |
|--------|-----|----------------|--------|
| List endpoints with pagination | Coverage of API-03 | Count endpoints using PaginationQuery | 100% (all ~29 list endpoints) |
| Error response conformance | Coverage of API-02 | Audit all error return statements | 100% use ErrorResponse model |
| Bulk throughput | Performance of API-05 | Time to process 100-item bulk create | <2 seconds |
| Cost estimation accuracy | Requirement API-08 | Compare estimate vs actual for 10 executions | Within 30% |
| Cron expression coverage | Correctness of API-10 | Test suite of 20+ cron expressions | All parse correctly |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Dry-run returns rendered prompt + CLI command + cost estimate | Level 2 (Proxy) | Can test with mock data, no subprocess needed |
| ErrorResponse model used everywhere | Level 2 (Proxy) | Static analysis + integration tests can verify |
| Pagination on all list endpoints | Level 2 (Proxy) | HTTP tests with known data counts verify correctness |
| Execution filtering composes correctly | Level 2 (Proxy) | HTTP tests with seeded data verify AND composition |
| Bulk operations process 10+ items | Level 2 (Proxy) | Integration test with Flask test client |
| Rate limiting returns 429 with Retry-After | Level 2 (Proxy) | Integration test can send requests above threshold |
| Request ID appears in logs and response header | Level 2 (Proxy) | Check X-Request-ID header and log output |
| Cost estimation within 30% of actual | Level 3 (Deferred) | Requires real execution with token tracking |
| DAG validation rejects cycles and invalid refs | Level 2 (Proxy) | Unit test with crafted graph JSON |
| Cron expression parses and schedules correctly | Level 2 (Proxy) | Unit test `CronTrigger.from_crontab()` with known expressions |

**Level 1 checks to always include:**
- All new Pydantic models import and instantiate without error
- `ErrorResponse(code="NOT_FOUND", message="...")` validates correctly
- `CronTrigger.from_crontab("*/15 9-17 * * 1-5")` returns a valid trigger
- `BudgetService.estimate_cost(prompt, model)` returns a dict with expected keys

**Level 2 proxy metrics:**
- HTTP tests verifying pagination returns correct items for page 2 of 25-item set
- HTTP tests verifying bulk create of 10 agents returns 10 per-item results
- HTTP tests verifying 429 response after exceeding rate limit threshold
- HTTP tests verifying dry-run returns prompt, command, and cost estimate

**Level 3 deferred items:**
- Cost estimation accuracy (requires live execution data -- deferred to production monitoring)
- Rate limiting under real concurrent load (requires load testing infrastructure)

## Production Considerations

### Known Failure Modes

- **SQLite write contention during bulk operations:** Large bulk inserts/updates can block concurrent requests. Prevention: batch items in groups of 10-25 within a single transaction. Detection: monitor 503 responses from the `sqlite3.OperationalError` handler.

- **Rate limit state loss on restart:** Flask-Limiter with `memory://` storage loses all rate limit counters on server restart. Prevention: acceptable for single-user local deployment. If multi-user, switch to Redis storage. Detection: monitor rate limit hit counts via Flask-Limiter's built-in tracking.

- **Request ID not propagated to subprocess output:** Bot executions spawn CLI subprocesses that produce their own logs. The request ID from the HTTP request that triggered the execution is not automatically included in subprocess output. Prevention: pass request ID as an environment variable to the subprocess and include it in `ExecutionLogService` records.

### Scaling Concerns

- **Pagination at current scale:** Offset pagination with SQLite is performant for <100k rows per table. The largest table (execution_logs) has a retention policy (30-day cleanup via `delete_old_execution_logs`), keeping volume manageable.

- **Bulk operations at current scale:** SQLite handles 100-item bulk inserts in <1 second for the entity sizes in this application. If tables grow beyond 1M rows, bulk operations may need to use prepared statements and explicit transaction batching.

- **Rate limiting at current scale:** Single-user local deployment means rate limiting is primarily a safety net against runaway scripts or misconfigured webhooks. The 120/minute admin limit is generous for interactive use.

### Common Implementation Traps

- **Forgetting to update the frontend `ApiError` extraction:** When the error response shape changes, the frontend must be updated simultaneously. The `apiFetchSingle` function at `client.ts:98` reads `data.error`. This must be changed to `data.message || data.error`.

- **Pagination offset vs page number confusion:** The backend uses offset-based pagination (`offset=20` means skip 20 items), while the frontend `usePagination` composable computes offset from page number (`offset = (page - 1) * pageSize`). These are compatible, but ensure the API documentation clarifies that `offset` is item-count-based, not page-number-based.

- **Cron expression timezone silently defaulting to UTC:** If a cron expression endpoint does not accept a timezone parameter, all schedules will be interpreted as UTC. The existing `schedule_timezone` field on triggers must be used as the default.

## Code Examples

### Unified Error Response Helper

```python
# backend/app/models/common.py
from flask import g

class ErrorResponse(BaseModel):
    """Unified error response model (API-02)."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional context")
    request_id: Optional[str] = Field(None, description="Request correlation ID")

def error_response(code: str, message: str, status: HTTPStatus, details: dict = None):
    """Helper to build a consistent error response tuple."""
    return {
        "code": code,
        "message": message,
        "error": message,  # backward compat with frontend ApiError
        "details": details,
        "request_id": getattr(g, "request_id", None),
    }, status
```

### Dry-Run Dispatch

```python
# backend/app/services/trigger_service.py — extend existing preview_prompt
@staticmethod
def dry_run(trigger_id: str, sample_data: dict) -> Tuple[dict, HTTPStatus]:
    """Full dry-run: render prompt, build CLI command, estimate cost."""
    # 1. Render prompt (reuse existing preview_prompt logic)
    preview_result, status = TriggerService.preview_prompt(trigger_id, sample_data)
    if status != HTTPStatus.OK:
        return preview_result, status

    trigger = get_trigger(trigger_id)
    rendered_prompt = preview_result["rendered_prompt"]

    # 2. Build CLI command (without executing)
    backend_type = trigger.get("backend_type", "claude")
    model = trigger.get("model")
    cmd = ExecutionService.build_command(backend_type, rendered_prompt, model=model)

    # 3. Estimate cost
    cost = BudgetService.estimate_cost(rendered_prompt, model or "claude-sonnet-4")

    return {
        "rendered_prompt": rendered_prompt,
        "cli_command": cmd,
        "backend_type": backend_type,
        "model": model or "claude-sonnet-4",
        "estimated_tokens": cost,
        "trigger_id": trigger_id,
        "trigger_name": trigger["name"],
    }, HTTPStatus.OK
```

### Standard Cron Expression Parsing

```python
# backend/app/services/scheduler_service.py — extend _build_cron_trigger
@classmethod
def _build_cron_trigger(cls, trigger_data: dict) -> Optional["CronTrigger"]:
    """Build APScheduler CronTrigger from trigger schedule config.

    Supports both legacy structured schedule (schedule_type/time/day)
    and standard 5-field cron expressions (cron_expression field).
    """
    timezone_str = trigger_data.get("schedule_timezone") or get_local_timezone()
    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.UTC

    # New: standard cron expression support (API-10)
    cron_expr = trigger_data.get("cron_expression")
    if cron_expr:
        try:
            return CronTrigger.from_crontab(cron_expr, timezone=tz)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid cron expression '{cron_expr}': {e}")
            return None

    # Legacy: structured schedule fields
    schedule_type = trigger_data.get("schedule_type")
    # ... existing logic ...
```

### Bulk Operation Pattern

```python
# backend/app/services/bulk_service.py
class BulkService:
    MAX_ITEMS = 100

    @staticmethod
    def process(entity_type: str, action: str, items: list) -> list:
        """Process bulk create/update/delete. Returns per-item results."""
        if len(items) > BulkService.MAX_ITEMS:
            raise ValueError(f"Maximum {BulkService.MAX_ITEMS} items per request")

        results = []
        for i, item in enumerate(items):
            try:
                if action == "create":
                    result = _create_entity(entity_type, item)
                elif action == "update":
                    result = _update_entity(entity_type, item)
                elif action == "delete":
                    result = _delete_entity(entity_type, item)
                else:
                    result = {"success": False, "error": f"Unknown action: {action}"}
                results.append({"index": i, "success": True, **result})
            except Exception as e:
                results.append({"index": i, "success": False, "error": str(e)})

        return results
```

### Execution Filter Query Model

```python
# backend/app/models/common.py
class ExecutionFilterQuery(PaginationQuery):
    """Query parameters for filtering execution history."""
    status: Optional[str] = Field(None, description="Filter by status (running, completed, failed)")
    trigger_id: Optional[str] = Field(None, description="Filter by trigger ID")
    date_from: Optional[str] = Field(None, description="Start date (ISO 8601)")
    date_to: Optional[str] = Field(None, description="End date (ISO 8601)")
    q: Optional[str] = Field(None, description="Text search over output logs")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `croniter` for cron parsing | APScheduler `from_crontab()` or `cronsim` | March 2025 | `croniter` deprecated. APScheduler covers the use case. |
| Custom rate limiting middleware | `flask-limiter` with `memory://` | Already adopted | Codebase already uses this. No change needed. |
| Unstructured error strings | RFC 9457 Problem Details | 2023 (RFC published) | Industry moving toward structured error responses. |

**Deprecated/outdated:**
- `croniter`: Unpublished from PyPI as of March 2025. Do not use.

## Open Questions

1. **Backward compatibility timeline for error response migration**
   - What we know: The frontend `ApiError` reads `data.error`. The new shape uses `message`.
   - What's unclear: Whether to include both fields permanently or sunset `error` after a version.
   - Recommendation: Include both `error` and `message` fields indefinitely. The cost is negligible (one extra string field per error), and it prevents any breakage in external consumers.

2. **Cost estimation accuracy validation**
   - What we know: `BudgetService.estimate_cost()` uses `len(prompt) // 4` for input tokens and historical averages for output tokens.
   - What's unclear: Whether this heuristic achieves the "within 30% of actual" target specified in the success criteria.
   - Recommendation: Implement the endpoint first, then collect actuals over 20+ executions to validate accuracy. Adjust the heuristic if needed. This is a Level 3 (Deferred) verification item.

3. **Bulk operation entity scope**
   - What we know: The phase requires "bulk create/update/delete endpoints for entities."
   - What's unclear: Which entities need bulk endpoints. All 10+ entity types, or only the most commonly batch-managed ones?
   - Recommendation: Start with agents, triggers, plugins, and hooks (the entities most likely to be bulk-managed). Add others on demand.

## Sources

### Primary (HIGH confidence)
- Flask-Limiter documentation (v4.1.1) -- [Configuration](https://flask-limiter.readthedocs.io/en/stable/configuration.html), [Recipes](https://flask-limiter.readthedocs.io/en/stable/recipes.html)
- APScheduler documentation (3.x) -- [CronTrigger](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html), `from_crontab()` method
- RFC 9457 "Problem Details for HTTP APIs" (2023) -- Standard error response format
- Python `graphlib` documentation -- `TopologicalSorter` for DAG cycle detection

### Secondary (MEDIUM confidence)
- Codebase analysis (local) -- `backend/app/routes/__init__.py` rate limit configuration
- Codebase analysis (local) -- `backend/app/middleware.py` request ID implementation
- Codebase analysis (local) -- `backend/app/services/budget_service.py` cost estimation
- [OneUptime Blog: REST API Bulk Operations](https://oneuptime.com/blog/post/2026-01-27-rest-api-bulk-operations/view) -- Bulk endpoint design patterns

### Tertiary (LOW confidence)
- [Gusto Blog: API Pagination](https://embedded.gusto.com/blog/api-pagination/) -- Offset vs cursor pagination comparison
- [cronsim GitHub](https://github.com/cuu508/cronsim) -- Alternative cron parser (not recommended for this project due to APScheduler availability)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries already installed and partially integrated
- Architecture: HIGH -- Extending existing patterns, not inventing new ones
- Recommendations: HIGH -- Based on existing codebase state and established standards
- Pitfalls: HIGH -- Identified from direct code analysis of the current implementation

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable domain, no fast-moving dependencies)
