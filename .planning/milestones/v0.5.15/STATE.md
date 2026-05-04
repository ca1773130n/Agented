# v0.5.15 State

Status: COMPLETE — pending Codex review + merge.

## Shipped

### Snapshot tool

- `backend/scripts/backup.py` — atomic online snapshot via
  `sqlite3.Connection.backup()` for both `agented.db` and
  `ai_accounts.db`. Configurable target, dest dir, retention,
  remote cmd via env or CLI flags. JSON summary on stdout.

### Restore tool

- `backend/scripts/restore.py` — interactive picker (or
  `--snapshot PATH` non-interactive). Live-DB guard refuses to
  overwrite when `*.db-wal` modified within last 60 seconds.
  Pre-restore safety snapshot (skippable via flag). Stale WAL/SHM
  cleanup post-restore.

### Justfile recipes

- `just backup` → `python scripts/backup.py`
- `just restore` → `python scripts/restore.py`

### Scheduling templates

- `scripts/launchd/com.agented.backup.plist` — daily 03:00 via launchd.
- `scripts/systemd/agented-backup.service` + `agented-backup.timer`
  — daily 03:00 via systemd-user timer.
- `scripts/cron/backup-crontab.example` — cron-style daily entry.

### Env vars + .env.example

- `AGENTED_BACKUP_DIR` (default `backend/backups/`)
- `BACKUP_REMOTE_CMD` (optional shell template; `{file}` token)
- `BACKUP_RETENTION_DAYS` (default 30)

Documented in `scripts/check_env.py:OPTIONAL_VARS`, echoed in
`.env.example`.

### Runbook

- `docs/deploy/BACKUP.md` — 8 sections: what's backed up, manual
  snapshot, off-site sync (rclone/aws/scp/rsync), scheduling
  (launchd/systemd/cron), restore, verification (PRAGMA
  integrity_check), DR checklist.

### Tests

- `test_backup.py` — 9 tests (snapshot atomicity, retention
  boundaries, remote-cmd substitution + nonzero exit, CLI exit
  codes, missing-source handling).
- `test_restore.py` — 6 tests (newest-first ordering, label
  filter, target overwrite, safety-snapshot toggle, WAL/SHM
  cleanup, live-DB guard).
- `test_check_env.py` — `_clean_env` fixture extended for 3 new
  backup vars.

Total new: 15 backend tests.

## Verification

- `cd frontend && npm run test:run` — **1128 passed** (no change) ✓
- `cd backend && uv run pytest` — pending full-suite confirmation
- `just build` — vue-tsc + vite clean ✓

## Out of scope (deferred)

- Continuous WAL streaming (litestream).
- Cloud-specific SDKs — operator picks via `BACKUP_REMOTE_CMD`.
- Encryption-at-rest of snapshots — operator-managed.
- Restore-time integrity verification (operator runs PRAGMA
  manually per BACKUP.md).
- UI for browsing or triggering backups.
- Automated restore drills.

## What's done across v0.5.x

After v0.5.15, the production-readiness sequence is complete:
- v0.5.10 → v0.5.11 — observability UI (traces + agent memory)
- v0.5.12 — A: auth depth (RBAC + session lifecycle)
- v0.5.13 — B: deploy story (single-host + container + CI/CD)
- v0.5.14 — D: rate limiting (per-key + per-route + env-tunable)
- v0.5.15 — E: backups (snapshot + retention + scheduling + restore)

## Next milestone

**v0.6.0** — TBD. Production-readiness backlog is closed; next
milestone should reset on product priorities (new features, UI
improvements, performance, etc.). Fresh brainstorming pass.
