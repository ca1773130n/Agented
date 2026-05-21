# v0.7.82 State

Status: COMPLETE — shipped PR #126 (2026-05-18).

## Shipped

v0.7.79 fixed the hidden-until-ready Create button on /skills/new
but left the same unkind UX on the other five wizards that use
the AiChatPanel. Per the bug-class-sweep convention: sweep the
codebase, fix every instance in one PR.

## Key files touched

- `frontend/src/views/AgentCreateWizard.vue`
- `frontend/src/views/CommandDesignPage.vue`
- `frontend/src/views/HookDesignPage.vue`
- `frontend/src/views/PluginDesignPage.vue`
- `frontend/src/views/RuleDesignPage.vue`

## Reference

- PR: #126
- Commit: `42a6d03a`
