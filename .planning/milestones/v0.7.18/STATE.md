# v0.7.18 State

Status: COMPLETE — shipped PR #73 (2026-05-10).

## Shipped

The v0.7.17 ship landed a global `agent_yolo_mode` setting (default
ON) that flips sketches and agent flows from CLIProxyAPI to the CLI
agent runner. The user's spec called for the AiChatPanel itself to
opt back into CLIProxyAPI by default with a per-panel toggle that
overrides the global on demand — the panel's existing-CLIProxy
behavior is the safer default for chat-style ideation, and YOLO is
the explicit opt-in.

## Key files touched

- `backend/app/services/sketch_execution_service.py`
- `frontend/src/composables/useSketchChat.ts`
- `frontend/src/services/api/sketches.ts`
- `frontend/src/views/SketchChatPage.vue`

## Reference

- PR: #73
- Commit: `51ac748f`
