# v0.7.80 State

Status: COMPLETE — shipped PR #123 (2026-05-17).

## Shipped

The "Proxy error: messages: text content blocks must be non-empty"
that v0.7.76 fixed for /skills/new was live on every other wizard
that shares the same pattern. Root cause is identical: the
service's ``start_conversation`` puts only a system message into
``conv["messages"]`` and then calls ``_process_with_claude(conv_id,
kickoff_text)``.

## Key files touched

- `backend/app/services/base_conversation_service.py`
- `backend/app/services/plugin_conversation_service.py`
- `backend/app/services/skill_conversation_service.py`

## Reference

- PR: #123
- Commit: `e9b26b9d`
