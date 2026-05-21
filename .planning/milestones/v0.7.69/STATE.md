# v0.7.69 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

Phase 6 of the TUI-parity arc. Until now, the chat panel could see
hook decisions after the fact (v0.7.66) but the user couldn't
intervene mid-tool-call — only yolo mode actually bypassed claude's
internal permission gate. This commit makes the web panel the
permission UI: claude is about to use a tool → backend pauses
claude via a hook → user clicks Approve/Deny in the panel → claude
proceeds (or skips).

## Key files touched

- `backend/app/services/claude_config_overlay.py`
- `backend/app/services/execution_type_handler.py`
- `backend/app/services/permission_prompt_service.py`
- `backend/app/services/project_session_manager.py`
- `backend/scripts/agented_permission_hook.py`
- `frontend/src/components/sessions/PermissionPromptCard.vue`

## Reference

- Commit: `f05974e9`
