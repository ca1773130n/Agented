# v0.7.94 State

Status: COMPLETE — shipped PR #141 (2026-05-19).

## Shipped

When two Keychain entries share the same ``svce`` (service name) but
differ on ``acct``, ``security find-generic-password -s <svce>``
returns only ONE of them — whichever happens to be first by Keychain
order. This silently broke the credential resolver for accounts where
a plugin had pre-created an entry under the same svce as Claude Code's
auth entry.

## Key files touched

- `backend/app/services/provider_usage_client.py`
- `backend/tests/test_provider_usage_client.py`

## Reference

- PR: #141
- Commit: `dfa4055a`
