# Phase 15: Code Consistency & Standards - Research

**Researched:** 2026-03-04
**Domain:** Code quality, naming conventions, type safety, logging standards, error handling patterns
**Confidence:** HIGH

## Summary

Phase 15 is a codebase-wide cleanup that enforces consistent patterns across the backend (Python/Flask) and frontend (TypeScript/Vue). The codebase already has many of the right building blocks in place: a centralized `ids.py` module using `secrets.choice()`, an `ErrorResponse` Pydantic model in `models/common.py`, loggers declared in most service files, and a well-structured `useConversation` composable for SSE. The work is primarily about eliminating inconsistencies and closing gaps rather than introducing new architecture.

The research identified 7 print() calls in `app/services/` (plus ~50 in `app/db/migrations.py` and `app/db/seeds.py`), 2 stray `random.choices()` calls, ~148 service methods missing return type annotations (vs ~481 that have them), ~55 TypeScript `any` usages, and one duplicate message type (`ChatMessage` in `useSketchChat.ts` vs `ConversationMessage` in `types.ts`). All error responses already use `{"error": "..."}` dict format but none reference the `ErrorResponse` Pydantic model for OpenAPI documentation. Magic numbers are scattered across ~20+ service files for timeouts, thresholds, TTLs, and limits.

**Primary recommendation:** Execute as a systematic file-by-file sweep, working through one requirement (CON-01 through CON-09) at a time, verifying each with grep-based checks before moving to the next.

## Standard Stack

### Core

No new libraries are required. This phase uses only existing tools already in the project.

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| Python `logging` | stdlib | Structured logging replacement for print() | Already used in 90+ files; `logger = logging.getLogger(__name__)` is the established pattern |
| Python `secrets` | stdlib | Cryptographically secure ID generation | Already used in `ids.py`; replaces `random.choices()` |
| Ruff | configured | Linting and formatting | Already configured in project; can enforce style rules |
| `vue-tsc` | configured | TypeScript type checking | Already part of build; will catch `any` removals |

### Supporting

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| Pydantic v2 `BaseModel` | existing | Error/response model definitions | For `ErrorResponse` standardization in route decorators |
| `mypy` or `pyright` | optional | Static type checking for return annotations | Could verify CON-03 compliance; not currently in project |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python `logging` | `structlog` | Better structured output but adds dependency; not worth it for this cleanup |
| Manual grep verification | `ruff` custom rules | Could automate print() detection but custom plugin development is overkill |
| Inline constants | `pydantic-settings` | Over-engineered for simple named constants; a plain Python module suffices |

## Architecture Patterns

### Recommended Project Structure

No new directories needed. Existing structure is correct:

```
backend/app/
  db/ids.py           # Already centralized ID factory (expand with validation)
  models/common.py    # Already has ErrorResponse (expand usage)
  config.py           # Add constants module or expand existing
  services/           # Apply consistent patterns across all files
```

### Pattern 1: Structured Logger Replacement for print()

**What:** Replace every `print()` call with the appropriate `logger.info()`, `logger.warning()`, or `logger.error()` call.
**When to use:** Every file in `app/services/` and `app/db/` that uses `print()`.
**Evidence:** The project's own CONVENTIONS.md specifies `logger = logging.getLogger(__name__)` at the top of each file. 90+ files already follow this pattern. The 7 print() calls in services and ~50 in db/ are the exceptions.

**Example:**
```python
# BEFORE (app/services/harness_loader_service.py:241)
print(f"Failed to import agent {agent_name}: {e}")

# AFTER
logger.error("Failed to import agent %s: %s", agent_name, e, exc_info=True)
```

**Migration note for db/migrations.py:** The ~50 print() calls in migrations.py serve as startup progress output. These should use `logger.info()` for informational messages and `logger.warning()` for the WAL mode warning. The migration runner is called during `init_db()` which runs before logging may be fully configured, but Python's logging module works with basicConfig defaults, so this is safe.

### Pattern 2: ErrorResponse Model in Route Decorators

**What:** Use the existing `ErrorResponse` model from `models/common.py` as the response type annotation for error cases in flask-openapi3 route decorators.
**When to use:** All route handlers that return error dictionaries.
**Evidence:** Routes currently return `{"error": "..."}, HTTPStatus.NOT_FOUND` as plain dicts. The `ErrorResponse` Pydantic model exists but is not referenced in any route decorator's `responses` parameter. flask-openapi3 supports `responses={404: ErrorResponse}` for OpenAPI spec generation.

**Example:**
```python
# BEFORE
@agents_bp.get("/<agent_id>")
def get_agent_detail(path: AgentPath):
    ...
    return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND

# AFTER - route decorator documents error responses
@agents_bp.get("/<agent_id>", responses={404: ErrorResponse, 500: ErrorResponse})
def get_agent_detail(path: AgentPath):
    ...
    return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND
```

**Note:** The actual return format (`{"error": "..."}` dict + HTTPStatus) does not need to change. The standardization is about documenting error shapes in OpenAPI and ensuring no route returns a different format (e.g., bare strings or differently-keyed dicts).

### Pattern 3: Centralized Constants Module

**What:** Create `backend/app/constants.py` (or expand `config.py`) to hold all magic numbers as named constants.
**When to use:** Replace any hardcoded numeric literal that represents a timeout, threshold, limit, TTL, or retry count.
**Evidence:** The codebase has magic numbers scattered across 20+ files. Some are already partially centralized (e.g., `WEBHOOK_DEDUP_WINDOW = 10` in `execution_service.py`, `STALE_CONVERSATION_THRESHOLD = 1800` duplicated in 3 conversation services).

**Example:**
```python
# backend/app/constants.py
# --- Timeouts ---
THREAD_JOIN_TIMEOUT = 5          # seconds
SSE_HEARTBEAT_TIMEOUT = 30      # seconds
QUEUE_GET_TIMEOUT = 30           # seconds
CLI_PROCESS_TIMEOUT = 120        # seconds

# --- Limits ---
PTY_RING_BUFFER_SIZE = 10_000   # lines
SSE_REPLAY_LIMIT = 500          # lines

# --- Thresholds ---
STALE_CONVERSATION_THRESHOLD = 1800  # seconds (30 min)
ROTATION_UTILIZATION_THRESHOLD = 80.0  # percentage

# --- TTLs ---
CACHE_TTL = 300                 # seconds (5 min)
WEBHOOK_DEDUP_WINDOW = 10      # seconds

# --- Budget defaults ---
DEFAULT_5H_TOKEN_LIMIT = 300_000
DEFAULT_WEEKLY_TOKEN_LIMIT = 1_000_000
```

### Pattern 4: ID Factory with Validation

**What:** Consolidate the ID generation in `ids.py` by extracting the repeated `chars = string.ascii_lowercase + string.digits` / `secrets.choice()` boilerplate into the existing `_generate_short_id()` helper, and add a validation function.
**When to use:** All `generate_*_id()` functions and the 2 stray `random.choices()` calls.
**Evidence:** `ids.py` already has `_generate_short_id(length)` but individual generators duplicate the logic instead of calling it. Two files still use `random.choices()` instead of `secrets.choice()`:
- `backend/app/routes/super_agents.py:317`
- `backend/app/services/team_execution_service.py:62`

**Example:**
```python
# Simplified generate using existing helper
def generate_agent_id() -> str:
    return f"{AGENT_ID_PREFIX}{_generate_short_id(AGENT_ID_LENGTH)}"

# New: Validation function
def validate_entity_id(entity_id: str, prefix: str) -> bool:
    """Validate that an ID matches the expected prefix-random format."""
    if not entity_id.startswith(prefix):
        return False
    suffix = entity_id[len(prefix):]
    return all(c in string.ascii_lowercase + string.digits for c in suffix)
```

### Anti-Patterns to Avoid

- **Mixing print() and logger in the same file:** Several files (e.g., `audit_service.py`) have both `logger = logging.getLogger(__name__)` and `print()` calls. Every file should use exclusively the logger.
- **Catching bare `Exception` without logging:** Some exception handlers catch `Exception as e` but only print or silently pass. All should log with appropriate severity and `exc_info=True` for stack traces.
- **Duplicating threshold constants:** `STALE_CONVERSATION_THRESHOLD = 1800` appears identically in `skill_conversation_service.py`, `plugin_conversation_service.py`, and `agent_conversation_service.py`. Should be defined once in constants.
- **Using `any` in TypeScript catch blocks:** `catch (e: any)` should be `catch (e: unknown)` with type narrowing, which is the TypeScript best practice since 4.4.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Logging | Custom print wrappers | Python `logging` module | Already established pattern; supports levels, formatting, handlers |
| ID generation | Per-file random calls | `ids.py` centralized factory | Already exists; just needs deduplication |
| Error response typing | Per-route error dicts | `ErrorResponse` from `models/common.py` | Already exists; needs to be referenced in decorators |
| TypeScript catch typing | `catch (e: any)` | `catch (e: unknown)` with narrowing | TypeScript 4.4+ best practice; `unknown` is type-safe |

**Key insight:** All required building blocks already exist in the codebase. This phase is about enforcement and gap-filling, not creating new infrastructure.

## Common Pitfalls

### Pitfall 1: Breaking Migration Output

**What goes wrong:** Replacing `print()` in `migrations.py` with `logger.info()` could suppress migration progress output if logging is not configured before `init_db()` runs.
**Why it happens:** `init_db()` is called early in `create_app()`, potentially before logging handlers are fully set up.
**How to avoid:** Ensure `logging.basicConfig()` is called (or Flask's default logging is active) before `init_db()`. Python's logging module sends WARNING+ to stderr by default even without explicit configuration, but INFO messages would be suppressed without a handler. Either configure logging first in `create_app()` or keep migrations at WARNING level.
**Warning signs:** Migration messages disappear from startup output after the change.

### Pitfall 2: Over-Standardizing Error Responses

**What goes wrong:** Attempting to make every route return `ErrorResponse` model instances instead of plain dicts breaks the existing response pipeline.
**Why it happens:** flask-openapi3 routes return `(dict, HTTPStatus)` tuples. Replacing dicts with Pydantic model instances changes the serialization path.
**How to avoid:** Keep returning `{"error": "..."}` dicts from route handlers. Only add `ErrorResponse` to the `responses` parameter in route decorators for OpenAPI documentation. The dict format already matches the `ErrorResponse` schema.
**Warning signs:** Routes start returning Pydantic model `.model_dump()` output instead of direct dicts; response format changes in API.

### Pitfall 3: Breaking Tests with Constant Refactoring

**What goes wrong:** Moving magic numbers to a constants module and changing import paths breaks existing test mocks or assertions.
**Why it happens:** Tests may assert on specific timeout values or mock functions that use those values.
**How to avoid:** Search for each magic number value in test files before extracting it. Update tests to import the constant or use the same reference.
**Warning signs:** Test failures with unexpected values after constant extraction.

### Pitfall 4: Type Annotation False Sense of Security

**What goes wrong:** Adding return type annotations like `-> bool` to functions that actually return `Optional[bool]` or `None` in error paths.
**Why it happens:** Quick annotation without tracing all code paths, especially exception handlers that return `None`.
**How to avoid:** For each function being annotated, trace every return statement and exception handler. Use `Optional[T]` when any path returns `None`.
**Warning signs:** `mypy` or `pyright` errors after annotations are added (if these tools are run).

### Pitfall 5: Frontend ChatMessage/ConversationMessage Merge Breaking Props

**What goes wrong:** Removing `ChatMessage` from `useSketchChat.ts` and using `ConversationMessage` everywhere changes the interface shape, breaking components that depend on the simpler `ChatMessage` type.
**Why it happens:** `ChatMessage` has `{role, content, timestamp}` while `ConversationMessage` has the same fields plus an optional `backend` field. They are structurally compatible but code may type-narrow differently.
**How to avoid:** Since `ChatMessage` is a subset of `ConversationMessage`, the merge is safe as long as all `ChatMessage` usage sites accept the broader type. Verify `useSketchChat.ts` consumers can handle the optional `backend` field.
**Warning signs:** TypeScript errors in `SketchChatPage.vue` after the type change.

## Experiment Design

### Recommended Experimental Setup

This phase involves deterministic refactoring, not algorithmic experimentation. The "experiment" is the codebase sweep itself.

**Independent variables:** Which files are modified in each sweep
**Dependent variables:** Zero violations detected by grep/lint checks
**Controlled variables:** Existing test suite passes before and after each change

**Baseline comparison:**
- Before: 7 print() in services, ~50 in db/, 2 random.choices(), ~148 methods without return annotations, ~55 `any` usages, 1 duplicate message type
- Target: 0 print() in services, 0 random.choices(), 0 `any` in non-test files, 1 canonical message type

**Ablation plan:**
Not applicable -- this is a sequential cleanup, not a component-toggling experiment.

**Statistical rigor:**
Not applicable -- verification is binary (passes grep check or does not).

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| print() calls in app/ | CON-01 compliance | `grep -rn "print(" backend/app/ --include="*.py" \| grep -v test \| wc -l` | ~57 |
| random.choices() calls | CON-04 compliance | `grep -rn "random.choices" backend/app/ --include="*.py" \| wc -l` | 2 |
| Methods without return types | CON-03 compliance | Grep for `def.*):$` in services/ | ~148 |
| TypeScript `any` usage | CON-08 compliance | `grep -rn ": any\|as any" frontend/src/ --include="*.ts" --include="*.vue" \| grep -v __tests__ \| wc -l` | ~40 (excl. tests) |
| Duplicate message types | CON-08 compliance | Grep for `ChatMessage` interface definitions | 1 duplicate |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Zero print() calls in app/services/ | Level 1 (Sanity) | Simple grep check |
| Zero random.choices() calls | Level 1 (Sanity) | Simple grep check |
| All error responses use consistent format | Level 1 (Sanity) | Grep for response patterns |
| Return type annotations present | Level 1 (Sanity) | Grep for `def.*):$` (missing annotations) |
| Named constants replace magic numbers | Level 1 (Sanity) | Grep for common magic number patterns |
| Frontend zero `any` in non-test files | Level 1 (Sanity) | Grep check |
| Frontend single message type | Level 1 (Sanity) | Grep for interface definitions |
| All tests pass after changes | Level 1 (Sanity) | `pytest` + `npm run test:run` |
| Frontend builds without type errors | Level 1 (Sanity) | `just build` includes `vue-tsc` |
| Backend ruff format passes | Level 1 (Sanity) | `cd backend && uv run ruff format --check .` |

**Level 1 checks to always include:**
- `grep -rn "^\s*print(" backend/app/services/ --include="*.py"` returns 0 matches
- `grep -rn "random\.choices" backend/app/ --include="*.py"` returns 0 matches
- `grep -rn ": any\b" frontend/src/ --include="*.ts" --include="*.vue" | grep -v __tests__ | grep -v node_modules` returns 0 matches
- `cd backend && uv run pytest` passes
- `cd frontend && npm run test:run` passes
- `just build` succeeds (vue-tsc + vite build)

**Level 2 proxy metrics:**
Not applicable -- Level 1 is sufficient for this phase.

**Level 3 deferred items:**
- Static type checking with `mypy` or `pyright` for full return type verification (not currently in project toolchain)

## Production Considerations

### Known Failure Modes

- **Logging configuration timing:** If `init_db()` runs before logging is configured, migration log messages may be lost. Prevention: call `logging.basicConfig()` early in `create_app()`. Detection: check that migration messages appear in startup output.
- **Constant import cycles:** If `constants.py` imports from services or services import from each other through constants, circular imports can occur. Prevention: keep `constants.py` as a leaf module with zero local imports. Detection: `ImportError` on startup.

### Scaling Concerns

- No scaling concerns for this phase. Code consistency changes do not affect runtime behavior or resource usage.

### Common Implementation Traps

- **Partial sweep:** Cleaning up print() in some files but missing others creates inconsistency worse than the original state. Correct approach: use grep to build a complete file list before starting, then check them off.
- **Over-engineering the constants module:** Creating nested config classes or environment-variable-backed settings for simple constants like timeout values. Correct approach: plain module-level constants in a single file.
- **Changing return values while adding annotations:** Adding `-> bool` to a function and "fixing" it to always return `True`/`False` when it previously returned `None` on error paths. Correct approach: annotate what IS, using `Optional`, not what you wish it was.

## Code Examples

Verified patterns from the existing codebase:

### Logger Setup (already standard in 90+ files)
```python
# Source: backend/app/services/execution_service.py:39
import logging
logger = logging.getLogger(__name__)
```

### Error Response Pattern (already standard in all routes)
```python
# Source: backend/app/routes/agents.py (typical pattern)
return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND
```

### ID Generation (already standard in ids.py)
```python
# Source: backend/app/db/ids.py:77-80
def _generate_short_id(length: int = 6) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))
```

### SSE Composable (already centralized for most use cases)
```typescript
// Source: frontend/src/composables/useConversation.ts
export interface ConversationApi {
  start: () => Promise<{ conversation_id: string; message: string }>;
  sendMessage: (convId: string, message: string, options?: {...}) => Promise<{...}>;
  stream: (convId: string) => AuthenticatedEventSource;
  finalize: (convId: string) => Promise<Record<string, unknown>>;
  abandon: (convId: string) => Promise<{ message: string }>;
}
```

### Stray random.choices() to Fix
```python
# Source: backend/app/routes/super_agents.py:317 -- NEEDS FIXING
suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))

# Source: backend/app/services/team_execution_service.py:62 -- NEEDS FIXING
suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
```

### ChatMessage Duplicate to Merge
```typescript
// Source: frontend/src/composables/useSketchChat.ts:6-9 -- DUPLICATE
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

// Source: frontend/src/services/api/types.ts:329-335 -- CANONICAL
export interface ConversationMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  backend?: string;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `print()` for debugging | `logging.getLogger(__name__)` | Python best practice since 2.3 | Structured output, configurable levels, handler routing |
| `random.choices()` for IDs | `secrets.choice()` | Python 3.6+ security guidance | Cryptographically secure randomness for identifiers |
| TypeScript `catch (e: any)` | `catch (e: unknown)` | TypeScript 4.4 (2021) | Type-safe error handling, forces explicit narrowing |
| Duplicate type definitions | Single canonical type | General DRY principle | Prevents type drift, reduces maintenance surface |

**Deprecated/outdated:**
- `random.choices()` for security-sensitive values: Python docs recommend `secrets` module since 3.6 for tokens and IDs
- `catch (e: any)` in TypeScript: `useUnknownInCatchVariables` has been default in strict mode since TS 4.4

## Codebase Findings Summary

### CON-01: print() Calls

| Location | Count | Severity |
|----------|-------|----------|
| `app/services/harness_loader_service.py` | 6 | High -- error handling |
| `app/services/audit_service.py` | 1 | High -- error handling |
| `app/db/migrations.py` | ~50 | Medium -- startup info |
| `app/db/seeds.py` | 4 | Medium -- startup info |

### CON-02: Error Response Format

All routes already return `{"error": "message"}` dict format. Zero routes return bare strings or differently-keyed dicts. The `ErrorResponse` model in `models/common.py` exists but is not used in route decorator `responses` parameters for OpenAPI documentation.

### CON-03: Return Type Annotations

- ~481 service methods have return type annotations
- ~148 service methods are missing return type annotations
- 3 DB functions (`add_agent`, `update_agent`, `update_agent_conversation`) span multiple lines and have annotations on the closing line (not truly missing, just multi-line)
- 2 DB functions (`update_backend_last_used`, `update_backend_models`) are missing return type annotations

### CON-04: ID Generation

- `ids.py` is already centralized with `secrets.choice()` -- well structured
- 2 stray `random.choices()` calls exist outside `ids.py` (in `super_agents.py` route and `team_execution_service.py`)
- `_generate_short_id()` helper exists but is not used by the public generators (each duplicates the logic)
- No validation function exists to verify ID format

### CON-05: Exception Handling

- ~40 uses of `exc_info=True` across the codebase (good practice, inconsistently applied)
- Many `except Exception as e` blocks log at `logger.error()` -- good
- Some `except Exception as e` blocks use `print()` instead of logger -- addressed by CON-01
- No documented severity level guide exists

### CON-06: DB Function Naming and Service Method Styles

- DB functions use `add_*` prefix (not `create_*`) for creation -- e.g., `add_agent()`, `add_trigger()`, `add_team()`
- Exception: `create_token_usage_record()`, `create_execution_log()`, `create_agent_conversation()`, `create_design_conversation()` use `create_` prefix
- 673 total `@staticmethod` or `@classmethod` decorators across 80 service files
- Services use `@staticmethod` predominantly; some use `@classmethod` for accessing class-level state (e.g., `ExecutionLogService`, `ProcessManager`)

### CON-07: Magic Numbers

Major categories found:
- **Timeouts:** `timeout=5`, `timeout=10`, `timeout=15`, `timeout=30`, `timeout=60`, `timeout=120`, `timeout=180` across model_discovery, github_service, cli services
- **Thread joins:** `thread.join(timeout=5)`, `thread.join(timeout=10)` in execution_service
- **Queue gets:** `queue.get(timeout=30)` in 3+ conversation services
- **Ring buffers:** `deque(maxlen=10000)` in project_session_manager
- **Thresholds:** `STALE_CONVERSATION_THRESHOLD = 1800` duplicated in 3 files
- **Cache TTLs:** `_CACHE_TTL = 300` duplicated in 2 files
- **Budget defaults:** `DEFAULT_5H_TOKEN_LIMIT = 300_000` etc. in budget_service

### CON-08: Frontend Type Duplication

- `ConversationMessage` in `types.ts` (canonical): `{role, content, timestamp, backend?}`
- `ChatMessage` in `useSketchChat.ts` (duplicate): `{role, content, timestamp}` -- subset of ConversationMessage
- ~55 `any` usages in non-test frontend code (services, composables, components)
- Common `any` sources: canvas components (TeamCanvas, OrgCanvas, CanvasSidebar), catch blocks, Chart.js mocks

### CON-09: Frontend SSE Patterns

- `useConversation.ts` is well-structured as a generic SSE composable for hook/command/rule/plugin/skill/agent conversations
- `useAiChat.ts` handles super agent SSE with state_delta protocol (different from useConversation)
- `useWorkflowExecution.ts` has its own SSE lifecycle management
- `usePlanningSession.ts` has its own SSE lifecycle management
- `ProjectManagementPage.vue` and `WorkflowPlaygroundPage.vue` have inline SSE setup (not using composables)
- `InteractiveSetup.vue` and `MessageInbox.vue` have inline SSE setup in components
- Pattern: each SSE connection manages `let eventSource`, `closeEventSource()`, `onUnmounted(closeEventSource)` independently

## Open Questions

1. **Should db/migrations.py print() calls be converted?**
   - What we know: Migrations run once at startup, print() provides visible progress. Logger would be more consistent but may require logging config to be ready first.
   - Recommendation: Convert to `logger.info()` but ensure `create_app()` configures logging before calling `init_db()`. This is low risk because Flask configures basic logging by default.

2. **Should DB function naming be unified to `create_` or `add_`?**
   - What we know: Majority use `add_*` (40+ functions). A few use `create_*` (4 functions). CONVENTIONS.md does not mandate one over the other.
   - Recommendation: Standardize on `add_*` since it is the dominant pattern. Rename the 4 `create_*` functions to `add_*`. This is a mechanical rename with grep-verified call site updates.

3. **Should @staticmethod vs @classmethod be standardized?**
   - What we know: `@staticmethod` is used for stateless methods. `@classmethod` is used when accessing class-level state (locks, buffers, dicts). This is actually correct usage.
   - Recommendation: Do NOT force one style. Document the convention: use `@classmethod` when method accesses `cls._*` class state, `@staticmethod` otherwise. The current mix is intentional and correct.

4. **How aggressive should `any` removal be in test files?**
   - What we know: ~15 of the 55 `any` usages are in test files for mocking purposes (`as any` for mock objects).
   - Recommendation: Focus `any` removal on non-test files first (~40 usages). Test file `any` can be addressed separately if time allows but is lower priority.

## Sources

### Primary (HIGH confidence)
- Codebase grep analysis across all backend and frontend files (2026-03-04)
- `.planning/codebase/CONVENTIONS.md` -- established project conventions
- `.planning/codebase/ARCHITECTURE.md` -- service and DB layer patterns
- `.planning/codebase/CONCERNS.md` -- known technical debt (sections 3.5, 3.7)
- `backend/app/db/ids.py` -- current ID generation implementation
- `backend/app/models/common.py` -- existing ErrorResponse model
- `frontend/src/services/api/types.ts` -- canonical TypeScript types
- `frontend/src/composables/useConversation.ts` -- SSE composable pattern

### Secondary (MEDIUM confidence)
- Python `logging` module documentation -- standard library best practices
- Python `secrets` module documentation -- cryptographic ID generation guidance
- TypeScript 4.4 release notes -- `useUnknownInCatchVariables` default behavior

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries; all tools already in project
- Architecture patterns: HIGH -- all patterns are extensions of existing codebase conventions
- Recommendations: HIGH -- based on direct grep analysis of the actual codebase, not assumptions
- Pitfalls: HIGH -- based on concrete examples found in the codebase

**Research date:** 2026-03-04
**Valid until:** Indefinite -- these are internal codebase patterns, not external library APIs
