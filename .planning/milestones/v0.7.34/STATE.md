# v0.7.34 State

Status: COMPLETE — shipped PR #89 (2026-05-11).

## Shipped

Two distinct issues caused 5 tests to fail since v0.7.14, forcing
every developer to remember the ``--ignore=...`` flags or wade through
red output to find new regressions:

## Key files touched

- `backend/app/db/migrations/__init__.py`
- `backend/tests/test_backend_service.py`

## Reference

- PR: #89
- Commit: `c91499c4`
