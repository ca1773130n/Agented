---
phase: 21-one-click-team-harness-setup
plan: 06
subsystem: team-harness-setup
tags: [forge-materialization, context-renderers, compile-smoke, idempotency]
requires: ["21-02"]
provides: ["step-f-materialize-compile", "4-backend-compile-smoke"]
affects: ["backend/app/services/team_harness_setup_service.py"]
tech-stack:
  added: []
  patterns: ["materialize_primitives(project-dict)", "renderer_for() over private _REGISTRY", "renderer.apply() compile smoke", "golden-file tmp_path test"]
key-files:
  created: []
  modified:
    - backend/app/services/team_harness_setup_service.py
    - backend/tests/test_team_harness_setup_service.py
decisions:
  - "Used renderer.apply(cmd, env, bundle, session_id) — the actual public Protocol method — not the plan's prose reference to .render(); render does not exist on the Renderer Protocol."
  - "Default materialize kinds = [rule, hook, command, mcp_server, skill, subagent], mirroring forge_create_service's kind set plus subagent."
  - "Compile smoke = clean renderer.apply() return with non-empty cmd; renderers may legitimately no-op an empty bundle, so non-empty mutation is not required."
metrics:
  tasks: 2
  duration: ~15m
  completed: 2026-06-13
---

# Phase 21 Plan 06: Materialize + Compile Smoke Summary

Step (f) materializes the project's bound forge primitives into `<local_path>/.claude` via `materialize_primitives(project_dict, kinds, workspace)` and runs a per-backend compile smoke — `renderer_for(b).apply(...)` for claude/codex/gemini/opencode — proving every backend renderer accepts the materialized projection without raising.

## What Was Built

- **`_step_materialize_compile`** (replaces the placeholder): resolves the project DICT (required by the materializer signature), calls `materialize_primitives` over kinds `[rule, hook, command, mcp_server, skill, subagent]`, then iterates the four backends calling the PUBLIC `renderer_for(backend).apply(cmd, env, ContextBundle(), session_id)`. All clean → `StepResult ok`; any raise / missing renderer / emptied cmd → `StepResult failed` naming the backend (retryable, since the orchestrator records the failed row and stops). The binding into `_STEP_FUNCS["materialize_compile"]` was already present (mapped to the real function name) — replacing the body bound it automatically.
- **No-destructive-delete invariant** is satisfied entirely by the materializer's built-in `_NEVER_DELETE` guard (manifest / `.claude/settings.json` / `.claude/mcp.json`); step f issues no manual deletes.
- **Tests** (`renderer_compile` keyword): `test_step_f_renderer_compile_all_backends` (golden-file `tmp_path` pattern from `test_forge_materialization.py`) — materialize writes `.claude` + manifest + `commands/deploy.md`, all 4 renderers accept it, and a re-run is idempotent and preserves `_NEVER_DELETE` files. `test_step_f_compile_failure_names_backend` — a renderer whose `apply` raises yields a `failed` StepResult naming the backend.

## Deviations from Plan

**1. [Rule 1 - Bug avoidance] Renderer method is `apply`, not `render`.** The plan prose repeatedly says `renderer.render(...)`, but the `Renderer` Protocol (`context_renderers/base.py`) defines `apply(cmd, env, bundle, session_id)`. Referencing `.render` would raise `AttributeError` on every backend. Implemented against the real `apply` method. No structural change — this is the same compile-smoke semantics the plan intended.

## Experiment Results

### Results (EVAL P4)

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| 4 renderers accept materialized projection without raising | all 4 clean | claude/codex/gemini/opencode all clean | PASS |
| re-materialize preserves _NEVER_DELETE (P1/P2) | preserved | manifest persists across re-run | PASS |
| failed backend named in StepResult | named | "gemini" in detail | PASS |

`pytest tests/test_team_harness_setup_service.py -k "renderer_compile"` → 2 passed. Full file → 20 passed.

## Self-Check: PASSED
