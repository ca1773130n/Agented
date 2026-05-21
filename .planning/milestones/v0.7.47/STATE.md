# v0.7.47 State

Status: COMPLETE — shipped 2026-05-13.

## Shipped

The previous chat-view scheme buffered each stream-json output event
into a ``streamingContent`` ref and only flushed it into the
permanent ``messages`` array on session-complete:

## Key files touched

- `frontend/src/components/sessions/GrdSessionChatView.vue`

## Reference

- Commit: `6f9eff30`
