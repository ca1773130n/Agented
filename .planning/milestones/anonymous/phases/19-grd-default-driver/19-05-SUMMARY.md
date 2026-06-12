---
phase: 19-grd-default-driver
plan: "05"
subsystem: backend-streaming
tags: [driver-spine, cliproxy-regression, grd-default, funnel, REQ-10, REQ-11]
requires:
  - "backend/app/services/cli_agent_runner_service.py:resolve_execution_driver"
  - "backend/app/services/turn_classifier_service.py:classify_turn"
  - "backend/app/services/execution_type_handler.py:HANDLER_REGISTRY['grd_chat']"
  - "backend/app/services/grd_chat_bridge.py:bridge_psm_to_chat"
provides:
  - "backend/app/services/streaming_helper.py:run_streaming_response (3-way driver branch)"
affects:
  - "backend/app/services/base_conversation_service.py"
  - "backend/app_litestar/routes/grd_routes.py:project_chat"
tech-stack:
  added: []
  patterns:
    - "subscribe_raw-before-start to feed an in-process PSM event generator into bridge_psm_to_chat"
    - "extract-shared-closure (_run_cliproxy) so the grd-conversational fallthrough reuses the byte-identical cliproxy block"
key-files:
  created:
    - "backend/tests/test_streaming_helper_driver.py"
  modified:
    - "backend/app/services/streaming_helper.py"
    - "backend/app/services/base_conversation_service.py"
    - "backend/app_litestar/routes/grd_routes.py"
    - "backend/tests/test_answer_pipeline_hook.py"
    - "backend/tests/test_sketch_execution.py"
decisions:
  - "design-conversation path (base_conversation_service) has no PSM/chat-SSE surface — grd treated identically to cli_agent there"
  - "project_id is derived best-effort from the session-state row in the funnel; the resolver tolerates None and degrades grd->cli_agent"
metrics:
  duration: "~35min"
  completed: "2026-06-13"
  tasks: 3
  files: 6
---

# Phase 19 Plan 05: GRD Default Driver at the Streaming Funnel Summary

GRD becomes the default execution driver at the single streaming funnel:
`run_streaming_response` now resolves a 3-way driver (cliproxy | cli_agent |
grd) and the cliproxy conversational path is provably byte-identical to its
pre-change form, with task-shaped grd turns dispatched through the
`grd_chat` handler + PSM→chat-SSE bridge.

## What shipped

- **Task 1 — funnel 3-way branch** (`streaming_helper.py`): replaced
  `should_route_via_cli_agent` with `resolve_execution_driver`. The cliproxy
  block was lifted verbatim into a `_run_cliproxy()` closure (body untouched)
  so the grd-conversational fallthrough SHARES it rather than duplicating it.
  `driver=="cliproxy"` → `_run_cliproxy()`; `driver=="grd"` → `classify_turn`
  (conversational → `_run_cliproxy()`; task → `get_handler('grd_chat').start`
  then `bridge_psm_to_chat` over a `subscribe_raw` event generator);
  `else` → the existing cli_agent rotation block. Any grd-dispatch failure
  logs and falls through to cli_agent — the turn is never dropped.
- **Task 2 — migrate the two remaining call sites**:
  `base_conversation_service._stream_and_accumulate` (grd≡cli_agent — no
  PSM/chat-SSE surface there) and `grd_routes.project_chat` (grd-task →
  handler+bridge; grd-conversational/cliproxy → `stream_llm_response`). All
  three legacy `should_route_via_cli_agent` call sites are now migrated
  (REQ-10).
- **Task 3 — tests** (`test_streaming_helper_driver.py`): the
  criterion-3 regression (conversational driver=grd deltas byte-for-byte
  equal to the cliproxy baseline), grd-task dispatch (handler+bridge run,
  cliproxy stream NOT called), and the degrade case (driver=cli_agent takes
  the runner path, turn not dropped).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing funnel/project_chat tests stubbed the removed routing seam**
- **Found during:** Task 3 (targeted regression run)
- **Issue:** `test_answer_pipeline_hook.py` and `test_sketch_execution.py`
  monkeypatched `should_route_via_cli_agent` to force the cliproxy path. After
  the migration the funnel/project_chat call `resolve_execution_driver`, so
  those stubs no longer took effect — the real resolver defaulted to grd and
  dispatched the handler, breaking 5 tests.
- **Fix:** Re-pointed the stubs at `resolve_execution_driver` returning
  `"cliproxy"`.
- **Files modified:** `tests/test_answer_pipeline_hook.py`,
  `tests/test_sketch_execution.py`
- **Commit:** 0f74d6cebf

## Verification

- Level 1 (Sanity): all three sites import/use `resolve_execution_driver`;
  cliproxy guard present — PASS.
- Level 2 (Proxy): `test_streaming_helper_driver.py` 3/3 — byte-identical
  conversational regression, grd-task dispatch, degrade path — PASS.
- House gates:
  - Backend full serial suite hung at the documented ~40-48% point (killed by
    watchdog, no failures before the hang). Comprehensive targeted
    substitution disclosed: 305 passed / 0 failed across
    execution/streaming/harness-adjacent/goal_loop/grd_chat/classifier/
    cli_agent/conversation/retry/evidence/activity suites.
  - `just build`: fails ONLY on the pre-existing `AnswerGroundednessCard.vue`
    TS2345 error (STATE.md-documented, PR #212). This plan touched zero
    frontend files.
  - `npm run test:run`: 1480 passed / 7 known-baseline failures / 0 NEW.

## Self-Check: PASSED

- FOUND: backend/app/services/streaming_helper.py
- FOUND: backend/app/services/base_conversation_service.py
- FOUND: backend/app_litestar/routes/grd_routes.py
- FOUND: backend/tests/test_streaming_helper_driver.py
- FOUND commits: 8f91b3d844, 5b430b5fb1, 0f74d6cebf
