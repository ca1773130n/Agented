# v0.7.89 State

Status: COMPLETE — shipped PR #136 (2026-05-19).

## Shipped

The user is reporting the v0.7.80 error class re-emerging on the
design wizards (skills/plugins/commands/hooks/rules) despite the
defense filter being in place. The defense excludes
None/whitespace string content, so something else is shaping the
payload such that CLIProxyAPI's translation produces an empty
text content block downstream.

## Key files touched

- `backend/app/services/conversation_streaming.py`

## Reference

- PR: #136
- Commit: `e325bf6e`
