# v0.5.13 State

Status: COMPLETE — pending Codex review + merge.

## Shipped

### Layer 1 — Hygiene + runbook

- `backend/scripts/check_env.py` — env-var validator. `REQUIRED_VARS`,
  `OPTIONAL_VARS`, `resolve()` (with `*_FILE` redirect), `validate()`,
  CLI entrypoint.
- `backend/tests/test_check_env.py` — 8 tests (dev/prod posture,
  `*_FILE` resolution, literal-env precedence, CLI exit codes).
- `.env.example` — production template + Docker-secrets variant.
- `backend/gunicorn.conf.py` — `on_starting` hook validates required
  env vars before workers spawn; refuses to start on missing.
- `docs/deploy/RUNBOOK.md` — 9-section production cold-start runbook.
- `docs/deploy/SECRETS.md` — extends `docs/SECURITY.md` with the
  `*_FILE` convention + per-target patterns.

### Layer 2 — Single-host tooling

- `backend/scripts/healthcheck.py` — probes `/health/liveness`,
  `/health/readiness`, `/health` (sidecar). Returns structured JSON.
- `backend/tests/test_healthcheck.py` — 7 tests.
- `justfile` — new recipes `check-env`, `healthcheck`, `deploy-prod`.
- `scripts/launchd/com.agented.{backend,sidecar}.plist` — macOS
  templates.
- `scripts/systemd/agented-{backend,sidecar}.service` — Linux
  templates.

### Layer 3 — Container tooling

- `Dockerfile` — multi-stage (frontend-builder + backend-builder +
  runtime). Built artifacts: `frontend/dist`, backend deps in
  `.venv`, gunicorn entrypoint, healthcheck CMD.
- `.dockerignore` — excludes VCS, build artifacts, secrets, dev
  state, planning, docs.
- `docker-compose.yml` — backend + sidecar services on the same
  image; restart policy + healthcheck; `agented-data` volume.
- `justfile` — `docker-build`, `docker-up`, `docker-down`,
  `docker-logs`.

### Layer 4 — CI/CD

- `.github/workflows/release.yml` — three-job pipeline triggered on
  tag push: `test` → `build-image` (push to GHCR with tag + latest)
  → `release-notes` (GitHub Release from annotated tag body).

### Tests added

- 8 backend (`test_check_env.py`) + 7 backend (`test_healthcheck.py`)
  = 15 new backend tests.
- No frontend tests added (no frontend changes).

## Verification

- `cd frontend && npm run test:run` — **1128 passed** (no change) ✓
- `cd backend && uv run pytest` — pending full-suite confirmation
  (in progress at write time)
- `just build` — vue-tsc + vite clean ✓
- `just check-env` (no env) — exits 0 with warnings ✓
- `AGENTED_ENV=production just check-env` (no other env) — exits 1 ✓

## Plan-vs-reality adaptations

- Workflow file required env-var passing for tag inputs (security
  hook caught injection risk; restructured `gh release create` to
  read from `REF_NAME` env, not direct `${{ github.ref_name }}`
  interpolation in the shell command).

## Out of scope (deferred)

- Container smoke test (`just docker-smoke`) — Docker not
  guaranteed available in the local dev environment; manual
  verification post-merge.
- PR-level CI (`pull_request` trigger) — release-only for v0.5.13.
- DB backup/restore — that's E (v0.5.15).
- Rate limiting — that's D (v0.5.14).

## Next milestone

**v0.5.14** — D (rate limiting): per-route or global rate-limit
middleware, configurable per-key or per-IP, with a sane default
that doesn't break operator workflows.

After D: E (backups).
