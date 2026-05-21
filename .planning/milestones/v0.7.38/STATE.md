# v0.7.38 State

Status: COMPLETE — shipped PR #93 (2026-05-11).

## Shipped

``just deploy`` fails because ``npm run build`` runs ``vue-tsc -b``
which is stricter than the ``vue-tsc --noEmit`` mode I'd been using
to verify each audit PR — build mode flags unused imports and a few
narrowing edges that the non-build mode tolerates.

## Key files touched

- `frontend/src/components/layout/AppHeader.vue`
- `frontend/src/composables/useSketchChat.ts`
- `frontend/src/views/ProjectsPage.vue`
- `frontend/src/views/TeamLeaderboard.vue`
- `frontend/src/views/TeamsPage.vue`

## Reference

- PR: #93
- Commit: `8943eadf`
