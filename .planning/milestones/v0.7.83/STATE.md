# v0.7.83 State

Status: COMPLETE — shipped PR #127 (2026-05-18).

## Shipped

Brings the v0.7.78 skill-wizard pattern (DB persistence + per-user
ownership + auto-resume) to the other four conversation services
in one sweep, plus adds user_id scoping to the existing
design_conversations + agent_conversations tables that
commands/hooks/rules/agents share.

## Key files touched

- `backend/app/db/__init__.py`
- `backend/app/db/agents.py`
- `backend/app/db/migrations/v07_features.py`
- `backend/app/db/plugin_conversations.py`
- `backend/app/services/agent_conversation_service.py`
- `backend/app/services/base_conversation_service.py`

## Reference

- PR: #127
- Commit: `49404437`
