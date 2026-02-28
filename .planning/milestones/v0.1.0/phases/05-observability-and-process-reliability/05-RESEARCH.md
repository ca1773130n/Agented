# Phase 5: Observability and Process Reliability - Research

**Researched:** 2026-02-28
**Domain:** Structured logging, error tracking, webhook deduplication, Flask middleware
**Confidence:** HIGH

## Summary

This phase adds three observability and reliability capabilities to the Agented backend: (1) structured JSON logging with request ID correlation on every log line, (2) Sentry SDK integration for error tracking, and (3) DB-backed webhook deduplication that survives server restarts. All three requirements address documented concerns in the codebase analysis: CONCERNS.md Section 4.2 (no structured error monitoring), Section 5.1 (in-memory webhook dedup lost on restart), and the general absence of request-level traceability across log lines.

The technical domain is well-understood. `python-json-logger` is the standard library-compatible JSON formatter for Python logging. It integrates directly with the existing `logging.getLogger(__name__)` pattern used across all 90+ service classes. The Sentry Python SDK 2.x auto-detects Flask and provides turnkey error tracking with a single `sentry_sdk.init()` call. Webhook deduplication via a SQLite table with a UNIQUE constraint and TTL-based cleanup is a standard idempotency key pattern documented extensively in distributed systems literature.

The primary complexity lies in two areas: (1) propagating request IDs through the gevent-based concurrency model using Python's `contextvars` module (which gevent >= 20.5 patches correctly), and (2) initializing the Sentry SDK at the correct point in the Gunicorn/gevent worker lifecycle to avoid socket patching conflicts. Both challenges have well-documented solutions.

**Primary recommendation:** Use `python-json-logger` with a `contextvars`-based `logging.Filter` for request ID injection, `sentry-sdk[flask]` initialized at module level in `run.py` (before Gunicorn forks), and a `webhook_dedup_keys` SQLite table with a UNIQUE index on `(trigger_id, payload_hash)` and periodic TTL cleanup via APScheduler.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: python-json-logger for structured logging (not structlog)

**Recommendation:** Use `python-json-logger` v3.x with a custom `logging.Filter` for request ID injection. Do NOT adopt structlog.

**Evidence:**
- [python-json-logger Official Docs / Cookbook](https://github.com/nhairs/python-json-logger/blob/main/docs/cookbook.md) -- Provides three patterns for request ID injection: `extra` dict, `logging.Filter`, and formatter subclass override. The `logging.Filter` pattern is the most maintainable because it injects `request_id` into every `LogRecord` automatically without requiring changes at call sites.
- [Context7: python-json-logger /nhairs/python-json-logger](https://context7.com/nhairs/python-json-logger/llms.txt) -- Benchmark score 90.7, HIGH source reputation. Confirms `JsonFormatter` supports arbitrary extra fields and produces parseable JSON output.
- [structlog Official Docs](https://www.structlog.org/en/stable/standard-library.html) -- structlog requires replacing all `logging.getLogger(__name__)` calls with `structlog.get_logger()` across the entire codebase. The Agented backend has 90+ service files using stdlib logging.
- [BetterStack Comparison (2025)](https://betterstack.com/community/guides/logging/best-python-logging-libraries/) -- Recommends structlog for greenfield projects but notes that python-json-logger is the standard choice for adding JSON output to existing logging setups.

**Confidence:** HIGH -- Multiple authoritative sources agree. python-json-logger is a stdlib-compatible drop-in that requires zero changes to existing `logger.info(...)` call sites.

**Expected improvement:** Every log line becomes machine-parseable JSON with `request_id`, `timestamp`, `level`, `logger`, and `message` fields. Log aggregation tools (Datadog, CloudWatch, Loki) can index and filter by request ID.

**Caveats:** python-json-logger v3.x uses a new package namespace (`pythonjsonlogger.json.JsonFormatter` instead of `pythonjsonlogger.jsonlogger.JsonFormatter`). The import path changed between v2 and v3; use the v3 path.

### Recommendation 2: contextvars for request ID propagation (not threading.local)

**Recommendation:** Use Python's `contextvars.ContextVar` for storing the request ID. Set it in a Flask `before_request` handler. Read it in a `logging.Filter`.

**Evidence:**
- [Python contextvars Documentation (3.10+)](https://docs.python.org/3/library/contextvars.html) -- `ContextVar` is natively supported in Python 3.10+ (the project's target). Context variables are scoped to the current execution context, which under gevent corresponds to the current greenlet.
- [gevent 20.5+ Release Notes](https://github.com/gevent/gevent/blob/master/CHANGES.rst) -- gevent >= 20.5 patches `contextvars` correctly when `monkey.patch_all()` is called. Each greenlet gets its own copy of context variables. The project uses gevent >= 24.10.1 (confirmed in `pyproject.toml`).
- [structlog contextvars Documentation](https://www.structlog.org/en/stable/contextvars.html) -- While we do not use structlog itself, its documentation validates the pattern: "contextvars can be thread-local if using threads or stored in the asyncio event loop" and provides Flask examples using `before_request` to bind request IDs.
- [flask-log-request-id GitHub](https://github.com/Workable/flask-log-request-id) -- Popular Flask extension (500+ stars) that implements exactly this pattern. We do not need the library itself (it would be an unnecessary dependency), but its architecture validates the approach: `before_request` handler reads or generates UUID, stores in context, `logging.Filter` reads from context.

**Confidence:** HIGH -- Python stdlib, gevent source code, and multiple Flask extension implementations confirm the pattern works correctly under gevent monkey patching with Python 3.10+.

**Expected improvement:** Every log line during a request includes the same `request_id` UUID. Background tasks (APScheduler jobs, daemon threads) will have `request_id=null`, clearly distinguishing request-scoped from background logs.

**Caveats:** The `_trace_logger` pattern already used in `execution_service.py` (line 40) creates a `LoggerAdapter` with a `trace_id` for execution-scoped logging. The new request ID is orthogonal: `request_id` tracks the HTTP request, `trace_id` tracks the execution. Both can coexist on the same log line.

### Recommendation 3: Sentry SDK 2.x with FlaskIntegration

**Recommendation:** Use `sentry-sdk[flask]` >= 2.0 with `FlaskIntegration()`. Initialize at module level in `run.py` before `create_app()`. Configure `SENTRY_DSN` via environment variable with a no-op when unset.

**Evidence:**
- [Sentry Official Flask Documentation](https://docs.sentry.io/platforms/python/integrations/flask/) -- States: "If you have the flask package in your dependencies, the Flask integration will be enabled automatically." FlaskIntegration hooks into Flask signals (not the app object) and captures request context, user info, and breadcrumbs automatically.
- [Context7: sentry-sdk /getsentry/sentry-python](https://context7.com/getsentry/sentry-python/llms.txt) -- Benchmark score 91.3, HIGH source reputation. Confirms `sentry_sdk.init()` with `integrations=[FlaskIntegration()]`, `traces_sample_rate`, and `send_default_pii` parameters.
- [Sentry SDK 2.0 Migration Guide](https://github.com/getsentry/sentry-python/discussions/2980) -- SDK 2.x is the current major version. Auto-enables Flask integration. Uses `contextvars` for scope isolation (compatible with gevent >= 20.5).
- [Sentry Gunicorn Troubleshooting](https://docs.sentry.io/platforms/python/troubleshooting/) -- Documents that gevent older than 20.5 causes context leakage, but this is resolved in recent gevent versions. Our gevent >= 24.10.1 is well above this threshold.

**Confidence:** HIGH -- Official Sentry docs, Context7 verification, and GitHub discussions confirm Flask integration is turnkey. The gevent compatibility concern is resolved in our version.

**Expected improvement:** Unhandled exceptions are automatically captured with full request context (URL, headers, user, breadcrumbs) and appear in the Sentry dashboard within seconds. Performance transactions provide latency breakdown by endpoint.

**Caveats:**
1. **Initialization timing with Gunicorn/gevent:** Sentry SDK 2.x handles Gunicorn workers correctly when initialized at module level. The SDK detects the gevent monkey patching and adapts its transport accordingly. Do NOT initialize in `post_fork()` or `post_worker_init()` -- the module-level initialization in `run.py` is correct because Gunicorn with `preload_app=False` (our current config) loads `run.py` fresh in each worker AFTER monkey patching.
2. **DSN must be optional:** When `SENTRY_DSN` is not set, `sentry_sdk.init(dsn="")` is a no-op. This means local development works without Sentry configuration. The init call should always be present but guarded by the DSN value.
3. **SSE endpoints should not create transactions:** The long-lived SSE stream endpoints (`/admin/executions/{id}/stream`, super-agent session streams) would create extremely long transactions. Use `before_send_transaction` to filter these out.

### Recommendation 4: SQLite-backed webhook deduplication with UNIQUE constraint

**Recommendation:** Create a `webhook_dedup_keys` table with columns `(trigger_id TEXT, payload_hash TEXT, created_at REAL, PRIMARY KEY (trigger_id, payload_hash))`. Use `INSERT OR IGNORE` for atomic check-and-insert. Clean up expired entries via an APScheduler job.

**Evidence:**
- [Webhook Deduplication Checklist (Latenode, 2025)](https://latenode.com/blog/integration-api-management/webhook-setup-configuration/webhook-deduplication-checklist-for-developers) -- Recommends: "Store idempotency keys in durable storage using atomic operations to check and store keys simultaneously, avoiding race conditions."
- [Idempotency in API Design (Technori, 2026)](https://technori.com/2026/02/24486-idempotency-in-api-design-prevent-duplicates/editorial-team/) -- Documents the standard pattern: unique key generation, persistent storage with uniqueness constraint, TTL-based expiry. Recommends retention period matching the retry horizon.
- [SQLite INSERT OR IGNORE Documentation](https://www.sqlite.org/lang_insert.html) -- `INSERT OR IGNORE` silently skips the insert when a UNIQUE constraint is violated, making it an atomic check-and-insert operation. No SELECT-then-INSERT race condition.
- [Codebase Analysis: CONCERNS.md Section 5.1](/.planning/codebase/CONCERNS.md) -- Documents the current problem: "This state is in-memory only and is lost on server restart. A flood of webhooks that arrives immediately after a restart will bypass deduplication."
- [Existing Implementation: execution_service.py lines 1153-1173](backend/app/services/execution_service.py) -- Current in-memory dedup uses `hashlib.sha256` of `json.dumps(payload, sort_keys=True, default=str)` truncated to 16 hex chars. The same hash computation can be reused for the DB-backed version.

**Confidence:** HIGH -- SQLite UNIQUE constraints and INSERT OR IGNORE is a well-documented atomic operation. The pattern is standard for idempotency keys in relational databases.

**Expected improvement:** Webhook deduplication survives server restarts. The 10-second dedup window (currently `WEBHOOK_DEDUP_WINDOW = 10`) is preserved but now persisted. The in-memory dict can be removed entirely or kept as a fast-path cache in front of the DB.

**Caveats:**
1. **TTL cleanup frequency:** With a 10-second dedup window, entries expire quickly. A cleanup job running every 60 seconds is sufficient to prevent unbounded table growth. Use APScheduler since it is already initialized in the app factory.
2. **SQLite write contention:** With `workers=1`, there is no multi-process contention. The `busy_timeout=5000` already configured in `get_connection()` handles any greenlet-level contention from concurrent webhook arrivals.
3. **Dual-layer optimization:** Keep the in-memory dict as a fast-path check (avoids a DB round-trip for rapid consecutive duplicates), but always write to DB and check DB as the source of truth. This means: check memory first, if not found check DB, if not found insert into both.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-json-logger | >= 3.2.0 | JSON log formatter for stdlib logging | Official cookbook covers request ID injection; drop-in for existing `logging.getLogger()` pattern; 1800+ GitHub stars |
| sentry-sdk | >= 2.0.0 | Error tracking and performance monitoring | Official Sentry Python SDK; auto-detects Flask; FlaskIntegration is turnkey; 2000+ GitHub stars |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none -- all supporting libraries are already in the project) | | | |

Note: `contextvars` is Python stdlib (3.7+). `uuid` is Python stdlib. `hashlib` is Python stdlib. No new supporting dependencies needed.

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Evidence |
|------------|-----------|----------|----------|
| python-json-logger | structlog | structlog is more powerful but requires replacing all 90+ `logging.getLogger(__name__)` calls with `structlog.get_logger()`. Too invasive for this codebase. | [structlog docs: Standard Library Logging](https://www.structlog.org/en/stable/standard-library.html) |
| python-json-logger | loguru | loguru replaces stdlib logging entirely (not interoperable). Would break all existing `logging.getLogger` patterns and flask-openapi3's internal logging. | [BetterStack comparison](https://betterstack.com/community/guides/logging/best-python-logging-libraries/) |
| Custom `logging.Filter` for request ID | flask-log-request-id library | Adds an unnecessary dependency for a 15-line filter. The library does exactly what we need but brings configuration complexity for minimal benefit. | [flask-log-request-id GitHub](https://github.com/Workable/flask-log-request-id) |
| SQLite dedup table | Redis with TTL keys | Redis provides native TTL expiry and atomic SETNX but adds infrastructure dependency. SQLite is sufficient for `workers=1` and avoids new operational complexity. | System design standard -- use the simplest datastore that meets requirements |

**Installation:**
```bash
# Add to pyproject.toml dependencies:
# "python-json-logger>=3.2.0"
# "sentry-sdk[flask]>=2.0.0"
cd backend && uv sync
```

## Architecture Patterns

### Recommended Project Structure Changes

```
backend/
├── app/
│   ├── __init__.py              # Add Sentry init call in create_app() (MODIFIED)
│   ├── logging_config.py        # NEW: JSON logging setup, RequestIdFilter, configure_logging()
│   ├── middleware.py             # NEW: before_request/after_request hooks for request ID
│   ├── db/
│   │   ├── migrations.py        # Add webhook_dedup_keys table migration (MODIFIED)
│   │   ├── schema.py            # Add webhook_dedup_keys to fresh schema (MODIFIED)
│   │   └── webhook_dedup.py     # NEW: check_dedup_key(), insert_dedup_key(), cleanup_expired()
│   └── services/
│       └── execution_service.py # Replace in-memory dedup with DB-backed dedup (MODIFIED)
├── run.py                       # Add sentry_sdk.init() and configure_logging() (MODIFIED)
├── .env.example                 # Add SENTRY_DSN and LOG_FORMAT variables (MODIFIED)
```

### Pattern 1: Request ID via contextvars + logging.Filter

**What:** Generate a UUID4 request ID in `before_request`, store it in a `ContextVar`, and inject it into every `LogRecord` via a `logging.Filter` attached to the root logger.
**When to use:** Every HTTP request. Background tasks (APScheduler) will have `request_id=None`.
**Source:** [python-json-logger Cookbook: Request IDs](https://github.com/nhairs/python-json-logger/blob/main/docs/cookbook.md)

**Example:**
```python
# backend/app/logging_config.py
# Source: python-json-logger cookbook + Flask before_request pattern
import logging
import uuid
from contextvars import ContextVar
from pythonjsonlogger.json import JsonFormatter

# Context variable for request-scoped request ID
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Inject request_id from contextvars into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()  # type: ignore[attr-defined]
        return True


def configure_logging(log_level: str = "INFO") -> None:
    """Configure root logger with JSON formatter and request ID filter."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    root.handlers.clear()

    handler = logging.StreamHandler()
    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.addFilter(RequestIdFilter())
```

### Pattern 2: Flask middleware for request lifecycle

**What:** `before_request` generates and stores request ID; `after_request` adds it to response headers.
**When to use:** Registered in `create_app()`.
**Source:** [structlog Flask integration example](https://www.structlog.org/en/stable/contextvars.html), adapted for stdlib logging

**Example:**
```python
# backend/app/middleware.py
# Source: structlog Flask example adapted for stdlib + contextvars
import uuid
from flask import g, request
from .logging_config import request_id_var


def init_request_middleware(app):
    """Register before/after request hooks for request ID tracking."""

    @app.before_request
    def set_request_id():
        # Honor incoming X-Request-ID header (from load balancer or upstream)
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(rid)
        g.request_id = rid

    @app.after_request
    def add_request_id_header(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers["X-Request-ID"] = rid
        return response
```

### Pattern 3: Sentry initialization with environment guard

**What:** Initialize Sentry at module level in `run.py`, guarded by `SENTRY_DSN` environment variable. When DSN is empty, Sentry is a no-op.
**When to use:** Always present in `run.py`. Active only when `SENTRY_DSN` is configured.
**Source:** [Sentry Flask Integration Docs](https://docs.sentry.io/platforms/python/integrations/flask/)

**Example:**
```python
# In run.py, after load_dotenv() and before create_app()
# Source: Sentry official Flask docs
import os
import sentry_sdk

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("SENTRY_RELEASE", "agented@0.1.0"),
        send_default_pii=False,
        # Filter out long-lived SSE transactions
        before_send_transaction=_filter_sse_transactions,
    )


def _filter_sse_transactions(event, hint):
    """Drop transactions for SSE streaming endpoints."""
    transaction_name = event.get("transaction", "")
    if "/stream" in transaction_name or "/sessions/" in transaction_name:
        return None
    return event
```

### Pattern 4: DB-backed webhook deduplication with INSERT OR IGNORE

**What:** Use a SQLite table with a composite UNIQUE key on `(trigger_id, payload_hash)`. `INSERT OR IGNORE` is atomic: it inserts if the key is new, does nothing if it exists.
**When to use:** In `dispatch_webhook_event()` to replace the in-memory `_webhook_dedup` dict.
**Source:** [SQLite INSERT OR IGNORE docs](https://www.sqlite.org/lang_insert.html), [Webhook deduplication checklist](https://latenode.com/blog/integration-api-management/webhook-setup-configuration/webhook-deduplication-checklist-for-developers)

**Example:**
```python
# backend/app/db/webhook_dedup.py
# Source: SQLite INSERT OR IGNORE + standard idempotency key pattern
import time
from .connection import get_connection


def check_and_insert_dedup_key(trigger_id: str, payload_hash: str, ttl_seconds: int = 10) -> bool:
    """Atomically check if a dedup key exists and insert if not.

    Returns True if the key was NEW (not a duplicate).
    Returns False if the key already exists (IS a duplicate).
    """
    now = time.time()
    with get_connection() as conn:
        # First, clean up any expired entry for this exact key
        conn.execute(
            "DELETE FROM webhook_dedup_keys WHERE trigger_id = ? AND payload_hash = ? AND created_at < ?",
            (trigger_id, payload_hash, now - ttl_seconds),
        )
        # Atomic insert-or-ignore: returns rowcount=1 if inserted, 0 if duplicate
        cursor = conn.execute(
            "INSERT OR IGNORE INTO webhook_dedup_keys (trigger_id, payload_hash, created_at) VALUES (?, ?, ?)",
            (trigger_id, payload_hash, now),
        )
        conn.commit()
        return cursor.rowcount > 0


def cleanup_expired_keys(ttl_seconds: int = 10) -> int:
    """Remove dedup keys older than TTL. Returns count of deleted rows."""
    cutoff = time.time() - ttl_seconds
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM webhook_dedup_keys WHERE created_at < ?", (cutoff,)
        )
        conn.commit()
        return cursor.rowcount
```

### Anti-Patterns to Avoid

- **Replacing stdlib logging with structlog across 90+ files:** Invasive change with high risk of breaking existing log patterns. python-json-logger achieves JSON output without changing call sites.
- **Initializing Sentry in `post_fork()` or `post_worker_init()`:** With `preload_app=False` (our config), `run.py` is loaded fresh in each worker AFTER monkey patching. Module-level init is correct and simpler.
- **Using SELECT-then-INSERT for deduplication:** Race condition between the SELECT and INSERT under concurrent greenlets. `INSERT OR IGNORE` is atomic.
- **Storing the full webhook payload in the dedup table:** Only the hash is needed. Storing full payloads wastes disk and slows queries.
- **Making Sentry DSN required:** Must be optional. Local development and CI should not need a Sentry account.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON log formatting | Custom `json.dumps()` in log handlers | `python-json-logger` `JsonFormatter` | Handles datetime serialization, exception formatting, extra fields, encoding edge cases |
| Error tracking | Custom exception handler that POSTs to an API | `sentry-sdk` with `FlaskIntegration` | Automatic breadcrumbs, stack traces, request context, performance transactions, source maps |
| Request ID generation | Custom sequential counter or timestamp-based ID | `uuid.uuid4()` | Cryptographically random, no collision risk, 122 bits of entropy |
| Atomic dedup check | SELECT + INSERT with application-level locking | SQLite `INSERT OR IGNORE` on UNIQUE constraint | Database-level atomicity, no race conditions, zero application locking code |

**Key insight:** Every component in this phase has a well-established library solution. The engineering is integration: wiring the JSON formatter to the root logger, calling `sentry_sdk.init()` at the right lifecycle point, and creating a simple SQLite table with the right constraints.

## Common Pitfalls

### Pitfall 1: Forgetting to clear contextvars between requests

**What goes wrong:** Without clearing the `ContextVar` at the start of each request, a request ID from a previous greenlet could leak into a new request if gevent reuses the greenlet's context.
**Why it happens:** Gevent may reuse greenlets from a pool, carrying forward context from the previous request.
**How to avoid:** Always call `request_id_var.set(new_uuid)` in `before_request`. This overwrites any stale value. Optionally also call `request_id_var.set(None)` in `teardown_request` for defense-in-depth.
**Warning signs:** Log lines showing mismatched request IDs (two different requests sharing the same UUID).
**Source:** [structlog contextvars docs](https://www.structlog.org/en/stable/contextvars.html) -- "clear_contextvars() at the beginning of your request handler."

### Pitfall 2: JSON formatter breaking Gunicorn's access log

**What goes wrong:** If the JSON formatter is applied to the root logger (which Gunicorn's access logger inherits from), Gunicorn's access log lines become doubly formatted or garbled.
**Why it happens:** Gunicorn configures its own access log format via `accesslog` and `access_log_format`. If the root handler also has a JSON formatter, both formatters apply.
**How to avoid:** Either (a) configure the JSON formatter on the `app.*` logger hierarchy only (not the root), or (b) set Gunicorn's `accesslog = None` and let application-level logging handle all output, or (c) give Gunicorn's logger a separate handler that bypasses JSON formatting. Option (b) is simplest: disable Gunicorn's access log and log request lifecycle in the `after_request` middleware instead.
**Warning signs:** Garbled log output with mixed JSON and plaintext lines.

### Pitfall 3: Sentry capturing expected errors as incidents

**What goes wrong:** HTTP 404 and 400 responses (which are normal application behavior) flood Sentry with noise, making real errors hard to find.
**Why it happens:** Sentry's Flask integration captures all unhandled exceptions by default. Flask's `@app.errorhandler(404)` catches 404 before it reaches Sentry, but any uncaught exception (including `abort(400)` in some configurations) propagates.
**How to avoid:** Use `before_send` to filter events by fingerprint or exception type. Specifically, ignore `werkzeug.exceptions.NotFound` and `werkzeug.exceptions.BadRequest`. The existing error handlers in `create_app()` already catch 404/405/413/500, so Sentry should only see truly unhandled exceptions.
**Warning signs:** Sentry dashboard flooded with 404/400 events.

### Pitfall 4: Dedup cleanup job running too infrequently

**What goes wrong:** If the cleanup job runs less frequently than the dedup window (10 seconds), expired entries accumulate. While `check_and_insert_dedup_key()` cleans up the specific key being checked, orphaned entries from triggers that are no longer active remain forever.
**Why it happens:** The 10-second dedup window is very short. Without periodic cleanup, the table grows proportionally to webhook traffic volume.
**How to avoid:** Schedule a cleanup job via APScheduler at 60-second intervals. The cleanup deletes all rows with `created_at < (now - ttl)`. With a 10-second TTL, rows are at most 70 seconds old after cleanup.
**Warning signs:** Growing `webhook_dedup_keys` row count visible in SQLite analysis tools.

### Pitfall 5: SSE endpoints creating long Sentry transactions

**What goes wrong:** SSE endpoints (`/admin/executions/{id}/stream`) keep connections open for minutes. Sentry creates a transaction for each request, leading to extremely long-duration transactions that distort performance metrics and consume Sentry quota.
**Why it happens:** Flask's request lifecycle wraps SSE generators. Sentry's Flask integration creates a transaction at request start and closes it at request end.
**How to avoid:** Use `before_send_transaction` callback to drop transactions whose name matches SSE endpoint patterns (e.g., contains `/stream` or long-lived session endpoints).
**Warning signs:** Sentry performance dashboard showing multi-minute transactions.

## Experiment Design

### Recommended Experimental Setup

This phase is operational infrastructure. The "experiments" are integration smoke tests, not algorithm benchmarks.

**Independent variables:** Logging configuration (JSON vs plaintext), Sentry DSN (present vs absent), dedup storage (memory vs DB)
**Dependent variables:** Log output format, Sentry event delivery, dedup survival across restarts
**Controlled variables:** Application code (routes, services unchanged), webhook payloads (same test payloads)

**Baseline comparison:**
- Current state: Plaintext `%(asctime)s [%(levelname)s] %(name)s: %(message)s` with no request ID; no Sentry; in-memory dedup lost on restart
- Target state: JSON `{"timestamp": ..., "level": ..., "logger": ..., "message": ..., "request_id": ...}`; Sentry captures unhandled exceptions; dedup keys persisted in SQLite

**Validation plan:**
1. **Request ID correlation test:** Make an API call, grep logs for the returned `X-Request-ID` header value, verify all log lines from that request share the same UUID.
2. **Sentry delivery test:** Configure `SENTRY_DSN` with a test project. Call a route that raises an unhandled exception. Verify the event appears in the Sentry dashboard within 60 seconds.
3. **Dedup survival test:** Send webhook payload A twice (expect second deduplicated). Restart server. Send payload A again (expect third deduplicated because key is in DB). Verify via execution log that only one execution was created.
4. **Dedup TTL test:** Send webhook payload B. Wait 15 seconds (past the 10-second window). Send payload B again. Verify both result in executions (TTL expired, no dedup).
5. **Background log test:** Trigger an APScheduler job. Verify its log lines have `request_id: null` (not a stale request ID from a previous greenlet).

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Request ID presence on log lines | Core OBS-01 requirement | `grep -c '"request_id"' logfile` / total log lines | 0% (no request IDs currently) |
| Sentry event delivery latency | OBS-02 requirement | Time between exception raise and Sentry dashboard appearance | N/A (no Sentry currently) |
| Dedup survival across restart | OBS-03 requirement | Send same payload before and after restart, count executions | Fails (in-memory dedup lost) |
| Dedup table size after 1 hour | Operational health | `SELECT COUNT(*) FROM webhook_dedup_keys` | N/A (table does not exist) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Log lines contain `request_id` field | Level 1 (Sanity) | Grep log output for JSON with request_id key |
| Request ID is consistent across all logs for one request | Level 2 (Proxy) | Make API call, collect all log lines with that UUID, verify count > 1 |
| Sentry receives unhandled exception within 60 seconds | Level 2 (Proxy) | Trigger exception, check Sentry API for event |
| Dedup survives server restart | Level 2 (Proxy) | Three-payload restart test from success criteria |
| Dedup TTL expiry works correctly | Level 2 (Proxy) | Wait past TTL, verify re-delivery succeeds |
| SSE endpoints do not create Sentry transactions | Level 2 (Proxy) | Open SSE stream, verify no transaction in Sentry |
| Background tasks have null request_id | Level 2 (Proxy) | Trigger scheduler job, check log line |
| Dedup cleanup job prevents table growth | Level 3 (Deferred) | Run under sustained webhook load for 1 hour, check table size |

**Level 1 checks to always include:**
- `curl http://localhost:20000/admin/triggers` and verify response includes `X-Request-ID` header
- Application logs show JSON format with `request_id`, `timestamp`, `level`, `logger` fields
- `SENTRY_DSN` env var documented in `.env.example`
- `webhook_dedup_keys` table exists in SQLite schema

**Level 2 proxy metrics:**
- Full request ID correlation test (all log lines for one request share UUID)
- Sentry delivery test (unhandled exception appears within 60 seconds)
- Three-payload restart dedup test

**Level 3 deferred items:**
- Load testing dedup table under high webhook volume
- Sentry transaction sampling rate tuning based on production traffic volume
- Structured log alerting rules in log aggregation tool

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is an empty template. The following are derived from codebase analysis (CONCERNS.md) and research findings.

### Known Failure Modes

- **Sentry SDK transport failure:** If the Sentry ingest endpoint is unreachable, the SDK queues events in memory (default 100) and drops them silently after the queue fills. This is by design -- error tracking should never break the application.
  - Prevention: Monitor Sentry project's "Rejected Events" metric in the Sentry dashboard.
  - Detection: If Sentry dashboard shows zero events for a service that is known to be running, check network connectivity to `sentry.io`.

- **JSON logging breaking log parsing for existing tools:** If any existing tooling (monitoring scripts, systemd journal parsers) depends on the plaintext log format `%(asctime)s [%(levelname)s] %(name)s: %(message)s`, switching to JSON will break them.
  - Prevention: Add a `LOG_FORMAT` env var (`json` or `text`) that controls whether JSON or plaintext formatter is used. Default to `json` in production, allow `text` for development readability.
  - Detection: Log processing pipeline failures after deployment.

- **SQLite dedup table locking under burst webhook traffic:** Many concurrent webhook arrivals can contend on the `INSERT OR IGNORE` into `webhook_dedup_keys`. With `workers=1` and gevent, this is cooperative (not parallel), so contention is sequential and the 5-second `busy_timeout` is more than sufficient.
  - Prevention: The `workers=1` constraint eliminates true parallel write contention.
  - Detection: SQLite `OperationalError: database is locked` in logs.

### Scaling Concerns

- **At current scale (single user, local):** JSON logging, Sentry, and SQLite dedup are all lightweight. No performance concern.
- **At production scale (multiple users, high webhook traffic):** The dedup table grows linearly with unique webhook payloads per TTL window. With a 10-second TTL and cleanup every 60 seconds, the table stays small. Sentry SDK batches events and has minimal overhead (documented at < 1ms per request in their benchmarks). JSON logging is marginally slower than plaintext due to serialization, but `python-json-logger` uses `json.dumps` which is fast for small records.

### Common Implementation Traps

- **Logging inside the logging filter:** If the `RequestIdFilter.filter()` method calls `logger.info(...)`, it creates infinite recursion. The filter must never log.
  - Correct approach: Filter should only read from `ContextVar` and assign to `record`. No logging.

- **Importing sentry_sdk at module level in service files:** Sentry should be initialized once in `run.py`. Service files should NOT import `sentry_sdk` to set tags or breadcrumbs -- instead use the automatic Flask integration which captures request context. If custom context is needed later, it can be added via middleware.
  - Correct approach: Initialize once, let FlaskIntegration handle context.

## Code Examples

Verified patterns from official sources:

### SQLite migration for webhook_dedup_keys table

```python
# In backend/app/db/migrations.py — append as next migration
# Source: SQLite CREATE TABLE docs + idempotency key pattern
def migrate_54(conn):
    """Add webhook_dedup_keys table for persistent webhook deduplication."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_dedup_keys (
            trigger_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (trigger_id, payload_hash)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_webhook_dedup_created
        ON webhook_dedup_keys (created_at)
    """)
```

### Updated dispatch_webhook_event dedup logic

```python
# In execution_service.py, replacing the in-memory dedup block
# Source: Adapted from existing code + DB-backed pattern
from ..db.webhook_dedup import check_and_insert_dedup_key

# ... inside dispatch_webhook_event, replacing lines 1153-1173:
payload_hash = hashlib.sha256(
    json.dumps(payload, sort_keys=True, default=str).encode()
).hexdigest()[:16]

is_new = check_and_insert_dedup_key(
    trigger_id=trigger["id"],
    payload_hash=payload_hash,
    ttl_seconds=cls.WEBHOOK_DEDUP_WINDOW,
)
if not is_new:
    logger.info(
        "Webhook dedup: skipping duplicate dispatch for trigger '%s' (DB-backed)",
        trigger["name"],
    )
    continue
```

### Complete logging_config.py

```python
# backend/app/logging_config.py
# Source: python-json-logger cookbook + contextvars pattern
import logging
import os
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Inject request_id from contextvars into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()  # type: ignore[attr-defined]
        return True


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure root logger with optional JSON formatting and request ID filter.

    Args:
        log_level: Python log level name (default: INFO)
        log_format: 'json' for structured JSON output, 'text' for human-readable
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler()

    if log_format == "json":
        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.addFilter(RequestIdFilter())
```

### Sentry initialization in run.py

```python
# In run.py, after load_dotenv() and logging config, before create_app()
# Source: Sentry official Flask docs
import os
import sentry_sdk

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    def _filter_sse_transactions(event, hint):
        """Drop Sentry transactions for long-lived SSE endpoints."""
        tx = event.get("transaction", "")
        if "/stream" in tx or "sessions/" in tx:
            return None
        return event

    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("SENTRY_RELEASE", "agented@0.1.0"),
        send_default_pii=False,
        before_send_transaction=_filter_sse_transactions,
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Source |
|--------------|------------------|--------------|--------|--------|
| Plaintext logging | Structured JSON logging | Widespread adoption ~2018-2020 | Machine-parseable logs, log aggregation, request correlation | python-json-logger, structlog adoption |
| No error tracking | Sentry SDK auto-instrumentation | Sentry SDK 1.0 (2021), 2.0 (2024) | Automatic exception capture, performance monitoring, breadcrumbs | Sentry official docs |
| In-memory dedup dicts | DB-backed idempotency keys | Standard pattern since distributed systems became common | Dedup survives restarts, no state loss | Webhook deduplication literature |
| threading.local for request context | contextvars (PEP 567) | Python 3.7 (2018), gevent support 20.5 (2020) | Works with asyncio, gevent, and threads; no manual cleanup | Python PEP 567, gevent release notes |

**Deprecated/outdated:**
- **`threading.local()` for request context:** Replaced by `contextvars` in Python 3.7+. `threading.local()` does not work correctly with gevent greenlets unless monkey patched, and even then `contextvars` is the cleaner solution.
- **python-json-logger v2 import path:** `pythonjsonlogger.jsonlogger.JsonFormatter` is the v2 path. v3 uses `pythonjsonlogger.json.JsonFormatter`. Always use the v3 path.
- **Sentry SDK 1.x:** SDK 2.x is current. Major differences include auto-enabled integrations and improved scope isolation.

## Open Questions

1. **Should Gunicorn access logging be disabled in favor of application-level request logging?**
   - What we know: Gunicorn has its own access log format configured via `accesslog = "-"`. Adding a JSON formatter to the root logger may cause Gunicorn's access logs to be double-formatted or garbled.
   - What's unclear: Whether Gunicorn's access logger inherits from the root logger or has an independent handler.
   - Recommendation: Set `accesslog = None` in `gunicorn.conf.py` and log request lifecycle (method, path, status code, duration) in the `after_request` middleware. This gives unified JSON logging for all output.

2. **Should the in-memory dedup dict be kept as a fast-path cache?**
   - What we know: The in-memory dict avoids a DB round-trip for rapid consecutive duplicates within the same process lifetime.
   - What's unclear: Whether the DB round-trip overhead is significant for the expected webhook volume.
   - Recommendation: Remove the in-memory dict entirely for simplicity. SQLite reads are fast (< 1ms for indexed lookups) and the `workers=1` constraint means there is no cross-process coordination concern. The DB is the single source of truth.

3. **Should `LOG_FORMAT` default to `json` or `text`?**
   - What we know: JSON is needed for production log aggregation. Plaintext is more readable during local development.
   - What's unclear: Whether developers will find JSON logs disruptive during `just dev-backend`.
   - Recommendation: Default to `json`. Developers who prefer plaintext can set `LOG_FORMAT=text` in their `.env`. Production deployments always want JSON.

## Sources

### Primary (HIGH confidence)
- [python-json-logger Official Docs and Cookbook](https://github.com/nhairs/python-json-logger) -- JSON formatter API, request ID injection patterns
- [Context7: python-json-logger /nhairs/python-json-logger](https://context7.com/nhairs/python-json-logger/llms.txt) -- Benchmark score 90.7, version verification
- [Sentry Official Flask Documentation](https://docs.sentry.io/platforms/python/integrations/flask/) -- FlaskIntegration setup, auto-detection
- [Context7: sentry-sdk /getsentry/sentry-python](https://context7.com/getsentry/sentry-python/llms.txt) -- Benchmark score 91.3, init parameters
- [Python contextvars Documentation (3.10+)](https://docs.python.org/3/library/contextvars.html) -- ContextVar API
- [SQLite INSERT OR IGNORE Documentation](https://www.sqlite.org/lang_insert.html) -- Atomic check-and-insert semantics
- Codebase: `.planning/codebase/CONCERNS.md` -- Sections 4.2, 5.1, 1.7
- Codebase: `backend/app/services/execution_service.py` -- Lines 97-120 (in-memory dedup), lines 1153-1173 (dedup logic)

### Secondary (MEDIUM confidence)
- [structlog contextvars Documentation](https://www.structlog.org/en/stable/contextvars.html) -- Flask integration pattern (validated approach even though we use stdlib)
- [Sentry SDK 2.0 Discussion](https://github.com/getsentry/sentry-python/discussions/2980) -- Migration guide, gevent compatibility notes
- [Sentry Troubleshooting: Gunicorn/gevent](https://docs.sentry.io/platforms/python/troubleshooting/) -- Gevent >= 20.5 compatibility confirmation
- [gevent 20.5+ Release Notes](https://github.com/gevent/gevent/blob/master/CHANGES.rst) -- contextvars patching support
- [flask-log-request-id GitHub](https://github.com/Workable/flask-log-request-id) -- Architecture validation for request ID middleware
- [Webhook Deduplication Checklist (Latenode)](https://latenode.com/blog/integration-api-management/webhook-setup-configuration/webhook-deduplication-checklist-for-developers) -- Idempotency key storage patterns
- [Idempotency in API Design (Technori, 2026)](https://technori.com/2026/02/24486-idempotency-in-api-design-prevent-duplicates/editorial-team/) -- TTL retention guidance

### Tertiary (LOW confidence)
- [BetterStack: Python Logging Libraries Comparison](https://betterstack.com/community/guides/logging/best-python-logging-libraries/) -- structlog vs python-json-logger comparison (blog post, verified against official docs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Both libraries (python-json-logger, sentry-sdk) are verified via Context7 with benchmark scores > 90
- Architecture: HIGH -- All patterns validated against official docs and existing Flask extensions
- Paper recommendations: HIGH -- Idempotency key pattern is well-established in distributed systems; logging and error tracking patterns are standard
- Pitfalls: HIGH -- All pitfalls derived from official documentation, GitHub issues, or codebase analysis with specific references

**Research date:** 2026-02-28
**Valid until:** 2026-05-28 (90 days -- stable domain; library release cadence is moderate)
