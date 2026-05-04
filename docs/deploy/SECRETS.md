# Secrets pathway extensions (v0.5.13)

Builds on `docs/SECURITY.md`. That document covers what NOT to commit
and how to rotate. This one covers HOW secrets reach the running
process across the two deploy targets.

## The `*_FILE` convention

Any environment variable named `<NAME>_FILE` is resolved at startup
by `scripts/check_env.py:resolve()` to the contents of the file at
the given path. This unifies three distinct secret sources behind
one mechanism:

| Source | Variable form |
|---|---|
| Literal env var | `AGENTED_API_KEY=abc` |
| Mounted file (Docker secret, host secret-mount) | `AGENTED_API_KEY_FILE=/run/secrets/agented_api_key` |
| Keychain export from `~/.zshrc` | `AGENTED_API_KEY=$(security find-generic-password ...)` |

Literal env wins if both are set.

## Per-target patterns

### Single-host (macOS)

Recommended: macOS Keychain stores the high-value secrets, exported
into the shell environment via `~/.zshrc`. `launchd` plists run
under the operator's user, so `~/.zshrc` is sourced if you specify
the launch script as `bash -lc 'cd ... && exec gunicorn ...'`.

```xml
<!-- scripts/launchd/com.agented.backend.plist excerpt -->
<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd ~/Developer/Projects/Agented/backend && exec uv run gunicorn -c gunicorn.conf.py</string>
</array>
```

Lower-value vars (`LOG_LEVEL`, `GUNICORN_BIND`) live in `.env`.

### Single-host (Linux)

Recommended: `.env` file under restrictive perms (`chmod 600`) plus
systemd `EnvironmentFile=` directive. systemd loads the file before
exec; Python doesn't need to re-load it.

```ini
# scripts/systemd/agented-backend.service excerpt
[Service]
EnvironmentFile=/home/operator/Agented/.env
WorkingDirectory=/home/operator/Agented/backend
ExecStart=/home/operator/.local/bin/uv run gunicorn -c gunicorn.conf.py
```

Linux Keychain alternatives (`pass`, `libsecret`) work via the same
shell-export-into-env pattern as macOS.

### Container

Recommended: Docker secrets via `docker-compose.yml`. The compose
file mounts secrets as files at `/run/secrets/<name>`; the image
reads them via the `*_FILE` convention.

```yaml
services:
  agented-backend:
    environment:
      AGENTED_API_KEY_FILE: /run/secrets/agented_api_key
      AI_ACCOUNTS_VAULT_KEY_FILE: /run/secrets/ai_accounts_vault_key
    secrets:
      - agented_api_key
      - ai_accounts_vault_key

secrets:
  agented_api_key:
    file: ./secrets/agented_api_key.txt
  ai_accounts_vault_key:
    file: ./secrets/ai_accounts_vault_key.txt
```

Add `secrets/` to `.gitignore`. `chmod 600 secrets/*.txt`.

`.env` is also loaded via `env_file:` in compose — that's where
non-secret config lives (`AGENTED_ENV=production`, `LOG_LEVEL=info`).

## Validation

`just check-env` runs `scripts/check_env.py` which iterates
`REQUIRED_VARS` and exits nonzero if any are missing. The validator
is also wired into `gunicorn.conf.py`'s `on_starting` hook so the
server refuses to start on missing required vars rather than booting
in a silently-degraded state.

In dev posture (`AGENTED_ENV != "production"`), missing vars emit
warnings but don't block startup.
