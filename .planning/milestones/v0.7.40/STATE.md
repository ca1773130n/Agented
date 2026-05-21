# v0.7.40 State

Status: COMPLETE — shipped PR #95 (2026-05-12).

## Shipped

User reported the Sessions tab on /projects/proj-xwl0p5/management
still showed nothing after v0.7.39, even though they'd routed work
via /sketch. Tracing showed the wire-up was right, but the data was
wrong: every ``super_agent_sessions`` row for sketches in that
project had ``project_id = NULL``.

## Key files touched

- `backend/app/db/migrations/v07_features.py`
- `backend/app/services/sketch_execution_service.py`
- `backend/app/services/super_agent_session_service.py`

## Reference

- PR: #95
- Commit: `5cb43b38`
