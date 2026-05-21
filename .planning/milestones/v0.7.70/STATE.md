# v0.7.70 State

Status: COMPLETE — shipped 2026-05-17.

## Shipped

Wires the operator's Forge artifacts (rules, skills, hooks, commands, MCP servers, plugins) into project-session claude runs, plus a per-prompt context tray and a session-creation context dialog.

## Key files touched

- `backend/app/db/__init__.py`
- `backend/app/db/migrations/v07_features.py`
- `backend/app/db/project_forge_bindings.py`
- `backend/app/services/claude_config_overlay.py`
- `backend/app/services/cli_overlay_base.py`
- `backend/app/services/codex_config_overlay.py`

## Reference

- Commit: `0bda9559`
