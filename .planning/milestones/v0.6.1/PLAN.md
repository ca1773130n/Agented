# v0.6.1 — Tech debt sweep

Three deferred items from v0.5.x and v0.6.0 closed:

1. **`datetime.utcnow` deprecation sweep** — `app/utils/timezone.utcnow()`
   shim returning naive UTC; 18 callsites across 8 files migrated.
2. **`expire_sessions` soft-delete** — renamed from `purge_expired_sessions`
   (kept as alias); now sets `revoked_at` + `revoke_reason='expired'`
   instead of hard-deleting. Audit-log consistency.
3. **`rotated_from_token` partial unique index** — migration 113
   enforces the "at most 2 rows per token" invariant that
   `get_session_by_token` relies on.

Auto-approved scope (A/A/C from brainstorming).
