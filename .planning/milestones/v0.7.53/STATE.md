# v0.7.53 State

Status: COMPLETE — shipped 2026-05-15.

## Shipped

User asked claude "show me the content of CLAUDE.md" and saw a wall
of raw ``#``-prefixed text in the chat panel. Live-tested what
claude emits: it wraps file contents in a ``markdown`` fence by
default — e.g.

## Key files touched

- `backend/app/services/project_session_manager.py`
- `backend/tests/test_project_session_manager.py`

## Reference

- Commit: `978f0b80`
