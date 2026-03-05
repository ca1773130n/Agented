---
phase: 15-code-consistency-standards
plan: 03
subsystem: backend-routes-db-services
tags: [error-response, db-rename, type-annotations, exception-handling, code-quality]
dependency_graph:
  requires:
    - centralized-config-constants
    - id-generation-factory
    - service-logger-declarations
  provides:
    - unified-error-responses
    - consistent-db-naming
    - return-type-annotations
    - exception-handling-conventions
  affects:
    - backend/app/routes/*.py
    - backend/app/db/*.py
    - backend/app/services/*.py
    - backend/app/models/common.py
tech_stack:
  added: []
  patterns:
    - "error_response(code, message, status) for all API error returns"
    - "create_ prefix for entity creation DB functions, add_ prefix for collection-add operations"
    - "Three-level exception handling: critical (error+exc_info), best-effort (warning), silenced (comment)"
    - "db_ prefix aliases in routes/services to resolve naming collisions with handler functions"
key_files:
  created: []
  modified:
    - backend/app/models/common.py
    - backend/app/routes/*.py (52 route files)
    - backend/app/db/*.py (20 DB module files)
    - backend/app/db/__init__.py
    - backend/app/database.py
    - backend/app/services/*.py (54 service files)
    - backend/tests/*.py (20 test files)
decisions:
  - "Used error_response() helper instead of ErrorResponse.model_dump() -- ErrorResponse requires code field, error_response() provides backward-compatible schema with code+message+error+details+request_id"
  - "DB function naming: db_ prefix aliases in route/service files to resolve collisions between handler function names (e.g., def create_workflow) and DB imports (create_workflow from database)"
  - "error_response() made robust to accept both HTTPStatus enum and int status codes"
  - "Collection-add functions preserved as add_ (add_team_member, add_workflow_version, etc.) per plan guidance"
  - "Bare except-pass blocks classified by context: process cleanup, JSON parsing, file IO, optional features"
metrics:
  duration: "54min"
  completed: "2026-03-06"
---

# Phase 15 Plan 03: Backend Consistency -- Error Responses, DB Naming, Type Annotations, Exception Handling

Standardized error responses across 52 route files and 22 service files using error_response(), renamed 18 entity creation DB functions from add_ to create_, added 206+ return type annotations to service methods, and classified 68 bare except-pass blocks with severity-level comments.

## Task Summary

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Adopt ErrorResponse model in all route error returns | bdc0cc9 | Replaced 562 ad-hoc error dicts with error_response() across 52 route files |
| 2 | Rename DB functions from add_ to create_ and add return type annotations | ceb9f3a | Renamed 18 entity creation functions, updated 477 references, added 206 type annotations |
| 3 | Standardize exception handling with severity levels | b65cb04 | Added comments to 68 bare pass blocks, exc_info to 101 logger.error calls, converted 137 service error returns |

## Changes Made

### Task 1: ErrorResponse Standardization (CON-02)

Replaced all ad-hoc `{"error": "message"}` dict returns in route handlers with `error_response(code, message, status)` calls. The `error_response()` helper from `app.models.common` produces a unified error schema with backward-compatible `error` field alongside new `code`, `message`, `details`, and `request_id` fields.

- 562 string-literal and variable-based error returns converted
- DAG validation errors use the `details` parameter for structured error lists
- Import sorting fixed across all 52 route files via ruff --fix
- Test updated for DAG validation (errors now in details dict)

### Task 2: DB Function Rename + Return Type Annotations (CON-06 + CON-03)

**Part A -- Rename:** Renamed 18 entity creation functions from `add_` to `create_` prefix:
- `add_agent` -> `create_agent`, `add_team` -> `create_team`, `add_trigger` -> `create_trigger`, `add_workflow` -> `create_workflow`, `add_plugin` -> `create_plugin`, `add_marketplace` -> `create_marketplace`, `add_product` -> `create_product`, `add_project` -> `create_project`, `add_command` -> `create_command`, `add_hook` -> `create_hook`, `add_rule` -> `create_rule`, `add_sketch` -> `create_sketch`, `add_super_agent` -> `create_super_agent`, `add_mcp_server` -> `create_mcp_server`, `add_snippet` -> `create_snippet`, `add_audit_event` -> `create_audit_event`, `add_milestone` -> `create_milestone`, `add_campaign_execution` -> `create_campaign_execution`

Collection-add functions preserved as `add_`: `add_team_member`, `add_project_path`, `add_workflow_version`, etc. (30+ functions).

Used `db_` prefix aliases in 15 route/service files to resolve naming collisions between route handler functions (e.g., `def create_workflow()`) and DB imports.

**Part B -- Return type annotations:** Added `-> None` to 206 service methods. Fixed incorrect annotations on closures: `replacer -> str` (not None), `decorator/wrapper -> Callable` (not None).

### Task 3: Exception Handling Standardization (CON-05)

Classified and annotated all exception handling blocks following three-level severity convention:

1. **Critical path** (Level 1): `logger.error()` with `exc_info=True` -- applied to 101 existing error-level log calls in except blocks
2. **Best-effort** (Level 2): `logger.warning()` -- already present in most cases
3. **Intentionally silenced** (Level 3): Added explanatory comments to 68 bare `pass` blocks, e.g., `# Intentionally silenced: process already terminated`

Also converted 137 ad-hoc `{"error": ...}` dicts in 22 service files to `error_response()` calls, and made `error_response()` robust to accept both `HTTPStatus` enum and int status codes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed naming collisions between route handlers and DB imports**
- **Found during:** Task 2
- **Issue:** 15 route files and 2 service files had handler functions named identically to renamed DB functions (e.g., both `def create_workflow()` route handler and `create_workflow` DB import)
- **Fix:** Used `db_` prefix aliases for DB imports in affected files (e.g., `from ..database import create_workflow as db_create_workflow`)
- **Files modified:** 13 route files, 2 service files
- **Commit:** ceb9f3a

**2. [Rule 1 - Bug] Fixed error_response() int status code handling**
- **Found during:** Task 3
- **Issue:** RBAC service used `error_response("FORBIDDEN", msg, 403)` with int, but `error_response()` called `status.value` which fails on ints
- **Fix:** Made `error_response()` handle both `HTTPStatus` enum and int status codes; also fixed RBAC calls to use `HTTPStatus.FORBIDDEN`
- **Files modified:** backend/app/models/common.py, backend/app/services/rbac_service.py
- **Commit:** b65cb04

**3. [Rule 1 - Bug] Fixed misplaced imports in multiline import blocks**
- **Found during:** Task 3
- **Issue:** Automated import insertion placed `from app.models.common import error_response` inside multiline `from ..database import (...)` blocks in 11 service files
- **Fix:** Moved imports to correct position before multiline import blocks
- **Files modified:** 11 service files
- **Commit:** b65cb04

**4. [Rule 1 - Bug] Fixed incorrect return type annotations on closures**
- **Found during:** Task 2
- **Issue:** Automated `-> None` annotation was wrong for closures that return values: `replacer()` returns `str`, `decorator()`/`require_role()` return `Callable`
- **Fix:** Changed to correct return types: `-> str`, `-> Callable`
- **Files modified:** backend/app/services/prompt_snippet_service.py, backend/app/services/rbac_service.py
- **Commit:** ceb9f3a

## Verification Results

- Zero `return {"error":` patterns in routes (grep verified)
- Zero entity creation `add_` functions remain (grep verified, excluding 30+ collection-add functions)
- All backend tests: 1447 passed, 1 pre-existing failure (test_import_error_handled_gracefully)
- Ruff lint: 1 pre-existing unused variable warning in test file
- Ruff format: all files formatted

## Self-Check: PASSED

- [x] Commit bdc0cc9 exists (Task 1: ErrorResponse adoption)
- [x] Commit ceb9f3a exists (Task 2: DB rename + type annotations)
- [x] Commit b65cb04 exists (Task 3: Exception handling standardization)
- [x] SUMMARY.md exists
- [x] backend/app/models/common.py exists with error_response()
- [x] Zero ad-hoc error dicts in routes
- [x] Zero entity creation add_ functions in DB layer
- [x] 1447 tests pass (1 pre-existing failure)
