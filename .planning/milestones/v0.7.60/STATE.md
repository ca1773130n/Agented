# v0.7.60 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

User report: when claude does a sequence of tool calls in a single
turn (e.g. Read + ToolSearch + WebSearch + text reply), each block
was landing in its own chat bubble — even though they belong to one
logical exchange. The bubble stream looked fragmented.

## Key files touched

- `frontend/src/components/sessions/ProjectSessionPanel.vue`

## Reference

- Commit: `d6f4e75c`
