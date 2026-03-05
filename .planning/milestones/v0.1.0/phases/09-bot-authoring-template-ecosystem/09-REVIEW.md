---
phase: 09-bot-authoring-template-ecosystem
wave: "all"
plans_reviewed: [09-01, 09-02, 09-03, 09-04]
timestamp: 2026-03-05T10:30:00Z
blockers: 0
warnings: 3
info: 4
verdict: warnings_only
---

# Code Review: Phase 09 — Bot Authoring & Template Ecosystem

## Verdict: WARNINGS ONLY

All four plans executed successfully with 8 feature commits merged to main. The implementation faithfully follows the plan specifications and research recommendations. Three warnings identified: a schedule field mapping gap in template deploy, migration number deviation from plan, and a minor test gap. No blockers.

## Stage 1: Spec Compliance

### Plan Alignment

**09-01 (Bot Template Marketplace & NL Bot Creator Backend):** Both tasks complete. 5 curated templates seeded with correct slugs (pr-reviewer, dependency-updater, security-scanner, changelog-generator, test-writer). Deploy endpoint uses `add_trigger()` directly as specified (not TriggerService). TriggerGenerationService extends BaseGenerationService with `_gather_context()`, `_build_prompt()`, `_validate()`, and adds `_extract_progress()` for SSE progress reporting. SSE endpoint at `POST /admin/triggers/generate/stream`. Commits: 4d2e2c2, 94bcb8b.

**09-02 (Prompt Snippets, Version History, Preview):** Both tasks complete. `prompt_snippets` table with CRUD, `SnippetService.resolve_snippets()` with MAX_DEPTH=5 cycle detection, integration into `PromptRenderer.render()` as first step (confirmed at line 65-66 of prompt_renderer.py). Version history enhanced with `author` and `diff_text` columns. Rollback endpoint restores `new_template` from target version. `preview-prompt-full` endpoint returns rendered prompt + CLI command with no subprocess invocation (confirmed by grep and mock test). Commits: 9dc4531, 16eb120.

**09-03 (Frontend — Marketplace, NL Creator, Snippet Library):** Both tasks complete. API client modules for bot-templates and prompt-snippets with correct TypeScript types. BotTemplateMarketplace.vue with 3-column grid, deploy per card, NL creator with SSE via fetch+ReadableStream. PromptSnippetLibrary.vue with full CRUD and teleport modals. Routes registered at `/bot-templates` and `/prompt-snippets`. Sidebar nav links added. Commits: 2fff1bd, 302bd87.

**09-04 (Version History UI, Webhook Console, Backend Tests):** Both tasks complete. PromptVersionHistory.vue with colored diff view and rollback. WebhookTestConsole.vue with JSON validation and dry-run preview. Both integrated into GenericTriggerDashboard via collapsible tool tabs. 27 backend tests across 3 files (6 template + 10 snippet + 11 version history). Bug fix in `get_prompt_template_history` ordering (added `id DESC` secondary sort). Commits: 49d6ec6, 83de6ce.

No plan tasks were left unexecuted.

### Research Methodology

Implementation follows all five research recommendations:

1. **Immutable versioning (Rec 1):** `log_prompt_template_change()` stores old/new templates, author, timestamp, and `difflib.unified_diff` output. History entries are never mutated.
2. **{{double_braces}} snippet syntax (Rec 2):** Snippet resolution uses `re.sub(r"\{\{(\w[\w\-]*)\}\}", ...)` and runs before `{placeholder}` substitution in `PromptRenderer.render()`.
3. **In-DB curated templates (Rec 3):** Templates stored in `bot_templates` table, seeded at startup. No Git-based marketplace (anti-pattern avoided).
4. **BaseGenerationService extension (Rec 4):** `TriggerGenerationService` follows the exact subclass pattern of 5 existing generation services. No LiteLLM or direct API calls.
5. **Expanded preview (Rec 5):** `preview_prompt_full()` uses `PromptRenderer.render()` + `ExecutionService.build_command()` without subprocess.

No contradictions with referenced research.

### Known Pitfalls

All five documented pitfalls from 09-RESEARCH.md are addressed:

- **Pitfall 1 (Circular snippets):** MAX_DEPTH=5 + visited set. Tested in `test_resolve_snippets_circular`.
- **Pitfall 2 (Duplicate deploy names):** Counter suffix logic in `deploy_template()`. Tested in `test_deploy_same_template_twice_creates_unique_name`.
- **Pitfall 3 (Snippet update propagation):** Snippets resolved at execution time (no caching). Deferred to DEFER-09-03.
- **Pitfall 4 (Preview spawning processes):** Verified via grep and `test_preview_prompt_full_does_not_spawn_process` mock test.
- **Pitfall 5 (Unbounded history):** Default LIMIT 50 on `get_prompt_template_history()` queries.

### Eval Coverage

09-EVAL.md defines 12 sanity checks, 8 proxy metrics, 3 ablation conditions, and 4 deferred validations. The implementation produces all artifacts required for eval execution:

- Test files exist at the expected paths (`test_bot_templates.py`, `test_prompt_snippets.py`, `test_prompt_version_history.py`)
- All sanity check commands reference correct module paths
- Proxy metrics are computable from the current implementation
- Deferred validations properly scoped to phase-09-e2e

No eval coverage gaps.

### Context Decision Compliance

No CONTEXT.md file exists for this phase. No locked decisions to verify.

## Stage 2: Code Quality

### Architecture

All new code follows established project patterns:

- **Routes:** `APIBlueprint` with `abp_tags`, `@require_role` decorator, Pydantic path/body models. Follows the exact pattern of existing routes.
- **Database:** Raw SQLite with `get_connection()` context manager. CRUD functions in `db/` modules. ID generation with entity-specific prefixes (`tpl-`, `snip-`).
- **Models:** Pydantic v2 `BaseModel` for request/response validation.
- **Services:** `TriggerGenerationService` extends `BaseGenerationService` identically to 5 existing services. `SnippetService` is a standalone utility class (classmethod pattern).
- **Frontend:** Vue 3 Composition API with `ref`, `onMounted`, `inject('showToast')`. TypeScript types in `types.ts`, API clients as plain objects with `apiFetch`. SSE via fetch+ReadableStream (correct for POST body requirement).

No conflicting architectural patterns introduced.

### Reproducibility

N/A -- no experimental code. This is feature development, not ML experimentation.

### Documentation

- `SnippetService` has clear docstrings explaining resolution behavior, cycle detection, and missing snippet handling.
- `TriggerGenerationService` methods are documented.
- `deploy_template()` has a clear docstring.
- Template configs include descriptive prompt_templates that serve as self-documentation.

Paper references in 09-RESEARCH.md are not duplicated in code comments, which is acceptable for engineering features (not algorithm implementations).

### Deviation Documentation

Three deviations reported across all plans:

1. **09-02: Migration numbering (v70/v71 instead of v58/v59)** -- Documented in 09-02-SUMMARY.md. Auto-fixed, no behavioral impact. Correctly handled -- migration numbers must be sequential with existing migrations.

2. **09-03: Vue template interpolation collision with {{}}** -- Documented in 09-03-SUMMARY.md. Created `snippetRef()` helper function. Legitimate bug fix during implementation.

3. **09-04: Fixed get_prompt_template_history ordering** -- Documented in 09-04-SUMMARY.md. Added `id DESC` secondary sort for deterministic ordering. Genuine bug fix discovered during testing.

All deviations are properly documented with rationale. No undocumented file modifications found.

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| 1 | WARNING | 2 | Architecture | `deploy_template()` does not pass `schedule_value` to `add_trigger()`; Dependency Updater template would deploy without schedule config |
| 2 | WARNING | 1 | Plan Alignment | Migration numbers changed from plan-specified v57/v58/v59 to actual v69/v70/v71; documented but indicates plan was written without checking current migration state |
| 3 | WARNING | 2 | Code Quality | `deploy_template()` does not pass `schedule_time`, `schedule_day`, or `schedule_timezone` from template config to `add_trigger()`, only `schedule_type` is mapped |
| 4 | INFO | 1 | Plan Alignment | 09-02 plan specified `get_trigger_by_name()` for deploy uniqueness but actual implementation correctly uses the same function |
| 5 | INFO | 2 | Architecture | Collapsible tool tabs pattern in GenericTriggerDashboard is a positive UX improvement over the plan's suggestion of permanent tabs |
| 6 | INFO | 1 | Deviations | All 3 deviations are well-documented with clear rationale and minimal impact |
| 7 | INFO | 2 | Code Quality | `SnippetService.resolve_snippets()` uses `visited | {name}` (set copy) instead of mutating the visited set, which correctly handles sibling snippet references independently |

## Recommendations

**WARNING #1 and #3 (Schedule field mapping in deploy_template):**
The `deploy_template()` function passes `schedule_type` from the template config but omits `schedule_value`/`schedule_time`/`schedule_day`. The Dependency Updater template config contains `"schedule_value": "monday"` and `"schedule_type": "weekly"`, but `add_trigger()` expects `schedule_time` and `schedule_day` parameters (not `schedule_value`). This means deploying the Dependency Updater template would create a trigger with `schedule_type="weekly"` but no day configured. Fix by mapping `schedule_value` to the appropriate `add_trigger()` parameters in `deploy_template()`, or restructure the template config to use the exact parameter names that `add_trigger()` expects.

**WARNING #2 (Migration numbering):**
No action needed -- the execution correctly adjusted to the actual migration sequence. For future plans, the planner should check the current highest migration number before specifying migration versions in plan files. This is an informational finding about plan quality, not a code issue.

