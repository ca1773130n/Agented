---
phase: 19-grd-default-driver
plan: 03
subsystem: backend/sketch-execution + grd-routes
tags: [cwd-resolution, backend-derivation, req-12, anti-regression]
requires: []
provides:
  - "backend/app/services/sketch_execution_service.py:execute_delegate (cwd-resolved)"
  - "backend/app/services/sketch_execution_service.py:_scan_mentions_and_notify (cwd-resolved)"
  - "backend/app_litestar/routes/grd_routes.py:project_chat (cwd-resolved, backend-derived)"
affects:
  - "backend/app/services/streaming_helper.py:run_streaming_response (cwd consumer)"
tech-stack:
  patterns:
    - "Inline resolve_working_directory(project_id) with try/except ValueError -> warn + None fallback"
    - "Backend derived from SuperAgent.backend_type; None passed through to stream/runner default"
key-files:
  created:
    - backend/tests/test_sketch_execution.py
  modified:
    - backend/app/services/sketch_execution_service.py
    - backend/app_litestar/routes/grd_routes.py
decisions:
  - "Inlined resolve_working_directory at each site (vs shared helper) so both call sites unambiguously reference the resolver and degrade independently"
  - "project_chat backend = SA.backend_type or None; None flows to should_route_via_cli_agent (filters non-runnable) and stream_llm_response (own default) — no backend literal remains"
metrics:
  duration: ~22min
  completed: 2026-06-13
  tasks: 3
  files: 3
---

# Phase 19 Plan 03: cwd/backend Fixes for Delegate / Mention / Project-Chat Turns Summary

Resolved the project workspace cwd at the three `cwd=None` sites
(`execute_delegate`, `_scan_mentions_and_notify`, `project_chat`) and derived
the backend from the SuperAgent's `backend_type` in `project_chat`, removing the
forbidden `backend='claude'` hardcode — delegated, mention-triggered, and
project-chat turns now run in the project clone with the correct backend.

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Resolve cwd in execute_delegate + _scan_mentions_and_notify | 2634ffc0f4 | sketch_execution_service.py |
| 2 | Fix project_chat cwd + backend hardcode | 4c6192ecb4 | grd_routes.py |
| 3 | Delegation cwd + backend-derivation tests | ed5fe8b338, e730e80042 | tests/test_sketch_execution.py |

## What Changed

- **execute_delegate / _scan_mentions_and_notify** (`sketch_execution_service.py`):
  Each now looks up the sketch's `project_id` and calls
  `ProjectWorkspaceService.resolve_working_directory(project_id)`, passing the
  result as `cwd` (and `chat_mode="work"` when a cwd resolves) into
  `run_streaming_response`. `ValueError` is caught, logged as a warning, and
  degrades to `cwd=None` (prior behavior) rather than crashing the turn.
- **project_chat** (`grd_routes.py`): Derives `backend` from the manager
  SuperAgent's `backend_type` (falling back to `None`, never `"claude"`),
  resolves the workspace cwd once (ValueError → warn + None), and forwards both
  through the closure to `stream_via_cli_agent` / `stream_llm_response` and the
  `finish` delta. The literal `"claude"` no longer appears anywhere in the
  function (REQ-12 anti-regression). `should_route_via_cli_agent` already
  filters a `None` backend (not in `_CLI_RUNNABLE_BACKENDS`), so the CLI-agent
  branch is only reachable with a concrete backend.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `project_chat` "finish" delta still emitted `backend: "claude"`**
- **Found during:** Task 2
- **Issue:** Plan named the two stream launch sites (~597, ~603) but the
  `push_delta(..., "finish", {"backend": "claude"})` at ~612 was a third claude
  literal that would fail the no-claude-literal verify and mislead the frontend
  about which backend ran.
- **Fix:** Changed it to `_backend` (the SA-derived value).
- **Files modified:** backend/app_litestar/routes/grd_routes.py
- **Commit:** 4c6192ecb4

### Implementation notes (not deviations)

- The plan's Task 1 verify (`src.count('resolve_working_directory') >= 2`) drove
  the decision to inline the resolver at each site rather than centralize in one
  helper (a shared helper would yield a single literal occurrence). Both sites
  degrade independently, which is also clearer.
- Pre-existing lint in `grd_routes.py` (unsorted import block + unused
  `datetime` import) was confirmed present on the base commit (HEAD~3) and left
  untouched — out of scope for this plan.

## Verification

- **Level 1 (Sanity):** `sketch_execution_service` source contains
  `resolve_working_directory` ≥2× (PASS); `project_chat` source contains
  `resolve_working_directory` and no `claude` literal (PASS).
- **Level 2 (Proxy):** `tests/test_sketch_execution.py` — 4/4 green:
  - `execute_delegate` forwards resolved cwd `/clones/proj-x`.
  - `execute_delegate` degrades to `cwd=None` on `ValueError` (no raise).
  - `_scan_mentions_and_notify` forwards resolved cwd.
  - `project_chat` forwards backend `codex` (not `claude`) and resolved cwd.
- **Regression:** `test_sketch_session_project_id.py` + `test_cli_agent_runner.py`
  — 55/55 green.
- **Lint:** ruff clean on all three changed/created files (pre-existing
  grd_routes import-block warnings excluded).

## Self-Check: PASSED

- Files: all 3 FOUND.
- Commits: 2634ffc0f4, 4c6192ecb4, ed5fe8b338, e730e80042 all in `git log`.
