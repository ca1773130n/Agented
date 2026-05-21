# v0.7.27 State

Status: COMPLETE — shipped PR #82 (2026-05-10).

## Shipped

Three click handlers were navigating to routes that don't exist in
the router config. The user clicked a button, the navigation fired,
``router.push`` resolved to no match, and the user landed on the
not-found page (or a blank screen depending on guards) without any
hint that the action even succeeded.

## Key files touched

- `frontend/src/views/BotCloneForkPage.vue`
- `frontend/src/views/CrossTeamBotSharing.vue`
- `frontend/src/views/NaturalLanguageBotCreator.vue`

## Reference

- PR: #82
- Commit: `b0cf7236`
