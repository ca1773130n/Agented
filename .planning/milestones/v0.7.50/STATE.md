# v0.7.50 State

Status: COMPLETE — shipped 2026-05-15.

## Shipped

The terminal panel renders ``SessionOutput`` (a markdown stream)
plus ``SessionInput``. When you typed a prompt it went to claude
over the SSE pipeline but was never echoed into ``SessionOutput`` —
so the panel looked like a one-sided monologue: only claude's
replies appeared, never your messages. User report: "still you
don't show my prompt on the ui. just response is showing. make
some proper ui to distinguish my mention and response".

## Key files touched

- `frontend/src/components/sessions/ProjectSessionPanel.vue`

## Reference

- Commit: `676f802b`
