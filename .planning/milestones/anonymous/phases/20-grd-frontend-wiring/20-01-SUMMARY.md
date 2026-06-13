---
phase: 20-grd-frontend-wiring
plan: 01
subsystem: backend/grd-research
tags: [grd, research, autoresearch, execution-handler, litestar-routes, REQ-14]
requires:
  - GrdChatSessionHandler (19-04) — pattern mirrored
  - ProjectWorkspaceService.resolve_working_directory
  - ProjectSessionManager.create_session (stream_json PSM session)
  - generic /sessions/{id}/output SSE route (streaming reuse)
provides:
  - GrdResearchSessionHandler (HANDLER_REGISTRY['grd_research'])
  - GrdCliService.research_status / list_threads / read_thread
  - 5 /api/projects/{id}/research/* routes
affects:
  - backend/app/services/execution_type_handler.py
  - backend/app/services/grd_cli_service.py
  - backend/app_litestar/routes/grd_routes.py
tech-stack:
  added: []
  patterns: [json.dumps-prompt-framing, on-disk-frontmatter-read, generic-sse-reuse]
key-files:
  created:
    - backend/tests/test_grd_research_handler.py
    - backend/tests/test_grd_research_routes.py
  modified:
    - backend/app/services/execution_type_handler.py
    - backend/app/services/grd_cli_service.py
    - backend/app_litestar/routes/grd_routes.py
decisions:
  - "Resume uses thread_id (no question required); prompt = /grd:research resume <json.dumps(thread_id)>"
  - "list_threads/read_thread read disk directly (THREAD/HYPOTHESES/FINDING) — no CLI round-trip; no gd research report/portfolio invented"
  - "research routes reuse generic /sessions/{id}/output SSE — no research-specific bridge"
metrics:
  duration: ~14min
  completed: 2026-06-13
---

# Phase 20 Plan 01: GRD Research Backend Slice Summary

GrdResearchSessionHandler (registered as `grd_research`) plus five
`/api/projects/{id}/research/*` routes make the `gd research` autoresearch
loop fully reachable from the backend with SSE streaming — the only net-new
server code in phase 20. The proven `grd_chat` path is untouched.

## What shipped

### Handler — `execution_type_handler.py`
`GrdResearchSessionHandler` mirrors `GrdChatSessionHandler` verbatim:
- `start(session_config)` resolves cwd via
  `ProjectWorkspaceService.resolve_working_directory(project_id)` (raises
  `ValueError` when no clone — preserved), spawns
  `["claude","-p","--output-format","stream-json","--verbose", prompt]`
  through `ProjectSessionManager.create_session(... execution_type="grd_research",
  stream_json=True, use_pty=False, forge_bundle=..., super_agent_id=...)`.
- **Prompt framing uses `json.dumps`** (19-04 prompt-injection hardening) —
  `/grd:research <json.dumps(question)>`, or
  `/grd:research resume <json.dumps(thread_id)>` for a resume.
- Optional knobs appended to the prompt tail only when provided:
  `--max-iterations N`, `--no-gates`.
- `monitor`/`stop`/`get_output` delegate to PSM identically to grd_chat;
  `stop` stops the PSM session (no orphaned subprocess on abort).
- Registered: `HANDLER_REGISTRY["grd_research"] = GrdResearchSessionHandler()`.

### CLI helpers — `grd_cli_service.py`
Read-only / status surfaces (NOT the long loop):
- `research_status(project_path, thread_id=None)` → `run_gd_json(cwd,
  "research", "status", [thread_id])`; `{"error": ...}` when `gd` unavailable.
- `list_threads(project_path)` → on-disk read of
  `.planning/research/threads/*/THREAD.md` frontmatter (id/question/status/
  iteration/max_iterations); **returns `[]` when the dir is missing** (it does
  not exist until first run). Tiny `_read_frontmatter` line-parser coerces
  `iteration`/`max_iterations` to int.
- `read_thread(project_path, thread_id)` → None-safe bundle of THREAD.md +
  HYPOTHESES.md + FINDING.md (each `None` when absent).
- No `gd research report`/`portfolio` invented — report = FINDING.md on disk,
  portfolio = the thread list.

### Routes — `grd_routes.py` (contracts 20-02 consumes)
| Method | Path | Returns |
|--------|------|---------|
| POST | `/{project_id}/research/start` (body: question, max_iterations?, no_gates?) | `{"session_id": ...}` |
| POST | `/{project_id}/research/{thread_id}/resume` (body: max_iterations?, no_gates?) | `{"session_id": ...}` |
| GET | `/{project_id}/research/threads` | `{"threads": [...]}` |
| GET | `/{project_id}/research/threads/{thread_id}` | `{id, thread, hypotheses, finding}` (None-safe) |
| GET | `/{project_id}/research/status?thread_id=` | `gd research status` passthrough |

Streaming reuses the generic `/sessions/{session_id}/output` SSE route — no
research-specific bridge.

## Deviations from Plan

None — plan executed as written. (One trivial mid-write cleanup of a no-op
test assertion before any commit; not a behavioral deviation.)

## Experiment Results

### Parameters
| Parameter | Value |
|-----------|-------|
| execution_type | grd_research |
| prompt_framing | json.dumps (19-04 hardening) |
| streaming | generic /sessions/{id}/output SSE |
| verification_level | proxy |

### Results
| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| handler+route tests pass | grd_chat green | 0 fail / 0 err | 27 passed (19 new + 8 chat regression) | PASS |
| ruff format --check (3 files) | clean | clean | clean | PASS |
| handler import smoke (S3) | n/a | OK: GrdResearchSessionHandler | OK | PASS |

### Analysis
Both new test files green; grd_chat handler regression green. The empty-dir
`[]` case and frontmatter-present parse case are both covered, as is the
None-safe thread bundle. Level 3 (live `gd research` SSE through PSM) is
deferred per the plan (DEFER-20-01 — needs gd binary + running server).

## Self-Check: PASSED
- FOUND: backend/app/services/execution_type_handler.py (grd_research)
- FOUND: backend/app/services/grd_cli_service.py (research helpers)
- FOUND: backend/app_litestar/routes/grd_routes.py (5 routes)
- FOUND: backend/tests/test_grd_research_handler.py
- FOUND: backend/tests/test_grd_research_routes.py
- FOUND commits: 297d7f4745, 4129812573, 00c9f8371a
