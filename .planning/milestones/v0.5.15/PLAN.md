# v0.5.15 — Backups

Spec: `docs/superpowers/specs/2026-05-04-v0.5.15-backups-design.md`

E-E piece. Online SQLite snapshots for both DBs (`agented.db` +
`ai_accounts.db`) via `sqlite3.Connection.backup()`, optional
off-site sync via `BACKUP_REMOTE_CMD` shell template, retention
policy via `BACKUP_RETENTION_DAYS`, scheduling templates (cron +
launchd + systemd timer), restore procedure with pre-restore safety
snapshot + live-DB guard.

After v0.5.15 the E (backups) piece of the v0.5.x post-onboarding
cleanup is done. The full A→E sequence (auth depth, deploy story,
rate limiting, backups) closes the production-readiness backlog.
