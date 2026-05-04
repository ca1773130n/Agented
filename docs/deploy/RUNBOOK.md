# Production deploy runbook

End-to-end procedure for standing up Agented in production. Two
targets are supported: **single-host** (macOS launchd or Linux
systemd) and **container** (Docker Compose). Pick one — they
share `.env` as the canonical configuration source.

## 1. Prerequisites

- Python 3.10+ (`uv` will install if missing)
- Node 20+ (managed via `mise` per project setup)
- `just` (recipe runner)
- `uv` (Python package manager)
- For container target: Docker Desktop (macOS) or Docker Engine + Compose v2 (Linux)
- For macOS Keychain integration: built-in `security` CLI
- For systemd target: a Linux user with `--user` services enabled

## 2. Initial setup

```bash
git clone git@github.com:ca1773130n/Agented.git
cd Agented
bash scripts/setup.sh
```

`setup.sh` provisions Python deps via `uv`, frontend deps via `npm`,
and the local SQLite DB at `agented.db`.

## 3. Provision secrets

Three pathways. Pick one or layer them.

### 3a. `.env` file (canonical)

```bash
cp .env.example .env
# Generate fresh secret values:
echo "AGENTED_API_KEY=$(openssl rand -hex 32)" >> .env.tmp
echo "AI_ACCOUNTS_API_KEY=$(openssl rand -hex 32)" >> .env.tmp
echo "AI_ACCOUNTS_VAULT_KEY=$(openssl rand -base64 32)" >> .env.tmp
# AGENTED_VAULT_KEYS uses Fernet (cryptography lib) and must be base64-encoded.
echo "AGENTED_VAULT_KEYS=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" >> .env.tmp
# Merge .env.tmp into .env, then:
rm .env.tmp
chmod 600 .env  # sole-user-readable
```

### 3b. macOS Keychain (extends `docs/SECURITY.md`)

For the highest-value secrets, store in the Keychain and export
into the shell environment via `~/.zshrc`:

```bash
security add-generic-password -a "$USER" -s 'agented-api-key' -w "$(openssl rand -hex 32)"
security add-generic-password -a "$USER" -s 'agented-vault-key' -w "$(openssl rand -base64 32)"
```

Add to `~/.zshrc`:

```bash
export AGENTED_API_KEY="$(security find-generic-password -a "$USER" -s 'agented-api-key' -w 2>/dev/null)"
export AI_ACCOUNTS_VAULT_KEY="$(security find-generic-password -a "$USER" -s 'agented-vault-key' -w 2>/dev/null)"
```

`launchd` plists shipped under `scripts/launchd/` source `~/.zshrc`
during startup; see step 5a.

### 3c. Docker secrets (container target)

For Docker Compose, mount secret files and use the `*_FILE`
convention:

```yaml
# In docker-compose.override.yml (gitignored):
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

Then `chmod 600 secrets/*.txt` and add `secrets/` to `.gitignore`
(already covered by the broader `.env*` rule? — no, add explicitly).

## 4. Validate

```bash
just check-env
```

Exits 0 with no output on success. Exits 1 with a table of missing
required vars otherwise. In dev posture (`AGENTED_ENV` unset or not
`production`), it emits warnings but exits 0.

## 5. Start

### 5a. Single-host (macOS / Linux)

```bash
just deploy-prod
```

This recipe:
1. Runs `just check-env` (aborts on failure)
2. Builds the frontend (`vue-tsc + vite build → frontend/dist/`)
3. Stops any existing instance (`just kill`)
4. Starts the sidecar daemonized; waits for `:20001/health` 200
5. Starts gunicorn daemonized
6. Prints PID + log paths

For a service-managed deploy, copy the templates:

```bash
# macOS:
cp scripts/launchd/com.agented.*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.agented.backend.plist
launchctl load ~/Library/LaunchAgents/com.agented.sidecar.plist

# Linux:
mkdir -p ~/.config/systemd/user
cp scripts/systemd/agented-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agented-backend.service agented-sidecar.service
```

Edit each unit file's `WorkingDirectory` / `EnvironmentFile` paths
before installing.

### 5b. Container (Docker Compose)

The container build needs the sibling `ai-accounts/` repo at the
parent of Agented (same layout as dev — see `CLAUDE.md`):

```
parent/
├── Agented/
└── ai-accounts/
```

Both backend (`pyproject.toml`) and frontend (`package.json`) have
path deps that reference `../../ai-accounts/packages/*`. The
Dockerfile builds from the parent directory so those resolve.

```bash
just docker-build      # cd .. && docker build -f Agented/Dockerfile .
just docker-up         # starts backend + sidecar
just docker-logs       # tails both services
```

Frontend is served as static assets by the backend container in this
mode (no Vite dev server).

## 6. Healthcheck

```bash
just healthcheck
```

Probes:
- `:20000/health/liveness` (200?)
- `:20000/health/readiness` (200 + DB ok + scheduler ok?)
- `:20001/health` (sidecar)

Exits 0 if all green; nonzero with structured stderr otherwise.

## 7. Rotation + upgrade

### Rotating secrets

- API keys (`AGENTED_API_KEY`, `AI_ACCOUNTS_API_KEY`):
  re-run `openssl rand -hex 32`, update `.env` or Keychain, restart.
- Vault key (`AI_ACCOUNTS_VAULT_KEY`):
  **destructive** — re-encrypt the secrets table; stop the sidecar
  before doing this. Out of scope for online rotation.
- GitHub PAT: `scripts/install-github-pat-keychain.sh <new-pat>`
  (see `docs/SECURITY.md`).
- Per-account AI-backend keys: rotate in the operator UI
  (Settings → AI accounts).

### Upgrading

```bash
git pull
bash scripts/setup.sh    # pick up new deps + run migrations
just deploy-prod
just healthcheck         # confirm
```

For containers:

```bash
git pull
just docker-build
just docker-down
just docker-up
just healthcheck
```

## 8. Rollback

Single-host:

```bash
git checkout <previous-tag>
bash scripts/setup.sh
just deploy-prod
```

Container (the compose file interpolates `${GHCR_TAG:-latest}`):

```bash
docker pull ghcr.io/ca1773130n/agented:<previous-tag>
docker compose down
GHCR_TAG=<previous-tag> docker compose up -d
```

DB migrations are **forward-only**. If a migration is incompatible
with the previous app version, rolling back the binary alone is not
sufficient — restore the DB from backup (E milestone, v0.5.15).

## 9. CI/CD release workflow setup

The `.github/workflows/release.yml` workflow fires on every `v*` tag
push. It checks out both Agented and the sibling `ai-accounts` repo,
runs the test suite, builds the multi-stage Docker image, pushes
to GHCR, and creates a GitHub Release.

**Cross-repo checkout requires a PAT.** The default `GITHUB_TOKEN`
is scoped to the repo running the workflow; checking out
`ca1773130n/ai-accounts` from within Agented's workflow needs a
token with read access to that separate repository.

Setup (one-time):

1. Create a fine-grained personal access token:
   - Go to https://github.com/settings/personal-access-tokens
   - Click "Generate new token"
   - Repository access: `ca1773130n/ai-accounts` only
   - Repository permissions: Contents → Read-only
   - Expiration: longest available (the workflow won't recover from
     a silent expiration; calendar a renewal)
2. Save the token value
3. In Agented's GitHub Settings → Secrets and variables → Actions:
   - New repository secret named `AI_ACCOUNTS_TOKEN`
   - Paste the token

Without this secret, the release workflow fails at the
"Checkout ai-accounts" step with a 404. The build won't reach the
docker push.

## 10. Logs + observability

- Single-host gunicorn logs: `backend/backend.log` (default;
  configurable via `LOG_LEVEL`).
- Sidecar logs: `backend/sidecar.log`.
- launchd logs: `~/Library/Logs/agented-*.log`.
- systemd logs: `journalctl --user -u agented-backend -f`.
- Container logs: `just docker-logs`.

The session-events audit log shipped in v0.5.12 is queryable via
`GET /admin/auth/session-events` (admin-only).
