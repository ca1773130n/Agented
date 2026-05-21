# v0.7.25 State

Status: COMPLETE — shipped PR #80 (2026-05-10).

## Shipped

The SuperAgents page only showed each SA's manual ``enabled`` toggle
state (Active / Inactive) — no signal for live activity. The user
asked for "which SA has an active session and which is actively
working or idle" on both ``/super-agents`` and the project detail
page.

## Key files touched

- `backend/app/db/super_agents.py`
- `backend/app/services/chat_state_service.py`
- `frontend/src/services/api/index.ts`
- `frontend/src/services/api/super-agents.ts`
- `frontend/src/views/ProjectDashboard.vue`
- `frontend/src/views/SuperAgentsPage.vue`

## Reference

- PR: #80
- Commit: `d130033f`
