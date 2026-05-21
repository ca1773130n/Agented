# v0.7.39 State

Status: COMPLETE — shipped PR #94 (2026-05-12).

## Shipped

User reported the Sessions tab on the project management page showed
nothing after they routed work via /sketch. Tracing showed two parallel
session systems hanging off ``/api/projects/{id}/sessions`` /
``/admin/projects/{id}/sessions``:

## Key files touched

- `frontend/src/components/sessions/ProjectSuperAgentSessions.vue`
- `frontend/src/services/api/projects.ts`
- `frontend/src/views/ProjectManagementPage.vue`

## Reference

- PR: #94
- Commit: `cff0dfc8`
