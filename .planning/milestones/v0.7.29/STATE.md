# v0.7.29 State

Status: COMPLETE — shipped PR #84 (2026-05-10).

## Shipped

Seven page-level modals had backdrop-click close (``@click.self``)
but no Escape-key handler. Users got stuck unless they reached for
the mouse, which is a UX regression vs. every other modal in the app
(component-level modals all already handle Escape).

## Key files touched

- `frontend/src/views/BotMemoryStorePage.vue`
- `frontend/src/views/DataRetentionPoliciesPage.vue`
- `frontend/src/views/DependencyAwareSchedulingPage.vue`
- `frontend/src/views/MetricsExportPage.vue`
- `frontend/src/views/PromptSnippetLibrary.vue`
- `frontend/src/views/RepoBotDefaultsPage.vue`

## Reference

- PR: #84
- Commit: `cfe3da59`
