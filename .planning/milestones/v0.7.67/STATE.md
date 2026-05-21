# v0.7.67 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

Phase 4 of the TUI-parity arc. Until now claude's responses landed
as one complete bubble per ``assistant`` event; users waited for the
full answer before anything appeared. The TUI streams text token by
token. This commit brings that to the web panel.

## Key files touched

- `backend/app/services/project_session_manager.py`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/composables/useProjectSession.ts`

## Reference

- Commit: `c13af3bb`
