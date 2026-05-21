# v0.7.97 State

Status: COMPLETE — shipped PR #144 (2026-05-20).

## Shipped

Root cause of the recurring "text content blocks must be non-empty"
proxy error: ``streaming_helper.py`` was the only path into
``stream_llm_response`` that DIDN'T filter empty/whitespace content
when building its messages list. base_, plugin_, and skill_
conversation_service all apply ``if msg.content and msg.content.strip()``;
streaming_helper just appended every conversation_log entry verbatim. Shipped as 2 sequential commits implementing the full slice.

## Key files touched

- `backend/app/services/project_session_manager.py`
- `backend/app/services/agent_conversation_service.py`
- `backend/app/services/streaming_helper.py`

## Reference

- PR: #144
- Commit: `d49bb8f0`
- Commits in slice: 2
