# v0.7.84 State

Status: COMPLETE — shipped PR #128 (2026-05-18).

## Shipped

Brings Agented's GRD integration up to v0.3.24, which introduces a
second entry-point binary (``gd.js``) alongside the legacy
``grd-tools.js`` and a new set of "Ouroboros" deterministic
commands (think / health / dead-end / genome / verify mechanical /
plan-tournament). This is Layer A of a 3-layer migration; PR B
adds DB-side artifact sync and PR C adapts the pattern to
GoalLoopRunner.

## Key files touched

- `backend/app/models/grd.py`
- `backend/app/services/grd_cli_service.py`
- `backend/app_litestar/lifecycle.py`
- `backend/app_litestar/routes/grd_routes.py`
- `backend/tests/test_grd_cli_v0324.py`

## Reference

- PR: #128
- Commit: `df8ab9b7`
