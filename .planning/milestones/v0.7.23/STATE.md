# v0.7.23 State

Status: COMPLETE — shipped PR #78 (2026-05-10).

## Shipped

Reported gap: only top-level segments and the final segment were
clickable. Mid-depth entity IDs (``sa-...``, ``proj-...``, ``team-...``,
``psa-...``) rendered as plain text, so the user couldn't jump from
``/super-agents/sa-X/playground`` to the SA detail page just by
clicking ``sa-X`` in the breadcrumb.

## Key files touched

- `frontend/src/components/layout/AppHeader.vue`

## Reference

- PR: #78
- Commit: `c7c3395f`
