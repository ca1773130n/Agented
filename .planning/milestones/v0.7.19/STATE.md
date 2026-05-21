# v0.7.19 State

Status: COMPLETE — shipped PR #74 (2026-05-10).

## Shipped

v0.7.18 plumbed the per-panel toggle through SketchChatPage. The pill
already rendered on every other AiChatPanel-driven surface (the prop
landed in ai-accounts/PR#27), but flipping it didn't change behavior
because each consumer had its own send path that wasn't carrying the
override. This PR wires the remaining five end-to-end so flipping the
toggle on any of them actually re-routes the next message.

## Key files touched

- `backend/app/services/base_conversation_service.py`
- `frontend/src/composables/useConversation.ts`
- `frontend/src/services/api/commands.ts`
- `frontend/src/services/api/grd.ts`
- `frontend/src/services/api/hooks.ts`
- `frontend/src/services/api/plugins.ts`

## Reference

- PR: #74
- Commit: `eb75d159`
