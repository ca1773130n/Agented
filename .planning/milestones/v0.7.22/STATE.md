# v0.7.22 State

Status: COMPLETE — shipped PR #77 (2026-05-10).

## Shipped

User flipped the AiChatPanel to CLI-runner mode and got
"Not logged in · Please run /login [Claude CLI error: exit code 1]"
because the spawned CLI loaded ``~/.claude`` (no creds) instead of
the user's ai-accounts vault at ``~/.claude-personal1``.

## Key files touched

- `backend/app/services/base_conversation_service.py`
- `backend/app/services/cli_agent_runner_service.py`
- `backend/app/services/streaming_helper.py`

## Reference

- PR: #77
- Commit: `5f1f1f6b`
