---
phase: 02-environment-and-wsgi-foundation
plan: 02
status: complete
started: 2026-02-28
completed: 2026-02-28
tasks_total: 2
tasks_completed: 2
tasks_deviated: 0
verification_level: sanity
---

## Summary

Created `.env.example` documenting all 18 environment variables discovered in the codebase, updated the `just deploy` recipe to use Gunicorn instead of `python run.py`, and added both systemd and launchd process supervisor configurations for restart-on-crash in production.

## Tasks Completed

### Task 1: Create .env.example with all documented environment variables
- **Commit:** `docs(env): add .env.example with all documented environment variables`
- **Result:** Created `backend/.env.example` with 18 environment variables organized into 11 sections (Security, Server, CORS, Database, GitHub, AI/LLM, Plugins, External Tool Homes, Tuning, Timezone, Experimental). Each variable includes type, default value, and description comment. Three additional variables discovered during audit beyond the plan's 15: `CODEX_HOME`, `GEMINI_CLI_HOME`, `OPENCODE_HOME` (used by model discovery service).

### Task 2: Update justfile deploy target and create process supervisor configs
- **Commit:** `feat(deploy): gunicorn deploy target and process supervisor configs`
- **Result:**
  - **justfile:** Deploy recipe now runs `uv run gunicorn -c gunicorn.conf.py` instead of `python run.py`. `dev-backend` recipe unchanged (still uses `python run.py --debug`).
  - **deploy/agented.service:** systemd unit file with `Restart=on-failure`, `RestartSec=3`, `Type=notify`, `KillMode=mixed`. References `gunicorn -c gunicorn.conf.py`.
  - **deploy/com.agented.backend.plist:** launchd plist with `KeepAlive=true`, `RunAtLoad=true`. Both stdout and stderr directed to `/var/log/agented/`.

## Verification Results

All sanity checks passed:
1. `backend/.env.example` exists and contains all 7+ key env vars
2. `justfile` deploy recipe references `gunicorn -c gunicorn.conf.py`
3. `justfile` dev-backend recipe still references `python run.py --debug`
4. `deploy/agented.service` exists with `Restart=on-failure` and `RestartSec=3`
5. `deploy/com.agented.backend.plist` exists with `KeepAlive=true`
6. Backend tests: 911 passed
7. Frontend build: successful

## Deviations

None. All tasks executed as planned.

## Artifacts

| Path | Description |
|------|-------------|
| `backend/.env.example` | Documented environment variable template (18 vars, 11 sections) |
| `justfile` | Updated deploy target using Gunicorn |
| `deploy/agented.service` | systemd unit file for Linux deployment |
| `deploy/com.agented.backend.plist` | launchd plist for macOS deployment |

## Decisions

- **Added 3 extra env vars:** `CODEX_HOME`, `GEMINI_CLI_HOME`, `OPENCODE_HOME` found during codebase audit but not in the plan's original list. Included for completeness since they are referenced by `os.environ.get()` calls.
- **RestartSec=3:** Set to 3 seconds (within the 5-second constraint from the plan), matching the research recommendation.
