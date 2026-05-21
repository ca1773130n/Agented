# v0.7.85 State

Status: COMPLETE — shipped PR #131 (2026-05-18).

## Shipped

Layer B of the v0.3.24 migration. PR #128 added the CLI surface
(write/invoke); this PR adds the storage + parse layer so the
artifacts GRD writes to ``.planning/`` land in queryable SQLite
tables and the planning UI can surface them without shelling out.

## Key files touched

- `backend/app/db/__init__.py`
- `backend/app/db/grd_ouroboros.py`
- `backend/app/db/ids.py`
- `backend/app/db/migrations/v07_features.py`
- `backend/app/services/grd_sync_service.py`

## Reference

- PR: #131
- Commit: `1f4b4b85`
