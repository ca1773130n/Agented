# v0.7.61 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

When you click a session in the History sidebar that was created
before v0.7.54 (the commit that started writing to ``log_json``),
the messages-fetch returns ``[]`` and the chat panel falls back to
its default welcome screen — which reads "AI will guide you through
designing your" with a blank entity label. That copy is template
state for an entity-creation flow we don't use; users (rightly)
read it as broken.

## Key files touched

- `frontend/src/components/sessions/ProjectSessionPanel.vue`

## Reference

- Commit: `9b579db0`
