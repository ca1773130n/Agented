# v0.7.65 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

When claude is in plan mode it writes a markdown plan and calls
``ExitPlanMode`` to ask whether to start executing. Until now this
came through the chat as a generic ``▸ ExitPlanMode`` tool chip —
clicking it just expanded the JSON input, with no way to actually
accept or decline. Following the v0.7.63 pattern for AskUserQuestion,
this commit lifts ExitPlanMode into its own structured event with a
dedicated approve / keep-planning card.

## Key files touched

- `backend/app/services/project_session_manager.py`
- `frontend/src/components/sessions/PlanModeCard.vue`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/composables/useProjectSession.ts`
- `frontend/src/services/api/grd.ts`

## Reference

- Commit: `1a2d16bc`
