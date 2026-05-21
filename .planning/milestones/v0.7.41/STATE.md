# v0.7.41 State

Status: COMPLETE — shipped PR #96 (2026-05-12).

## Shipped

User reported "Connection lost" appearing on the GRD session panel
right after typing the first message. Two coordinated bugs caused
the same symptom:

## Key files touched

- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/composables/useProjectSession.ts`

## Reference

- PR: #96
- Commit: `e4e1b7e4`
