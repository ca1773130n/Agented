# v0.7.87 State

Status: COMPLETE — shipped PR #133 (2026-05-18).

## Shipped

PR #132 (v0.7.86) introduced Ouroboros as an opt-in flag
``goal_loop_config["ouroboros"]`` defaulting to ``False``. This
PR flips the default to ``True`` so every new goal-loop session
runs the Ouroboros loop unless the operator explicitly disables
it. The escape hatch is preserved — pass ``"ouroboros": false``
in the config to get the legacy plain-continue behaviour.

## Key files touched

- `backend/app/services/goal_loop_runner.py`
- `frontend/src/components/sessions/ProjectSessionPanel.vue`
- `frontend/src/components/sessions/SessionStartDialog.vue`

## Reference

- PR: #133
- Commit: `f7421b11`
