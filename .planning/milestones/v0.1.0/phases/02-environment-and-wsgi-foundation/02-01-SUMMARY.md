---
phase: 02-environment-and-wsgi-foundation
plan: 01
status: complete
started: 2026-02-28T02:50:00
completed: 2026-02-28T03:00:00
commits:
  - hash: 9be53aa
    message: "feat(deps): add gevent, python-dotenv, APScheduler, pytz to pyproject.toml"
  - hash: bbc6033
    message: "feat(config): implement SECRET_KEY persistence and dotenv loading"
  - hash: 53056a7
    message: "feat(deploy): add gunicorn.conf.py with gevent worker configuration"
files_modified:
  - backend/pyproject.toml
  - backend/uv.lock
  - backend/app/__init__.py
  - backend/run.py
  - backend/gunicorn.conf.py
  - .gitignore
deviations: none
---

# Plan 02-01 Summary: Dependencies, SECRET_KEY, Gunicorn Config

## What Was Done

### Task 1: Add missing dependencies to pyproject.toml
Added four explicit dependencies to `backend/pyproject.toml`:
- `gevent>=24.10.1` — Gunicorn GeventWorker for async SSE support
- `python-dotenv>=1.0.0` — 12-factor .env file loading
- `APScheduler>=3.10.0` — Background scheduler (was transitive only)
- `pytz>=2023.3` — Timezone handling for APScheduler

All four verified importable after `uv sync`.

### Task 2: SECRET_KEY persistence and dotenv loading
- Added `_get_secret_key()` helper to `backend/app/__init__.py` with three-tier fallback: env var > `.secret_key` file > generate-and-persist
- Added `load_dotenv()` to `backend/run.py` before any app imports
- Added `.env` and `backend/.secret_key` to `.gitignore`

Verified SECRET_KEY is identical across consecutive `create_app()` calls (persisted to `.secret_key` file).

### Task 3: Gunicorn configuration
Created `backend/gunicorn.conf.py` with:
- `workers=1` (mandatory — in-memory SSE state not shared across processes)
- `worker_class="gevent"` for async SSE connection handling
- `worker_connections=1000`, `timeout=300` for long-running AI executions
- `preload_app` intentionally NOT set (breaks gevent monkey patching order)
- `wsgi_app = "run:application"`

Validated with `gunicorn --check-config` (exit 0).

## Verification Results

| Check | Result |
|-------|--------|
| `uv sync` succeeds | Pass |
| All four imports work | Pass |
| SECRET_KEY persists across restarts | Pass (64-char hex, identical on second call) |
| `gunicorn --check-config` exits 0 | Pass |
| `load_dotenv` in run.py before create_app | Pass |
| `.env` and `.secret_key` in .gitignore | Pass |
| Backend tests (911/911) | Pass |
| Frontend build (vue-tsc + vite) | Pass |

## Decisions

- Accepted default `monkey.patch_all()` from GeventWorker rather than custom `thread=False` — will validate APScheduler compatibility in integration testing if issues arise
- `.secret_key` file placed in `backend/` directory (sibling to `run.py`) for locality with the app

## Deviations

None. All three tasks executed as specified in the plan.
