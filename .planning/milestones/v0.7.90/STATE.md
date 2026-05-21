# v0.7.90 State

Status: COMPLETE — shipped PR #137 (2026-05-19).

## Shipped

These three Forge design pages opened in Form mode by default,
leaving the AI chat as a secondary toggle the operator had to
discover. Flipping the default to chat matches the recommended
flow for bootstrapping a new entity from a natural-language
description — the form remains available for operators who
already know the entity shape and want to fill it directly.

## Key files touched

- `frontend/src/views/CommandDesignPage.vue`
- `frontend/src/views/HookDesignPage.vue`
- `frontend/src/views/RuleDesignPage.vue`

## Reference

- PR: #137
- Commit: `c549c034`
