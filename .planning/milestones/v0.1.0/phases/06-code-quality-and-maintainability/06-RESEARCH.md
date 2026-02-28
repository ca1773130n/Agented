# Phase 6: Code Quality and Maintainability - Research

**Researched:** 2026-02-28
**Domain:** Python code quality tooling, migration/seed separation, service decomposition
**Confidence:** HIGH

## Summary

Phase 6 addresses three independent code quality improvements: (1) extracting seed data from `migrations.py` into a dedicated `seeds.py` module, (2) replacing Black with Ruff as the sole linter/formatter, and (3) decomposing `ExecutionService` into a coordinator plus stateless helper classes (`PromptRenderer`, `CommandBuilder`).

All three requirements are well-understood refactoring tasks with minimal risk. The migration/seed split is the simplest -- the seeding functions are already clearly delineated in a labeled section at the bottom of `migrations.py`. The Ruff migration is near-trivial since Ruff is already installed and partially configured in `pyproject.toml` alongside Black -- the task is to remove Black, extend Ruff's formatter config, and reformat. The `ExecutionService` split is the most complex but is well-bounded: two pure-function extraction targets (`build_command` and prompt rendering logic from `run_trigger`) can be moved to standalone classes while the facade delegates to them.

**Primary recommendation:** Execute all three requirements in parallel since they touch non-overlapping files; start each with a verification baseline (existing test pass), make the change, and re-verify.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Ruff as Unified Linter/Formatter (Replacing Black)

**Recommendation:** Remove Black entirely and use `ruff check` + `ruff format` as the sole Python quality toolchain.

**Evidence:**
- Ruff official documentation (astral.sh/ruff, 2024-2025) -- Ruff's formatter is designed as a "drop-in replacement for Black" with identical output for 99.9% of cases. It respects the same `line-length`, `target-version`, and `quote-style` settings.
- Ruff benchmark data (astral.sh/ruff, Context7 verified) -- Ruff is 10-100x faster than Flake8+Black combined. On a 240-file codebase like this backend, formatting completes in <1 second vs. multi-second Black runs.
- Current project state: `pyproject.toml` already has `[tool.ruff]` with `line-length = 100`, `target-version = "py310"`, and `[tool.ruff.lint]` with `select = ["E", "F", "I"]`. Black is `26.1.0` in dev dependencies. Both tools are installed. Only the `[tool.ruff.format]` section and removal of `[tool.black]` are needed.

**Confidence:** HIGH -- Verified via Context7 (library ID: `/websites/astral_sh_ruff`), current `pyproject.toml` read, and `ruff format --check` execution (29 files need reformatting under Ruff's rules).

**Expected improvement:** Simpler toolchain (1 tool instead of 2), faster CI, consistent lint+format in one command.

**Caveats:** Ruff formatter output may differ slightly from Black in edge cases (trailing comma handling, magic trailing comma). The 29 files flagged by `ruff format --check` will change, but since the project has no CI formatting gate currently, this is purely cosmetic.

### Recommendation 2: Facade Pattern for Service Decomposition

**Recommendation:** Extract stateless helper classes from `ExecutionService` while preserving the existing public API surface as a thin facade.

**Evidence:**
- Fowler, M. "Refactoring: Improving the Design of Existing Code" (2018, 2nd ed.) -- "Extract Class" refactoring pattern (Chapter 7). When a class has methods that operate on distinct subsets of data, extracting them into separate classes improves cohesion and testability.
- Martin, R.C. "Clean Architecture" (2017) -- Single Responsibility Principle applied to service classes: a 1,387-line `ExecutionService` with prompt rendering, command building, rate-limit management, webhook dispatch, and process lifecycle violates SRP.
- Current project state: `ExecutionService.build_command()` is a pure `@staticmethod` (lines 434-485) with zero dependencies on class state -- it is a textbook extraction candidate. Prompt rendering logic (lines 628-677 of `run_trigger`) is similarly stateless: it performs string replacements on a template dict.

**Confidence:** HIGH -- Both extraction targets are pure functions with well-defined inputs/outputs, verified by code reading. Existing tests (`TestBuildCommand` in `test_backend_detection.py`) already test `build_command` in isolation.

**Expected improvement:** Each helper class can be unit-tested independently. `ExecutionService.run_trigger` shrinks by approximately 80 lines. New modules are <100 lines each.

**Caveats:** The facade must preserve exact method signatures so that all existing call sites (`test_budget_integration.py`, `test_team_execution.py`, `test_agent_scheduler.py`, `test_rotation_service.py`, `test_trigger_team_integration.py`) continue to work without changes.

### Recommendation 3: Migration/Seed Separation Pattern

**Recommendation:** Extract seeding functions and their data constants into `backend/app/db/seeds.py`, keeping `migrations.py` as a pure schema-migration record.

**Evidence:**
- Django documentation (docs.djangoproject.com, "Data Migrations" section) -- Django explicitly separates schema migrations from data seeding (`loaddata` / fixtures). Mixing schema changes with seed data makes it impossible to run migrations on empty databases without seeding, and makes seed updates require migration versions.
- Rails "db/seeds.rb" convention (guides.rubyonrails.org) -- Rails separates `db/migrate/` (schema) from `db/seeds.rb` (reference data). This is the industry standard for relational web frameworks.
- Current project state: `migrations.py` is 3,220 lines. Lines 3034-3221 are clearly labeled `# Seeding` and contain 4 functions (`seed_predefined_triggers`, `seed_preset_mcp_servers`, `migrate_existing_paths`, `auto_register_project_root`) plus their data constants (`PREDEFINED_TRIGGERS`, `PREDEFINED_TRIGGER_IDS`, `PRESET_MCP_SERVERS`). These are called at startup in `__init__.py` (lines 98-101) independent of the migration flow.

**Confidence:** HIGH -- The separation boundary is already clearly marked in the code. The seeding functions use `get_connection()` independently (not the `conn` parameter passed to migration functions), confirming they are decoupled from the migration transaction.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Ruff | >=0.9.7 | Python linting + formatting | Already installed; replaces both flake8-style linting and Black formatting in a single Rust binary. Context7 verified. |
| pytest | >=9.0.2 | Test runner | Already in use; needed to verify all three refactorings. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-cov | >=7.0.0 | Coverage reporting | Already installed; use to verify no coverage regression after split. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| Ruff formatter | Black (current) | Black is more mature but slower; Ruff is Black-compatible and already partially configured | Use Ruff -- simpler toolchain |
| `PromptRenderer` class | Template engine (Jinja2) | Jinja2 adds dependency for simple `str.replace()` calls | Keep `str.replace()` in a class -- no new dependency needed |

**Installation:**
```bash
# No new packages needed. Remove Black from dev dependencies:
# In pyproject.toml, remove "black==26.1.0" from [project.optional-dependencies] dev
```

## Architecture Patterns

### Recommended Project Structure

After Phase 6, the affected files should look like:

```
backend/app/
├── db/
│   ├── migrations.py      # Schema migrations ONLY (3,032 lines → ~2,820 lines)
│   ├── seeds.py            # NEW: seed functions + data constants (~200 lines)
│   ├── schema.py           # Fresh schema (unchanged)
│   └── __init__.py         # Updated: re-export seed functions from seeds.py
├── services/
│   ├── execution_service.py    # Facade: delegates to helpers (~1,200 lines → ~1,100 lines)
│   ├── prompt_renderer.py      # NEW: PromptRenderer class (~80 lines)
│   └── command_builder.py      # NEW: CommandBuilder class (~70 lines)
```

### Pattern 1: Facade Delegation

**What:** `ExecutionService` remains the public API but delegates prompt rendering and command building to imported helper classes.
**When to use:** When a large service class has clearly separable stateless logic.
**Example:**
```python
# backend/app/services/prompt_renderer.py
class PromptRenderer:
    """Stateless prompt template rendering."""

    # Known placeholders for unresolved-placeholder warnings
    _KNOWN_PLACEHOLDERS = {
        "trigger_id", "bot_id", "paths", "message",
        "pr_url", "pr_number", "pr_title", "pr_author",
        "repo_url", "repo_full_name",
    }

    @staticmethod
    def render(trigger: dict, message_text: str, paths_str: str,
               event: dict = None) -> str:
        """Render a trigger's prompt_template with contextual values."""
        prompt = trigger["prompt_template"]
        prompt = prompt.replace("{trigger_id}", trigger["id"])
        prompt = prompt.replace("{bot_id}", trigger["id"])
        prompt = prompt.replace("{paths}", paths_str)
        prompt = prompt.replace("{message}", message_text)
        if event:
            if event.get("type") == "github_pr":
                for key in ("pr_url", "pr_number", "pr_title",
                            "pr_author", "repo_url", "repo_full_name"):
                    prompt = prompt.replace(
                        "{" + key + "}", str(event.get(key, ""))
                    )
        # Prepend skill_command if configured
        skill_command = trigger.get("skill_command", "")
        if skill_command and not prompt.lstrip().startswith(skill_command):
            prompt = f"{skill_command} {prompt}"
        return prompt

    @staticmethod
    def warn_unresolved(prompt: str, trigger_name: str, logger) -> None:
        """Log warning for any unresolved {placeholder} patterns."""
        import re
        remaining = re.findall(r"\{(\w+)\}", prompt)
        unknown = [p for p in remaining
                    if p not in PromptRenderer._KNOWN_PLACEHOLDERS]
        if unknown:
            logger.warning(
                "Prompt for trigger '%s' has unresolved placeholders: %s",
                trigger_name, unknown,
            )
```

```python
# backend/app/services/command_builder.py
class CommandBuilder:
    """Stateless CLI command construction for all supported backends."""

    @staticmethod
    def build(backend: str, prompt: str, allowed_paths: list = None,
              model: str = None, codex_settings: dict = None,
              allowed_tools: str = None) -> list:
        """Build CLI command list for the specified backend."""
        # ... exact logic currently in ExecutionService.build_command ...
```

```python
# In execution_service.py (facade):
from .prompt_renderer import PromptRenderer
from .command_builder import CommandBuilder

class ExecutionService:
    @staticmethod
    def build_command(backend, prompt, allowed_paths=None,
                      model=None, codex_settings=None,
                      allowed_tools=None):
        """Build CLI command. Delegates to CommandBuilder."""
        return CommandBuilder.build(
            backend, prompt, allowed_paths, model,
            codex_settings, allowed_tools
        )
```

### Pattern 2: Seed Data Module

**What:** All reference/seed data and their insert/upsert functions live in a single `seeds.py` module, separated from schema migrations.
**When to use:** When seeding logic is called at app startup but is conceptually independent of schema evolution.
**Example:**
```python
# backend/app/db/seeds.py
"""Seed data and startup seeding functions for Agented.

Separated from migrations.py so that the migration history remains
a pure schema-evolution record.
"""
from .connection import get_connection
from .ids import _get_unique_mcp_server_id, generate_trigger_id

# Predefined trigger data constants
PREDEFINED_TRIGGERS = [...]
PREDEFINED_TRIGGER_IDS = {t["id"] for t in PREDEFINED_TRIGGERS}
PREDEFINED_TRIGGER_ID = "bot-security"
PREDEFINED_TRIGGER = PREDEFINED_TRIGGERS[0]

# Preset MCP server definitions
PRESET_MCP_SERVERS = [...]

def seed_predefined_triggers():
    """Insert/update predefined triggers."""
    ...

def seed_preset_mcp_servers():
    """Insert/update preset MCP servers."""
    ...

def migrate_existing_paths():
    """Create symlinks for paths that don't have them."""
    ...

def auto_register_project_root():
    """Auto-register project root for predefined security trigger."""
    ...
```

### Anti-Patterns to Avoid

- **Moving migration functions to seeds.py:** Only seed/startup functions move. The 54 versioned `_migrate_*` functions and the `VERSIONED_MIGRATIONS` list stay in `migrations.py`. The migration functions reference `PREDEFINED_TRIGGER_ID` and `VALID_BACKENDS` -- these constants must be importable from `seeds.py` by `migrations.py`.
- **Breaking the facade contract:** Never rename or remove `ExecutionService.build_command()` or change its signature. Tests call it directly (`test_backend_detection.py::TestBuildCommand`).
- **Circular imports between seeds.py and migrations.py:** `seeds.py` should not import from `migrations.py`. If `migrations.py` needs seed constants (e.g., `PREDEFINED_TRIGGER_ID`), it should import from `seeds.py`. This reverses the current dependency direction -- plan carefully.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Python formatting | Custom format scripts | `ruff format` | Ruff is Black-compatible with 10-100x speed |
| Import sorting | Manual isort config | `ruff check --select I` | Ruff's `I` rule set replaces isort |
| Template rendering | Jinja2 or custom template engine | Simple `str.replace()` in `PromptRenderer` | The current prompt templates use `{placeholder}` syntax (not Jinja2 `{{ }}`); adding Jinja2 would be over-engineering |

**Key insight:** All three requirements are refactoring tasks, not feature additions. No new libraries are needed.

## Common Pitfalls

### Pitfall 1: Circular Import Between seeds.py and migrations.py

**What goes wrong:** After moving `PREDEFINED_TRIGGERS` and `PREDEFINED_TRIGGER_ID` to `seeds.py`, `migrations.py` still references these constants (line 383: `PREDEFINED_TRIGGER_ID` in `_migrate_to_string_ids`; line 3197 area). If `seeds.py` imports from `migrations.py` and vice versa, Python raises `ImportError`.
**Why it happens:** The seed constants and migration functions were historically in the same file.
**How to avoid:** Move constants to `seeds.py`. Have `migrations.py` import from `seeds.py`, never the reverse. Verify with `python -c "from app.db.seeds import seed_predefined_triggers"`.
**Warning signs:** `ImportError` at startup; circular import traceback.

### Pitfall 2: Ruff Format Diff Noise

**What goes wrong:** Running `ruff format .` after removing Black reformats 29 files, creating a large diff that obscures the actual configuration changes.
**Why it happens:** Ruff's formatter has minor differences from Black (e.g., magic trailing comma handling, string quote normalization).
**How to avoid:** Create the Ruff configuration commit first (change `pyproject.toml`), then run `ruff format .` in a separate commit. This keeps the config change reviewable and the formatting change mechanical.
**Warning signs:** A single commit with both config changes and 29 reformatted files.

### Pitfall 3: Forgetting to Update __init__.py Re-exports

**What goes wrong:** After moving functions from `migrations.py` to `seeds.py`, code that imports via `from app.db import seed_predefined_triggers` breaks because `app/db/__init__.py` imports from `.migrations`.
**Why it happens:** The `__init__.py` re-export chain needs updating.
**How to avoid:** Update `app/db/__init__.py` to import seed functions from `.seeds` instead of `.migrations`. Also update `app/database.py` shim if needed. Verify with `cd backend && uv run pytest`.
**Warning signs:** `ImportError: cannot import name 'seed_predefined_triggers' from 'app.db'`.

### Pitfall 4: Breaking ExecutionService Test Mocking Paths

**What goes wrong:** Tests that mock `app.services.execution_service.ExecutionService.run_trigger` or `build_command` may break if the method is moved instead of delegated.
**Why it happens:** `monkeypatch.setattr` targets the fully qualified path where the function is defined.
**How to avoid:** Keep `build_command` and `run_trigger` as methods on `ExecutionService` that delegate to the new classes. The mock paths remain `app.services.execution_service.ExecutionService.build_command` etc.
**Warning signs:** Test failures in `test_budget_integration.py`, `test_team_execution.py`, `test_agent_scheduler.py`, `test_backend_detection.py`.

### Pitfall 5: PREDEFINED_TRIGGER_ID Import Chains

**What goes wrong:** `execution_service.py` line 20 imports `PREDEFINED_TRIGGER_ID` from `..database`. After the seed extraction, this import must still resolve.
**Why it happens:** The `database.py` shim does `from app.db import *`, and `app/db/__init__.py` re-exports from migrations. If the constant moves to `seeds.py`, the re-export chain needs updating.
**How to avoid:** In `app/db/__init__.py`, change the import of `PREDEFINED_TRIGGER_ID`, `PREDEFINED_TRIGGERS`, `PREDEFINED_TRIGGER_IDS`, `PREDEFINED_TRIGGER` from `.migrations` to `.seeds`. Add backward-compat re-exports in `migrations.py` (`from .seeds import PREDEFINED_TRIGGER_ID, ...`) so that any direct imports from migrations still work.
**Warning signs:** `ImportError` in `execution_service.py` at app startup.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:** N/A (refactoring, not experimentation)

**Dependent variables:**
- Test suite pass rate: must be 100% before and after each change
- `ruff check .` exit code: must be 0 after QUAL-02
- `ruff format --check .` exit code: must be 0 after QUAL-02
- Import verification: `python -c "from app.db.seeds import seed_predefined_triggers"` exits 0

**Controlled variables:**
- No functional behavior changes
- No test call-site modifications (for QUAL-03)

**Baseline comparison:**
- Current state: `cd backend && uv run pytest` passes; `ruff check .` has 2 errors (import sorting); `ruff format --check .` has 29 files to reformat; Black is configured but co-exists with Ruff

**Ablation plan:**
1. QUAL-01 alone: verify tests pass after seed extraction
2. QUAL-02 alone: verify `ruff check . && ruff format --check .` exits 0
3. QUAL-03 alone: verify tests pass after service split

**Statistical rigor:** N/A for refactoring. Binary pass/fail verification.

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Test pass rate | Refactoring must not break tests | `uv run pytest --tb=short` | 100% pass |
| Ruff check exit code | Lint cleanliness | `uv run ruff check .` | Currently 2 errors |
| Ruff format exit code | Format cleanliness | `uv run ruff format --check .` | Currently 29 files differ |
| Import smoke test | Seed module accessible | `python -c "from app.db.seeds import ..."` | N/A (module doesn't exist yet) |
| ExecutionService line count | Complexity reduction | `wc -l execution_service.py` | 1,387 lines |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| QUAL-01: seeds.py import works | Level 1 (Sanity) | Single command: `python -c "from app.db.seeds import seed_predefined_triggers"` |
| QUAL-01: migrations.py still works | Level 1 (Sanity) | `uv run pytest tests/test_migration_path.py` |
| QUAL-02: ruff check exits 0 | Level 1 (Sanity) | `uv run ruff check .` |
| QUAL-02: ruff format exits 0 | Level 1 (Sanity) | `uv run ruff format --check .` |
| QUAL-02: pyproject.toml has no Black config | Level 1 (Sanity) | Grep for `[tool.black]` |
| QUAL-03: PromptRenderer class exists | Level 1 (Sanity) | `python -c "from app.services.prompt_renderer import PromptRenderer"` |
| QUAL-03: CommandBuilder class exists | Level 1 (Sanity) | `python -c "from app.services.command_builder import CommandBuilder"` |
| QUAL-03: All tests pass unchanged | Level 2 (Proxy) | `uv run pytest` at 100% -- no test call sites modified |
| Full suite regression | Level 2 (Proxy) | `uv run pytest && cd ../frontend && npm run test:run && npm run build` |

**Level 1 checks to always include:**
- Import smoke tests for new modules
- `ruff check .` and `ruff format --check .` exit 0
- No `[tool.black]` section in `pyproject.toml`

**Level 2 proxy metrics:**
- Full `uv run pytest` pass with zero failures
- Frontend build passes (no backend API contract changes)

**Level 3 deferred items:**
- Manual end-to-end execution test (trigger a webhook, verify prompt rendering and command building work through the facade)

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is a template with no production notes yet. The following are derived from codebase analysis:

### Known Failure Modes

- **Import chain breakage after seed extraction:** The `database.py` shim, `db/__init__.py`, and `execution_service.py` all import from the migration module. Moving constants requires updating all three import chains.
  - Prevention: Create a dependency graph of imports before moving code. Update `__init__.py` re-exports first, then move the code.
  - Detection: `uv run pytest` will fail immediately on any import error.

- **Ruff format divergence from Black:** If any CI or pre-commit hook references `black`, it will fail after Black is removed.
  - Prevention: Grep the entire repo for `black` references before removing. Update CLAUDE.md which mentions `uv run black .`.
  - Detection: CI failure or developer confusion.

### Scaling Concerns

- **At current scale:** All three changes are safe. The codebase is 240+ Python files; Ruff handles this in <1s.
- **At production scale:** No scaling concerns -- these are code organization changes, not runtime behavior changes.

### Common Implementation Traps

- **Trap:** Moving `VALID_BACKENDS` and `VALID_TRIGGER_SOURCES` to `seeds.py` when they are used by migration functions.
  - Correct approach: These constants are used by both migration and seed code. Place them in `seeds.py` (as they define valid domain values) and import them in `migrations.py`. Alternatively, if they are only used by migration functions, leave them in `migrations.py`.

- **Trap:** Adding `[tool.ruff.format]` section but leaving `[tool.black]` section, causing confusion about which tool is authoritative.
  - Correct approach: Remove `[tool.black]` entirely. Remove `black==26.1.0` from all dependency lists.

## Code Examples

Verified patterns from official sources and codebase analysis:

### Ruff pyproject.toml Configuration (Replacing Black)

```toml
# Source: Context7 /websites/astral_sh_ruff + current pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I"]
ignore = ["E501", "E402"]
fixable = ["ALL"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401", "F403"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"

# REMOVE these sections:
# [tool.black]
# line-length = 100
# target-version = ["py310"]
```

### Seed Module Structure

```python
# Source: Codebase analysis of backend/app/db/migrations.py lines 3034-3221
# backend/app/db/seeds.py

"""Seed data and startup data-population functions for Agented.

This module contains reference data constants (predefined triggers, preset
MCP servers) and the functions that insert/update them at startup. Separated
from migrations.py to keep the migration history as a pure schema record.
"""

import logging
import os
import sqlite3

import app.config as config

from .connection import get_connection
from .ids import _get_unique_mcp_server_id, generate_trigger_id

logger = logging.getLogger(__name__)

# --- Predefined trigger data ---
VALID_BACKENDS = ("claude", "opencode", "gemini", "codex")
VALID_TRIGGER_SOURCES = ("webhook", "github", "manual", "scheduled")

PREDEFINED_TRIGGERS = [
    # ... moved from migrations.py lines 28-55
]
PREDEFINED_TRIGGER_IDS = {t["id"] for t in PREDEFINED_TRIGGERS}
PREDEFINED_TRIGGER_ID = "bot-security"
PREDEFINED_TRIGGER = PREDEFINED_TRIGGERS[0]

# --- Preset MCP server data ---
PRESET_MCP_SERVERS = [
    # ... moved from migrations.py lines 2723-2851
]

# --- Predefined backend data (used by _create_migration_only_tables) ---
PREDEFINED_BACKENDS = [
    # ... moved from migrations.py lines 255-292
]


def seed_predefined_triggers():
    # ... moved from migrations.py lines 3039-3093


def seed_preset_mcp_servers():
    # ... moved from migrations.py lines 3096-3154


def migrate_existing_paths():
    # ... moved from migrations.py lines 3162-3187


def auto_register_project_root():
    # ... moved from migrations.py lines 3190-3221
```

### ExecutionService Facade Delegation

```python
# Source: Codebase analysis of backend/app/services/execution_service.py
# In run_trigger(), replace inline prompt rendering with:

from .prompt_renderer import PromptRenderer
from .command_builder import CommandBuilder

# Inside run_trigger():
paths_str = ", ".join(effective_paths) if effective_paths else "no paths configured"
prompt = PromptRenderer.render(trigger, message_text, paths_str, event)
PromptRenderer.warn_unresolved(prompt, trigger.get("name", trigger_id), logger)

# Security audit special handling stays in run_trigger (side-effect: file I/O)
if "/weekly-security-audit" in prompt:
    threat_report_path = cls.save_threat_report(trigger_id, message_text)
    prompt = prompt.replace(
        "/weekly-security-audit", f"/weekly-security-audit {threat_report_path}"
    )

backend = trigger["backend_type"]
model = trigger.get("model")
allowed_tools = trigger.get("allowed_tools")
cmd = CommandBuilder.build(backend, prompt, effective_paths, model,
                           allowed_tools=allowed_tools)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Black + flake8 + isort (3 tools) | Ruff (1 tool) | 2023-2024 | 10-100x faster, single config file |
| Black formatter | Ruff formatter | Ruff 0.1.2 (2023-11) | Drop-in compatible, maintained by Astral |
| Mixed seed/migration files | Separated seed modules | Industry standard | Cleaner migration history, independent seed updates |

**Deprecated/outdated:**
- `black` as a standalone formatter: Still maintained, but Ruff's formatter is the recommended replacement for new projects and migrations. The Ruff project is backed by Astral (formerly known as the team behind `ruff`, `uv`, `rye`).

## Open Questions

1. **Should `VALID_BACKENDS` and `VALID_TRIGGER_SOURCES` go to seeds.py or stay in migrations.py?**
   - What we know: These constants are used by migration function `_migrate_to_string_ids` (line 20 of migrations.py) and also semantically belong with seed data.
   - What's unclear: Whether any migration function directly references them beyond the import.
   - Recommendation: Move them to `seeds.py` since they define domain values. Have `migrations.py` import them from `seeds.py`. The migration functions that need them (like `_create_migration_only_tables` which seeds backends) already call `PREDEFINED_TRIGGERS` data.

2. **Should `_create_migration_only_tables` move to seeds.py?**
   - What we know: This function (lines 221-337) creates tables AND seeds backend data. It is called from `init_db()` in the fresh-database path (line 203).
   - What's unclear: It is tightly coupled to the `init_db` flow.
   - Recommendation: Keep `_create_migration_only_tables` in `migrations.py` since it creates tables (schema). Extract just the backend seeding data (`predefined_backends` list) to `seeds.py` and import it.

3. **How much integration test coverage does `run_trigger` have?**
   - What we know: `test_budget_integration.py` has 4 tests that call `run_trigger` directly with mocked subprocess. `test_team_execution.py` and `test_agent_scheduler.py` mock `run_trigger` entirely. The `TestBuildCommand` class has 7 tests for `build_command`.
   - What's unclear: There are no tests that verify prompt rendering logic end-to-end (placeholder substitution).
   - Recommendation: Add 2-3 unit tests for `PromptRenderer.render()` as part of QUAL-03. This addresses the phase constraint "assess coverage at Phase 6 planning time" -- coverage is sufficient for the split but prompt rendering tests should be added.

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/astral_sh_ruff` -- Ruff configuration, formatter setup, rule selection
- Codebase analysis: `backend/pyproject.toml`, `backend/app/db/migrations.py` (3,220 lines), `backend/app/services/execution_service.py` (1,387 lines)
- Codebase analysis: `backend/app/__init__.py` (seed function call sites), `backend/app/db/__init__.py` (re-export chain)
- Codebase analysis: `backend/tests/test_backend_detection.py` (7 `build_command` tests), `backend/tests/test_budget_integration.py` (4 `run_trigger` integration tests)

### Secondary (MEDIUM confidence)
- Fowler, M. "Refactoring" (2018) -- Extract Class pattern
- Martin, R.C. "Clean Architecture" (2017) -- Single Responsibility Principle
- Django docs: data migration / seed separation pattern
- Rails guides: db/seeds.rb convention

### Tertiary (LOW confidence)
- None -- all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Ruff already installed and partially configured; no new tools needed
- Architecture: HIGH -- Extraction targets identified by line number; pure functions with clear boundaries
- Paper recommendations: HIGH -- Industry-standard patterns (Facade, Extract Class) applied to concrete code
- Pitfalls: HIGH -- All pitfalls verified against actual import chains and test mock paths in the codebase

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable -- refactoring patterns don't expire)
