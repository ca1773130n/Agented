# v0.7.54 State

Status: COMPLETE — shipped 2026-05-15.

## Shipped

User report: clicking a prior session in the terminal panel's
sidebar showed only the AiChatPanelManaged welcome screen
("Connecting to AI...") — no history of what was actually said.
Diagnosis: the in-memory ring buffer ``ProjectSessionManager`` uses
for SSE replay is per-process state. The 17 sessions in the DB were
all created before the current gunicorn started, so ``subscribe()``
yielded ``error: "Session not found"`` and the panel showed the
empty state.

## Key files touched

- `backend/app/db/grd.py`
- `backend/app/services/project_session_manager.py`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/services/api/grd.ts`

## Reference

- Commit: `135d266c`
