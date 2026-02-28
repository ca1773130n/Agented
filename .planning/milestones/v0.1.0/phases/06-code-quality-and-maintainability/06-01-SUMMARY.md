---
phase: 06-code-quality-and-maintainability
plan: 01
subsystem: database
tags: [refactoring, seeds, migrations, sqlite, code-quality]

# Dependency graph
requires: []
provides:
  - "Dedicated seeds.py module with 4 startup seed functions and PRESET_MCP_SERVERS data"
  - "Clean migrations.py containing only schema migration code"
  - "Intact re-export chain: seeds.py -> __init__.py -> database.py -> app factory"
affects: [06-02, 06-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Seed/migration separation: seed data and startup functions in seeds.py, schema evolution in migrations.py"
    - "Import from canonical source: seeds.py imports PREDEFINED_TRIGGERS from triggers.py instead of duplicating"

key-files:
  created:
    - "backend/app/db/seeds.py"
  modified:
    - "backend/app/db/migrations.py"
    - "backend/app/db/__init__.py"

key-decisions:
  - "seeds.py imports PREDEFINED_TRIGGERS and PREDEFINED_TRIGGER_ID from .triggers (canonical source) to avoid duplication"
  - "migrations.py retains its own copies of PREDEFINED_TRIGGERS and VALID_BACKENDS for migration function isolation"
  - "Removed unused _get_unique_mcp_server_id import from migrations.py after extraction"

patterns-established:
  - "Seed/migration separation: startup seeding functions live in seeds.py, schema migrations in migrations.py"

# Metrics
duration: 7min
completed: 2026-02-28
---

# Phase 06 Plan 01: Migration/Seed Separation Summary

**Extracted 4 seed functions and PRESET_MCP_SERVERS (9 entries) from migrations.py into dedicated seeds.py, reducing migrations.py by 322 lines while maintaining 906/906 test pass rate with zero test modifications.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-28T02:43:04Z
- **Completed:** 2026-02-28T02:50:26Z
- **Tasks:** 2/2 completed
- **Files modified:** 3

## Accomplishments

- Created `backend/app/db/seeds.py` (349 lines) containing all 4 seed functions (`seed_predefined_triggers`, `seed_preset_mcp_servers`, `migrate_existing_paths`, `auto_register_project_root`) and the `PRESET_MCP_SERVERS` data constant (9 preset MCP server definitions)
- Cleaned `migrations.py` from 3,102 to 2,780 lines -- now contains only schema migration code, version tracking, and the `VERSIONED_MIGRATIONS` registry
- Updated `__init__.py` re-exports to route seed function imports through `seeds.py` and `init_db` through `migrations.py`, preserving the full import chain (`app.db.seeds` -> `app.db` -> `app.database` -> app factory)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create seeds.py with extracted seed functions and data** - `135ec30` (feat)
2. **Task 2: Update __init__.py re-exports and verify full test suite** - `d848c2f` (refactor)

## Files Created/Modified

- `backend/app/db/seeds.py` - New module with seed functions and PRESET_MCP_SERVERS data extracted from migrations.py
- `backend/app/db/migrations.py` - Removed seed functions, PRESET_MCP_SERVERS, and path migration helpers; cleaned unused import; updated docstring
- `backend/app/db/__init__.py` - Split migrations import into init_db from .migrations and seed functions from .seeds

## Decisions Made

1. **seeds.py imports from .triggers (canonical source):** Instead of duplicating PREDEFINED_TRIGGERS and PREDEFINED_TRIGGER_ID, seeds.py imports them from triggers.py where they are canonically defined. This follows DRY principles and avoids drift.
2. **migrations.py constants left in place:** The PREDEFINED_TRIGGERS, VALID_BACKENDS, etc. duplicated in migrations.py were intentionally left in place because migration functions (_migrate_to_string_ids, _create_migration_only_tables) reference them. Removing would require cross-module imports from within migration functions, violating migration isolation.
3. **Cleaned unused import:** Removed `_get_unique_mcp_server_id` from migrations.py imports since the only consumer (seed_preset_mcp_servers) moved to seeds.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Cleaned unused import in migrations.py**
- **Found during:** Task 1
- **Issue:** After extracting seed_preset_mcp_servers to seeds.py, the `_get_unique_mcp_server_id` import in migrations.py became unused
- **Fix:** Removed the unused import from the `from .ids import` line
- **Files modified:** backend/app/db/migrations.py
- **Verification:** `grep -c "_get_unique_mcp_server_id" backend/app/db/migrations.py` returns 0
- **Committed in:** 135ec30 (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2: unused import cleanup)
**Impact on plan:** Minimal -- standard cleanup that prevents linter warnings

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 06-01 (migration/seed separation) is complete
- Plans 06-02 (Ruff migration) and 06-03 (ExecutionService decomposition) can proceed independently
- No blockers identified

## Self-Check: PASSED

All claims verified:
- `backend/app/db/seeds.py` exists (349 lines, above 150 minimum)
- `backend/app/db/migrations.py` contains 0 seed functions
- `PRESET_MCP_SERVERS` not in migrations.py
- All imports resolve: `app.db.seeds`, `app.db`, `app.database`
- Test suite: 906/906 passed (100%)
- Commits 135ec30 and d848c2f exist

---
*Phase: 06-code-quality-and-maintainability*
*Completed: 2026-02-28*
