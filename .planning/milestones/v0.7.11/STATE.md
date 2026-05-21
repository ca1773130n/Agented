# v0.7.11 State

Status: COMPLETE — shipped 2026-05-10.

## Shipped

User reported model list still showing 'via CLIProxyAPI' after v0.7.9
shipped sidecar-preferred discovery. Probe revealed the sidecar
returns 401 for the Agented→sidecar GET /api/v1/backends/{id}/models
call because AI_ACCOUNTS_API_KEY isn't in the gunicorn process env. Shipped as 3 sequential commits implementing the full slice.

## Key files touched

- `backend/app/services/model_discovery_service.py`
- `backend/tests/test_model_discovery_sidecar_path.py`

## Reference

- Commit: `4ef05501`
- Commits in slice: 3
