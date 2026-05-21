# v0.7.6 State

Status: COMPLETE — shipped 2026-05-10.

## Shipped

PR #50 (schema split) review:
- Reorder backend/app/db/schema/__init__.py to follow FK dependency order.
  Codex flagged 6 violations where a referencing table was created before its
  referenced parent (triggers→teams, project_paths→projects, project_skills→
  projects, team_members→super_agents, project_sa_instances→super_agents,
  rate_limit_snapshots→backend_accounts). New order: agents → super_agents →
  orgs → skills → core → workflows → security → plugins → triggers_infra →
  setup → embeddings → misc → monitoring.

## Key files touched

- `backend/app/db/schema/__init__.py`
- `backend/tests/test_schema_split.py`
- `frontend/src/composables/__tests__/useAppBoot.test.ts`
- `frontend/src/composables/__tests__/useToastSystem.test.ts`
- `frontend/src/views/__tests__/App.test.ts`

## Reference

- Commit: `52d0ab8d`
