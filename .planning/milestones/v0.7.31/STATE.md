# v0.7.31 State

Status: COMPLETE — shipped PR #86 (2026-05-10).

## Shipped

Three create modals had submit buttons with no in-flight tracking —
double-clicking the Create button fired two API calls and produced
duplicate entities. ProjectsPage already had the right guard
(``:disabled="creatingProject"``); the others now match it.

## Key files touched

- `frontend/src/views/ProductsPage.vue`
- `frontend/src/views/SuperAgentsPage.vue`
- `frontend/src/views/TeamsPage.vue`

## Reference

- PR: #86
- Commit: `47c341d7`
