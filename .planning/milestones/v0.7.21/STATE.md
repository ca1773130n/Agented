# v0.7.21 State

Status: COMPLETE — shipped PR #76 (2026-05-10).

## Shipped

User reported "Connection lost. You can retry by routing again." on
every sketch send, regardless of whether the panel was in CLI runner
or CLIProxy mode. Tracing showed the SSE handler at
``/admin/super-agents/{sa}/sessions/{sid}/chat/stream`` was hitting
``ChatStateService.subscribe()``'s "session not found" branch and
yielding an immediate error event before the streaming thread even
started, which closed the EventSource and triggered the panel's
``onerror`` toast.

## Key files touched

- `backend/app/services/streaming_helper.py`
- `backend/app_litestar/routes/leaf_crud_i.py`
- `backend/tests/test_streaming_helper_init_session.py`

## Reference

- PR: #76
- Commit: `45b24fb3`
