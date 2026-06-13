---
phase: 19-grd-default-driver
plan: 04
subsystem: backend/execution
tags: [grd, chat, execution-handler, sse, bridge, REQ-11]
requires:
  - "backend/app/services/turn_classifier_service.py:GRD_COMMAND_MAP"
  - "backend/app/services/project_session_manager.py:create_session (forge_bundle, super_agent_id)"
  - "backend/app/services/project_workspace_service.py:ProjectWorkspaceService.resolve_working_directory"
  - "backend/app/services/chat_state_service.py:ChatStateService.push_delta / push_status"
provides:
  - "backend/app/services/execution_type_handler.py:GrdChatSessionHandler"
  - "backend/app/services/execution_type_handler.py:HANDLER_REGISTRY['grd_chat']"
  - "backend/app/services/grd_chat_bridge.py:bridge_psm_to_chat"
affects:
  - "19-05 (funnel wiring consumes GrdChatSessionHandler + bridge)"
tech-stack:
  added: []
  patterns:
    - "Mirror GoalLoopSessionHandler.start for a one-shot /grd: stream-json session"
    - "Injectable event-source bridge loop (test feeds fakes without real PSM)"
key-files:
  created:
    - backend/app/services/grd_chat_bridge.py
    - backend/tests/test_grd_chat_handler.py
    - backend/tests/test_grd_chat_bridge.py
  modified:
    - backend/app/services/execution_type_handler.py
decisions:
  - "Bridge emits the WIRE strings content_delta/tool_use/finish/error — NOT the ChatDeltaType enum member 'tool_call' — because the frontend consumes the raw wire strings (19-RESEARCH §10 risk 2)"
  - "GRD_COMMAND_MAP values already carry the /grd: prefix; _resolve_grd_command normalizes bare/prefixed inputs to exactly one /grd:<cmd> token"
  - "stop() delegates to ProjectSessionManager.stop_session so a chat abort never orphans the GRD subprocess (risk 5)"
  - "Bridge emits a synthetic finish+complete when the source drains without a terminal marker (clean stream teardown)"
metrics:
  duration: 9min
  completed: 2026-06-13
  tasks: 3
  tests: 12
---

# Phase 19 Plan 04: GRD Chat Session Handler + PSM→Chat-SSE Bridge Summary

GrdChatSessionHandler (registered as `grd_chat`) spawns a one-shot `claude -p`
stream-json PSM session running the classifier-mapped `/grd:<command> "<task>"`
(default `/grd:quick`) in the resolved project cwd with forge/super-agent
linkage, and `bridge_psm_to_chat` maps that session's stream-json events onto
the chat `state_delta` wire protocol — wiring REQ-11's GRD execution path
(success criterion 2). 12/12 proxy tests green.

## What Was Built

- **GrdChatSessionHandler** (`execution_type_handler.py`) mirroring
  `GoalLoopSessionHandler.start`: resolves cwd via
  `ProjectWorkspaceService.resolve_working_directory`, picks the `/grd:` command
  from `session_config["grd_command"]` or `intent`→`GRD_COMMAND_MAP` (default
  `/grd:quick`), builds `cmd = ["claude","-p","--output-format","stream-json",
  "--verbose", '/grd:<cmd> "<task>"']`, and forwards `forge_bundle` +
  `super_agent_id` to `create_session(execution_type="grd_chat", stream_json=True,
  use_pty=False)`. `stop` stops the PSM session. Registry gains `"grd_chat"`.
- **bridge_psm_to_chat** (`grd_chat_bridge.py`): injectable event-source loop
  mapping `text→("content_delta",{content})`, `tool_use→("tool_use",tool_dict)`,
  `result→("finish",{finish_reason})+push_status("complete")`,
  `error→("error",{error_message})+push_status("error")`. Order preserved;
  terminal markers break the loop; synthetic finish on drain.
- **Tests**: handler forwarding (cmd/cwd/forge/super_agent, intent mapping,
  normalization, stop) and bridge (ordering, error propagation, wire-string
  fidelity, synthetic finish).

## Deviations from Plan

None — plan executed as written. Minor: `_resolve_grd_command` was added as a
helper because `GRD_COMMAND_MAP` values already include the leading `/grd:`
prefix (the plan's parenthetical normalization note anticipated this).

## Verification

- Level 1 (Sanity): `grd_chat` in `HANDLER_REGISTRY`; both modules import.
- Level 2 (Proxy): `pytest tests/test_grd_chat_handler.py tests/test_grd_chat_bridge.py -q` → 12 passed.
- Level 3 (Deferred): real PSM end-to-end GRD session (integration).

## Self-Check: PASSED
