# v0.7.93 State

Status: COMPLETE — shipped PR #140 (2026-05-19).

## Shipped

The Token Usage Dashboard silently drops accounts whose OAuth token
the poller can't resolve from local keychain/config — the only signal
was a backend log line ("Claude: no OAuth token for account 2") that
operators had to grep for. Real-user feedback today: confusion about
why "personal2" wasn't appearing on the dashboard despite the account
existing in AI Backends.

## Key files touched

- `backend/app/services/provider_usage_client.py`
- `frontend/src/components/credentials/CredentialStatusBanner.vue`
- `frontend/src/services/api/index.ts`
- `frontend/src/services/api/monitoring.ts`
- `frontend/src/views/AIBackendsPage.vue`
- `frontend/src/views/TokenUsageDashboard.vue`

## Reference

- PR: #140
- Commit: `b2c7e90a`
