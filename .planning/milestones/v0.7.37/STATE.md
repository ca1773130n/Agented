# v0.7.37 State

Status: COMPLETE — shipped PR #92 (2026-05-11).

## Shipped

v0.7.36 fixed HistoricalSessionViewer rendering markdown content as
plain text. A grep for ``{{ msg.content }}`` / ``{{ message.content }}``
found two more sites with the exact same bug:

## Key files touched

- `frontend/src/components/base/MarkdownContent.vue`
- `frontend/src/components/monitoring/HistoricalSessionViewer.vue`
- `frontend/src/components/super-agents/MessageThread.vue`
- `frontend/src/components/triggers/BranchNavigator.vue`

## Reference

- PR: #92
- Commit: `866cfe13`
