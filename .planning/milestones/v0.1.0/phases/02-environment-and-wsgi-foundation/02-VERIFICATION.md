---
phase: 02-environment-and-wsgi-foundation
verified: 2026-02-27T18:11:44Z
status: passed
score:
  level_1: 12/12 sanity checks passed
  level_2: N/A — no proxy metrics applicable (infrastructure phase)
  level_3: 2/2 deferred (tracked below)
re_verification: false
gaps: []
deferred_validations:
  - id: DEFER-02-01
    description: "Concurrent SSE load test — 10 simultaneous SSE connections, verify all receive all events with no drops under gevent worker"
    metric: "SSE event delivery rate"
    target: "10/10 connections receive all events; no WORKER TIMEOUT in Gunicorn logs"
    depends_on: "Phase 2 complete (Gunicorn running), Phase 3 complete (SSE auth)"
    validates_at: "phase-05-observability-and-process-reliability"
    tracked_in: "STATE.md"
  - id: DEFER-02-02
    description: "workers=1 startup assertion — enforce constraint in code to prevent accidental misconfiguration with workers>1"
    metric: "Presence of startup assertion in gunicorn.conf.py or app factory"
    target: "assert workers == 1 present with explanatory message"
    depends_on: "Phase 5 complete (structured logging makes assertion visible)"
    validates_at: "phase-06-code-quality-and-maintainability"
    tracked_in: "STATE.md"
human_verification: []
---

# Phase 02: Environment and WSGI Foundation — Verification Report

**Phase Goal:** Replace the dev-server entry-point with a production-grade Gunicorn + gevent WSGI stack, add .env / secret-key management, and provide deployment helpers (justfile target, systemd/launchd configs).
**Verified:** 2026-02-27T18:11:44Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Verification Summary by Tier

### Level 1: Sanity Checks

All 12 checks from EVAL.md executed directly. Results:

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| S1 | Dependencies installed and importable | PASS | `uv sync` exits 0; `import gevent; import dotenv; import apscheduler; import pytz` all succeed |
| S2 | Gunicorn configuration file is valid | PASS | `uv run gunicorn --check-config -c gunicorn.conf.py` exits 0 |
| S3 | gunicorn.conf.py enforces workers=1 and worker_class=gevent | PASS | `workers = 1` (line 28), `worker_class = "gevent"` (line 36) confirmed by exec() assertion |
| S4 | preload_app is NOT set in gunicorn.conf.py | PASS | `grep "^preload_app" gunicorn.conf.py` returns no match — only present in a comment |
| S5 | load_dotenv() called before create_app() in run.py | PASS | `load_dotenv()` at line 6; `from app import create_app` at line 22; `create_app()` at line 25 — correct order confirmed |
| S6 | SECRET_KEY is stable across two consecutive create_app() calls | PASS | Two consecutive calls return identical 64-char hex key — `_get_secret_key()` persists to `.secret_key` file |
| S7 | .env and .secret_key are gitignored | PASS | `.gitignore` contains `.env` (exact match line) and `backend/.secret_key` (exact match line) |
| S8 | .env.example covers all known environment variables | PASS | `grep -c` returns 10/10 — all required variables (SECRET_KEY, GUNICORN_BIND, CORS_ALLOWED_ORIGINS, AGENTED_DB_PATH, GITHUB_WEBHOOK_SECRET, ANTHROPIC_API_KEY, LOG_LEVEL, SSE_REPLAY_LIMIT, STALE_CONVERSATION_*, STALE_EXECUTION_*) present |
| S9 | just deploy uses Gunicorn (not python run.py) | PASS | `justfile` deploy recipe: `cd backend && uv run gunicorn -c gunicorn.conf.py &` — no `python run.py` in deploy recipe |
| S10 | dev-backend recipe preserved | PASS | `dev-backend` recipe confirmed: `cd backend && uv run python run.py --debug` unchanged |
| S11 | Backend test suite passes with no regressions | PASS | `uv run pytest --tb=short -q` — **911 passed in 123.96s** (0 failed, 0 errors) |
| S12 | Process supervisor configs exist with correct restart semantics | PASS | `Restart=on-failure` + `RestartSec=3` in `deploy/agented.service`; `<key>KeepAlive</key><true/>` in `deploy/com.agented.backend.plist` |

**Level 1 Score: 12/12 passed**

### Level 2: Proxy Metrics

Not applicable. Per EVAL.md rationale: this phase implements infrastructure plumbing. All success criteria are directly and immediately verifiable via exact binary-outcome commands. No proxy approximation is more informative than the direct sanity checks above.

### Level 3: Deferred Validations

2 items tracked for future phases (see frontmatter `deferred_validations`):

| ID | Validation | Metric | Target | Validates At |
|----|-----------|--------|--------|--------------|
| DEFER-02-01 | Concurrent SSE load test | SSE event delivery rate | 10/10 connections, no WORKER TIMEOUT | phase-05-observability-and-process-reliability |
| DEFER-02-02 | workers=1 startup assertion enforcement | Code guard presence | `assert workers == 1` with message | phase-06-code-quality-and-maintainability |

---

## Goal Achievement

### Observable Truths (from Plan 01 must_haves)

| # | Truth | Verification Level | Status | Evidence |
|---|-------|--------------------|--------|----------|
| 1 | pyproject.toml lists gevent>=24.10.1, python-dotenv>=1.0.0, APScheduler>=3.10.0, pytz>=2023.3 as dependencies | Level 1 | PASS | All four lines confirmed in `backend/pyproject.toml` `dependencies` list |
| 2 | uv sync completes without errors and all four are importable | Level 1 | PASS | `uv sync` exits 0; all four imports succeed |
| 3 | run.py calls load_dotenv() before create_app() | Level 1 | PASS | `load_dotenv()` at line 6, `from app import create_app` at line 22 |
| 4 | SECRET_KEY loaded from env var first, then .secret_key file, then generate-and-persist — never auto-regenerated on restart | Level 1 | PASS | `_get_secret_key()` implements three-tier fallback; two consecutive calls return identical 64-char key |
| 5 | gunicorn.conf.py exists with workers=1, worker_class='gevent', and single-worker constraint comment | Level 1 | PASS | File exists; `workers = 1` at line 28; `worker_class = "gevent"` at line 36; 55-line docstring explains constraint with service list |
| 6 | .gitignore includes .env and .secret_key entries | Level 1 | PASS | `.env` and `backend/.secret_key` both present as exact-match lines |

### Observable Truths (from Plan 02 must_haves)

| # | Truth | Verification Level | Status | Evidence |
|---|-------|--------------------|--------|----------|
| 7 | `just deploy` uses Gunicorn (not python run.py) | Level 1 | PASS | `cd backend && uv run gunicorn -c gunicorn.conf.py &` in deploy recipe |
| 8 | .env.example documents all environment variables with types, defaults, descriptions | Level 1 | PASS | 18 vars in 11 sections; 10/10 key variables confirmed by grep count |
| 9 | systemd unit (deploy/agented.service) specifies Restart=on-failure and RestartSec<=5 | Level 1 | PASS | `Restart=on-failure`, `RestartSec=3` — 3s is within the 5s requirement |
| 10 | launchd plist (deploy/com.agented.backend.plist) specifies KeepAlive=true | Level 1 | PASS | `<key>KeepAlive</key><true/>` confirmed |
| 11 | A fresh clone copying .env.example to .env reaches a runnable state | Level 1 | PASS (indirect) | All env vars have documented defaults; SECRET_KEY auto-generates; backend test suite passes on isolated DB without .env |

### Required Artifacts

| Artifact | Expected | Exists | Sanity | Wired |
|----------|----------|--------|--------|-------|
| `backend/gunicorn.conf.py` | Gunicorn config with gevent worker | YES (61 lines) | PASS — `--check-config` exits 0 | PASS — `wsgi_app = "run:application"` |
| `backend/pyproject.toml` | Updated deps with gevent, python-dotenv, APScheduler, pytz | YES | PASS — all four lines present | PASS — `uv sync` installs them |
| `backend/run.py` | Dev entry point with dotenv loading | YES (89 lines) | PASS — `load_dotenv()` at line 6 | PASS — `create_app()` called after load_dotenv() |
| `backend/app/__init__.py` | App factory with `_get_secret_key()` | YES (299 lines) | PASS — `_get_secret_key()` defined at line 25 | PASS — called at `SECRET_KEY=_get_secret_key()` line 62 |
| `backend/.env.example` | Documented env var template | YES (74 lines) | PASS — 10/10 key vars present | PASS — documents `SECRET_KEY` used by `create_app()` |
| `justfile` | Updated deploy target using Gunicorn | YES | PASS — `gunicorn -c gunicorn.conf.py` present | PASS — `dev-backend` still uses `python run.py --debug` |
| `deploy/agented.service` | systemd unit with restart-on-failure | YES (29 lines) | PASS — valid INI format | PASS — `ExecStart` references `gunicorn -c gunicorn.conf.py` |
| `deploy/com.agented.backend.plist` | launchd plist with KeepAlive | YES (34 lines) | PASS — valid XML plist | PASS — ProgramArguments includes `gunicorn.conf.py` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `backend/run.py` | `backend/app/__init__.py` | `load_dotenv()` runs before `create_app()` | WIRED | `load_dotenv()` line 6, `from app import create_app` line 22, `create_app()` line 25 — ordering confirmed |
| `backend/gunicorn.conf.py` | `backend/run.py` | `wsgi_app = "run:application"` | WIRED | Line 60 of gunicorn.conf.py: `wsgi_app = "run:application"` |
| `backend/app/__init__.py` | `backend/.secret_key` | `_get_secret_key()` reads/writes `.secret_key` file | WIRED | `key_file = Path(__file__).parent.parent / ".secret_key"` at line 39 |
| `justfile` | `backend/gunicorn.conf.py` | deploy target invokes `gunicorn -c gunicorn.conf.py` | WIRED | `cd backend && uv run gunicorn -c gunicorn.conf.py &` |
| `deploy/agented.service` | `backend/gunicorn.conf.py` | `ExecStart` invokes gunicorn with config | WIRED | `ExecStart=/opt/agented/backend/.venv/bin/gunicorn -c gunicorn.conf.py` |
| `backend/.env.example` | `backend/app/__init__.py` | Documents `SECRET_KEY`, `CORS_ALLOWED_ORIGINS` used by `create_app()` | WIRED | `SECRET_KEY` section at line 12; `CORS_ALLOWED_ORIGINS` at line 23 |

---

## WebMCP Verification

WebMCP verification skipped — phase does not modify frontend views. All changes are backend-only (per EVAL.md: "WebMCP tool definitions skipped — phase does not modify frontend views").

---

## Anti-Patterns Found

None. Scanned `backend/gunicorn.conf.py`, `backend/run.py`, and `backend/app/__init__.py` for TODO/FIXME/XXX/HACK/PLACEHOLDER comments and stub implementations. No issues found.

Notable quality observations:
- `gunicorn.conf.py` docstring (lines 1-16) explicitly documents the six in-memory services that mandate `workers=1` — well-reasoned constraint documentation
- `_get_secret_key()` has correct `OSError` handling for read-only filesystems (falls back to ephemeral key rather than crashing)
- `preload_app` is not set, consistent with RESEARCH.md Pitfall 3

---

## Requirements Coverage

| Requirement ID | Description | Status | Artifact |
|----------------|-------------|--------|----------|
| ENV-01 | Stable SECRET_KEY across restarts | PASS | `_get_secret_key()` in `app/__init__.py` |
| ENV-02 | All env vars documented in .env.example | PASS | `backend/.env.example` (18 vars, 11 sections) |
| DEP-01 | Gunicorn + gevent as production server | PASS | `backend/gunicorn.conf.py` (workers=1, worker_class=gevent) |
| DEP-02 | Gunicorn configuration file | PASS | `backend/gunicorn.conf.py` validated by `--check-config` |
| DEP-03 | `just deploy` uses Gunicorn | PASS | `justfile` deploy recipe updated |
| DEP-04 | Process supervisor restart-on-crash within 5s | PASS | systemd `RestartSec=3`; launchd `KeepAlive=true` |

---

## Deferred Validations (Level 3)

### DEFER-02-01: Concurrent SSE load test

- **What:** Verify gevent cooperative scheduling allows one worker to serve 10+ simultaneous SSE subscribers without connection drops or event delivery failures
- **Target:** 10/10 SSE connections receive all events; no `WORKER TIMEOUT` in Gunicorn logs; no connection drops within 5 minutes
- **Validates at:** phase-05-observability-and-process-reliability
- **Depends on:** Phase 2 complete (Gunicorn running), Phase 3 complete (SSE auth in place)
- **Risk if unmet:** A blocking C extension or non-monkey-patched I/O call would freeze all SSE connections simultaneously; no error would be produced

### DEFER-02-02: workers=1 startup assertion enforcement

- **What:** A startup assertion enforces the `workers=1` constraint to prevent accidental misconfiguration in production
- **Target:** `assert workers == 1, "workers > 1 is unsafe until Redis pub/sub replaces in-memory SSE state"` present in gunicorn.conf.py or app factory
- **Validates at:** phase-06-code-quality-and-maintainability
- **Depends on:** Phase 5 complete (structured logging makes assertion visible in production logs)
- **Risk if unmet:** A future operator sets `workers=4`; in-memory SSE state fragments silently with no error output

---

## Human Verification Required

None. All 12 sanity checks have binary, automated outcomes. No visual, qualitative, or subjective verification is needed for this infrastructure phase.

---

## Summary

Phase 02 fully achieves its goal: the production-grade Gunicorn + gevent WSGI stack is in place, secret-key management is implemented with stable persistence, and deployment helpers are provided for both Linux (systemd) and macOS (launchd).

All 12 sanity checks from EVAL.md pass with zero regressions to the existing test suite (911/911). The dev-backend workflow is preserved. Two Level 3 validations are appropriately deferred to phases 5 and 6 where their dependencies will be met.

---

_Verified: 2026-02-27T18:11:44Z_
_Verifier: Claude (grd-verifier)_
_Verification levels applied: Level 1 (sanity — all 12 checks), Level 3 (2 items deferred to phases 5 and 6)_
