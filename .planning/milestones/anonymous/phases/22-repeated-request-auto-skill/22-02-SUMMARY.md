---
phase: 22-repeated-request-auto-skill
plan: 02
subsystem: tesserae-integration / harness-evolver
tags: [REQ-26, consistency, normalization, evolver-prompt]
requires: []
provides:
  - "_build_harness_session normalizes all 5 session kinds (no silent None for project_session/workflow/team_session)"
  - "evolver prompts declare skills writable"
affects:
  - backend/app/services/tesserae_integration.py
  - backend/app/services/harness_evolver.py
key-files:
  created:
    - backend/tests/test_build_harness_session_kinds.py
  modified:
    - backend/app/services/tesserae_integration.py
    - backend/app/services/harness_evolver.py
decisions:
  - "Reused table/column names from harness_failure_annotator fetchers (no guessing): project_sessions(log_json/summary/agent_id), workflow_executions+workflow_node_executions(output_json/error), team_executions(execution_ids JSON → execution_logs.stdout_log)"
  - "workflow/team normalizers receive pre-aggregated child rows via _nodes/_components keys to keep normalizer pure (DB I/O stays in _build_harness_session)"
  - "Evolver change is text-only: skills were already in WRITABLE_KINDS + _create_dispatch; only stale read-only/deferred prompt phrasing removed"
metrics:
  tasks: 2
  files: 3
  completed: 2026-06-13
---

# Phase 22 Plan 02: REQ-26 Consistency Fixes Summary

Closed the two REQ-26 consistency gaps: `_build_harness_session` now normalizes
all five session kinds (project_session/workflow/team_session no longer fall
through to `None`), and the evolver's `_DESIGN_GUIDE`/`_PROMPT_TEMPLATE` now tell
the LLM that skills are writable — matching the `WRITABLE_KINDS`/`_create_dispatch`
logic that already supported skill create/update.

## Tasks

1. **Three `_build_harness_session` normalizers + 5-kind test** (`f5978959cb`)
   - Added `_normalize_project_session`, `_normalize_workflow`, `_normalize_team_session`,
     mirroring `_normalize_super_agent_session`/`_normalize_trigger_execution` field shape.
   - Replaced the `else: return None` branch with explicit dispatch for the three
     kinds; `None` now returned only for genuinely-unknown kinds or missing rows.
   - `tests/test_build_harness_session_kinds.py` seeds a minimal row per kind and
     asserts a non-None HarnessSession with expected title/kind. 6/6 green
     (5 kinds + unknown-kind None).

2. **Evolver prompt strings reflect writable skills** (`ceccec48a8`)
   - Rewrote the deferred/read-only skill clauses in both prompt constants to
     state the loop MAY create/update skills (`.claude/skills/<name>/SKILL.md`).
   - Text-only — `WRITABLE_KINDS`, `_create_dispatch`, `_update_dispatch` untouched.
   - Verified via assertion: combined `_DESIGN_GUIDE+_PROMPT_TEMPLATE` contains no
     `read-only`/`deferred`.

## Deviations from Plan

None — plan executed as written. (Test seeds required parent FK rows —
`super_agents`/`workflows`/`teams` — which were added; an expected consequence
of FK constraints, not a deviation from intent.)

## Verification

- `uv run pytest tests/test_build_harness_session_kinds.py -v` → 6 passed.
- Evolver assertion (`'read-only'`/`'deferred'` absent) → OK.
- `ruff check` clean on `harness_evolver.py`; the 3 ruff findings in
  `tesserae_integration.py` (lines 43/133/728) are PRE-EXISTING (verified via
  stash — count unchanged) and outside the edited regions.

## Self-Check: PASSED

- FOUND: backend/app/services/tesserae_integration.py
- FOUND: backend/tests/test_build_harness_session_kinds.py
- FOUND: backend/app/services/harness_evolver.py
- FOUND commit f5978959cb
- FOUND commit ceccec48a8
