# v0.7.1 State

Status: COMPLETE — shipped 2026-05-06.

## Shipped

Captures incoming webhook payloads in DB for inspection + replay.
trigger_id is intentionally nullable + no FK CASCADE — history is
retained when triggers are deleted, and unmatched webhooks are also
recorded so debugging works for "trigger didn't fire" reports. Shipped as 12 sequential commits implementing the full slice.

## Key files touched

- `frontend/src/components/triggers/TriggerPayloadHistory.vue`
- `frontend/src/services/api/index.ts`
- `frontend/src/services/api/trigger-events.ts`
- `backend/app/services/trigger_dispatcher.py`
- `backend/app/services/execution_service.py`
- `backend/app/services/trigger_event_service.py`

## Reference

- Commit: `bc7b65fa`
- Commits in slice: 12
