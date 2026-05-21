# v0.7.45 State

Status: COMPLETE — shipped 2026-05-13.

## Shipped

The chat panel's ``is-processing`` prop was bound to
``session.isStreaming``, which flips true the moment the SSE
stream connects — well before the user has typed anything. Result:
the panel shows "AI is thinking..." immediately after clicking
Start, with no message in flight and nothing actually pending.

## Key files touched

- `frontend/src/components/sessions/GrdSessionChatView.vue`

## Reference

- Commit: `996479e2`
