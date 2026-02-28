---
phase: 06-code-quality-and-maintainability
wave: all
plans_reviewed: [06-01, 06-02, 06-03]
timestamp: 2026-02-28T04:15:00Z
blockers: 1
warnings: 2
info: 4
verdict: blocker_found
---

# Code Review: Phase 6 (Code Quality and Maintainability)

## Verdict: BLOCKER FOUND

All three plans were executed and produced the expected artifacts. Plan 06-01 (seed/migration separation) and Plan 06-02 (Ruff migration) were executed cleanly. Plan 06-03 (ExecutionService Extract Class) has a behavioral regression: the `allowed_tools` parameter is silently dropped in the `CommandBuilder.build()` extraction and in the `ExecutionService.build_command()` facade delegation, diverging from the original implementation which used `allowed_tools or "Read,Glob,Grep,Bash"` to support per-trigger tool allowlists.

## Stage 1: Spec Compliance

### Plan Alignment

**Plan 06-01 (Migration/Seed Separation):**

All tasks executed as planned. Commits `d938f6d` (Task 1) and `4b3c51b` (Task 2) on the `grd/v0.1.0/06-code-quality-and-maintainability` branch correspond to the two plan tasks. The SUMMARY reports commit hashes `135ec30` and `d848c2f` which are from the worktree agent branch -- the actual branch has equivalent commits with different hashes. Artifacts verified:

- `backend/app/db/seeds.py` exists at 348 lines (above the 150-line minimum).
- `backend/app/db/migrations.py` contains zero seed functions (grep verified).
- `backend/app/db/__init__.py` imports `init_db` from `.migrations` and seed functions from `.seeds`.
- One documented deviation: removed unused `_get_unique_mcp_server_id` import from migrations.py (appropriate cleanup).

No issues found.

**Plan 06-02 (Replace Black with Ruff):**

All tasks executed as planned. Commits `735e831` (Task 1: config change) and `60b9976` (Task 2: reformat + lint fix) correctly separate config from formatting. Artifacts verified:

- `pyproject.toml` has `[tool.ruff.format]` section; no `[tool.black]` section or `black` dependency remains.
- `AGENTS.md` (which `CLAUDE.md` symlinks to) updated to reference `ruff format`.
- Plan predicted 2 lint errors and 29 files; actual was 1 lint error and 21 files -- minor discrepancy explained by prior Plan 06-01 changes resolving some formatting issues.

No issues found.

**Plan 06-03 (ExecutionService Extract Class):**

Both tasks were committed (`31adecb` Task 1, `a80208f` Task 2). The SUMMARY correctly documents two deviations:
1. `warn_unresolved` implemented as new functionality (did not exist in current codebase).
2. Line number references adapted to current file size (748 vs planned 1,387 lines).

However, the plan's core success criterion -- "the extracted code must produce identical outputs for identical inputs. No logic changes, no added features, no removed edge cases" -- is violated by the `allowed_tools` parameter being dropped. See Finding #1 below.

### Research Methodology

The RESEARCH.md references Fowler "Refactoring" (2018) Extract Class pattern and Martin "Clean Architecture" (2017) SRP. The implementation follows the recommended facade delegation pattern from RESEARCH.md correctly for `build_command` (keeping it as a thin delegate) and `run_trigger` (using `PromptRenderer.render()`). The pattern is faithfully applied, but the extraction missed preserving the `allowed_tools` behavior.

The RESEARCH.md code example for `PromptRenderer.render()` shows `render(trigger, message_text, paths_str, event)` with 4 parameters. The actual implementation has `render(trigger, trigger_id, message_text, paths_str, event)` with 5 parameters -- an appropriate deviation since `trigger_id` was needed as a separate argument (not always derivable from trigger dict).

### Known Pitfalls

**RESEARCH.md Pitfall 4 (Breaking Test Mock Paths):** Successfully avoided. The facade pattern preserves all mock paths. Tests that mock `ExecutionService.build_command` continue to work because the method still exists at the same path.

**RESEARCH.md Pitfall 1 (Circular Import):** Successfully avoided. `seeds.py` imports from `.triggers`, not from `.migrations`.

**RESEARCH.md Pitfall 2 (Ruff Format Diff Noise):** Successfully avoided. Configuration change (commit `735e831`) is separate from reformatting (commit `60b9976`).

**RESEARCH.md Pitfall 3 (Forgetting __init__.py Re-exports):** Successfully avoided. The `__init__.py` re-exports are correctly updated.

### Eval Coverage

The 06-EVAL.md defines 13 sanity checks (S1-S13) and 4 proxy metrics (P1-P4). The eval checks are well-designed and cover the structural constraints. However:

- **S13 (delegation wired):** Checks `grep -c "CommandBuilder.build\|PromptRenderer.render"` expecting 2. The actual count is correct -- but this grep check only verifies the *call exists*, not that it passes all parameters correctly. The `allowed_tools` regression would not be caught by S13.
- **P2 (TestBuildCommand):** The 7 tests in TestBuildCommand do not test the `allowed_tools` parameter, so this proxy metric would not catch the regression either.
- The EVAL.md honestly documents this blind spot in its "What this evaluation CANNOT tell us" section, noting that prompt rendering coverage is limited. The `allowed_tools` gap falls into the same category.

## Stage 2: Code Quality

### Architecture

**Consistent with existing patterns.** The new `PromptRenderer` and `CommandBuilder` classes follow the project's existing pattern of using `@staticmethod` / `@classmethod` methods on service classes. Module-level docstrings reference the refactoring pattern used. The `seeds.py` module follows the existing `backend/app/db/` package structure with proper `__init__.py` re-exports.

The facade delegation in `execution_service.py` is clean -- imports at module top, single-line delegation in `build_command`, and two-line replacement in `run_trigger`. The security audit threat-report logic correctly remains in `run_trigger` as planned (side effects cannot be in stateless helpers).

### Reproducibility

N/A -- no experimental code in this phase. All changes are deterministic refactoring.

### Documentation

Both new modules (`prompt_renderer.py`, `command_builder.py`) have module-level and class-level docstrings explaining the extraction rationale and referencing Fowler's "Refactoring" (2018). The `PromptRenderer.render()` method has comprehensive docstrings covering all five substitution steps. The `seeds.py` module docstring explains the separation rationale and references Django/Rails conventions.

The `warn_unresolved` method is documented as detecting unknown placeholders vs. known ones, which is a useful distinction.

### Deviation Documentation

**Plan 06-01:** 1 deviation documented (unused import cleanup). Matches git diff.

**Plan 06-02:** 0 deviations documented. Plan predicted 2 lint errors / 29 files; actual was 1 / 21. The SUMMARY explains this discrepancy (prior Plan 06-01 resolved some). Acceptable.

**Plan 06-03:** 2 deviations documented:
1. `warn_unresolved` as new functionality -- documented.
2. Line number adaptation -- documented.

**Undocumented:** The `allowed_tools` parameter being dropped from `CommandBuilder.build()` and the facade delegation is not documented as a deviation. The SUMMARY claims "All 906 backend tests pass with zero test file modifications" which is true, but the behavioral regression is silent because no test exercises `allowed_tools` passthrough.

The SUMMARY lists `execution_service.py` as modified, which matches the git diff. The `key-files` section in the SUMMARY frontmatter is accurate.

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| 1 | BLOCKER | 1 | Plan Alignment (06-03) | `allowed_tools` parameter dropped in `CommandBuilder.build()` and `ExecutionService.build_command()` facade -- behavioral regression |
| 2 | WARNING | 2 | Deviation Documentation (06-03) | `allowed_tools` regression undocumented in SUMMARY.md |
| 3 | WARNING | 1 | Plan Alignment (06-03) | `execution_service.py` line reduction of 51 lines (6.8%) falls short of the 60-line minimum stated in success criteria |
| 4 | INFO | 1 | Plan Alignment (06-02) | Test files reformatted by Ruff (6 files) -- purely cosmetic assertion style changes, appropriate for Plan 06-02 scope |
| 5 | INFO | 2 | Architecture | SUMMARY commit hashes (135ec30, d848c2f, 0d272c8, 51f0529, 521a8dd, 6938623) differ from branch hashes (d938f6d, 4b3c51b, 735e831, 60b9976, 31adecb, a80208f) due to worktree agent workflow -- equivalent content, not an issue |
| 6 | INFO | 1 | Eval Coverage | EVAL.md S13 grep check only verifies delegation call presence, not parameter completeness -- consider adding parameter-level checks for extracted facades |
| 7 | INFO | 2 | Documentation | `PromptRenderer.render()` signature differs from RESEARCH.md example (5 params vs 4) -- appropriate adaptation, well-documented |

## Recommendations

### Finding #1 (BLOCKER): `allowed_tools` parameter dropped

**Location:** `backend/app/services/command_builder.py` line 70 and `backend/app/services/execution_service.py` line 449.

**What happened:** The original `ExecutionService.build_command()` (visible in `git show main:backend/app/services/execution_service.py` at line 469) used `tools = allowed_tools or "Read,Glob,Grep,Bash"` for the claude backend's `--allowedTools` flag. The extracted `CommandBuilder.build()` accepts `allowed_tools` as a parameter but ignores it, hardcoding `"Read,Glob,Grep,Bash"` on line 70. Additionally, the facade delegation on line 449 calls `CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings)` without forwarding `allowed_tools`.

**Impact:** Any trigger with a custom `allowed_tools` configuration (e.g., `"bash"`) will silently have its tool allowlist ignored and default to `"Read,Glob,Grep,Bash"`. The `run_trigger` method on line 606-608 reads `allowed_tools = trigger.get("allowed_tools")` and passes it to `cls.build_command(..., allowed_tools=allowed_tools)`, but it is dropped by the facade.

**Fix (two changes required):**

1. In `backend/app/services/command_builder.py`, line 70, change:
   ```python
   "Read,Glob,Grep,Bash",
   ```
   to:
   ```python
   allowed_tools or "Read,Glob,Grep,Bash",
   ```
   Store in a local variable first:
   ```python
   tools = allowed_tools or "Read,Glob,Grep,Bash"
   ```
   and use `tools` on the `--allowedTools` line.

2. In `backend/app/services/execution_service.py`, line 449, change:
   ```python
   return CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings)
   ```
   to:
   ```python
   return CommandBuilder.build(backend, prompt, allowed_paths, model, codex_settings, allowed_tools)
   ```

### Finding #3 (WARNING): Line reduction below target

The Plan 06-03 success criteria state "execution_service.py line count reduced by at least 60 lines." The actual reduction was 51 lines (748 -> 697, as reported in the SUMMARY). This occurred because the plan was written against a 1,387-line version of the file, but the Ruff reformatting in Plan 06-02 had already condensed it to 748 lines before Plan 06-03 executed. The net reduction from the original 1,381-line baseline (on main) is 74 lines, which exceeds the 60-line target. No action required, but the SUMMARY should note this context.

---

*Reviewed: 2026-02-28*
*Reviewer: Claude (grd-code-reviewer)*
