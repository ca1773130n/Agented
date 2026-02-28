---
phase: 06-code-quality-and-maintainability
verified: 2026-02-28T05:30:00Z
status: gaps_found
score:
  level_1: 12/13 sanity checks passed
  level_2: 3/4 proxy metrics met
  level_3: 0 deferred
re_verification:
  previous_status: ~
  previous_score: ~
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps:
  - truth: "ExecutionService.build_command() delegates to CommandBuilder.build() with unchanged signature"
    status: failed
    verification_level: 1
    reason: "The facade delegation at execution_service.py:449 omits the allowed_tools kwarg. run_trigger passes allowed_tools=allowed_tools via cls.build_command() but build_command's delegation call is CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings) — allowed_tools is silently dropped. CommandBuilder.build() also accepts the parameter but never applies it in the claude branch (hardcodes 'Read,Glob,Grep,Bash' regardless)."
    quantitative:
      metric: "allowed_tools propagation"
      expected: "trigger.allowed_tools applied to --allowedTools flag in claude commands"
      actual: "allowed_tools silently dropped; --allowedTools hardcoded to 'Read,Glob,Grep,Bash'"
    artifacts:
      - path: "backend/app/services/execution_service.py"
        issue: "Line 449: CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings) — missing allowed_tools kwarg"
      - path: "backend/app/services/command_builder.py"
        issue: "Lines 60-77: claude branch hardcodes '--allowedTools Read,Glob,Grep,Bash', never uses the allowed_tools parameter"
    missing:
      - "Pass allowed_tools through the delegation: CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings, allowed_tools)"
      - "Apply allowed_tools in CommandBuilder.build claude branch: use (allowed_tools or 'Read,Glob,Grep,Bash') instead of hardcoded string"
deferred_validations: []
human_verification: []
---

# Phase 06: Code Quality and Maintainability Verification Report

**Phase Goal:** Migration seeding is separated from schema history; Ruff replaces Black as the linter/formatter; ExecutionService is split into coordinator plus stateless helpers with the public interface preserved.
**Verified:** 2026-02-28T05:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Verification Summary by Tier

### Level 1: Sanity Checks

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | `backend/app/db/seeds.py` exists | PASS | 349 lines, 14,736 bytes |
| 2 | seeds.py contains 4 seed functions | PASS | `seed_predefined_triggers`, `seed_preset_mcp_servers`, `migrate_existing_paths`, `auto_register_project_root` all found |
| 3 | seeds.py contains PRESET_MCP_SERVERS | PASS | 9 entries defined at lines 31-159 |
| 4 | seeds.py imports from `.triggers` (canonical) | PASS | Line 23: `from .triggers import PREDEFINED_TRIGGER_ID, PREDEFINED_TRIGGERS` |
| 5 | `migrations.py` has 0 seed functions | PASS | `grep -c "def seed_" migrations.py` returns 0 |
| 6 | `migrations.py` has 0 PRESET_MCP_SERVERS | PASS | `grep -c "PRESET_MCP_SERVERS" migrations.py` returns 0 |
| 7 | `from app.db.seeds import seed_predefined_triggers` exits 0 | PASS | Imports all 4 functions and PRESET_MCP_SERVERS without error |
| 8 | `from app.db import seed_predefined_triggers, init_db` exits 0 | PASS | Re-export chain via `__init__.py` intact |
| 9 | `pyproject.toml` has `[tool.ruff.format]` section | PASS | Lines 53-57: quote-style, indent-style, skip-magic-trailing-comma, line-ending all configured |
| 10 | `pyproject.toml` has no `[tool.black]` section | PASS | `grep "[tool.black]" pyproject.toml` returns empty |
| 11 | `black` not in any pyproject.toml dependency list | PASS | Only `ruff>=0.9.7` in dev deps; no black reference |
| 12 | `PromptRenderer` class exists in `prompt_renderer.py` with `render()` and `warn_unresolved()` | PASS | 106 lines; both methods verified at lines 31 and 87 |
| 13 | `CommandBuilder` class exists in `command_builder.py` with `build()` | PASS | 77 lines; method at line 15 |
| 14 | `ExecutionService.build_command()` delegates to `CommandBuilder.build()` with unchanged signature | **FAIL** | Line 449 omits `allowed_tools` from delegation call; parameter silently dropped. Original code applied `allowed_tools or "Read,Glob,Grep,Bash"` to --allowedTools flag. |
| 15 | `ExecutionService.run_trigger()` uses `PromptRenderer.render()` and `PromptRenderer.warn_unresolved()` | PASS | Lines 594-595 confirmed |
| 16 | `CLAUDE.md` references `ruff format` instead of `black` | PASS | Line 40: `uv run ruff format .`; line 109: "Python formatting: Ruff" |

**Level 1 Score:** 15/16 passed

### Level 2: Proxy Metrics

| # | Metric | Target | Achieved | Status |
|---|--------|--------|----------|--------|
| 1 | `cd backend && uv run ruff check .` exits 0 | exit 0 | exit 0, "All checks passed!" | PASS |
| 2 | `cd backend && uv run ruff format --check .` exits 0 | exit 0 | exit 0, "247 files already formatted" | PASS |
| 3 | `cd backend && uv run pytest` passes at 100% | 100% | 911/911 passed (136.78s) | PASS |
| 4 | `allowed_tools` from trigger applied to claude `--allowedTools` flag | per-trigger tool scoping | Hardcoded "Read,Glob,Grep,Bash" ignores trigger.allowed_tools | **FAIL** |

**Level 2 Score:** 3/4 met target

---

## Goal Achievement

### Observable Truths

| # | Truth | Level | Status | Evidence |
|---|-------|-------|--------|----------|
| T1 | `backend/app/db/seeds.py` exists with 4 seed functions and PRESET_MCP_SERVERS | Level 1 | PASS | 349 lines; 9 PRESET_MCP_SERVERS entries; 4 seed functions confirmed |
| T2 | `migrations.py` contains only schema migration code (no seed functions, no PRESET_MCP_SERVERS) | Level 1 | PASS | `grep -c "def seed_"` = 0; `grep -c "PRESET_MCP_SERVERS"` = 0; 2,913 lines (was 3,102) |
| T3 | `from app.db.seeds import seed_predefined_triggers` exits 0 | Level 1 | PASS | Import chain verified: seeds.py -> __init__.py -> database.py -> app factory |
| T4 | `from app.db import seed_predefined_triggers` exits 0 (re-export chain) | Level 1 | PASS | __init__.py line 423-428: `from .seeds import (...)` confirmed |
| T5 | `cd backend && uv run pytest` passes at 100% with no test modifications | Level 2 | PASS | 911/911 tests passed |
| T6 | `ruff check .` exits 0 | Level 1 | PASS | "All checks passed!" |
| T7 | `ruff format --check .` exits 0 | Level 1 | PASS | "247 files already formatted" |
| T8 | `pyproject.toml` has `[tool.ruff.format]` and no `[tool.black]` | Level 1 | PASS | Confirmed both conditions |
| T9 | `black` not listed in any pyproject.toml dependency | Level 1 | PASS | dev deps contain only ruff>=0.9.7 |
| T10 | `CLAUDE.md` references `ruff format` instead of `black` | Level 1 | PASS | Line 40 and line 109 updated |
| T11 | `PromptRenderer` in `prompt_renderer.py` with `render()` and `warn_unresolved()` | Level 1 | PASS | 106 lines; @staticmethod render(), @classmethod warn_unresolved() |
| T12 | `CommandBuilder` in `command_builder.py` with `build()` static method | Level 1 | PASS | 77 lines; @staticmethod build() |
| T13 | `ExecutionService.build_command()` delegates to `CommandBuilder.build()` with unchanged signature | Level 1 | **FAIL** | Delegation at line 449 omits `allowed_tools`; CommandBuilder.build claude branch hardcodes tool list |
| T14 | `ExecutionService.run_trigger()` uses `PromptRenderer.render()` and `PromptRenderer.warn_unresolved()` | Level 1 | PASS | Lines 594-595 confirmed |
| T15 | All existing test mock paths still resolve correctly | Level 2 | PASS | 911/911 tests pass with no test file modifications |

### Required Artifacts

| Artifact | Expected | Exists | Lines | Min Lines | Status |
|----------|----------|--------|-------|-----------|--------|
| `backend/app/db/seeds.py` | Seed functions and PRESET_MCP_SERVERS | Yes | 349 | 150 | PASS |
| `backend/app/services/prompt_renderer.py` | Stateless PromptRenderer class | Yes | 106 | 50 | PASS |
| `backend/app/services/command_builder.py` | Stateless CommandBuilder class | Yes | 77 | 40 | PASS |
| `backend/pyproject.toml` | Ruff-only configuration | Yes | 65 | — | PASS (contains `[tool.ruff.format]`) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `backend/app/db/__init__.py` | `backend/app/db/seeds.py` | `from .seeds import` | WIRED | Lines 423-428: imports all 4 seed functions |
| `backend/app/db/seeds.py` | `backend/app/db/triggers.py` | `from .triggers import PREDEFINED_TRIGGER` | WIRED | Line 23: `from .triggers import PREDEFINED_TRIGGER_ID, PREDEFINED_TRIGGERS` |
| `backend/app/__init__.py` | `backend/app/db/__init__.py` | seed function imports at startup | WIRED | Lines 159-170: imports and calls all 4 seed functions |
| `backend/app/services/execution_service.py` | `backend/app/services/prompt_renderer.py` | `from .prompt_renderer import PromptRenderer` | WIRED | Line 36: import confirmed; lines 594-595: used in run_trigger |
| `backend/app/services/execution_service.py` | `backend/app/services/command_builder.py` | `from .command_builder import CommandBuilder` | WIRED | Line 32: import confirmed; line 449: delegation in build_command |
| `backend/tests/test_backend_detection.py` | `backend/app/services/execution_service.py` | `ExecutionService.build_command` call | WIRED | Test mock path resolves; 911 tests pass |

---

## Gap Detail: allowed_tools Regression in CommandBuilder

### Root Cause

The plan specified: "ExecutionService.build_command() delegates to CommandBuilder.build() — the method signature is unchanged." The delegation is implemented, but the `allowed_tools` parameter is silently dropped.

**Before refactoring** (commit 24fa39b, original `execution_service.py` lines 441-469):
```python
def build_command(cls, backend, prompt, allowed_paths=None, model=None, codex_settings=None, allowed_tools=None):
    ...
    else:  # claude default
        cmd = ["claude", "-p", prompt, "--verbose", "--output-format", "json",
               "--allowedTools", tools]  # where tools = allowed_tools or "Read,Glob,Grep,Bash"
```

**After refactoring** (current state):
```python
# execution_service.py line 449:
return CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings)
# ↑ allowed_tools NOT passed

# command_builder.py lines 62-71 (claude branch):
cmd = ["claude", "-p", prompt, "--verbose", "--output-format", "json",
       "--allowedTools", "Read,Glob,Grep,Bash"]  # hardcoded, allowed_tools param ignored
```

### Impact

Any trigger that has a non-default `allowed_tools` value in the database (set via trigger service or harness loader) will now silently use the default tool list instead of its configured tools. The per-trigger tool scoping feature (QUAL migration v49 `trigger_allowed_tools`) is broken at the execution layer.

### Fix Required

**In `execution_service.py` line 449:**
```python
return CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings, allowed_tools)
```

**In `command_builder.py` claude branch (lines 62-71):**
```python
cmd = [
    "claude", "-p", prompt, "--verbose", "--output-format", "json",
    "--allowedTools", allowed_tools or "Read,Glob,Grep,Bash",
]
```

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `backend/app/services/command_builder.py` | `allowed_tools` parameter accepted but never used | Medium | Per-trigger tool scoping silently broken |
| `backend/app/services/execution_service.py` | `build_command` accepts `allowed_tools` kwarg but drops it before delegation | Medium | Same as above |

---

## Requirements Coverage

| Requirement | Truth | Status |
|-------------|-------|--------|
| QUAL-01: Migration seeding separated from schema history | T1, T2, T3, T4 | PASS |
| QUAL-02: Ruff replaces Black as linter/formatter | T6, T7, T8, T9, T10 | PASS |
| QUAL-03: ExecutionService split with public interface preserved | T11, T12, T13, T14, T15 | **PARTIAL** — split done, but allowed_tools interface not fully preserved |

---

## Summary

Phase 06 achieved 2 of its 3 QUAL requirements completely:

**QUAL-01 (Seed extraction):** Fully complete. `backend/app/db/seeds.py` (349 lines) contains all 4 seed functions and 9 PRESET_MCP_SERVERS entries. `migrations.py` is clean (2,913 lines, no seed code). Import chain verified end-to-end.

**QUAL-02 (Ruff migration):** Fully complete. `ruff check .` and `ruff format --check .` both exit 0 across 247 Python files. `[tool.black]` removed, `[tool.ruff.format]` configured, CLAUDE.md updated.

**QUAL-03 (ExecutionService split):** Structurally complete but has one functional regression. `PromptRenderer` and `CommandBuilder` are properly extracted and wired via facade. However, the `allowed_tools` parameter is silently dropped in the delegation chain — `build_command` does not pass it to `CommandBuilder.build`, and `CommandBuilder.build`'s claude branch hardcodes `"Read,Glob,Grep,Bash"` instead of using the parameter. This breaks per-trigger tool scoping for any trigger with a custom `allowed_tools` value.

All 911 tests pass because no existing test exercises a non-default `allowed_tools` value in the command-building path.

---

_Verified: 2026-02-28T05:30:00Z_
_Verifier: Claude (grd-verifier)_
_Verification levels applied: Level 1 (sanity), Level 2 (proxy)_
