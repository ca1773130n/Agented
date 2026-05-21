# v0.7.16 State

Status: COMPLETE — shipped PR #71 (2026-05-10).

## Shipped

`/dashboards/tokens` showed no gauges because the monitoring pipeline
queries the local `backend_accounts` table, which is empty post-wave-80
(accounts live in the ai-accounts sidecar's DB). The auto-enable check
saw zero accounts → monitoring stayed disabled → polling never ran →
`rate_limit_snapshots` stayed empty → no gauges.

## Key files touched

- `backend/app/services/monitoring_service.py`
- `backend/app/services/sidecar_account_sync_service.py`
- `backend/tests/test_sidecar_account_sync.py`

## Reference

- PR: #71
- Commit: `a71a45c0`
