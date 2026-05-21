# v0.7.49 State

Status: COMPLETE — shipped 2026-05-15.

## Shipped

v0.7.41 swapped ``ProjectSessionPanel``'s default cmd from
``claude -p 'You are in an interactive session'`` to bare ``claude``
to fix a "Connection lost" bug caused by ``-p``'s print-and-exit
semantics. The intent was multi-turn input; the unintended side
effect was that bare ``claude`` drops into its interactive TUI,
emitting box-drawing characters and cursor-movement escapes that
``SessionOutput``'s ``useStreamingParser`` (the ai-accounts markdown
streamer) cannot render.

## Key files touched

- `frontend/src/components/sessions/ProjectSessionPanel.vue`

## Reference

- Commit: `530a8acf`
