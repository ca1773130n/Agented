# Phase 2: Environment and WSGI Foundation - Research

**Researched:** 2026-02-28
**Domain:** Python WSGI deployment, process management, environment configuration
**Confidence:** HIGH

## Summary

This phase replaces the Flask development server with Gunicorn + gevent workers, introduces `.env`-based configuration via `python-dotenv`, stabilizes the `SECRET_KEY`, and adds a process supervisor for automatic restart-on-crash. The technical domain is well-understood and battle-tested: Gunicorn + gevent is the standard deployment pattern for Flask applications with SSE/long-lived connections, and `python-dotenv` is the de facto standard for `.env` file loading in Python.

The primary complexity lies in gevent's monkey patching interacting with existing in-memory state patterns (threading.Lock, threading.Thread, APScheduler's BackgroundScheduler, subprocess.Popen). Gunicorn 25.1.0 (already installed) calls `monkey.patch_all()` with no arguments in its `GeventWorker.patch()` method, which patches **everything** including threads and subprocess. The ROADMAP constraint to use `monkey.patch_all(thread=False)` cannot be enforced through Gunicorn's built-in gevent worker without a custom worker class, but the `workers=1` constraint combined with gevent's transparent thread-to-greenlet conversion makes this safe in practice. APScheduler (currently not installed via `uv`) must be added to `pyproject.toml` and will work correctly under gevent monkey patching when using a single worker, though switching to `GeventScheduler` is the cleaner long-term approach.

**Primary recommendation:** Use Gunicorn 25.1.0 (already installed) with `worker_class = "gevent"`, `workers = 1`, add `gevent >= 24.10.1` to `pyproject.toml`, use `python-dotenv` (already available as transitive dependency, add explicitly), implement SECRET_KEY persistence via `.env` file with fallback to auto-generated file, and provide both systemd (Linux) and launchd (macOS) process supervisor configs since the development platform is macOS.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Gunicorn + gevent for SSE-capable WSGI deployment

**Recommendation:** Use Gunicorn with `worker_class = "gevent"` and `workers = 1` for the production WSGI server.

**Evidence:**
- [Flask Official Documentation (3.1.x)](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/) — States: "If you need numerous, long running, concurrent connections" use `-k gevent` with Gunicorn. Confirms `gunicorn -k gevent 'hello:create_app()'` as the standard invocation.
- [Flask-SSE Documentation](https://flask-sse.readthedocs.io/en/latest/quickstart.html) — "You must use an asynchronous WSGI server" for SSE; Gunicorn + gevent is the recommended pattern.
- [Gunicorn Source: ggevent.py](https://github.com/benoitc/gunicorn/blob/master/gunicorn/workers/ggevent.py) — Verified in installed package (v25.1.0): `GeventWorker.patch()` calls `monkey.patch_all()` with no arguments. Requires `gevent >= 24.10.1`.
- [Codebase Analysis: CONCERNS.md Section 7.1](/.planning/codebase/CONCERNS.md) — Documents that the Flask dev server is single-threaded, blocks on SSE, and has no worker management. CONCERNS.md Section 1.7 documents that in-memory state (SSE subscribers, rate limit detection, retry scheduling) is not shared across processes.

**Confidence:** HIGH — Flask official docs + Gunicorn source code confirm the pattern. The `workers=1` constraint is mandated by the codebase's ~10 services with in-memory state (documented in CONCERNS.md 7.2).

**Expected improvement:** SSE streaming will work under concurrent connections; gevent's cooperative scheduling allows one worker to serve multiple simultaneous SSE subscribers without blocking.

**Caveats:** `workers=1` means no parallelism from multiple processes. Gevent provides concurrency through cooperative greenlets within the single worker. True multi-process scaling requires migrating in-memory state to Redis (out of scope for this phase).

### Recommendation 2: python-dotenv for .env configuration loading

**Recommendation:** Use `python-dotenv`'s `load_dotenv()` at the top of `run.py` (before `create_app()`) with `override=False` to load `.env` without overwriting explicitly set environment variables.

**Evidence:**
- [python-dotenv Official README](https://github.com/theskumar/python-dotenv/blob/main/README.md) — "Reads key-value pairs from a .env file and can set them as environment variables. It helps in developing applications following the 12-factor principles." Default `override=False` means shell-set env vars take precedence.
- [Context7: python-dotenv API](https://context7.com/theskumar/python-dotenv/llms.txt) — Confirmed: `load_dotenv()` with no args searches current directory and parent directories for `.env`; supports variable interpolation; `override=False` is default.
- Package already available: `python-dotenv 1.2.1` is installed as a transitive dependency in the backend virtualenv (verified via `uv run python -c "from dotenv import load_dotenv"`).

**Confidence:** HIGH — Official docs, Context7, and runtime verification confirm behavior.

### Recommendation 3: SECRET_KEY persistence strategy

**Recommendation:** Load `SECRET_KEY` from `.env` file. If not present in `.env` or environment, generate one, write it to a `.secret_key` file in the backend directory, and load from that file on subsequent restarts. Never auto-regenerate on restart.

**Evidence:**
- [Flask Configuration Documentation (3.1.x)](https://flask.palletsprojects.com/en/stable/config/) — Documents `SECRET_KEY` usage and recommends `python -c 'import secrets; print(secrets.token_hex())'` for generation.
- [Codebase Analysis: CONCERNS.md Section 4.4](/.planning/codebase/CONCERNS.md) — Documents the current problem: "When `SECRET_KEY` is not set, a new random secret is generated each restart. This invalidates any Flask sessions on server restart."
- [Flask-JWT-Extended Issue #240](https://github.com/vimalloc/flask-jwt-extended/issues/240) — Demonstrates that different `SECRET_KEY` values across workers/restarts cause authentication token validation failures. Reinforces the need for persistence.

**Confidence:** HIGH — Flask docs + multiple production issue reports confirm that SECRET_KEY must be stable across restarts.

### Recommendation 4: gevent monkey patching safety with existing codebase

**Recommendation:** Accept Gunicorn's default `monkey.patch_all()` (which patches everything including threads and subprocess). Do NOT attempt to customize monkey patching via a custom worker class. The `workers=1` constraint makes this safe because all in-memory state lives in a single process with a single event loop.

**Evidence:**
- [Gunicorn Issue #2468](https://github.com/benoitc/gunicorn/issues/2468) — Maintainers explicitly discourage customizing monkey patching. Jason Madden (gevent maintainer) explains that non-patched I/O calls block the gevent hub.
- [gevent.monkey Documentation](https://www.gevent.org/api/gevent.monkey.html) — `monkey.patch_all()` replaces `threading.Thread` with gevent greenlets, `threading.Lock` with gevent-compatible locks, and `subprocess.Popen` with cooperative versions. This means existing code using `threading.Lock` and `threading.Thread` (ProcessManager, AgentMessageBusService, ExecutionService) will transparently use greenlets.
- [APScheduler User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — Documents `GeventScheduler` as the correct scheduler for gevent environments. However, `BackgroundScheduler` using `ThreadPoolExecutor` will also work under gevent's monkey patching because threads become greenlets. With `workers=1`, there is no risk of duplicate job execution.
- [Gunicorn Source ggevent.py line 38](/Users/edward.seo/dev/private/project/harness/Agented/backend/.venv/lib/python3.10/site-packages/gunicorn/workers/ggevent.py) — Verified: Gunicorn 25.1.0 calls `monkey.patch_all()` with no arguments.

**Confidence:** MEDIUM-HIGH — Gunicorn maintainers confirm this is the intended behavior. The `workers=1` constraint eliminates the multi-process concerns. The remaining risk is that `monkey.patch_all()` converts threads to greenlets, which changes the concurrency model — but since `workers=1` means a single event loop, this is actually desirable (cooperative scheduling instead of preemptive threading).

**Caveats:** The ROADMAP says "use `monkey.patch_all(thread=False)` or validate APScheduler job firing rates." Since Gunicorn does not support customizing monkey patch arguments without a custom worker class, the pragmatic path is to validate APScheduler behavior. With `workers=1` and threads becoming greenlets, APScheduler's `BackgroundScheduler` will fire jobs as greenlets — functionally equivalent. The `coalesce=True` and `max_instances=1` settings already configured in `SchedulerService` prevent duplicate executions.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| gunicorn | >= 21.0.0 (installed: 25.1.0) | Production WSGI server | Flask official docs recommend it; pre-fork worker model; already a dependency |
| gevent | >= 24.10.1 | Async worker for concurrent SSE connections | Required by Gunicorn 25.x GeventWorker; Flask docs recommend for long-lived connections |
| python-dotenv | >= 1.0.0 (installed: 1.2.1) | Load `.env` file into environment | 12-factor app standard; 4700+ GitHub stars; already available as transitive dep |
| APScheduler | >= 3.10.0 | Background job scheduling | Already used by SchedulerService; needs to be added to pyproject.toml |
| pytz | >= 2023.3 | Timezone handling for scheduler | Required by APScheduler; already used in SchedulerService |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| greenlet | >= 3.0.0 (installed: 3.3.2) | Lightweight coroutines for gevent | Automatically installed with gevent |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Evidence |
|------------|-----------|----------|----------|
| gevent | gthread (Gunicorn built-in) | gthread uses real OS threads; works without monkey patching but doesn't scale to many concurrent SSE connections; each SSE connection ties up a thread | Flask docs: "If you need numerous, long running, concurrent connections" use gevent |
| gevent | eventlet | Similar green-thread model; less actively maintained; gevent has broader ecosystem support | Gunicorn docs list both; gevent has more recent releases (25.9.x vs eventlet's less frequent updates) |
| python-dotenv | environs | Higher-level env parsing with type casting; heavier dependency | python-dotenv is lighter and sufficient for this use case |
| BackgroundScheduler | GeventScheduler | GeventScheduler is more "correct" for gevent; BackgroundScheduler works because monkey patching converts threads to greenlets | APScheduler docs recommend GeventScheduler for gevent apps; defer switch to avoid scope creep |

**Installation:**
```bash
# Add to pyproject.toml dependencies:
# "gevent>=24.10.1"
# "python-dotenv>=1.0.0"
# "APScheduler>=3.10.0"
# "pytz>=2023.3"
cd backend && uv sync
```

## Architecture Patterns

### Recommended Project Structure Changes

```
backend/
├── gunicorn.conf.py          # Gunicorn configuration (NEW)
├── run.py                    # Development server entry point (MODIFIED — add dotenv loading)
├── .env.example              # Environment variable documentation (NEW)
├── .env                      # Local environment values (NEW, gitignored)
├── .secret_key               # Auto-generated SECRET_KEY fallback (NEW, gitignored)
├── pyproject.toml            # Add gevent, python-dotenv, APScheduler deps (MODIFIED)
├── app/
│   ├── __init__.py           # SECRET_KEY loading logic updated (MODIFIED)
│   └── config.py             # Centralized config loading (MODIFIED)
deploy/
├── agented.service           # systemd unit file for Linux (NEW)
└── com.agented.backend.plist # launchd plist for macOS (NEW)
justfile                      # deploy target updated (MODIFIED)
```

### Pattern 1: dotenv Loading at Entry Point

**What:** Call `load_dotenv()` before any other imports in the entry point files (run.py and gunicorn.conf.py).
**When to use:** Always — ensures environment variables are available before Flask app factory runs.
**Source:** [python-dotenv official docs](https://github.com/theskumar/python-dotenv#readme)

**Example:**
```python
# run.py — top of file, before create_app()
# Source: python-dotenv official docs
from dotenv import load_dotenv
load_dotenv()  # override=False by default — shell env vars take precedence

from app import create_app
application = create_app()
```

### Pattern 2: SECRET_KEY Persistence with Fallback

**What:** Load SECRET_KEY from environment first, then from a persisted file, and only generate + persist if neither exists.
**When to use:** In `create_app()` to ensure key stability across restarts.
**Source:** Flask Configuration docs + CONCERNS.md 4.4

**Example:**
```python
# Source: Flask docs + production best practice
import os
import secrets
from pathlib import Path

def _get_secret_key() -> str:
    """Load or generate a stable SECRET_KEY."""
    # 1. Environment variable (highest priority)
    key = os.environ.get("SECRET_KEY")
    if key:
        return key

    # 2. Persisted file fallback
    key_file = Path(__file__).parent.parent / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()

    # 3. Generate and persist
    key = secrets.token_hex(32)
    key_file.write_text(key)
    return key
```

### Pattern 3: Gunicorn Configuration File

**What:** `gunicorn.conf.py` at the backend root with documented settings.
**When to use:** Always — Gunicorn reads this file automatically when present in the working directory.
**Source:** [Gunicorn docs: Settings](https://docs.gunicorn.org/en/latest/settings.html)

**Example:**
```python
# gunicorn.conf.py
# Source: Gunicorn official docs + Flask SSE best practice

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

import os

# Server socket
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:20000")

# Worker processes
# IMPORTANT: workers=1 is MANDATORY until in-memory SSE state
# (ExecutionLogService._subscribers, ProcessManager._processes,
# AgentMessageBusService._subscribers, etc.) is migrated to Redis pub/sub.
# With workers>1, each process has independent state, causing SSE
# subscriptions to go to the wrong worker and rate-limit detection
# to be invisible across workers.
workers = 1

# Gevent worker class for async SSE support
# Allows one worker to handle many concurrent long-lived SSE connections
# via cooperative greenlet scheduling.
worker_class = "gevent"

# Worker connections (max concurrent greenlets per worker)
worker_connections = 1000

# Timeout for worker response (seconds)
# Long timeout to accommodate SSE streams and long-running AI executions
timeout = 300

# Graceful timeout — time to finish requests after SIGTERM
graceful_timeout = 30

# Access logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("LOG_LEVEL", "info")

# Application module
wsgi_app = "run:application"
```

### Anti-Patterns to Avoid

- **Running Flask dev server in production:** The Werkzeug dev server is single-threaded, has no worker management, and no restart-on-crash. Always use Gunicorn for anything beyond local development.
- **`workers > 1` with in-memory state:** Until Redis pub/sub replaces class-level dicts, multiple workers cause silent data loss (SSE events go to wrong worker, rate limits not shared).
- **Generating SECRET_KEY on every restart:** Invalidates all sessions, cookies, and signed tokens. Must be persisted.
- **Calling `load_dotenv(override=True)`:** Would override explicitly set environment variables (e.g., from systemd or Docker), defeating the 12-factor principle of environment-first configuration.
- **Custom monkey patching with Gunicorn gevent worker:** Gunicorn maintainers explicitly discourage this (Issue #2468). Accept the default `patch_all()` and design around it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| .env file parsing | Custom file parser with regex | `python-dotenv` `load_dotenv()` | Variable interpolation, multiline values, comment handling, encoding edge cases |
| WSGI server | Flask dev server (`app.run()`) | Gunicorn with gevent worker | Pre-fork model, graceful restarts, signal handling, worker health monitoring |
| Process supervision | Shell scripts with `while true` loops | systemd (Linux) / launchd (macOS) | OS-level restart guarantees, cgroup isolation, journal logging, dependency ordering |
| Secret key generation | `random.choice()` or UUID | `secrets.token_hex(32)` | Cryptographically secure random; Python stdlib; 256-bit entropy |

**Key insight:** Every component in this phase is a solved problem with battle-tested solutions. The only engineering is integration: wiring existing tools together correctly and documenting the configuration for the team.

## Common Pitfalls

### Pitfall 1: APScheduler Not in pyproject.toml

**What goes wrong:** APScheduler is listed in `requirements.txt` but not in `pyproject.toml`. Since `uv sync` reads `pyproject.toml`, a fresh install will not have APScheduler. The `SchedulerService` silently disables itself when APScheduler is missing (`SCHEDULER_AVAILABLE = False`).
**Why it happens:** Dual dependency file mismatch (requirements.txt vs pyproject.toml).
**How to avoid:** Add `APScheduler>=3.10.0` and `pytz>=2023.3` to `pyproject.toml` `dependencies` list. Remove `requirements.txt` or keep it as a secondary reference only.
**Warning signs:** Server starts without warnings about scheduling, but no scheduled triggers fire.
**Source:** Codebase analysis — CONCERNS.md Section 6.2; verified via `uv run python -c "import apscheduler"` → ModuleNotFoundError.

### Pitfall 2: gevent monkey patching after imports

**What goes wrong:** If modules like `threading`, `ssl`, or `subprocess` are imported before `monkey.patch_all()`, they retain references to unpatched stdlib functions, causing subtle bugs (deadlocks, blocking I/O in greenlets).
**Why it happens:** Python caches module references at import time. Monkey patching replaces module-level names but cannot retroactively fix already-cached references.
**How to avoid:** With Gunicorn's gevent worker, monkey patching happens in the worker's `patch()` method **before** the WSGI app is loaded. This is correct as long as `preload_app = False` (the default). Do NOT set `preload_app = True` with gevent workers — it loads the app in the master process before monkey patching occurs in workers.
**Warning signs:** `MonkeyPatchWarning` in logs about modules imported before patching.
**Source:** [gevent.monkey docs](https://www.gevent.org/api/gevent.monkey.html) — "Patching should be done as early as possible in the lifetime of the process."

### Pitfall 3: preload_app with gevent workers

**What goes wrong:** Setting `preload_app = True` in gunicorn.conf.py loads the Flask application in the master process before forking workers. The master process does NOT have monkey patching applied. When the app is copied to workers via fork, it carries unpatched module references.
**Why it happens:** Gunicorn's `preload_app` is designed for sync workers to save memory via copy-on-write. With gevent workers, monkey patching happens post-fork in `GeventWorker.patch()`.
**How to avoid:** Do NOT set `preload_app = True`. Leave it at the default (`False`) so the app is loaded fresh in each worker after monkey patching.
**Warning signs:** `ssl` or `threading` MonkeyPatchWarning messages; SSL connections may fail; threads don't become greenlets.
**Source:** [Gunicorn Issue #1816](https://github.com/benoitc/gunicorn/issues/1816), [Gunicorn Issue #2796](https://github.com/benoitc/gunicorn/issues/2796).

### Pitfall 4: subprocess.Popen SIGCHLD handling under gevent

**What goes wrong:** gevent monkey patching replaces subprocess.Popen with a cooperative version that relies on its own SIGCHLD handler. If SIGCHLD is reset to SIG_DFL (as can happen in certain fork scenarios), `process.wait()` can hang indefinitely.
**Why it happens:** gevent's subprocess cooperation uses a SIGCHLD watcher on the event loop hub. If the signal handler is disrupted, child process exit status is never collected.
**How to avoid:** With `workers=1` and Gunicorn managing the fork/exec, this should not occur in normal operation. The existing `ProcessManager` code in the codebase already handles process lifecycle correctly. Monitor for hanging subprocess calls in logs.
**Warning signs:** Trigger executions that never complete; worker health check timeout.
**Source:** [gevent Issue #857](https://github.com/gevent/gevent/issues/857), [Gunicorn Issue #418](https://github.com/benoitc/gunicorn/issues/418).

### Pitfall 5: Missing .env file on fresh clone

**What goes wrong:** If `.env` is gitignored (correct) but `.env.example` is not provided (or is incomplete), a fresh clone will start with no configured environment variables. The app will auto-generate a SECRET_KEY but other settings (CORS_ALLOWED_ORIGINS, GITHUB_WEBHOOK_SECRET, etc.) will use insecure defaults.
**Why it happens:** 12-factor apps expect environment configuration, but new developers expect a working setup out of the box.
**How to avoid:** Provide `.env.example` with all variables, their types, defaults, and descriptions. The first-run experience should be: `cp .env.example .env` then optionally edit values.
**Warning signs:** Application starts but with wildcard CORS, no webhook verification, and auto-generated secret key.

## Experiment Design

### Recommended Experimental Setup

This phase is operational infrastructure, not algorithm/model work. The "experiments" are integration smoke tests.

**Independent variables:** Gunicorn configuration (worker_class, workers, timeout)
**Dependent variables:** SSE stream delivery, scheduler job execution, subprocess completion, restart behavior
**Controlled variables:** Application code (unchanged), database state (preserved)

**Baseline comparison:**
- Current state: `python run.py` (Flask dev server, single-threaded, no restart-on-crash)
- Target state: `gunicorn -c gunicorn.conf.py` (gevent worker, SSE-capable, auto-restart)

**Validation plan:**
1. **SSE delivery test:** Start server with Gunicorn, open execution log stream in browser, trigger an execution, verify live log lines appear — tests that gevent worker correctly serves SSE.
2. **Scheduler test:** Start server, verify APScheduler jobs are registered (check logs for "Scheduler service initialized"), wait for a scheduled job interval, verify it fires.
3. **SECRET_KEY persistence test:** Start server, note SECRET_KEY from Flask config, restart server, verify SECRET_KEY is identical.
4. **Subprocess test:** Trigger a bot execution (which spawns Claude CLI subprocess), verify it completes successfully — tests that gevent's monkey-patched subprocess.Popen works correctly with the existing ProcessManager.
5. **Crash restart test:** `kill -9 $(pgrep gunicorn)`, verify new gunicorn process appears within 5 seconds (process supervisor test).

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| SSE event delivery | Core functionality | Open stream, count events vs expected | 0 (Flask dev server blocks) |
| Restart time after crash | Reliability requirement | Time between `kill -9` and new process | N/A (no restart currently) |
| SECRET_KEY stability | Security requirement | Compare `app.config['SECRET_KEY']` across restarts | Fails (regenerated each time) |
| Scheduler job firing | Operational correctness | Check logs for scheduled job execution | Fails (APScheduler not installed) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Gunicorn starts with gevent worker | Level 1 (Sanity) | `ps aux | grep gunicorn` shows worker process |
| SECRET_KEY persists across restarts | Level 1 (Sanity) | Two startup logs show same key hash |
| `.env.example` has all variables | Level 1 (Sanity) | grep each known env var in `.env.example` |
| SSE streaming works under Gunicorn | Level 1 (Sanity) | Open execution stream endpoint, verify events arrive |
| APScheduler initializes and fires | Level 1 (Sanity) | Check logs for scheduler init message |
| Process supervisor restarts on crash | Level 1 (Sanity) | `kill -9` followed by `ps aux` within 5s |
| `just deploy` uses Gunicorn | Level 1 (Sanity) | `ps aux` shows `gunicorn`, never `python run.py` |

**Level 1 checks to always include:**
- `ps aux | grep gunicorn` shows `gunicorn: master` and `gunicorn: worker` processes
- `curl http://localhost:20000/health/readiness` returns 200
- Server logs show "Using worker: gevent" on startup
- Server logs show "Scheduler service initialized"
- `.env.example` exists and lists all env vars from the codebase audit

**Level 2 proxy metrics (if time permits):**
- Concurrent SSE test: open 5 SSE connections simultaneously, trigger execution, verify all 5 receive events
- Long-running connection test: SSE connection stays open for 5 minutes without disconnect

**Level 3 deferred items:**
- Load testing with many concurrent SSE connections (Phase 5 observability)
- Multi-process deployment with Redis pub/sub (future milestone)

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is an empty template — no prior production knowledge captured. The following are derived from codebase analysis (CONCERNS.md) and research findings.

### Known Failure Modes

- **In-memory state loss on crash:** All SSE subscribers, rate limit state, pending retries, and process tracking are lost when the process dies. The process supervisor restarts Gunicorn, but connected SSE clients must reconnect and active executions may be orphaned.
  - Prevention: The existing `cleanup_dead_sessions()` and `cleanup_stale_executions()` already run on startup to handle this case.
  - Detection: Monitor for "interrupted" execution status entries in the database after restarts.

- **gevent hub blocking:** If any code path performs blocking I/O that is NOT monkey-patched (e.g., a C extension doing raw socket calls), it blocks the entire gevent hub, freezing all greenlets in the worker.
  - Prevention: All I/O in the codebase uses Python stdlib modules (socket, subprocess, threading) which gevent monkey patches. The `cryptography` C extension uses its own internal I/O and should not block the hub.
  - Detection: Worker health check timeout in Gunicorn logs (`[CRITICAL] WORKER TIMEOUT`).

### Scaling Concerns

- **At current scale (single user, local):** `workers=1` with gevent is sufficient. One greenlet per SSE connection, cooperative scheduling handles concurrency.
- **At production scale (multiple users, remote):** `workers=1` becomes a bottleneck. CPU-bound work in one greenlet starves all others. Migration to `workers=N` requires moving all in-memory state to Redis. This is documented in CONCERNS.md 7.2 and is out of scope for this phase.

### Common Implementation Traps

- **Forgetting to add `.env` to `.gitignore`:** The `.env` file contains secrets. It must never be committed. Add to `.gitignore` before creating the file.
- **Forgetting to add `.secret_key` to `.gitignore`:** Same as above — the auto-generated key file must be gitignored.
- **Setting `preload_app = True`:** Breaks monkey patching order. Must remain `False` (default).
- **Using `debug=True` with Gunicorn:** Gunicorn does not support Flask debug mode. The `--debug` flag in `run.py` should only apply to the Flask dev server path. Gunicorn uses its own reload mechanism (`--reload` flag for development).

## Code Examples

Verified patterns from official sources and codebase analysis:

### gunicorn.conf.py

```python
# Source: Gunicorn docs + Flask SSE best practice + codebase constraints
"""Gunicorn configuration for Agented backend.

workers=1 is MANDATORY until in-memory SSE state is migrated to Redis.
See .planning/codebase/CONCERNS.md Section 7.2 for the full list of
in-memory state that prevents multi-worker deployment.
"""

from dotenv import load_dotenv
load_dotenv()

import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:20000")
workers = 1
worker_class = "gevent"
worker_connections = 1000
timeout = 300
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
wsgi_app = "run:application"
```

### .env.example

```bash
# Source: Codebase audit of os.environ.get() calls across backend/app/
# ==============================================================
# Agented Backend Configuration
# ==============================================================
# Copy this file to .env and adjust values as needed.
# All variables have sensible defaults for local development.

# --- Security ---
# Flask session signing key. Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
# If not set, a key is auto-generated and persisted to .secret_key file.
# SECRET_KEY=

# --- Server ---
# Gunicorn bind address and port (default: 0.0.0.0:20000)
# GUNICORN_BIND=0.0.0.0:20000

# Log level: debug, info, warning, error, critical (default: info)
# LOG_LEVEL=info

# --- CORS ---
# Comma-separated list of allowed origins (default: * — INSECURE, set for production)
# CORS_ALLOWED_ORIGINS=http://localhost:3000

# --- Database ---
# SQLite database file path (default: backend/agented.db)
# AGENTED_DB_PATH=

# --- GitHub ---
# HMAC-SHA256 secret for verifying GitHub webhook signatures
# GITHUB_WEBHOOK_SECRET=

# --- AI / LLM ---
# Anthropic API key for direct API access (fallback when CLIProxyAPI unavailable)
# ANTHROPIC_API_KEY=

# Anthropic API base URL (for proxy setups)
# ANTHROPIC_API_BASE=

# --- Plugins ---
# Path to GRD CLI binary directory
# CLAUDE_PLUGIN_ROOT=

# --- Tuning ---
# Stale conversation threshold in seconds (default: 1800)
# STALE_CONVERSATION_THRESHOLD_SECS=1800

# Stale execution threshold in seconds (default: 900)
# STALE_EXECUTION_THRESHOLD_SECS=900

# SSE replay buffer limit (default: 500)
# SSE_REPLAY_LIMIT=500
```

### SECRET_KEY persistence in create_app()

```python
# Source: Flask docs + codebase CONCERNS.md 4.4 remediation
import os
import secrets
from pathlib import Path

def _get_secret_key() -> str:
    """Load SECRET_KEY from env, persisted file, or generate and persist."""
    # 1. Environment variable (highest priority — set in .env or shell)
    key = os.environ.get("SECRET_KEY")
    if key:
        return key

    # 2. Persisted file (auto-generated on first run)
    key_file = Path(__file__).parent.parent / ".secret_key"
    if key_file.exists():
        stored = key_file.read_text().strip()
        if stored:
            return stored

    # 3. Generate and persist for future restarts
    key = secrets.token_hex(32)
    try:
        key_file.write_text(key)
        key_file.chmod(0o600)  # Owner-readable only
    except OSError:
        pass  # Fallback: ephemeral key (not ideal but won't crash)
    return key
```

### systemd unit file

```ini
# Source: Gunicorn deployment docs + systemd best practice
# deploy/agented.service
[Unit]
Description=Agented Backend API Server
After=network.target

[Service]
Type=notify
User=agented
Group=agented
WorkingDirectory=/opt/agented/backend
Environment="PATH=/opt/agented/backend/.venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/opt/agented/backend/.venv/bin/gunicorn -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=3
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### launchd plist (macOS)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- Source: launchd.plist(5) man page + macOS best practice -->
<!-- deploy/com.agented.backend.plist -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agented.backend</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/agented/backend/.venv/bin/gunicorn</string>
        <string>-c</string>
        <string>gunicorn.conf.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/agented/backend</string>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/agented/backend.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/agented/backend-error.log</string>
</dict>
</plist>
```

### Updated justfile deploy target

```just
# Deploy: build frontend, then start both servers via Gunicorn
deploy: kill ensure-backend build
    @echo "Starting backend via Gunicorn on port 20000..."
    cd backend && uv run gunicorn -c gunicorn.conf.py &
    cd frontend && npm run dev
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Source |
|--------------|------------------|--------------|--------|--------|
| Flask dev server for production | Gunicorn + gevent | Established pattern since ~2012 | Concurrent SSE, worker management, graceful restarts | Flask docs |
| Manual env var export | python-dotenv `.env` files | python-dotenv 0.1.0 (2014) | 12-factor compliance, developer ergonomics | python-dotenv README |
| Random SECRET_KEY per restart | Persisted key from env or file | Flask best practice since 1.0 | Session stability, token validity | Flask config docs |
| No process supervisor | systemd / launchd | Standard since systemd adoption (~2015) | Auto-restart, logging, boot ordering | systemd/launchd docs |

**Deprecated/outdated:**
- **`requirements.txt` as primary dependency file:** `pyproject.toml` with `uv` is the current standard. `requirements.txt` in this project is out of sync (has APScheduler, pyproject.toml does not). Phase should consolidate to `pyproject.toml` only.
- **Gunicorn's `gunicorn[gevent]` extras syntax:** As of gunicorn 25.x, gevent must be installed separately. The `gunicorn[gevent]` extras installs gevent as a dependency but the version constraint may be stale. Prefer explicit `gevent>=24.10.1` in `pyproject.toml`.

## Open Questions

1. **Should APScheduler be switched to GeventScheduler?**
   - What we know: APScheduler docs recommend `GeventScheduler` for gevent environments. `BackgroundScheduler` works because monkey patching converts its threads to greenlets.
   - What's unclear: Whether `BackgroundScheduler` under monkey patching has any subtle timing/ordering differences from `GeventScheduler`.
   - Recommendation: Keep `BackgroundScheduler` for this phase to minimize code changes (it's already configured and tested). Add a TODO comment for future migration to `GeventScheduler`. The `workers=1` constraint makes both behave identically in practice.

2. **Should `requirements.txt` be removed?**
   - What we know: `pyproject.toml` is the primary dependency source for `uv`. `requirements.txt` is out of sync.
   - What's unclear: Whether any CI/CD or deployment scripts reference `requirements.txt`.
   - Recommendation: Move all dependencies to `pyproject.toml` and delete `requirements.txt` in this phase. If external systems need it, it can be regenerated with `uv pip compile pyproject.toml > requirements.txt`.

3. **Should the `run.py` entry point be preserved for development?**
   - What we know: `run.py` provides the Flask dev server with `--debug` mode, Werkzeug reloader, and signal handlers.
   - What's unclear: Whether developers prefer `python run.py --debug` or `gunicorn --reload` for development.
   - Recommendation: Keep `run.py` for development (`just dev-backend` uses it). Change `just deploy` to use Gunicorn. Both paths call `load_dotenv()` at the top.

## Sources

### Primary (HIGH confidence)
- [Flask Documentation (3.1.x): Gunicorn deployment](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/) — Worker class recommendations, gevent configuration
- [Gunicorn source code: ggevent.py](https://github.com/benoitc/gunicorn/blob/master/gunicorn/workers/ggevent.py) — Verified monkey.patch_all() behavior in installed v25.1.0
- [python-dotenv official docs](https://github.com/theskumar/python-dotenv) — API, override behavior, .env file format
- [gevent.monkey official docs](https://www.gevent.org/api/gevent.monkey.html) — patch_all() parameters, warnings, timing requirements
- [APScheduler 3.x User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — Scheduler types, GeventScheduler recommendation
- [Context7: python-dotenv /theskumar/python-dotenv](https://context7.com/theskumar/python-dotenv/llms.txt) — API functions, load_dotenv behavior
- [Context7: Gunicorn /benoitc/gunicorn](https://context7.com/benoitc/gunicorn/llms.txt) — Worker configuration, gevent worker requirements
- Codebase: `.planning/codebase/CONCERNS.md` — Sections 1.7, 4.4, 6.2, 7.1, 7.2

### Secondary (MEDIUM confidence)
- [Gunicorn Issue #2468](https://github.com/benoitc/gunicorn/issues/2468) — Maintainer guidance against custom monkey patching
- [Gunicorn Issue #1816](https://github.com/benoitc/gunicorn/issues/1816) — Monkey patching timing issues
- [gevent Issue #857](https://github.com/gevent/gevent/issues/857) — SIGCHLD handling in subprocess after monkey patching
- [Flask-JWT-Extended Issue #240](https://github.com/vimalloc/flask-jwt-extended/issues/240) — SECRET_KEY consistency across workers
- [Flask-SSE docs](https://flask-sse.readthedocs.io/en/latest/quickstart.html) — Gevent requirement for SSE
- [iximiuz Flask-gevent tutorial](https://iximiuz.com/en/posts/flask-gevent-tutorial/) — Practical gevent + Gunicorn setup

### Tertiary (LOW confidence)
- [launchd.plist(5) man page](https://keith.github.io/xcode-man-pages/launchd.plist.5.html) — macOS launchd configuration (verified structure, not tested with this specific app)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All libraries are well-established, versions verified against installed packages
- Architecture: HIGH — Patterns are standard Flask deployment; no novel design decisions
- Paper recommendations: N/A — This is infrastructure, not algorithm work; recommendations are based on official docs and source code analysis
- Pitfalls: HIGH — All pitfalls derived from Gunicorn/gevent issue trackers and codebase analysis with specific issue references

**Research date:** 2026-02-28
**Valid until:** 2026-06-28 (120 days — stable infrastructure domain; gunicorn/gevent release cadence is slow)
