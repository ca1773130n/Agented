# v0.7.9 State

Status: COMPLETE — shipped 2026-05-10.

## Shipped

Add a classmethod that hits the ai-accounts sidecar's
GET /api/v1/backends/{id}/models endpoint using a representative
account for the (kind, auth_method) pair. Returns the list of model
IDs or None on any failure so callers can continue the chain. Shipped as 4 sequential commits implementing the full slice.

## Key files touched

- `frontend/src/components/monitoring/BackendInfoSection.vue`
- `frontend/src/locales/en.json`
- `backend/app/services/model_cache_service.py`
- `backend/app/services/model_discovery_service.py`

## Reference

- Commit: `74c3dafd`
- Commits in slice: 4
