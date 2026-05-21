# v0.7.66 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

Phase 3 of the TUI-parity arc. Claude's ``PreToolUse``/``PostToolUse``
hooks (configured by the user in ``~/.claude/settings.json``) can
return permission decisions like ``allow`` / ``deny`` / ``ask``.
Until now these were filtered out as system noise. The chat panel
now surfaces them as compact inline pill badges so users can see
what hooks decided about each tool call.

## Key files touched

- `backend/app/services/project_session_manager.py`
- `frontend/src/App.vue`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/composables/useProjectSession.ts`

## Reference

- Commit: `15daa38e`
