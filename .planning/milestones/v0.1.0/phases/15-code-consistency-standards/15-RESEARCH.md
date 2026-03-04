# Phase 15: Code Consistency & Standards - Research

**Researched:** 2026-03-04
**Domain:** Code quality, consistency enforcement, refactoring patterns
**Confidence:** HIGH

## Summary

Phase 15 is a codebase cleanup phase that standardizes patterns across both the Flask backend and Vue frontend. The codebase audit reveals a well-structured project with many good patterns already in place (centralized ID generation with `secrets.choice`, existing `ErrorResponse` model, existing `useDataPage` composable), but with inconsistencies accumulated over rapid development. The work is entirely mechanical refactoring with no new features or dependencies.

The backend has 112 `print()` calls (mostly in migrations/seeds, 7 in services), 495 ad-hoc `{"error": ...}` dict returns in routes instead of the existing `ErrorResponse` model, 47 `add_` vs 7 `create_` DB function prefixes, 269 service methods without return type annotations, 175 DB functions without return type annotations, and 30 service files without logger setup. The frontend has 147 instances of TypeScript `any`, a duplicate `ChatMessage` interface alongside the canonical `ConversationMessage`, and SSE setup code centralized through `createAuthenticatedEventSource` but with varying error/loading patterns across composables.

**Primary recommendation:** Execute this as a systematic file-by-file refactoring with automated grep-based verification at each step, using Ruff and vue-tsc as guardrails. No new libraries required.

## Standard Stack

### Core

No new libraries are needed for this phase. All work uses existing tooling:

| Tool | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ruff` | current | Python linting and formatting | Already configured; will catch regressions |
| `vue-tsc` | 3.x | TypeScript type checking for Vue | Already in build pipeline; catches `any` regressions |
| `pytest` | 9.x | Backend test suite | Validates refactoring does not break behavior |
| `vitest` | 4.x | Frontend test suite | Validates frontend refactoring |
| Python `logging` | stdlib | Structured logging | Already used in 61 of 91 service files |
| Python `secrets` | stdlib | Cryptographic random ID generation | Already used in `app/db/ids.py` |

### Supporting

| Tool | Purpose | When to Use |
|---------|---------|-------------|
| `grep -rn` | Verify zero remaining instances of patterns | Post-refactoring verification |
| `ruff check --select` | Targeted lint checks (e.g., T201 for print) | CI enforcement of no-print rule |

### Alternatives Considered

None. This phase uses only existing project dependencies.

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure Changes

```
backend/app/
├── config.py           # EXTEND: Add timeouts, retry limits, thresholds, debounce constants
├── db/
│   └── ids.py          # EXTEND: Add generate_id(prefix, length) factory function
├── services/
│   └── [all files]     # MODIFY: Add logger, return types, standardize exceptions
├── routes/
│   └── [all files]     # MODIFY: Use ErrorResponse model
└── models/
    └── common.py       # EXISTS: ErrorResponse already defined
```

```
frontend/src/
├── services/api/
│   └── types.ts        # MODIFY: Remove ChatMessage duplicate, eliminate any
├── composables/
│   └── useAsyncState.ts # NEW: Shared error/loading lifecycle composable
└── [components]        # MODIFY: Replace any with proper types
```

### Pattern 1: Centralized Config Constants

**What:** All magic numbers (timeouts, limits, thresholds) move to `backend/app/config.py` as named constants.
**When to use:** Any numeric literal used as a timeout, retry count, buffer size, or threshold.
**Example:**
```python
# backend/app/config.py
# --- Execution constants ---
EXECUTION_TIMEOUT_DEFAULT = 600      # 10 minutes
EXECUTION_TIMEOUT_MIN = 60           # 1 minute
EXECUTION_TIMEOUT_MAX = 3600         # 1 hour
MAX_RETRY_ATTEMPTS = 5
MAX_RETRY_DELAY = 3600               # 1 hour ceiling for exponential backoff
WEBHOOK_DEDUP_WINDOW = 10            # seconds

# --- SSE constants ---
SSE_REPLAY_LIMIT = 500
SSE_KEEPALIVE_TIMEOUT = 30           # seconds
STALE_EXECUTION_THRESHOLD = 900      # 15 minutes

# --- Process management ---
THREAD_JOIN_TIMEOUT = 10             # seconds
SIGTERM_GRACE_SECONDS = 5

# --- Budget defaults ---
DEFAULT_5H_TOKEN_LIMIT = 300_000
DEFAULT_WEEKLY_TOKEN_LIMIT = 1_000_000
```

### Pattern 2: ErrorResponse Adoption in Routes

**What:** Replace all ad-hoc `{"error": "message"}` dicts with `ErrorResponse(error="message").model_dump()` or direct Pydantic model return.
**When to use:** Every route handler error return path.
**Note:** flask-openapi3 supports returning Pydantic models directly. However, the current codebase convention returns `(dict, HTTPStatus)` tuples. The minimal-risk approach is to keep the tuple convention but use `ErrorResponse(error="...").model_dump()` for the dict portion, ensuring a uniform structure. A more thorough approach is to register `ErrorResponse` in the OpenAPI response schemas for each endpoint.
**Example:**
```python
from app.models.common import ErrorResponse

# Before:
return {"error": "Plugin not found"}, HTTPStatus.NOT_FOUND

# After:
return ErrorResponse(error="Plugin not found").model_dump(), HTTPStatus.NOT_FOUND
```

### Pattern 3: Standardized DB Function Naming

**What:** All DB creation functions use the `create_` prefix (currently 47 use `add_`, 7 use `create_`).
**When to use:** Renaming is done in bulk; all callers must be updated simultaneously.
**Implementation note:** The `add_` to `create_` rename must update both the DB module definition, the `__init__.py` re-exports, and all service-layer callers. A search-and-replace with grep verification is safest.
**Example:**
```python
# Before:
def add_agent(name: str, ...) -> Optional[str]:

# After:
def create_agent(name: str, ...) -> Optional[str]:
```

### Pattern 4: Structured Logger Replacement

**What:** Replace `print()` calls with `logger.info()` / `logger.warning()` / `logger.error()` using the module-level logger pattern.
**When to use:** Every file that uses `print()`.
**Example:**
```python
import logging

logger = logging.getLogger(__name__)

# Before:
print(f"Created tables: {', '.join(tables_created)}")

# After:
logger.info("Created tables: %s", ", ".join(tables_created))
```

### Pattern 5: ID Factory Consolidation

**What:** Replace the repetitive per-entity generator functions with a single factory function, keeping the existing functions as thin wrappers.
**When to use:** To reduce the boilerplate in `ids.py` and make the 2 remaining `random.choices()` call sites use the central factory.
**Example:**
```python
# ids.py - new factory function
def generate_id(prefix: str, length: int) -> str:
    """Generate a prefixed ID using cryptographic randomness."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(length))
    return f"{prefix}{random_part}"

# Existing wrappers become one-liners:
def generate_agent_id() -> str:
    return generate_id(AGENT_ID_PREFIX, AGENT_ID_LENGTH)
```

The 2 call sites using `random.choices()` (in `app/routes/super_agents.py:317` and `app/services/team_execution_service.py:62`) must be converted to use `generate_id()` or `_generate_short_id()`.

### Pattern 6: Frontend useAsyncState Composable

**What:** A shared composable that standardizes the loading/error/data lifecycle pattern used across multiple composables.
**When to use:** Any composable or view that fetches async data and manages loading/error state.
**Example:**
```typescript
// composables/useAsyncState.ts
export function useAsyncState<T>(asyncFn: () => Promise<T>, initialValue: T) {
  const data = ref<T>(initialValue) as Ref<T>;
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  async function execute(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      data.value = await asyncFn();
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoading.value = false;
    }
  }

  return { data, isLoading, error, execute };
}
```

### Anti-Patterns to Avoid

- **Bare `except Exception` without logging:** 228 instances exist. Each must be reviewed; some intentionally silence errors, others should log. Do not blindly add logging to intentional silence blocks.
- **Mixing `add_` and `create_` prefixes in DB layer:** Choose one convention (`create_`) and apply everywhere.
- **Scattered `print()` in service code:** All output must go through the structured logger.
- **`catch (e: any)` in TypeScript:** Use `catch (err: unknown)` with proper type narrowing.
- **Inline `ChatMessage` interfaces that duplicate `ConversationMessage`:** Use the canonical type from `types.ts`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Logging framework | Custom print wrapper | Python `logging` stdlib | Already configured, supports levels, formatters, handlers |
| Error response format | New error class | Existing `ErrorResponse` Pydantic model | Already defined in `app/models/common.py` |
| ID generation | New random utilities | Existing `app/db/ids.py` factory | Already uses `secrets.choice()`, centralized |
| Frontend async state | Per-composable boilerplate | `useAsyncState` composable | Reduces duplication across 4+ composables |
| SSE connection management | Per-component EventSource setup | Existing `createAuthenticatedEventSource` | Already centralized in `api/client.ts` |

**Key insight:** The codebase already has the right abstractions (`ErrorResponse`, `ids.py`, `createAuthenticatedEventSource`, `useDataPage`). The problem is inconsistent adoption, not missing infrastructure.

## Common Pitfalls

### Pitfall 1: Breaking DB Function Renames

**What goes wrong:** Renaming `add_*` to `create_*` in DB modules without updating all callers, especially those in `app/db/__init__.py` re-exports and services that import from `app.database` (the legacy shim).
**Why it happens:** The `database.py` file uses `from app.db import *` (wildcard), and some services import from `app.database` while others import from `app.db`.
**How to avoid:** Use IDE rename refactoring or grep-based rename with verification. After renaming, run `cd backend && uv run pytest` immediately.
**Warning signs:** `ImportError` or `AttributeError` in test runs after rename.

### Pitfall 2: Over-Enthusiastic Exception Logging

**What goes wrong:** Adding `logger.error(...)` to intentional `except Exception: pass` blocks that are designed to silence non-critical failures (e.g., cleanup operations, optional feature detection).
**Why it happens:** Treating all bare exception blocks as bugs rather than intentional design.
**How to avoid:** Review each `except Exception` block individually. Check if the block is in a cleanup path, optional feature detection, or retry loop. Add a comment `# Intentionally silenced: <reason>` for blocks that should remain silent.
**Warning signs:** Log spam from non-actionable errors after the refactoring.

### Pitfall 3: TypeScript `any` Removal Cascade

**What goes wrong:** Removing `any` from a component prop or event handler reveals type incompatibilities that cascade through parent/child components.
**Why it happens:** `any` was used as an escape hatch for complex types (Chart.js callbacks, Vue Flow event handlers, dynamic form data).
**How to avoid:** Start with the simplest `any` instances (e.g., `catch (e: any)` to `catch (err: unknown)`), then tackle component props. For third-party library callbacks (Chart.js), use the library's actual types. Run `vue-tsc` after each file.
**Warning signs:** Build failures after removing `any` from shared interfaces.

### Pitfall 4: Migration File print() Removal

**What goes wrong:** Replacing `print()` in migration functions with `logger.info()` could change behavior if the migration runner relies on stdout output, or if logging is not configured when migrations run at startup.
**Why it happens:** Migrations run during `init_db()` in `create_app()`, before logging may be fully configured.
**How to avoid:** Ensure `logging.basicConfig()` or equivalent is called before `init_db()`. Test by running the app from scratch with a fresh database.
**Warning signs:** Silent migration failures, missing migration progress messages.

### Pitfall 5: Config Import Circular Dependencies

**What goes wrong:** Moving constants from service files to `config.py` can create circular imports if `config.py` imports from service modules.
**Why it happens:** `config.py` currently only has path constants. Adding behavioral constants is safe as long as `config.py` remains a leaf module with no local imports.
**How to avoid:** Keep `config.py` as a pure constants module with only stdlib imports (os, pathlib). Never import from `app.services` or `app.db`.
**Warning signs:** `ImportError` on startup.

## Experiment Design

### Recommended Experimental Setup

This is a refactoring phase, not an experimental phase. The "experiment" is the refactoring itself, validated by existing test suites and build checks.

**Independent variables:** Which files are refactored (incremental rollout by requirement).
**Dependent variables:** Test pass rate, build success, grep-verified zero counts.
**Controlled variables:** Application behavior (no feature changes).

**Baseline comparison:**
- Method: Current codebase state (pre-refactoring)
- Expected performance: All tests pass, build succeeds
- Our target: Same test pass rate + zero violations per requirement

**Verification approach:**
1. Before each refactoring task, run full test suite to establish baseline
2. After each task, run full test suite to confirm no regressions
3. Run grep-based verification to confirm zero remaining violations

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| `print()` count in `app/` | CON-01 progress | `grep -rn 'print(' app/ \| wc -l` | 112 (60 migrations/seeds, 7 services, rest in other code) |
| Ad-hoc error dicts in routes | CON-02 progress | `grep -rn '"error"' app/routes/ \| wc -l` | 495 |
| Missing return types (services) | CON-03 progress | Count functions without `->` annotation | 269 |
| Missing return types (DB) | CON-03 progress | Count functions without `->` annotation | 175 |
| `random.choices()` calls | CON-04 progress | `grep -rn 'random\.choices' app/` | 2 |
| `add_` prefixed DB functions | CON-06 progress | `grep -rn 'def add_' app/db/` | 47 |
| TypeScript `any` count | CON-08 progress | `grep -rn ': any\|as any' src/ \| wc -l` | 147 |
| `ChatMessage` references | CON-08 progress | `grep -rn 'ChatMessage' src/` | 1 definition + usages in useSketchChat |
| Services without logger | CON-01 supplement | Count service files missing `logger =` | 30 |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Zero `print()` in service code | Level 1 (Sanity) | grep check |
| All routes use ErrorResponse | Level 1 (Sanity) | grep check |
| All DB/service functions have return types | Level 1 (Sanity) | grep check or mypy |
| Zero `random.choices()` outside `ids.py` | Level 1 (Sanity) | grep check |
| `add_` renamed to `create_` everywhere | Level 1 (Sanity) | grep check |
| Zero TypeScript `any` in components/services | Level 1 (Sanity) | vue-tsc strict check |
| No `ChatMessage` duplicate type | Level 1 (Sanity) | grep check |
| All tests still pass | Level 1 (Sanity) | `pytest` + `vitest` |
| Frontend builds with zero errors | Level 1 (Sanity) | `npm run build` (includes vue-tsc) |
| Config constants used instead of magic numbers | Level 2 (Proxy) | Code review of key services |
| Exception handling follows severity guidelines | Level 2 (Proxy) | Code review of service catch blocks |

**Level 1 checks to always include:**
- `grep -rn 'print(' backend/app/services/ | grep -v '__pycache__'` returns empty
- `grep -rn 'random\.choices' backend/app/ | grep -v '__pycache__'` returns empty
- `grep -rn 'def add_' backend/app/db/ | grep -v '__pycache__' | grep -v __init__` returns empty
- `cd backend && uv run pytest` passes
- `cd frontend && npm run build` passes (includes vue-tsc)
- `cd frontend && npm run test:run` passes

**Level 2 proxy metrics:**
- Spot-check 5 service files for consistent exception handling patterns
- Spot-check 5 route files for ErrorResponse usage
- Verify `config.py` contains all extracted constants

**Level 3 deferred items:**
- Ruff rule T201 (no-print) enforcement in CI configuration
- TypeScript `any` ban via ESLint `@typescript-eslint/no-explicit-any` rule

## Production Considerations (from KNOWHOW.md)

The KNOWHOW.md registry is empty (initialized but not populated). Production considerations are derived from the CONCERNS.md analysis.

### Known Failure Modes

- **Migration `print()` removal may hide startup issues:** Migrations currently print progress to stdout. If replaced with `logger.info()` but logging is not configured before `init_db()`, migration progress becomes invisible.
  - Prevention: Ensure `logging.basicConfig(level=logging.INFO)` is called before `init_db()` in `create_app()`.
  - Detection: Run the app with a fresh DB and verify migration messages appear in logs.

- **DB function rename breaks imports through `database.py` wildcard:** The legacy `database.py` uses `from app.db import *`. Renaming `add_*` to `create_*` will break any code importing from `app.database`.
  - Prevention: Update `app/db/__init__.py` exports simultaneously. Grep for all import sites.
  - Detection: `ImportError` in test suite.

### Scaling Concerns

- **None specific to this phase.** This is a refactoring phase that does not change runtime behavior.

### Common Implementation Traps

- **Moving constants too aggressively:** Some constants are class-level on purpose (e.g., `ExecutionService.MAX_RETRY_ATTEMPTS`) because they are semantically scoped to that service. Moving everything to a flat `config.py` can reduce locality of reference.
  - Correct approach: Move only truly shared constants (used in 2+ files) and magic numbers (unnamed numeric literals) to `config.py`. Keep single-use class-level constants in place but name them properly.

- **Breaking the `@staticmethod` vs `@classmethod` split:** The codebase uses 174 `@staticmethod` and 499 `@classmethod` methods in services. The requirement asks to standardize, but the existing split is intentional: `@classmethod` is used for methods that access class-level state (locks, buffers), while `@staticmethod` is used for pure functions.
  - Correct approach: Do NOT convert all to one style. Instead, document the convention: use `@classmethod` when accessing class-level state (`cls._lock`, `cls._buffers`), use `@staticmethod` for stateless operations.

## Code Examples

### Example 1: Logger Setup Pattern (CON-01)
```python
# Source: Existing pattern in 61 service files
import logging

logger = logging.getLogger(__name__)

# Severity levels:
# logger.debug()    - Diagnostic detail, not shown in production
# logger.info()     - Normal operation progress
# logger.warning()  - Unexpected but recoverable situations
# logger.error()    - Failures that need attention, use exc_info=True for tracebacks
# logger.critical() - System-level failures

# For exceptions, always include exc_info:
try:
    do_something()
except Exception as e:
    logger.error("Failed to do something: %s", e, exc_info=True)
```

### Example 2: Return Type Annotations (CON-03)
```python
# Source: Existing convention from CONVENTIONS.md

# DB CRUD returns:
def create_agent(name: str, ...) -> Optional[str]:  # Returns ID or None on failure
    ...

def update_agent(agent_id: str, **kwargs) -> bool:  # True if row updated
    ...

def delete_agent(agent_id: str) -> bool:  # True if row deleted
    ...

# Service returns:
@classmethod
def get_agent_detail(cls, agent_id: str) -> Tuple[dict, HTTPStatus]:
    ...
```

### Example 3: Frontend Type Consolidation (CON-08)
```typescript
// Source: Existing ConversationMessage in types.ts
// This is the canonical type; ChatMessage in useSketchChat.ts is the duplicate

export interface ConversationMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  backend?: string;
}

// useSketchChat.ts should import and use ConversationMessage instead of defining ChatMessage
```

### Example 4: Config Constants Module (CON-07)
```python
# backend/app/config.py — extend existing file
import os

# --- Paths (existing) ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "backend", "agented.db")
DB_PATH = os.environ.get("AGENTED_DB_PATH", _DEFAULT_DB_PATH)
SYMLINK_DIR = os.path.join(PROJECT_ROOT, "project_links")

# --- Execution ---
EXECUTION_TIMEOUT_DEFAULT = 600
EXECUTION_TIMEOUT_MIN = 60
EXECUTION_TIMEOUT_MAX = 3600
MAX_RETRY_ATTEMPTS = 5
MAX_RETRY_DELAY = 3600
WEBHOOK_DEDUP_WINDOW = 10

# --- SSE ---
SSE_REPLAY_LIMIT = int(os.environ.get("SSE_REPLAY_LIMIT", "500"))
SSE_KEEPALIVE_TIMEOUT = 30
STALE_EXECUTION_THRESHOLD = int(os.environ.get("STALE_EXECUTION_THRESHOLD_SECS", "900"))

# --- Process management ---
THREAD_JOIN_TIMEOUT = 10
SIGTERM_GRACE_SECONDS = 5
OUTPUT_RING_BUFFER_SIZE = 1000

# --- Budget ---
DEFAULT_5H_TOKEN_LIMIT = 300_000
DEFAULT_WEEKLY_TOKEN_LIMIT = 1_000_000

# --- GitHub ---
CLONE_TIMEOUT = 300
GIT_OP_TIMEOUT = 120
```

### Example 5: Exception Handling Severity Convention (CON-05)
```python
# Documented severity convention for exception handling

# LEVEL 1: Critical path — always log with exc_info, always propagate or return error
try:
    result = execute_trigger(trigger_id)
except Exception as e:
    logger.error("Trigger execution failed for %s: %s", trigger_id, e, exc_info=True)
    return {"error": "Execution failed"}, HTTPStatus.INTERNAL_SERVER_ERROR

# LEVEL 2: Best-effort operation — log warning, continue
try:
    save_audit_event(event)
except Exception as e:
    logger.warning("Failed to save audit event: %s", e, exc_info=True)
    # Continue - audit is not critical

# LEVEL 3: Intentionally silenced — add comment explaining why
try:
    optional_cleanup()
except Exception:
    pass  # Intentionally silenced: cleanup is best-effort, failure is harmless

# NEVER: Bare except without comment
try:
    something()
except Exception:  # BAD: Why is this silenced? What exceptions are expected?
    pass
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `print()` for logging | `logging.getLogger(__name__)` | Python community standard | Structured, filterable, configurable output |
| `random.choices()` for IDs | `secrets.choice()` | Python 3.6+ | Cryptographically secure randomness |
| Inline `{"error": msg}` | Pydantic `ErrorResponse` model | flask-openapi3 convention | Type-safe, OpenAPI-documented error schema |
| TypeScript `any` | Proper types + `unknown` | TypeScript 3.0+ best practice | Full type safety, better IDE support |
| Per-file constants | Centralized config module | Common Flask pattern | Single source of truth, easy to discover/override |

**Deprecated/outdated:**
- `random.choices()` for security-adjacent IDs: Superseded by `secrets.choice()` since Python 3.6.
- `catch (e: any)` in TypeScript: Use `catch (err: unknown)` and narrow with `instanceof Error`.

## Open Questions

1. **Migration print() handling**
   - What we know: Migrations use ~60 `print()` calls for progress reporting. Logger may not be configured when migrations run.
   - What's unclear: Whether the app configures logging before `init_db()` is called.
   - Recommendation: Check `create_app()` ordering. If logging is configured first, safe to replace. If not, add `logging.basicConfig()` before `init_db()`.

2. **Scope of `add_` to `create_` rename**
   - What we know: 47 `add_` functions, 7 `create_` functions. Some `add_` functions are truly "add to a collection" (e.g., `add_team_member`, `add_project_path`) rather than "create a new entity."
   - What's unclear: Whether ALL `add_` should become `create_`, or only top-level entity creation.
   - Recommendation: Rename only top-level entity creation functions (e.g., `add_agent` -> `create_agent`, `add_team` -> `create_team`). Keep `add_team_member`, `add_project_path` etc. as `add_` since they add to an existing entity's collection.

3. **@staticmethod vs @classmethod standardization**
   - What we know: 174 `@staticmethod` and 499 `@classmethod` in services. The split correlates with whether the method accesses class-level state.
   - What's unclear: Whether the requirement intends full standardization or just documentation.
   - Recommendation: Document the convention, do not force-convert. The existing split is functionally correct.

4. **Frontend `any` reduction target**
   - What we know: 147 `any` instances. Some are in third-party library interaction code (Chart.js callbacks, Vue Flow events) where proper types are complex.
   - What's unclear: Whether "reduced to zero" is achievable for all 147 instances or if some library interaction `any` is acceptable.
   - Recommendation: Target zero `any` in component props, service files, and composables. Allow documented `any` for third-party library callbacks where proper types would require excessive type gymnastics. Use `// eslint-disable-next-line @typescript-eslint/no-explicit-any` with explanation for justified exceptions.

## Sources

### Primary (HIGH confidence)
- Direct codebase audit via grep (2026-03-04) -- all metrics measured directly
- `backend/app/db/ids.py` -- confirmed `secrets.choice()` usage throughout
- `backend/app/models/common.py` -- confirmed `ErrorResponse` model exists
- `frontend/src/services/api/client.ts` -- confirmed centralized `createAuthenticatedEventSource`
- `frontend/src/composables/useDataPage.ts` -- confirmed shared async pattern exists
- `.planning/codebase/CONVENTIONS.md` -- documented coding standards
- `.planning/codebase/CONCERNS.md` -- documented technical concerns

### Secondary (MEDIUM confidence)
- Python `logging` module best practices -- stdlib documentation
- TypeScript `unknown` vs `any` best practices -- TypeScript handbook

### Tertiary (LOW confidence)
- None. All findings based on direct codebase analysis.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all existing tooling
- Architecture: HIGH - patterns derived from existing codebase conventions
- Recommendations: HIGH - based on direct codebase audit with exact counts
- Pitfalls: HIGH - derived from actual codebase structure analysis

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable -- refactoring patterns do not change)
