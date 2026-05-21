# v0.7.58 State

Status: COMPLETE — shipped 2026-05-15.

## Shipped

Completes the permission control feature. Layer 1 (v0.7.57) shipped
the session-start dialog with a yolo toggle but persisted the flag
only — no actual gate. This commit adds the gate: non-yolo sessions
must use an ``account_id`` from the project's whitelist, enforced
server-side. Yolo bypasses the check (matching the agreed semantics
in the dialog copy).

## Key files touched

- `backend/app/db/grd.py`
- `backend/app/db/migrations/v07_features.py`
- `frontend/src/components/project/ProjectAllowedAccountsPanel.vue`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/components/sessions/SessionStartDialog.vue`
- `frontend/src/services/api/grd.ts`

## Reference

- Commit: `4063d2f9`
