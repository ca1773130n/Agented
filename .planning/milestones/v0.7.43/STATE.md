# v0.7.43 State

Status: COMPLETE — shipped 2026-05-12.

## Shipped

The v0.7.42 chat view spawned bare ``claude``, which (correctly)
drops into the interactive TUI — so the welcome banner, box-drawing
characters, and ANSI cursor moves leaked into the chat bubble:

## Key files touched

- `backend/app/services/project_session_manager.py`
- `frontend/src/components/sessions/GrdSessionChatView.vue`
- `frontend/src/services/api/grd.ts`

## Reference

- Commit: `e394d179`
