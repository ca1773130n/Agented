# v0.7.8 State

Status: COMPLETE — shipped 2026-05-10.

## Shipped

Per-(backend_kind, auth_method) cache with TTL columns, two indices on
expires_at and discovered_at, and a UNIQUE constraint on the
(backend_kind, auth_method) pair. Shipped as 11 sequential commits implementing the full slice.

## Key files touched

- `frontend/src/components/monitoring/BackendInfoSection.vue`
- `backend/app/services/model_cache_service.py`
- `frontend/src/locales/en.json`
- `frontend/src/views/BackendDetailPage.vue`
- `frontend/src/services/api/index.ts`
- `frontend/src/services/api/model-cache.ts`

## Reference

- Commit: `170d23a4`
- Commits in slice: 11
