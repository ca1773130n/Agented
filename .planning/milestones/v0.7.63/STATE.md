# v0.7.63 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

When claude calls the ``AskUserQuestion`` tool it expects a
structured tool_result back. Until now my chat panel rendered it
as a generic ``<details>`` tool-call chip and ignored the
``questions`` payload — no way for the user to actually answer.

## Key files touched

- `backend/app/services/project_session_manager.py`
- `frontend/src/components/sessions/InteractiveQuestionCard.vue`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/composables/useProjectSession.ts`
- `frontend/src/services/api/grd.ts`

## Reference

- Commit: `941ebcc9`
