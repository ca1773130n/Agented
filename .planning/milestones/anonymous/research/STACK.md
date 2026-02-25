# Stack Research

**Domain:** Production hardening — Flask + Vue.js AI bot automation platform
**Researched:** 2026-02-25
**Confidence:** HIGH (versions verified via PyPI, official docs, and Context7)

---

## Context: Existing Stack (Do Not Re-research)

The system already uses: Flask 2.x + flask-openapi3 3.x, Vue 3.5 + TypeScript + Vite, SQLite (raw sqlite3), APScheduler 3.10, subprocess CLI execution, Gunicorn 21.x (declared but not configured), Pydantic v2, Vitest, pytest 9.x.

This document covers **additions only** — what to bolt on to harden the existing platform for production. Existing choices are not re-evaluated unless they need to change.

---

## Recommended Stack Additions

### Authentication Layer

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `flask-jwt-extended` | 4.7.1 | JWT access + refresh token auth for API routes | Most mature JWT extension for Flask. Supports header and cookie token delivery, revocation, custom claims, `@jwt_required` decorator pattern. Directly compatible with flask-openapi3's APIBlueprint. Does not require ORM. Current as of Nov 2024. |
| `flask-httpauth` | 4.x | API-key authentication (simpler alternative) | Single-file extension — useful for a shared-secret model where there is one "user" (the platform operator). Only viable if multi-user auth is not needed. Lower complexity than JWT. |

**Decision: Use `flask-jwt-extended` 4.7.1.** Rationale: the platform will eventually need per-user tokens (team members, CI bots). JWT enables this without rearchitecting. A single before-request API key approach (via `flask-httpauth`) is acceptable as Phase 1 if JWT setup complexity must be deferred, but it creates ceiling problems later.

**What NOT to use:** `Flask-Login` (session-based, requires cookies/browser, wrong for API-first). `flask-security-too` (large, pulls in SQLAlchemy ORM dependency, overkill). `authlib` (full OAuth server — unnecessary until external SSO is required).

---

### Security Headers + HTTPS Enforcement

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `flask-talisman` | 1.1.0 | CSP, HSTS, X-Frame-Options, X-Content-Type-Options | One decorator call enables a full set of security headers. Maintained by wntrblm fork (GoogleCloudPlatform original is stale). Last release Nov 2025. Works with flask-openapi3. |

**What NOT to use:** Hand-rolling `@app.after_request` security headers — error-prone and incomplete. `flask-seasurf` (CSRF only, not comprehensive).

---

### Rate Limiting

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `flask-limiter` | 4.1.1 | Per-route and global rate limiting | Pairs with Redis backend for multi-process safety. Decorator-based (`@limiter.limit("10/minute")`). Supports burst allowances. Can protect webhook ingestion from flooding. Maintained and actively released (4.1.1 is current). |

**Note:** Even without Redis (Phase 1), flask-limiter works with in-memory storage — consistent with the existing single-process deployment. Migrating to Redis backend later requires only one config line change.

---

### Environment Configuration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `python-dotenv` | 1.2.1 | `.env` file loading for local development | Eliminates the current problem of no `.env` file. Follows 12-factor app pattern. `SECRET_KEY` generation on every restart (current critical bug) is fixed by persisting the key in `.env`. Last release Oct 2025. |

**Implementation:** Add `load_dotenv()` to `run.py` and `create_app()`. Commit a `.env.example` (no secrets) to the repo. This unblocks deployment scripts that cannot inject env vars via the shell.

---

### Production WSGI + Process Management

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `gunicorn` (existing) | 21.x | WSGI server | Already declared as a dependency. The gap is configuration — there is no `gunicorn.conf.py`. See configuration section below. |
| `gevent` | 24.x | Async worker class for Gunicorn | Required for SSE to work under concurrent connections. Without gevent (or eventlet), a single SSE subscriber blocks a synchronous Gunicorn worker, making other requests queue. One line in gunicorn config: `worker_class = "gevent"`. |

**Required `gunicorn.conf.py` (create this file):**
```python
import multiprocessing

workers = 1                        # SSE state is in-memory; single worker is mandatory until Redis migration
worker_class = "gevent"            # Required for concurrent SSE + REST
worker_connections = 1000
timeout = 120                      # Long enough for bot executions to start
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
bind = "0.0.0.0:20000"
accesslog = "-"
errorlog = "-"
loglevel = "info"
```

**Critical note on worker count:** The existing architecture stores execution logs, subscribers, and process state in Python class-level dicts. Running `workers > 1` causes SSE subscribers to miss events because they connect to the wrong worker. Until the in-memory state is migrated to Redis, `workers = 1` is the only correct configuration. This must be documented explicitly to prevent misconfiguration.

**What NOT to use:** uWSGI (now in maintenance mode as of 2024; Gunicorn is the community standard). Eventlet (gevent is preferred — better maintained, broader compatibility). Flask dev server for any production traffic.

---

### Reverse Proxy

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Caddy | 2.x | Reverse proxy, automatic TLS, static file serving | Simpler configuration than Nginx for this use case. `Caddyfile` is 5 lines vs 30 lines for equivalent Nginx. Automatic HTTPS via Let's Encrypt with zero config. Serves Vue.js static files and proxies `/api/*`, `/admin/*` to Gunicorn. Active 2025 community adoption. |
| Nginx | 1.x | Alternative reverse proxy | Acceptable alternative if the team has existing Nginx expertise. More configuration overhead but widely documented. |

**Decision: Caddy for new deployments.** Rationale: the team has no existing Nginx config, so complexity cost is paid either way. Caddy's zero-config HTTPS removes a whole failure category (expired certs, renewal scripts). For teams already running Nginx infrastructure, use Nginx.

**Minimal `Caddyfile` for this platform:**
```
yourdomain.com {
    handle /api/* { reverse_proxy localhost:20000 }
    handle /admin/* { reverse_proxy localhost:20000 }
    handle /health/* { reverse_proxy localhost:20000 }
    handle /docs/* { reverse_proxy localhost:20000 }
    handle /openapi/* { reverse_proxy localhost:20000 }
    handle { root * /srv/frontend/dist; try_files {path} /index.html; file_server }
}
```

---

### Error Monitoring and Observability

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `sentry-sdk[flask]` | 2.52.0 | Error tracking, performance monitoring, SSE transaction tracing | Flask integration auto-enables on `sentry_sdk.init()` when Flask is detected. Captures unhandled exceptions, slow requests, subprocess failures. One init call covers all 44 APIBlueprints. Current version is 2.52.0 (verified Jan 2026). |

**Installation:**
```bash
pip install "sentry-sdk[flask]"
```

**Minimal setup in `create_app()`:**
```python
import sentry_sdk
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    traces_sample_rate=0.1,  # 10% of transactions
    environment=os.environ.get("FLASK_ENV", "production"),
)
```

**What NOT to use:** OpenTelemetry as primary monitoring (heavy, requires collector infrastructure). Datadog (expensive, overkill for a single-node deployment). Rolling your own structured logging as a Sentry replacement — stdout logs are ephemeral and cannot alert.

---

### Database Migration (Incremental Path)

The existing raw-SQL + manual `migrations.py` pattern will hit limits if/when the platform migrates from SQLite to PostgreSQL. The recommendation is incremental:

**Phase 1 (Now): Keep raw sqlite3.** No migration tooling needed. Fix the actual problems (no auth, no production config) before adding ORM complexity.

**Phase 2 (If PostgreSQL needed): SQLAlchemy Core (not ORM) + Alembic.**

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `SQLAlchemy` | 2.0.46 | SQL expression layer (Core, not ORM) | SQLAlchemy Core allows writing explicit SQL with the text() API while gaining connection pooling, multi-dialect support (SQLite + PostgreSQL without code changes), and type safety. Does not require ORM models. Current stable release. |
| `alembic` | 1.18.4 | Migration management | Replaces the 3,210-line `migrations.py` with versioned, reversible migration files. The `render_as_batch=True` option handles SQLite's ALTER TABLE limitations. Current release. |
| `Flask-SQLAlchemy` | 3.1.1 | Flask integration for SQLAlchemy | Provides session-per-request lifecycle and app context management. Only needed if moving from Core to ORM. |

**What NOT to use for Phase 1:** SQLAlchemy ORM models — require rewriting all 77 service classes that currently do raw SQL. This is a multi-sprint refactor and should not block production auth + deployment fixes. `pgloader` for SQLite→PostgreSQL migration — useful tooling but adds infrastructure complexity.

---

### Code Quality Tools

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `ruff` | 0.15.2 | Linter + formatter (replaces Flake8 + isort) | 10-100x faster than Flake8. Single tool replaces Flake8, isort, pyupgrade, autoflake. The existing project uses Black for formatting — Ruff's formatter is Black-compatible, enabling a single-tool replacement. Pre-commit hooks available. |
| `mypy` | 1.x | Static type checking | The codebase has 77 TypeScript `any` equivalents in Python (service classmethods, raw sqlite3 Row objects). mypy catches these. Run in CI but not blocking in dev initially. |

**Note on Black vs Ruff:** The project currently uses Black (enforced in CLAUDE.md). Ruff's formatter is a Black-compatible superset. Migration path: add `ruff` to dev dependencies, configure `ruff format` as the formatter in `pyproject.toml`, remove `black` dependency. This is a one-line `pyproject.toml` change.

---

### Container and Process Supervisor

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Docker + docker-compose | 27.x / 2.x | Reproducible deployment environment | Multi-stage Dockerfile (Node build stage for Vue, Python stage for Flask). Eliminates "works on my machine" problems. Standard production pattern for Flask+Vue stacks in 2025. |
| systemd | (OS-provided) | Process supervisor alternative to Docker | For bare-metal deployments. More debuggable than Docker when subprocess execution (PTY, `os.fork()`) is involved. The existing `os.fork()` usage in PTY service is POSIX-only and may require `--pid=host` in Docker. |

**Critical Docker caveat:** The PTY service uses `os.fork()` and the `pty` module (POSIX-only). Docker containers run fine on Linux, but the subprocess spawning pattern requires careful UID mapping. If Docker is used, run as a non-root user and test PTY session creation explicitly.

**Decision:** Start with systemd unit file for simplicity (avoids Docker/PTY compatibility investigation). Add Docker only when team is ready to test the PTY interaction fully.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Auth | `flask-jwt-extended` 4.7.1 | `flask-httpauth` + API keys | API keys work for single-tenant use but create ceiling when multi-user is needed. JWT provides a superset with same initial effort. |
| Auth | `flask-jwt-extended` 4.7.1 | `authlib` (OAuth 2.0 server) | Full OAuth server is far too heavy for this use case. No external SSO requirement identified. |
| Reverse proxy | Caddy 2.x | Nginx 1.x | Both are valid; Caddy preferred for new deployments due to zero-config HTTPS. Nginx is the correct choice for teams with existing Nginx infrastructure. |
| Reverse proxy | Caddy 2.x | Traefik | Traefik is better for dynamic service discovery (Kubernetes, Docker Swarm) — unnecessary here. |
| WSGI async | gevent 24.x | eventlet | eventlet has had fewer maintenance updates in 2024-2025; gevent is more actively maintained. |
| Monitoring | sentry-sdk 2.52.0 | OpenTelemetry + Prometheus | OTel requires collector infrastructure. Sentry is simpler for a single-node setup and provides both error tracking + traces. |
| Monitoring | sentry-sdk 2.52.0 | Datadog | Expensive for a small platform; Sentry has a generous free tier appropriate for this scale. |
| DB migration | Alembic 1.18.4 | Flask-Migrate | Flask-Migrate is a thin Alembic wrapper. Direct Alembic provides more control. Both are valid; Alembic preferred for teams not using Flask-SQLAlchemy ORM. |
| Code quality | ruff 0.15.2 | Flake8 + isort + pyupgrade | Ruff replaces all three, is 10-100x faster, and is the 2025 community standard. No reason to maintain separate tools. |
| Process mgmt | systemd | Supervisor | Both work. systemd is present on all modern Linux distros and has better integration with journald for log management. Supervisor requires a separate install. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `Flask-Login` | Session-based auth requiring cookies and browser. Wrong for an API-first platform with CLI/CI consumers. | `flask-jwt-extended` |
| `flask-security-too` | Pulls in SQLAlchemy ORM as hard dependency. Forces ORM migration before auth can be added. | `flask-jwt-extended` |
| `uWSGI` | In maintenance mode as of 2024. Documentation sparse, community moving away. | Gunicorn + gevent |
| `Flask-SQLAlchemy` ORM (as Phase 1) | Rewrites all 77 service classes. A multi-sprint effort that blocks faster wins (auth, deployment). | SQLAlchemy Core + Alembic (Phase 2 only) |
| `gunicorn --workers > 1` (current arch) | In-memory state (`_log_buffers`, `_subscribers`, `_executions`) is not shared across workers. SSE subscribers will miss events. | `workers = 1` until Redis migration |
| `flask.run()` (dev server) in production | Single-threaded, not designed for concurrent SSE. The existing `just deploy` command uses this. | Gunicorn + gevent |
| `playwright` as a runtime dependency | ~100 MB of browser binaries in the production image for a feature used only in OAuth flows. | Move to dev/optional dependency or lazy-import |
| `OpenTelemetry` as primary monitoring | Requires collector infrastructure, sampling config, and dashboard setup. High operational cost for a single-node platform. | sentry-sdk with `traces_sample_rate=0.1` |

---

## Version Compatibility Matrix

| Package | Version | Compatible With | Notes |
|---------|---------|-----------------|-------|
| flask-jwt-extended 4.7.1 | Flask >=2.2, Python >=3.8 | Flask 2.x (current) | Verified via readthedocs.io |
| flask-talisman 1.1.0 | Flask >=1.0, Python >=3.6 | Flask 2.x (current) | Updated Nov 2025 by wntrblm fork |
| flask-limiter 4.1.1 | Flask >=2.2, Python >=3.10 | Flask 2.x + Python 3.10 (current) | Redis backend optional |
| sentry-sdk 2.52.0 | Flask >=1.1.4, Python >=3.6 | Flask 2.x (current) | Flask integration auto-detected |
| gunicorn 21.x + gevent 24.x | Python >=3.7 | Python 3.10 (current) | gevent requires greenlet>=1.0 |
| python-dotenv 1.2.1 | Python >=3.9 | Python 3.10 (current) | Framework-agnostic |
| SQLAlchemy 2.0.46 | Python >=3.7 | Python 3.10 (current) | Phase 2 only |
| alembic 1.18.4 | SQLAlchemy >=1.4 | SQLAlchemy 2.0.46 | Phase 2 only |
| ruff 0.15.2 | Python >=3.7 | All | Dev/CI only |

---

## Installation

```bash
# Authentication + Security (Phase 1 — immediate)
pip install flask-jwt-extended==4.7.1
pip install flask-talisman==1.1.0
pip install flask-limiter==4.1.1

# Environment configuration (Phase 1)
pip install python-dotenv==1.2.1

# Async workers for SSE (Phase 1)
pip install gevent

# Error monitoring (Phase 1)
pip install "sentry-sdk[flask]==2.52.0"

# Database migration (Phase 2 — only if PostgreSQL migration planned)
pip install SQLAlchemy==2.0.46 alembic==1.18.4 Flask-SQLAlchemy==3.1.1

# Dev/CI only
pip install ruff==0.15.2 mypy
```

In `backend/pyproject.toml`:
```toml
[project]
dependencies = [
    # existing deps...
    "flask-jwt-extended>=4.7.1",
    "flask-talisman>=1.1.0",
    "flask-limiter[redis]>=4.1.1",
    "python-dotenv>=1.2.1",
    "gevent>=24.0",
    "sentry-sdk[flask]>=2.52.0",
]

[tool.uv.dev-dependencies]
dev = [
    "ruff>=0.15.2",
    "mypy>=1.0",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

---

## Priority Order for Implementation

This is not a rebuild — it is additive hardening. Sequence by risk reduction per effort:

1. **`python-dotenv` + `SECRET_KEY` in `.env`** — fixes the SECRET_KEY regeneration bug with zero risk
2. **`gunicorn.conf.py` with `worker_class = "gevent"` and `workers = 1`** — fixes concurrent SSE, documented single-worker constraint
3. **`flask-jwt-extended`** — adds auth; this is the largest engineering effort and blocks multi-user safety
4. **`flask-talisman` + `flask-limiter`** — security hardening on top of auth
5. **`sentry-sdk`** — operational visibility
6. **Caddy/systemd deployment config** — replaces `just deploy` running the Flask dev server
7. **`ruff` in CI** — code quality
8. **SQLAlchemy + Alembic** — only if PostgreSQL migration is explicitly scheduled

---

## Sources

- Flask-JWT-Extended docs: https://flask-jwt-extended.readthedocs.io/en/stable/installation.html (version 4.7.1 confirmed)
- flask-talisman GitHub (wntrblm fork): https://github.com/wntrblm/flask-talisman (v1.1.0, Nov 2025)
- Flask-Limiter docs: https://flask-limiter.readthedocs.io/ (v4.1.1 confirmed)
- sentry-sdk PyPI: https://pypi.org/project/sentry-sdk/ (v2.52.0 confirmed)
- SQLAlchemy releases: https://www.sqlalchemy.org/blog/2025/10/10/sqlalchemy-2.0.44-released/ (2.0.46 confirmed Jan 2026)
- Alembic docs: https://alembic.sqlalchemy.org/ (v1.18.4 confirmed)
- python-dotenv releases: https://github.com/theskumar/python-dotenv/releases (v1.2.1, Oct 2025)
- ruff PyPI: https://pypi.org/project/ruff/ (v0.15.2 confirmed)
- redis-py PyPI: https://pypi.org/project/redis/ (v7.1.1, Python 3.10+)
- Gunicorn + gevent Flask docs: https://flask.palletsprojects.com/en/stable/deploying/gevent/
- Flask production hardening (Apr 2025): https://medium.com/@vicfcs/hardening-your-python-flask-app-for-production-the-essential-security-checklist-f9b5402c47ff
- Caddy vs Nginx 2025: https://onidel.com/blog/caddy-vs-nginx-vps-2025
- Python tooling 2025: https://osquant.com/papers/python-tooling-in-2025/
- Context7: flask-jwt-extended library ID /vimalloc/flask-jwt-extended (verified config options)

---

*Stack research for: Agented — production hardening of Flask+Vue bot automation platform*
*Researched: 2026-02-25*
