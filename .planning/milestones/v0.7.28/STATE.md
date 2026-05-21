# v0.7.28 State

Status: COMPLETE — shipped PR #83 (2026-05-10).

## Shipped

Eight list pages had each entity card rendered as
``<div @click="router.push(...)">``. Looks clickable, navigates on
left-click, but silently swallows every modifier-key intent:
* Cmd/Ctrl+click — should open in a new tab → no-op
* Middle-click — should open in a new tab → no-op
* Right-click → "Open in new tab" — context menu does nothing
* Sharing the URL — there's no URL on the element to copy

## Key files touched

- `frontend/src/views/AgentsPage.vue`
- `frontend/src/views/MySkills.vue`
- `frontend/src/views/PluginsPage.vue`
- `frontend/src/views/ProductsPage.vue`
- `frontend/src/views/ProjectsPage.vue`
- `frontend/src/views/SuperAgentsPage.vue`

## Reference

- PR: #83
- Commit: `70b0fbb2`
