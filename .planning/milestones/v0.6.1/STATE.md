# v0.6.1 State

Status: COMPLETE — pending Codex review + merge.

## Shipped

### Item 1 — datetime.utcnow shim

- `app/utils/timezone.utcnow()` — naive-UTC shim.
- 18 callsites swept across `app/db/sessions.py`, `password_resets.py`,
  `secrets.py`, `app/services/{memory_evolution,audit_log_service,
  project_health_service}.py`, `app_litestar/routes/grd_routes.py`,
  `scripts/backup.py`.
- Test-suite warnings dropped 55→25 in the touched-area run.

### Item 2 — expire_sessions soft-delete

- Renamed `purge_expired_sessions` → `expire_sessions`; old name kept
  as backwards-compatible alias.
- Now sets `revoked_at` + `revoke_reason='expired'` instead of
  hard-deleting. Session-events audit log can still reference
  expired sessions.

### Item 3 — rotated_from_token uniqueness

- Migration 113: `CREATE UNIQUE INDEX
  idx_sessions_rotated_from_token_unique ON sessions
  (rotated_from_token) WHERE rotated_from_token IS NOT NULL`.
- Closes the v0.6.0 Codex round-1 #7 deferral.

### Tests added

- `tests/test_sessions.py`: 2 new (soft-delete preserves row,
  alias resolves).
- `tests/test_migration_113.py`: 4 new (index presence, partial,
  IntegrityError on duplicate, NULL coexistence).
- Total new: 6 backend tests.

## Verification

- Frontend: 1128 passed (no change).
- Backend full suite: pending (in progress).
- Touched-area: all relevant tests pass.

## Out of scope (deferred)

- Wholesale aware-datetime migration across the codebase. The
  shim preserves naive-UTC semantics; future cleanup can audit
  comparison sites and migrate to `datetime.now(UTC)` properly.
- Hard-delete retention pass for long-revoked rows.

## Next milestone

**v0.6.2** — Observability deepening. Per the autopilot directive.
