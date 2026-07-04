# 26-02 SUMMARY — Render blueprint + install.sh + self-update

**Status:** complete (sanity S6–S9 green; L3 live-infra deferred as planned).

## What shipped

- **`render.yaml`** (repo root) — Render Blueprint declaring `agented-web`
  (Docker build from the existing `Agented/Dockerfile`, `healthCheckPath:
  /health/liveness`), the `agented-sidecar` private service (same image,
  `dockerCommand: python scripts/run_ai_accounts.py`), and a managed
  `agented-postgres` whose `connectionString` is wired into the web service's
  `DATABASE_URL` env — dogfooding the 26-01 Postgres adapter. SQLite stays the
  default everywhere DATABASE_URL is unset.
- **`install.sh`** — single-command installer: `set -euo pipefail`,
  shellcheck-clean (0.11.0), `--dry-run`, idempotent (never clobbers an existing
  `docker-compose.yml`/`.env`), pulls `ghcr.io/ca1773130n/agented:${GHCR_TAG}`
  and runs `docker compose pull && up -d`. No pipx/uv repackaging — the image is
  the distribution unit.
- **`justfile`** — `self-update` target = `docker compose pull && docker compose
  up -d` (GHCR_TAG-overridable).
- **`README.md`** — Deploy-to-Render button, install one-liner + `just
  self-update` in Quickstart, docs table row.
- **`docs/deploy.md`** + **`docs/deploy.ko.md`** — 1:1 bilingual guide covering
  one-click Render, single-install, self-update, and the optional Postgres
  DATABASE_URL story (locale-suffix + lang-switcher header per docs/i18n.md).

## Build-context risk (research pitfall #5) — documented, not silently shipped

The Dockerfile needs the sibling `ai-accounts/` tree. Render builds with the
connected repo as context root, so `render.yaml` uses `dockerContext: .` +
`dockerfilePath: ./Agented/Dockerfile` and REQUIRES the connected repo to be the
parent monorepo (both `Agented/` and `ai-accounts/` as siblings). The alternate
vendored-copy/submodule workaround is documented inline in `render.yaml` and in
`docs/deploy.md`.

## S-gates

- S6 render.yaml parses + declares services/databases + DATABASE_URL wired — PASS
- S7 shellcheck clean + `--dry-run` prints commands — PASS
- S8 `just self-update` present — PASS
- S9 docs/deploy.{md,ko.md} exist + README references render — PASS

## Deferred (L3, needs live infra)

- DEFER-26-01: real Render blueprint deploy confirming sibling build context.
- DEFER-26-02: live `just self-update` pull-and-restart with schema survival.

No Dockerfile/docker-compose.yml structural changes (reuse, not rewrite).
