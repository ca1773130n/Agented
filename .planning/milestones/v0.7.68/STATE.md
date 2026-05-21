# v0.7.68 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

Phase 5 of the TUI-parity arc. When claude is configured with
extended thinking, the model emits a ``thinking`` content block
that carries its reasoning. Until now the extractor only handled
``text`` / ``tool_use`` / ``tool_result`` blocks — thinking was
silently dropped.

## Key files touched

- `backend/app/services/project_session_manager.py`
- `frontend/src/App.vue`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/composables/useProjectSession.ts`

## Reference

- Commit: `80aaf20c`
