# Backup + restore runbook

v0.5.15. Companion to `docs/deploy/RUNBOOK.md`. Covers what gets
backed up, how to schedule snapshots, off-site sync, and the restore
procedure.

## What gets backed up

- `agented.db` — main app DB (users, RBAC, sessions, agents, projects,
  audit log, etc.).
- `ai_accounts.db` — sidecar DB (AI-backend accounts, OAuth state,
  per-account encrypted vault).

## What does NOT get backed up

- Vault keys (`AGENTED_VAULT_KEYS`, `AI_ACCOUNTS_VAULT_KEY`,
  `AGENTED_API_KEY`). These live in `.env` / macOS Keychain /
  Docker secrets per `docs/deploy/SECRETS.md`. Back them up
  separately. **Without the vault keys, the per-account secrets
  in `ai_accounts.db` cannot be decrypted.**
- Application source code. Use git.
- Log files. Out of scope.

## Manual snapshot

```bash
just backup
```

Effects:
1. `sqlite3.Connection.backup()` produces atomic online snapshots of
   both DBs into `$AGENTED_BACKUP_DIR` (default `backend/backups/`).
2. Filenames: `agented-2026-05-04T22-30-15Z.db`,
   `ai_accounts-2026-05-04T22-30-15Z.db`.
3. If `BACKUP_REMOTE_CMD` is set, each snapshot is piped through
   it (with `{file}` replaced by the snapshot path).
4. Snapshots older than `BACKUP_RETENTION_DAYS` (default 30) are
   removed.
5. JSON summary printed to stdout for scripted callers.

Exit codes:
- `0` — all snapshots succeeded (remote sync failures don't block 0).
- `1` — at least one source DB was missing or a snapshot raised.

## Off-site sync

Set `BACKUP_REMOTE_CMD` to any shell command that pushes a single
file to your storage of choice. The token `{file}` is replaced with
the snapshot path.

```bash
# rclone (most flexible — supports S3, B2, GCS, OneDrive, ...)
export BACKUP_REMOTE_CMD='rclone copy {file} agented-backup:'

# AWS CLI
export BACKUP_REMOTE_CMD='aws s3 cp {file} s3://agented-backups/'

# scp / rsync
export BACKUP_REMOTE_CMD='scp {file} backup-host:agented/'
export BACKUP_REMOTE_CMD='rsync {file} backup-host:/backups/agented/'
```

The local copy is always preserved — remote-sync failures only mark
`remote_synced: false` in the JSON summary, never abort the run.

For credential management: rclone configs go in
`~/.config/rclone/rclone.conf` (chmod 600); AWS creds in `~/.aws/`.
The Docker container mode (`just docker-up`) doesn't ship `rclone`
or `aws-cli` in the image — use a host-side cron / launchd timer
for off-site sync if running containerised.

## Scheduling

Three template options. Pick one based on platform.

### macOS launchd

```bash
cp scripts/launchd/com.agented.backup.plist ~/Library/LaunchAgents/
# Edit REPLACE_ME_REPO_PATH first.
launchctl load ~/Library/LaunchAgents/com.agented.backup.plist
```

Runs daily at 03:00 local time. Logs to
`backend/backup.log`.

### Linux systemd timer

```bash
mkdir -p ~/.config/systemd/user
cp scripts/systemd/agented-backup.service ~/.config/systemd/user/
cp scripts/systemd/agented-backup.timer   ~/.config/systemd/user/
# Edit REPLACE_ME placeholders first.
systemctl --user daemon-reload
systemctl --user enable --now agented-backup.timer
journalctl --user -u agented-backup -f   # tail
```

### Cron

```bash
crontab -e
# Paste from scripts/cron/backup-crontab.example, adjusting paths.
```

## Restore

**Stop the service first** — `restore.py` refuses to overwrite a
DB whose `*.db-wal` companion was modified within the last 60
seconds.

```bash
just kill                 # single-host
# or systemctl --user stop agented-backend agented-sidecar
# or just docker-down

just restore
```

Interactive flow:
1. Lists the 10 newest snapshots for the chosen target.
2. Prompts to pick by index.
3. Takes a pre-restore safety snapshot of the current DB
   (`{label}-pre-restore-{ts}.db`) so you can recover if the
   restore was the wrong choice.
4. Copies the chosen snapshot over the target DB.
5. Removes any stale `*.db-wal` / `*.db-shm` companions.
6. Reminds you to restart the service.

Non-interactive:

```bash
backend && uv run python scripts/restore.py \
  --target agented \
  --snapshot backend/backups/agented-2026-05-04T03-00-00Z.db \
  --yes
```

After restore, restart the service per `docs/deploy/RUNBOOK.md`.

## Verification

Validate a snapshot before relying on it:

```bash
sqlite3 backend/backups/agented-2026-05-04T03-00-00Z.db "PRAGMA integrity_check"
# expected output: ok
```

Periodic restore drills (recommended monthly):

1. Spin up a scratch checkout in a separate directory.
2. Restore yesterday's snapshot into it.
3. Boot the app, validate auth + recent data.
4. Tear down the scratch instance.

## Disaster recovery checklist

In the event of corruption or accidental deletion:

1. Stop both services (backend + sidecar) immediately.
2. List `$AGENTED_BACKUP_DIR` — pick the most recent KNOWN-GOOD
   snapshot.
3. `just restore --target agented --snapshot <path>`
4. `just restore --target ai_accounts --snapshot <path>`
   (the timestamps from the same `just backup` run match — pair
   them up).
5. Restart services.
6. Run `sqlite3 backend/agented.db "PRAGMA integrity_check"` and
   `sqlite3 backend/ai_accounts.db "PRAGMA integrity_check"`.
7. Verify auth still works (login a known user).
8. If vault keys were ALSO lost, the per-account encrypted secrets
   in `ai_accounts.db` are unrecoverable — operator must re-link
   AI-backend accounts via the wizard.
