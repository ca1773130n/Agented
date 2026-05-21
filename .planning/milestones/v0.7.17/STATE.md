# v0.7.17 State

Status: COMPLETE — shipped PR #72 (2026-05-10).

## Shipped

The legacy `run_streaming_response` path preferred CLIProxyAPI, which gave
nice token-by-token chat but ran the CLIs as stateless workers — no file
reads, shell commands, or worktree edits. Sketches and agent-driven
sessions want the opposite: an agent that opens a worktree, uses tools,
and reports back when done (Hermes-style).

## Key files touched

- `backend/app/services/cli_agent_runner_service.py`
- `backend/app/services/streaming_helper.py`
- `frontend/src/components/settings/GeneralSettings.vue`

## Reference

- PR: #72
- Commit: `0e3e65f0`
