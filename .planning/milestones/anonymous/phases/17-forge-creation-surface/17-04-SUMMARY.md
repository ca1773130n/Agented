---
phase: 17-forge-creation-surface
plan: 04
subsystem: forge / context-compilation
tags: [subagent, materialization, renderers, 4-backend-parity]
requires: ["17-02 subagents table + _get_asset dispatch + write-branch TODO"]
provides:
  - "subagent materialization → .claude/agents/<safe>.md (byte-stable, manifest-tracked)"
  - "ContextBundle.subagents + agents/ overlay file"
  - "4-backend subagent renderer projection (claude native; codex/gemini/opencode prompt-prefix)"
affects:
  - backend/app/services/forge_materialization_service.py
  - backend/app/services/context_compiler_service.py
  - backend/app/services/context_renderers/{base,claude,codex,gemini,opencode}.py
tech-stack:
  patterns:
    - "claude vs non-claude asymmetry: native agents/ discovery vs degrade-path prompt block"
    - "per-asset file reconciled by _finalize_manifest (not in _NEVER_DELETE)"
key-files:
  modified:
    - backend/app/services/forge_materialization_service.py
    - backend/app/services/context_compiler_service.py
    - backend/app/services/context_renderers/base.py
    - backend/app/services/context_renderers/claude.py
    - backend/app/services/context_renderers/codex.py
    - backend/app/services/context_renderers/gemini.py
    - backend/app/services/context_renderers/opencode.py
    - backend/tests/test_forge_materialization.py
    - backend/tests/test_prompt_renderer.py
    - backend/tests/services/test_context_compiler_service.py
decisions:
  - "Sub-agent body inlined into prompt only for codex/gemini/opencode; claude relies on overlay agents/<name>.md native discovery to avoid duplication"
  - "Compiler writes agents/<safe>.md into bundle.overlay_files so apply_forge_bundle materializes it for claude with no extra renderer logic"
metrics:
  duration: ~25m
  completed: 2026-06-13
  tasks: 3
  files: 10
---

# Phase 17 Plan 04: Subagent Materialization + 4-Backend Rendering Summary

Bound sub-agents now materialize to a byte-stable `.claude/agents/<name>.md` and project across all four backends — claude via native `agents/` discovery, codex/gemini/opencode via a named prompt-prefix degrade block.

## What was built

1. **Materialization write branch** (`materialize_primitives`): the `subagent` kind writes `.claude/agents/<safe>.md` = frontmatter (`name`, `description`, `agented-kind`/`agented-asset-id`/`agented-source`) + body, appends a `WrittenFile`, and the existing `_finalize_manifest` reconciles the `subagent` bucket like commands/rules. Resolved the 17-02 TODO in `_get_asset`.
2. **ContextBundle.subagents** + compiler resolution: `compile()` resolves bound sub-agents via `get_subagent`, appends `{name, body}` to `bundle.subagents`, and mirrors the body into `overlay_files["agents/<safe>.md"]` for claude's native discovery. Wired into `is_empty`, `to_dict`, `from_dict`, `to_preview_dict`.
3. **4-backend renderer projection**: `base.subagent_prompt_block` + `base.prefix_system_text` shared helpers. codex/opencode splice a `=== Sub-agents ===` named block into the trailing prompt arg; gemini splices above its `-p` arg; claude explicitly does NOT inline the body (commented asymmetry per the house rule).

## Deviations from Plan

None — plan executed as written. (The plan's `test_prompt_renderer.py` already existed for the unrelated trigger `PromptRenderer`; the 4-backend renderer goldens were added as a new `TestSubagentRendererProjection` class in that same file per the plan's file list.)

## Experiment Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| 4-backend subagent renderer golden parity | not renderable | all 4 project | claude+codex+gemini+opencode | PASS |
| byte-stable .claude/agents materialization | TODO | byte-identical 2nd run | byte-identical, no manifest churn | PASS |
| subagent in ContextBundle | absent | present | bundle.subagents + overlay agents/ | PASS |

## Verification

- `cd backend && uv run pytest tests/test_forge_materialization.py tests/test_prompt_renderer.py tests/services/test_context_compiler_service.py -q` → **58 passed**.
- `ruff check` on materialization service + renderers + compiler → clean.

## Self-Check: PASSED

- Commits: a7a9b01c8d, 85f717e6f4, fc750a76a5 — all FOUND.
- All 4 renderers reference subagent projection (claude/codex/gemini/opencode + base).
- `.claude/agents/<name>.md` write branch + manifest bucket confirmed by golden test.
