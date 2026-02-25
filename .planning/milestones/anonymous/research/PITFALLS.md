# Pitfalls Research

**Domain:** Flask bot automation platform — production hardening
**Researched:** 2026-02-25
**Confidence:** HIGH (codebase-verified) / MEDIUM (deployment patterns, verified via multiple sources)

---

## Critical Pitfalls

### Pitfall 1: Auth Middleware That Misses the Webhook Receiver

**What goes wrong:** The inbound webhook receiver at `POST /` (`backend/app/routes/webhook.py`) is structurally different from all `/admin/*` and `/api/*` routes. A `before_request` guard added at the app or blueprint level will likely protect the management API but leave the webhook endpoint either always blocked (if the guard applies globally with no exemption) or always open (if only `APIBlueprint`-scoped guards are used). The same risk applies to the GitHub webhook at `/api/webhooks/github/`, which already has its own HMAC validation that must not be replaced or double-wrapped by a JWT check.

**Why it happens:** The codebase has 44+ blueprints registered in a barrel (`routes/__init__.py`). When auth is added as a `before_request` on the app object or on specific blueprints, the developer must manually audit every blueprint for correctness. Blueprints registered before the auth decorator is attached do not automatically inherit it. flask-openapi3's `APIBlueprint` does not support a built-in `before_request` inheritance mechanism that guarantees coverage.

**How to avoid:**
- Add auth as an `app.before_request` handler (not per-blueprint) with an explicit allowlist of exempt paths: `["/", "/api/webhooks/github/", "/health/*", "/docs/*", "/openapi/*"]`
- Use path-prefix matching (`request.path.startswith(...)`) rather than blueprint names; blueprint name lookups are fragile
- Write an integration test that verifies every blueprint route returns `401` without a token before auth launch — use the OpenAPI spec (`/openapi/openapi.json`) to enumerate all routes programmatically

**Warning signs:**
- Webhook triggers stop firing in staging immediately after auth is enabled
- Health checks start returning 401 (breaks load balancer liveness probes)
- `/docs` Swagger UI stops loading (returns 401 instead of HTML)
- GitHub webhook HMAC validation is skipped because the `before_request` handler aborts before reaching the route function

**Phase to address:** Auth implementation phase (earliest auth phase)

---

### Pitfall 2: Auth Token Injected Into SSE EventSource (Browser Can't Set Headers)

**What goes wrong:** `EventSource` in the browser does not support custom request headers. If the auth scheme uses `Authorization: Bearer <token>` headers, all SSE endpoints (`/admin/executions/{id}/stream`, `/admin/super-agents/{id}/sessions/{id}/stream`, `/admin/workflows/executions/{id}/stream`, etc.) will be inaccessible from the frontend after auth is added — the `EventSource` constructor only accepts a URL.

**Why it happens:** The frontend uses `new EventSource(url)` directly in composables (`useAiChat.ts`, `useWorkflowExecution.ts`, `useProjectSession.ts`, etc.) with no provision for auth headers. JWT in headers is the most common Flask auth pattern, but headers cannot be set on `EventSource`.

**How to avoid:**
- Use short-lived signed query-string tokens for SSE endpoints only (e.g., `?token=<short-lived-jwt>`) — generate them server-side at stream subscription time, expire them in 30–60 seconds
- Alternatively use cookie-based auth; cookies are sent automatically with `EventSource` requests
- Do NOT attempt to convert SSE endpoints to polling to work around auth — this destroys real-time UX
- Identify all SSE endpoints before the auth phase: grep `EventSource` and `yield` + `stream_with_context` in the backend

**Warning signs:**
- SSE streams work in unit tests (which use the Flask test client, not `EventSource`) but fail in the browser after auth is added
- Execution log viewer shows no output; monitoring charts go blank
- `401` responses visible in browser DevTools Network tab for `/stream` URLs

**Phase to address:** Auth implementation phase, must be resolved before SSE endpoints are gated

---

### Pitfall 3: Gunicorn Sync Workers Kill SSE Connections After Default 30-Second Timeout

**What goes wrong:** The `just deploy` command runs `python run.py` directly (Flask dev server), not gunicorn. If/when gunicorn is adopted for production, the default worker class is `sync` with a 30-second timeout. SSE streams are long-lived HTTP connections held open until execution completes — Claude executions can run for many minutes. Every SSE connection on a sync worker will be killed at 30 seconds with `[CRITICAL] WORKER TIMEOUT`.

**Why it happens:** Gunicorn sync workers interpret "silent for N seconds" as worker hang. An SSE generator that `Queue.get(timeout=30)` between events will be silent for up to 30 seconds between log lines, hitting the default timeout. This is a well-known and documented gunicorn issue (GitHub issues #1801, #677, #1186).

**How to avoid:**
- Use `--worker-class gevent` with `--worker-connections 1000` for SSE support; gevent green threads can hold thousands of concurrent SSE connections without blocking
- Set `--timeout 0` only with async workers (gevent/eventlet) — with sync workers, timeout=0 disables the timeout entirely and risks zombie workers
- If gevent is chosen, call `monkey.patch_all()` before `create_app()` in the gunicorn config's `post_fork` hook, not at module import time — patching at import time in the master process causes incorrect fork semantics
- Alternative: use `gthread` workers with `--threads 4` and `--timeout 120`; thread workers can hold SSE connections across thread switches without green thread complexity
- Write a gunicorn config file (`backend/gunicorn.conf.py`) and commit it; do not rely on undocumented CLI flags

**Warning signs:**
- SSE log stream cuts off exactly at 30 seconds in production but works in dev
- `[CRITICAL] WORKER TIMEOUT` appears in gunicorn logs
- Execution logs appear complete in the database but the frontend shows truncated output

**Phase to address:** Deployment infrastructure phase

---

### Pitfall 4: Gevent Monkey Patching Breaks APScheduler Threading and Subprocess PGID Kill

**What goes wrong:** If gevent is adopted for SSE workers, `gevent.monkey.patch_all()` replaces Python's `threading` module with gevent greenlets. `APScheduler` uses `threading.Thread` and `threading.Event` internally. After monkey-patching, APScheduler's background scheduler may deadlock, fire jobs at wrong intervals, or fail silently. Separately, `os.killpg(os.getpgid(process.pid), signal.SIGKILL)` in `execution_service.py` (lines 518 and 826) sends a signal to the process group of a subprocess. With gevent's I/O loop, the SIGKILL delivery and the gevent hub's reaction to the subprocess pipe closing can race, leaving zombie processes.

**Why it happens:** Gevent patches `threading.Thread` to use greenlets but does not patch `os.killpg` or `subprocess.Popen`. The subprocess is a real OS process with a real PGID (`start_new_session=True` is already used, which is correct). The interaction between gevent's cooperative I/O and blocking `process.wait()` in `run_trigger` is the danger point: `process.wait()` is a blocking call that gevent cannot yield on without an explicit `spawn`.

**How to avoid:**
- Patch selectively: `monkey.patch_all(thread=False)` if APScheduler thread compatibility is required; test APScheduler job firing rates under gevent before deploying
- Move `process.wait()` to a dedicated `gevent.spawn()` greenlet so the gevent hub can yield; never call blocking wait in the request greenlet
- Consider `gthread` workers as an alternative to gevent entirely — `gthread` does not monkey-patch and has no APScheduler conflict
- Add an integration test that verifies a scheduled trigger fires on time when running under the production worker class

**Warning signs:**
- APScheduler logs show jobs skipped or fired twice after deploying gevent workers
- `CRITICAL` log from gevent hub: "switch to hub with no active callbacks"
- Subprocess zombie processes visible in `ps aux` after execution completes

**Phase to address:** Deployment infrastructure phase, before gevent adoption

---

### Pitfall 5: Multi-Worker Gunicorn Splits SSE Subscribers Across Processes

**What goes wrong:** `ExecutionLogService._subscribers` is a class-level `Dict[str, List[Queue]]` stored in each worker's private memory. If gunicorn runs with `--workers 2+`, an SSE subscriber connecting to worker A will never receive log lines appended by the execution running in worker B. The client will receive the initial replay (up to `SSE_REPLAY_LIMIT=500`) and then wait forever. This applies to every in-memory subscriber pattern in the codebase:

| Service | In-Memory State Affected |
|---|---|
| `ExecutionLogService` | `_log_buffers`, `_subscribers` |
| `ProjectSessionManager` | `_sessions`, `_subscribers` |
| `AgentMessageBusService` | `_subscribers` |
| `WorkflowExecutionService` | `_executions` |
| `ProcessManager` | `_processes`, `_cancelled` |
| `MonitoringService` | `_recent_alerts` |

**Why it happens:** The pre-fork model of gunicorn forks worker processes after app initialization. Each worker gets its own copy of the class-level state at fork time, but subsequent mutations (log appends, subscriber registrations) are isolated. Gunicorn's `--workers 1` masks this entirely in development.

**How to avoid:**
- Enforce `--workers 1` explicitly until in-memory state is migrated to a shared backend (Redis or DB)
- Document this constraint prominently in `gunicorn.conf.py` with a comment
- Phase the migration: migrate SSE pub/sub to Redis first (Redis `PUBLISH`/`SUBSCRIBE`); migrate process tracking to the database second
- The `ProcessManager._processes` dict (which tracks running subprocesses) *cannot* be shared across processes without IPC redesign — the actual `subprocess.Popen` object is process-local

**Warning signs:**
- SSE log viewer loads the first 500 replayed lines but never updates while execution is running
- `ProcessManager.cancel(execution_id)` returns "not found" even though the execution is listed as running
- PGID-based kill (`os.killpg`) fails with `ProcessLookupError` because the PID was registered in a different worker

**Phase to address:** State persistence phase (must precede any multi-worker deployment)

---

### Pitfall 6: `isolated_db` Fixture Breaks When Auth Middleware Reads from a Second Config Path

**What goes wrong:** The `isolated_db` fixture patches `app.config.DB_PATH` via `monkeypatch.setattr`. This works because `get_connection()` reads `config.DB_PATH` dynamically at call time. If auth is implemented using flask-jwt-extended or similar, the JWT extension reads its own configuration from `app.config["JWT_*"]` keys, not from `app.config`. If auth middleware also performs a DB lookup (e.g., to validate a user token or check a revocation list), and that DB lookup uses a separate config key or a module-level constant captured at import time, the `isolated_db` patch will not redirect those reads.

**Why it happens:** The `monkeypatch.setattr` approach is fragile against module-level constants and import-time captures. The fixture patches `app.config.DB_PATH` but not `app.db.connection.DB_PATH` if the connection module caches the value. Any new code that reads the DB path at module import time rather than call time will silently use the production DB during tests.

**How to avoid:**
- Add `assert isolated_db in str(get_connection)` — or more practically, add a sanity assertion in conftest that the DB path used by the first query matches the temp path
- When implementing auth middleware, ensure any DB lookups in the middleware go through `get_connection()` (which reads `config.DB_PATH` dynamically) not a module-level constant
- Add a test that creates a token revocation record and verifies it is visible only in the test DB, not in a shared state

**Warning signs:**
- Auth-related tests pass individually but fail when run in parallel (due to shared state in a non-patched DB)
- Tests that create users or tokens unexpectedly find pre-existing data
- A test's `isolated_db` teardown produces warnings about missing tables from auth-related queries

**Phase to address:** Auth implementation phase — verify fixture coverage before writing auth tests

---

### Pitfall 7: SQLite Dialect SQL Fails on PostgreSQL Migration (Boolean, RETURNING, PRAGMA)

**What goes wrong:** The codebase uses raw SQL with SQLite-specific features throughout 80+ DB function files. A PostgreSQL migration requires auditing every query. Key incompatibilities:

| SQLite Pattern | PostgreSQL Equivalent | Files at Risk |
|---|---|---|
| `WHERE enabled = 1` | `WHERE enabled = TRUE` | Most list query functions |
| `INSERT OR IGNORE INTO` | `INSERT ... ON CONFLICT DO NOTHING` | `migrations.py` seeding |
| `INSERT OR REPLACE INTO` | `INSERT ... ON CONFLICT DO UPDATE` | Several upsert functions |
| `PRAGMA foreign_keys = ON` | Not applicable (always on) | `connection.py` |
| `PRAGMA busy_timeout = 5000` | Use connection pool retry | `connection.py` |
| `PRAGMA journal_mode=WAL` | Not applicable | `migrations.py` |
| `SELECT last_insert_rowid()` | `RETURNING id` or `cursor.lastrowid` | ID retrieval throughout |
| Integer booleans `0`/`1` | Boolean `true`/`false` | Schema and queries |
| `strftime('%Y-...')` | `to_char(...)` | Monitoring/scheduling queries |

The 3,210-line `migrations.py` contains 53 migrations written entirely in SQLite SQL. All DDL, seeding, and migration SQL would need to be rewritten or abstracted.

**Why it happens:** Raw SQL without an ORM couples every query to the database dialect. The codebase explicitly chose raw SQL over SQLAlchemy for simplicity (see ARCHITECTURE.md §Key Design Decisions), which means there is no abstraction layer to swap.

**How to avoid:**
- Do not attempt a big-bang SQLite → PostgreSQL cutover; the risk is too high with 80+ query files
- If PostgreSQL is required, introduce SQLAlchemy as an ORM in a new module and incrementally port domain modules (start with least-critical: `budgets.py`, end with `migrations.py`)
- Alternatively, treat SQLite as the production DB and address its real limitations directly (connection pooling via `sqlite-pool` or `aiosqlite`, WAL checkpoint tuning) — SQLite is viable for single-node deployment
- If migration is planned, add a `DB_DIALECT` environment variable and write an adapter layer around the 5 most-used query patterns before porting

**Warning signs:**
- Queries return empty result sets silently (boolean 0/1 vs true/false mismatch)
- `INSERT OR IGNORE` raises `ProgrammingError` syntax error on PostgreSQL
- ID generation after INSERT returns `None` (SQLite `lastrowid` not available in psycopg2 without `RETURNING`)

**Phase to address:** Database migration phase — must precede any multi-machine deployment

---

### Pitfall 8: WAL Checkpoint Starvation Under Concurrent SSE Connections

**What goes wrong:** SQLite WAL mode allows concurrent readers, but a checkpoint (which recycles the WAL file) requires an exclusive lock that blocks all readers. `ExecutionLogService` holds SSE connections open for the duration of executions — each SSE subscriber holds an open HTTP connection but not necessarily an open SQLite connection. However, the `_budget_monitor` thread and `_stream_pipe` thread each call `ExecutionLogService.append_log()` which in turn calls `get_connection()` per log line, resulting in dozens of short-lived read+write transactions per second during active executions. Under concurrent executions, the WAL file grows without bound until a checkpoint can acquire an exclusive window.

**Why it happens:** The `get_connection()` pattern opens and closes a new connection per operation (no pooling). This creates rapid connection churn. SQLite's WAL mode checkpoints are cooperative — they require all readers to finish. With constant new readers arriving (one per `append_log` call), the checkpoint window never opens.

**How to avoid:**
- Enable auto-checkpoint with `PRAGMA wal_autocheckpoint=1000` (default is 1000 pages) and verify the WAL file does not grow unbounded under load test
- Batch log appends: buffer 10–50 log lines in memory before a single DB write instead of one connection per line
- Monitor WAL file size in production: `ls -la backend/agented.db-wal` and alert if it exceeds 100MB
- Long-term: if connection pressure is severe, introduce a connection pool (`sqlite3` does not natively pool; use `threading.local()` to reuse one connection per thread)

**Warning signs:**
- `backend/agented.db-wal` file grows beyond 10MB during active executions
- SQLite `SQLITE_BUSY` (5-second timeout exhausted) errors appear in logs during high concurrency
- Execution log writes begin failing silently under load

**Phase to address:** Performance and reliability phase

---

### Pitfall 9: ExecutionService God Module Refactoring Breaks In-Flight State

**What goes wrong:** `execution_service.py` (1,387 lines) holds class-level dicts (`_rate_limit_detected`, `_pending_retries`, `_retry_timers`, `_retry_counts`) that track live execution state. If the refactoring splits `ExecutionService` into multiple smaller classes mid-execution (e.g., `RateLimitTracker`, `RetryScheduler`, `PromptRenderer`), any in-flight execution that was registered against the old class will lose its state reference. The same applies to `ProcessManager._processes` — if the class is moved or renamed, existing registered processes become invisible to cancellation.

**Why it happens:** Class-level (not instance-level) state means the state lives on the class object itself. Renaming or splitting the class requires migrating all state at once. There is no migration path for live state across a code refactor in a running server.

**How to avoid:**
- Refactor execution service only during maintenance windows (no active executions)
- Start the refactor by extracting **stateless** helpers first: `PromptRenderer`, `CommandBuilder`, `GitHubCloner` — these have no class-level state and can be extracted safely at any time
- Extract stateful components last and only after the state is persisted to the database (then the class dict is just a cache, not the source of truth)
- Keep the existing `ExecutionService` class as a facade with the original method signatures pointing to the new sub-services — do not rename the class
- Add a health check that counts active executions before and after each refactor step in CI

**Warning signs:**
- `ProcessManager.cancel(execution_id)` stops working after a code refactor
- Rate limit retry timers fire twice (if both old and new class are instantiated)
- Test failures in `test_execution_flow.py` that worked before the refactor

**Phase to address:** Service refactoring phase — after state is persisted to DB, before any multi-worker deployment

---

### Pitfall 10: migrations.py Partial Failure Leaves Schema in Unknown State

**What goes wrong:** `migrations.py` runs all pending migrations in a single `conn` context. The comment at line 180 states "the database will be rolled back" on failure, implying transaction rollback. However, `conn.commit()` is only called after all migrations succeed. If migration N fails partway through, the transaction rolls back and the database remains at version N-1. But some migrations include `PRAGMA` statements (`ALTER TABLE`, `CREATE INDEX`) that in SQLite have implicit commit semantics and cannot be rolled back. A failed migration that ran `ALTER TABLE` before raising an exception will have applied the column addition but not updated `schema_version`, leaving the database schema ahead of the version counter.

**Why it happens:** SQLite's `ALTER TABLE` is not transactional in all cases. In SQLite, DDL statements do participate in transactions, but `PRAGMA` changes do not. The migration runner assumes full rollback but this is only true for DML. The 53-migration history already shows this pattern — many migrations mix DDL and DML.

**How to avoid:**
- Add a `--dry-run` mode to `init_db()` that prints SQL without executing, for pre-production validation
- Back up `agented.db` before every migration run in production (`sqlite3 agented.db .backup agented.db.bak`)
- Wrap each migration in its own transaction with explicit savepoints where possible
- For the PostgreSQL path: use Alembic (not custom migration code); Alembic handles transactional DDL correctly on PostgreSQL

**Warning signs:**
- Server fails to start with `RuntimeError: migration N failed` but database is not at version N-1 (schema is ahead)
- `ALTER TABLE` succeeded but `schema_version` is behind by 1
- Running `init_db()` a second time after a failure re-attempts an already-partially-applied migration

**Phase to address:** Database stability phase — immediately

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `--workers 1` gunicorn constraint | Avoids all multi-process state issues | Single point of failure; no horizontal scale | Until SSE pub/sub is moved to Redis |
| Query-string tokens for SSE auth | No frontend changes needed | Tokens in access logs; short-lived mitigates risk | Acceptable with 60-second expiry |
| Keep `ExecutionService` facade class | No caller changes during refactor | Facade accumulates forever if not removed | During transition only; remove after migration |
| Batch log appends (buffer 10 lines) | Reduces SQLite connection churn | Adds up to ~100ms log delivery latency | Acceptable for audit logging; not for real-time debugging |
| SQLite in production (single node) | Zero migration work | Hard ceiling on write throughput; no multi-machine | Valid if single-server deployment is the target |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| flask-jwt-extended + SSE | Using `@jwt_required()` on SSE route (EventSource cannot send headers) | Short-lived query-string token or cookie-based auth for `/stream` endpoints |
| gunicorn + APScheduler | APScheduler starts in every forked worker (N schedulers running) | Use `--preload` + guard scheduler start with `os.getpid() == master_pid` or use gunicorn's `post_fork` hook |
| gunicorn + subprocess PGID kill | `os.killpg` sends signal to wrong process group if the worker was forked after the subprocess started | Always use `start_new_session=True` in `Popen` (already done) and verify the PGID is captured before any fork |
| `isolated_db` + auth middleware | JWT token validation hits DB path captured at import time | Ensure all DB reads in auth middleware go through `get_connection()` (dynamic read of `config.DB_PATH`) |
| SQLite `INSERT OR REPLACE` → PostgreSQL | Silently deletes and re-inserts the row (losing foreign key references) | Use `INSERT ... ON CONFLICT DO UPDATE SET` (UPSERT) which updates in place |
| gevent + `threading.Lock` | `_rate_limit_lock` in ExecutionService may deadlock under gevent cooperative scheduling if a lock-holder yields to the hub | Use `gevent.lock.RLock` instead of `threading.Lock` if adopting gevent workers |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| One SQLite connection per log line | WAL file grows unbounded; `SQLITE_BUSY` under load | Batch log writes; buffer 10–50 lines per DB write | > 5 concurrent long-running executions |
| `_log_buffers` unbounded growth | Memory spike during long Claude sessions | Cap buffer at `SSE_REPLAY_LIMIT` (already capped for replay; cap the buffer itself) | Sessions producing > 10,000 log lines |
| Thread-per-execution × 3 threads | Thread count = 3 × concurrent executions | Use thread pool with bounded workers | > 50 concurrent executions |
| `_webhook_dedup` dict never pruned | Memory leak proportional to unique webhook payloads | Prune entries older than `WEBHOOK_DEDUP_WINDOW` on each insert | Long-lived server with diverse webhook sources |
| `_repo_last_event` dict never pruned | Memory leak proportional to unique repos | Prune entries older than rate-limit window on each insert | Servers handling many different repositories |

---

## "Looks Done But Isn't" Checklist

- [ ] **Auth on webhook endpoint:** Verify `POST /` still accepts valid HMAC-signed payloads after auth is added — webhook receiver has no user context
- [ ] **Auth on SSE endpoints:** Verify `/stream` endpoints are actually gated — EventSource in browser cannot set headers, so a naive `@jwt_required()` silently breaks all live log streaming
- [ ] **Gunicorn worker count:** Verify `--workers 1` is enforced; the default gunicorn worker count is `(2 * cpu_count) + 1` which will silently break all SSE subscriptions
- [ ] **APScheduler under gunicorn:** Verify scheduled triggers fire exactly once (not once per worker) when gunicorn is used
- [ ] **SECRET_KEY persistence:** Verify `SECRET_KEY` is set in the environment; without it, every server restart invalidates any session-based auth tokens
- [ ] **CORS on auth endpoints:** Verify `CORS_ALLOWED_ORIGINS` is set to the actual frontend domain; the default `*` bypasses CORS protection entirely
- [ ] **Migrations backup:** Verify a pre-migration DB backup exists before each production `init_db()` run
- [ ] **Boolean queries on PostgreSQL:** Verify all `WHERE column = 1` queries are changed to `WHERE column = TRUE` before PostgreSQL cutover

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Auth misses webhook receiver | Auth implementation | Integration test: every route returns 401 without token; webhook fires with HMAC but no JWT |
| EventSource can't send auth headers | Auth implementation | Browser smoke test: SSE log stream works after auth enabled |
| Gunicorn sync worker kills SSE at 30s | Deployment infrastructure | Load test: SSE stream survives 5-minute execution |
| Gevent breaks APScheduler + PGID kill | Deployment infrastructure | Scheduled trigger fires on time under gevent; subprocess kill works |
| Multi-worker splits SSE subscribers | State persistence (before multi-worker) | Test: subscriber in worker A receives logs from execution in worker B |
| `isolated_db` breaks with auth middleware | Auth implementation | Auth tests use isolated DB; no production DB contamination |
| SQLite dialect breaks on PostgreSQL | Database migration phase | Test suite passes against PostgreSQL target |
| WAL checkpoint starvation | Performance phase | Monitor `agented.db-wal` size under 10-execution load test |
| ExecutionService refactor breaks in-flight state | Service refactoring phase | Zero active executions during refactor; state persisted to DB first |
| migrations.py partial failure | Database stability (immediate) | Pre-migration backup script in CI; `--dry-run` mode before applying |

---

## Sources

- Gunicorn GitHub issues: [#1801](https://github.com/benoitc/gunicorn/issues/1801), [#677](https://github.com/benoitc/gunicorn/issues/677), [#1186](https://github.com/benoitc/gunicorn/issues/1186) — SSE with sync workers
- [Gunicorn Guide — Better Stack](https://betterstack.com/community/guides/scaling-python/gunicorn-explained/) — worker types and timeout behavior
- [Sharing data across gunicorn workers — JG Lee, Medium](https://medium.com/@jgleeee/sharing-data-across-workers-in-a-gunicorn-flask-application-2ad698591875) — process isolation pitfall
- [SQLite WAL mode — official docs](https://sqlite.org/wal.html) — checkpoint starvation mechanism
- [SQLite in Production with WAL — victoria.dev](https://victoria.dev/posts/sqlite-in-production-with-wal/) — WAL production guidance
- [Migrating Flask app to PostgreSQL — shallowsky.com](https://shallowsky.com/blog/tags/postgresql/) — dialect incompatibility list (reserved words, integer sequences, capitalization)
- [Flask-SSE docs — quickstart](https://flask-sse.readthedocs.io/en/latest/quickstart.html) — Redis pub/sub requirement for multi-process
- [Are You Making These Critical Mistakes with Python Singletons — leocon.dev](https://www.leocon.dev/blog/2025/06/are-you-making-these-critical-mistakes-with-python-singletons/) — class-level state thread safety
- [gevent monkey patching and APScheduler — gunicorn issue #1056](https://github.com/benoitc/gunicorn/issues/1056) — monkey patch ordering
- [Flask-JWT-Extended docs](https://flask-jwt-extended.readthedocs.io/en/stable/basic_usage.html) — before_request auth patterns
- Codebase analysis: `backend/app/services/execution_service.py`, `backend/app/db/migrations.py`, `backend/app/__init__.py`, `backend/app/db/connection.py`, `backend/tests/conftest.py` — verified against actual code (2026-02-25)

---
*Pitfalls research for: Flask bot automation platform — production hardening*
*Researched: 2026-02-25*
