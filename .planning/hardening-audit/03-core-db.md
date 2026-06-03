# Hardening Audit 03 — Core App Wiring (DB, middleware, exceptions, lifecycle, streaming)

Scope: `app_litestar/{main,exception_handlers,lifecycle}.py`, `app/database.py`,
`app/db/connection.py`, `app/services/{error_capture,circuit_breaker_service,
streaming_helper,conversation_streaming,health_monitor_service,retention_service}.py`.

Verdict: SQL access is well-disciplined (all parameterized; dynamic clauses use
static column literals or `safe_set_clause`). The real risks are in lifecycle
boot robustness, streaming-generator resource leakage on client disconnect, and a
couple of error-message leaks. Severity counts below.

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 3 |
| MEDIUM | 5 |
| LOW | 4 |

---

## HIGH

### H1 — CLI streaming generators leak subprocess + Timer thread on client disconnect
`app/services/conversation_streaming.py:728` (`_stream_via_cli`) and
`:838` (`_stream_via_opencode_cli`).

Both are `Generator`s that `subprocess.Popen(...)`, start a `threading.Timer`, and
`yield` inside a `while True` reading `proc.stdout`. There is **no `try/finally`
and no `GeneratorExit` handling**. When the SSE client disconnects, Litestar stops
iterating and the generator is garbage-collected mid-loop. The cleanup code
(`proc.wait()`, `timer.cancel()` at lines 804/805 and 915/916) only runs on the
normal exit path. On disconnect:
- The `claude`/`opencode` child process is **orphaned** (never `.kill()`ed, never
  reaped) — it keeps running and holding model/account resources until its own
  `SUBPROCESS_TIMEOUT` Timer fires.
- The `threading.Timer` stays armed; if the process already exited, `proc.kill()`
  in `_on_timeout` is a no-op, but the timer thread lingers.
- `proc.stdout`/`proc.stderr` pipes are not closed.

Under repeated client disconnects (browser tab close, navigation, network drop)
this accumulates orphaned subprocesses and pipe FDs → FD/process exhaustion.

Fix: wrap the read loop in `try: ... finally:` that always runs
`timer.cancel()`, `proc.kill()` (guarded by `except (OSError, ProcessLookupError)`),
`proc.stdout.close()`/`proc.stderr.close()`, and `proc.wait()`. Explicitly catch
`GeneratorExit` (or rely on `finally`, which runs on GC/close) to terminate the
child. Example skeleton:
```python
try:
    proc = subprocess.Popen(...)
    timer = threading.Timer(SUBPROCESS_TIMEOUT, _on_timeout); timer.start()
    while True:
        ...
        yield text
finally:
    timer.cancel()
    if proc.poll() is None:
        try: proc.kill()
        except (OSError, ProcessLookupError): pass
    for p in (proc.stdout, proc.stderr):
        try: p and p.close()
        except OSError: pass
    proc.wait()
```

### H2 — Unguarded startup steps crash the worker on boot
`app_litestar/lifecycle.py:397` `_init_database()`, `:410` `_detect_backends()`,
`:471` `_setup_scheduler(None)`, `:472` `_register_cleanup_handlers()`.

Inside `on_startup`, most side-effect blocks are wrapped in `try/except` (good),
but these four bare calls are **not**. With `workers=1` (per CLAUDE.md /
gunicorn.conf), any exception raised here (e.g. a migration failure, a disk-full
DB write, a corrupt SQLite file, a scheduler init error) propagates out of the
Litestar `on_startup` hook and **the single worker dies before serving any
traffic** — full outage, not graceful degradation. `_init_database` in
particular runs migrations and is the most likely to throw.

Fix: decide per-call which are truly fatal. `_init_database()` failing is
arguably fatal (you want a fast, loud crash with a clear log) — if so, wrap it to
log a structured fatal error first, then re-raise. `_detect_backends`,
`_setup_scheduler`, and `_register_cleanup_handlers` are degradable: wrap each in
its own `try/except Exception: logger.error(..., exc_info=True)` so the app still
boots and serves health/UI even if a background subsystem fails. Match the
pattern already used for the surrounding blocks (lines 390/400/414/426/436/450/462/476).

### H3 — `value_error_handler` leaks raw exception text to clients
`app_litestar/exception_handlers.py:93` (`value_error_handler`):
```python
return _json_response("VALIDATION_ERROR", f"Validation failed: {exc}", 422)
```

Every uncaught `ValueError` anywhere in a request path is rendered verbatim into
the response body. Unlike `integrity_error_handler` (`del exc`, generic message)
and `operational_error_handler` (generic "Service temporarily unavailable"), this
one passes internal `str(exc)` straight to the client. `ValueError` is raised in
many internal spots (parsing, `int()` casts, `safe_set_clause`'s
`"Unsafe expression in SET clause: ..."`, config lookups) that were never meant
to be user-facing and can disclose column names, internal identifiers, or logic.

Fix: return a fixed message (`"Validation failed"`) and log `str(exc)` server-side
via `logger`/`capture_error`. Only echo `exc` when it originates from a
deliberately client-safe validation path (e.g. a dedicated `ClientValidationError`
subclass), not the broad `ValueError` catch-all.

---

## MEDIUM

### M1 — `session_persist_error_handler` echoes `str(exc)`
`exception_handlers.py:142`: `detail = str(exc) or "Session persist failed"`.
The handler is registered for a broad `Exception` (the PSM `SessionPersistError`),
and the raw exception string is returned in the 409 body. If any non-PSM
`Exception` is ever routed here, or the PSM message embeds FK/SQL detail, it leaks.
Fix: map to a controlled message; log the detail instead of returning it.

### M2 — `get_connection()` provides no transaction safety; callers own commit/rollback
`app/db/connection.py` `get_connection()` yields a raw `sqlite3.Connection` and
only `conn.close()`s in `finally` — **no `commit()` on success, no `rollback()` on
exception**. sqlite3's default deferred-transaction behavior means an exception
mid-write inside the `with` block leaves an implicit transaction that is discarded
on close (acceptable rollback-by-accident), but a success path that forgets an
explicit `conn.commit()` **silently loses the write** with no error. This is a
foot-gun pattern repeated across ~20 `app/db/*` modules.
Fix: make the context manager transactional — `try: yield conn; conn.commit()
except: conn.rollback(); raise finally: conn.close()`. Audit callers that already
commit to avoid double-commit (harmless but worth a pass). At minimum document the
contract loudly in the docstring.

### M3 — No WAL / connection reuse; new connection per call under `workers=1`
`get_connection()` opens a fresh `sqlite3.connect(DB_PATH)` every call with
`busy_timeout=5000` but **no `PRAGMA journal_mode=WAL`**. With multiple threads
(scheduler jobs, message-bus dispatchers, streaming threads) writing concurrently
in rollback-journal mode, writers serialize hard and readers block writers,
making the 5s busy-timeout reachable under load → `OperationalError: database is
locked`. Fix: set `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` once
at init; consider a connection pool or per-thread connection.

### M4 — Retention "cleanup" is a no-op; data grows unbounded
`app/services/retention_service.py:126` `enqueue_cleanup()` only counts active
policies and returns a message — it performs **zero deletes** ("destructive
enforcement ships in a follow-up"). Policies can be created and toggled, but
nothing is ever purged through this path. Combined with the fact that the only
real purges are the scheduler jobs in `lifecycle.py`
(`purge_trigger_events_job`, `purge_super_agent_activity_job`,
`refresh_stale_model_caches`), tables governed by retention *policies* (e.g.
`execution_logs`, `system_errors`, `traces`) grow without bound. For a
long-running production instance this is a disk-exhaustion / query-slowdown risk.
Fix: implement the destructive sweep (parameterized `DELETE ... WHERE created_at <
?` per policy, batched + `VACUUM`-aware), or clearly gate the feature so operators
don't assume retention is enforced.

### M5 — HSTS sent unconditionally regardless of scheme
`app_litestar/middleware.py:315` sets
`Strict-Transport-Security: max-age=31536000; includeSubDomains` on **every**
response, including plain-HTTP dev/LAN access (`VITE_HOST=0.0.0.0` demos noted in
CLAUDE.md). A browser that reaches the backend once over HTTPS will then refuse
HTTP for a year for that host+subdomains. If the backend is ever exposed on a bare
host/IP over HTTP for a demo, this can wedge access. Fix: only emit HSTS when the
request is HTTPS (check `scope["scheme"] == "https"` or `X-Forwarded-Proto`), or
gate it behind a production env flag.

---

## LOW

### L1 — CSP allows `'unsafe-inline'` for scripts and styles
`middleware.py:303-304`: `script-src 'self' 'unsafe-inline'` and
`style-src 'self' 'unsafe-inline'`. Justified for Swagger UI at `/schema/swagger`,
but `'unsafe-inline'` in `script-src` defeats the main XSS protection CSP offers
for the whole app, not just the docs route. Fix: scope the relaxed CSP to the
`/schema/*` routes only and keep a strict `script-src 'self'` (nonce/hash-based if
inline is truly needed) everywhere else.

### L2 — CLI prompt passed via argv (process-list / argument exposure)
`conversation_streaming.py` `_stream_via_cli`: `cmd = ["claude", "-p", prompt,
...]`. The full prompt (which may contain user/system message content, secrets in
context, repo data) is an argv element, visible to any local user via `ps`/`/proc`
and to process-listing audit tools. Fix: pass the prompt via stdin
(`Popen(..., stdin=PIPE)` then `proc.stdin.write`) rather than the command line.

### L3 — `error_capture` and circuit-breaker swallow all exceptions to logs only
`error_capture.py:101` and `circuit_breaker_service.py:155/381/405/423` use broad
`except Exception:` then `logger.exception(...)`. These are intentional best-effort
sinks (a logging/telemetry failure must not break the request), so this is
acceptable — but note the persistence failures in `_persist_state` (`:423`) mean
circuit-breaker state can silently diverge from the DB. Low risk; flagging for
awareness. No change required beyond ensuring these never become the *only* signal.

### L4 — `not_found_handler` reads SPA index on every non-API 404
`exception_handlers.py:69`: `_SPA_INDEX.read_bytes()` is performed per 404 request
with only an `except OSError: pass`. Not a correctness bug, but a 404 flood does
synchronous disk reads on the event loop and a silently-swallowed OSError yields a
generic JSON 404 with no log. Fix: cache the index bytes at startup; log the OSError.

---

## Confirmed NON-issues (verified, no action)

- **SQL injection**: All `f"...{', '.join(updates)}..."` UPDATE/WHERE builders
  (`trigger_conditions.py:115`, `project_sa_instances.py:110`, `plugins.py`,
  `rbac.py:207`, `findings.py:118`, `system_errors.py`, `tracing.py`,
  `executions.py`) interpolate only **static column-name literals** appended in
  `if`-guarded blocks (`updates.append("name = ?")`), never user values. Values
  always go through `?` placeholders. `system_errors.py:189` additionally routes
  through `safe_set_clause()` which regex-validates each expression. No injection.
- `app/database.py` is a pure re-export shim (31 lines) — no logic.
- CORS (`main.py:169`): `allow_credentials=True` is paired with an **explicit
  origin allowlist** (env CSV + localhost dev), not `*` — correct.
- `unhandled_handler` (`:146`) returns a generic `"Internal server error"` body
  and routes the traceback to `error_capture` only — no stack-trace leak to client.
- `integrity_error_handler` / `operational_error_handler` use generic messages and
  `del exc` — correct.
- Middleware ordering in `main.py:203-216` is deliberate and documented (RequestContext
  before RateLimit/ApiKey; SecurityHeaders innermost cross-cutting) — sound.
