# Deploy Agented

**Languages:** English (canonical) · [한국어](deploy.ko.md)

Three ways to run Agented in production, from lowest to highest effort. The
prebuilt container image (`ghcr.io/ca1773130n/agented`) is the distribution
unit throughout — you never need a local Python/Node toolchain to deploy or
update.

| Path | Effort | When |
|---|---|---|
| [1. Render Blueprint](#1-render-blueprint) | Blueprint | hosted; managed Postgres; needs a parent-monorepo checkout |
| [2. Single-install script](#2-single-install-script) | one command | your own host / VM with Docker |
| [3. Self-update](#3-self-update) | one command | upgrade an existing install |

---

## 1. Render Blueprint

> **Not one-click from the standalone repo.** Render clones only the connected
> repository and uses it as the Docker build context. Because the image needs
> the sibling `ai-accounts/` tree (see the caveat below), you must connect a
> **parent monorepo** that contains both `Agented/` and `ai-accounts/`, with a
> copy of this `render.yaml` at its root. If you connect the standalone
> `Agented` repo, the build fails at the `COPY ai-accounts/ …` step.

The repo ships a [`render.yaml`](../render.yaml) Blueprint that declares:

- **`agented-web`** — the backend + static frontend, built from the existing
  `Dockerfile` (`healthCheckPath: /health/liveness`).
- **`agented-sidecar`** — the `ai-accounts` identity service on `:20001`,
  reusing the same image with `dockerCommand: python scripts/run_ai_accounts.py`.
- **`agented-postgres`** — a managed Postgres database whose connection string
  is injected into the web service's **`DATABASE_URL`** env.

That last wire **dogfoods the Postgres adapter** (Phase 26-01): when
`DATABASE_URL` is set the backend runs on Postgres; everywhere else it stays on
the zero-config SQLite default (see [§Optional Postgres](#optional-postgres-database_url)).

### Build-context caveat (read before deploying)

The `Dockerfile` requires the **sibling `ai-accounts/` tree** at build time —
backend `pyproject.toml` and frontend `package.json` both reference
`../../ai-accounts/packages/*` path deps. Locally this is satisfied by building
from the parent directory (`cd .. && docker build -f Agented/Dockerfile .`).

Render builds with the **connected repository as the Docker context root**, so
`render.yaml` uses `dockerContext: .` + `dockerfilePath: ./Agented/Dockerfile`.
For the build to resolve `ai-accounts/`, **the connected Render repo must be a
parent monorepo containing both `Agented/` and `ai-accounts/` as siblings.**

If you connect the standalone `Agented` repo (no sibling present), the build
fails at the `COPY ai-accounts/ …` step. Two workarounds:

1. **Connect the parent monorepo** (recommended) — keeps the paths in
   `render.yaml` as-is.
2. **Vendor `ai-accounts/`** into the Agented repo (git submodule or copy),
   then set `dockerContext: .` with `dockerfilePath: Dockerfile`.

> A real Render blueprint deploy (confirming the sibling build context end to
> end) is tracked as deferred live-infra validation for this phase.

---

## 2. Single-install script

On any host with Docker + `docker compose` (v2):

```bash
curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/main/install.sh | bash
```

[`install.sh`](../install.sh):

- pulls `ghcr.io/ca1773130n/agented:${GHCR_TAG:-latest}`,
- ensures a `docker-compose.yml` and a `.env` are present (never clobbering an
  existing one — customizations survive),
- runs `docker compose pull && docker compose up -d`.

It is **idempotent** — re-running is a no-op upgrade. Preview the exact commands
without executing anything:

```bash
./install.sh --dry-run
```

Environment knobs: `GHCR_TAG` (image tag, default `latest`), `INSTALL_DIR`
(where the compose file is written, default the current directory). Add secrets
to `.env` — see [docs/deploy/SECRETS.md](deploy/SECRETS.md).

---

## 3. Self-update

To move an existing install to the latest image:

```bash
just self-update
```

This runs `docker compose pull && docker compose up -d` — the **image is the
update unit**, so there is no source pull or rebuild. Pin a specific version
with `GHCR_TAG`:

```bash
GHCR_TAG=v0.10.0 just self-update
```

Re-running [`install.sh`](../install.sh) does the same thing on a host without
the repo checked out.

> A live self-update pull-and-restart (old → new image, DB schema survives) is
> tracked as deferred live-infra validation for this phase.

---

## Optional Postgres (`DATABASE_URL`)

> [!WARNING]
> **Postgres support is EXPERIMENTAL and not production-ready yet.** The
> Phase-26 DB-API adapter is a working foundation and the SQLite default is
> fully green, but full cross-backend parity is incomplete (tracked as
> **DEFER-26-01**, PR #289). Known gaps on Postgres: fresh-schema DDL
> (SQLite `fts5`/`randomblob`, one cyclic FK), `row_factory`/`cursor.description`
> compat that currently breaks auth on PG, the ai-accounts sidecar still reading
> admin keys from SQLite, and some untranslated date/catalog SQL. **Use SQLite
> for production** until parity lands — the Render blueprint's managed Postgres
> is likewise experimental for now.

**SQLite is the zero-config default.** With `DATABASE_URL` **unset**, behavior
is byte-for-byte unchanged — the compose stack and the local dev flow use the
embedded SQLite database at `AGENTED_DB_PATH`.

Postgres support (Phase 26-01) is purely **additive** and activated only when
`DATABASE_URL` is set:

```bash
export DATABASE_URL="postgresql://user:pass@host:5432/agented"
```

The Render blueprint sets this automatically from its managed database. On a
self-hosted install you can point at any Postgres instance by adding
`DATABASE_URL` to `.env`. Leave it unset to keep SQLite.

---

## See also

- [Runbook](deploy/RUNBOOK.md) · [Backup](deploy/BACKUP.md) · [Secrets](deploy/SECRETS.md)
- [Security](SECURITY.md)
- [i18n conventions](i18n.md)
