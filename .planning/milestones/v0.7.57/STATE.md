# v0.7.57 State

Status: COMPLETE — shipped 2026-05-15.

## Shipped

User asked for permission control of AI backend accounts per project
(with yolo-mode bypass) and a popup dialog on session start that
captures session name, an auto-title toggle, the yolo flag, and the
execution type. The user setting "default yolo on session start"
must seed the dialog's yolo toggle.

## Key files touched

- `backend/app/db/migrations/v07_features.py`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/components/sessions/SessionStartDialog.vue`
- `frontend/src/components/settings/GeneralSettings.vue`
- `frontend/src/services/api/grd.ts`

## Reference

- Commit: `a44f9b4f`
