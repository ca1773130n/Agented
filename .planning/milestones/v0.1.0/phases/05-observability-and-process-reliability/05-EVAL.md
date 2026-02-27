# Evaluation Plan: Phase 5 — Observability and Process Reliability

**Designed:** 2026-02-28
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** python-json-logger + contextvars request ID correlation; sentry-sdk[flask] error tracking; SQLite INSERT OR IGNORE webhook deduplication
**Reference docs:** 05-RESEARCH.md (Recommendations 1-4, Pitfalls 1-5, Experiment Design)

---

## Evaluation Overview

Phase 5 addresses three discrete infrastructure gaps identified in CONCERNS.md: the absence of request-level log traceability (Section 4.2), missing error monitoring (Section 4.2), and the fragility of in-memory webhook deduplication that does not survive restarts (Section 5.1).

Unlike algorithmic phases where output quality is measured against benchmarks, this phase implements operational infrastructure. The evaluation is fundamentally integration-oriented: does each component wire correctly into the existing Flask + Gunicorn + gevent runtime, and does it produce the exact observable behavior specified in the success criteria? There are no paper benchmarks to reproduce — all targets derive from the phase success criteria and documented requirements (OBS-01, OBS-02, OBS-03).

The most critical deferred item is Sentry delivery verification (OBS-02), which requires a real Sentry DSN and cannot be automated without external infrastructure. It is classified as deferred with a human-in-the-loop gate. The structured logging (OBS-01) and dedup persistence (OBS-03) checks are fully automatable via pytest and shell scripts and are therefore evaluated at Level 1 and Level 2 respectively.

No proxy metrics have been invented without evidence. Where a metric can only be assessed manually or with external infrastructure, it is classified as deferred rather than approximated with a surrogate measure.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| JSON log structure (all required fields present) | OBS-01 requirement + 05-PLAN-01 success criteria | Direct measure of structured logging correctness |
| Request ID consistency within a single HTTP request | OBS-01 requirement + RESEARCH.md Experiment Design #1 | Traces the ContextVar propagation chain end-to-end |
| X-Request-ID header on every response | 05-PLAN-01 must_haves | Observable without log parsing; verifies middleware wiring |
| Background task request_id=null | 05-PLAN-01 must_haves | Verifies no greenlet context leakage across requests |
| Sentry event delivery within 60 seconds | OBS-02 success criterion | The literal production SLA from the requirement |
| SSE endpoints absent from Sentry transactions | 05-PLAN-02 must_haves + RESEARCH.md Pitfall 5 | Prevents Sentry quota drain and distorted performance metrics |
| webhook_dedup_keys table existence and schema | OBS-03 requirement + 05-PLAN-03 must_haves | Verifies DB migration ran correctly |
| Dedup survives server restart | OBS-03 success criterion (3-delivery test) | The literal requirement from the phase goal |
| TTL expiry allows re-delivery | 05-PLAN-03 success criteria | Ensures TTL mechanism is correctly implemented |
| Existing test suite still passes | Regression baseline | Confirms no breaking changes to existing functionality |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 9 | Import checks, schema verification, pytest regression, env doc checks |
| Proxy (L2) | 7 | Request ID correlation, dedup behavioral tests, log format verification |
| Deferred (L3) | 4 | Sentry live delivery, load testing, log aggregation rules, sampling tuning |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding to proxy evaluation.

### S1: python-json-logger imports cleanly

- **What:** The new dependency is installed and importable
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from pythonjsonlogger.json import JsonFormatter; print('OK')"`
- **Expected:** `OK` printed, no ImportError
- **Failure means:** `python-json-logger>=3.2.0` not added to `pyproject.toml` or `uv sync` was not run

### S2: logging_config module exports expected symbols

- **What:** The new `logging_config.py` module exports all three required symbols
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.logging_config import configure_logging, request_id_var, RequestIdFilter; configure_logging(); print('OK')"`
- **Expected:** `OK` printed, no ImportError or AttributeError
- **Failure means:** Module missing, wrong export names, or configure_logging() raises on first call

### S3: middleware module imports cleanly

- **What:** The new `middleware.py` module is importable
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.middleware import init_request_middleware; print('OK')"`
- **Expected:** `OK` printed
- **Failure means:** Module not created or has a syntax error

### S4: sentry-sdk imports cleanly

- **What:** The sentry-sdk[flask] dependency is installed and importable
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "import sentry_sdk; from sentry_sdk.integrations.flask import FlaskIntegration; print('OK')"`
- **Expected:** `OK` printed
- **Failure means:** `sentry-sdk[flask]>=2.0.0` not added to `pyproject.toml` or `uv sync` was not run

### S5: Server starts without errors when SENTRY_DSN is unset

- **What:** Application creates without Sentry raising errors when DSN is not configured
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && SENTRY_DSN="" uv run python -c "from run import application; print('app created OK')"`
- **Expected:** `app created OK` printed, no exception
- **Failure means:** Sentry initialization is not guarded by the DSN env var check, or the app factory has a new import error

### S6: webhook_dedup_keys table exists after DB initialization

- **What:** Migration 55 runs and creates the dedup table with the correct schema
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "
from app.database import init_db
from app.db.connection import get_connection
init_db()
with get_connection() as conn:
    tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
    assert 'webhook_dedup_keys' in tables, f'Table missing. Found: {tables}'
    cols = [r[1] for r in conn.execute(\"PRAGMA table_info(webhook_dedup_keys)\").fetchall()]
    assert 'trigger_id' in cols and 'payload_hash' in cols and 'created_at' in cols, f'Wrong columns: {cols}'
    idx = [r[1] for r in conn.execute(\"SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='webhook_dedup_keys'\").fetchall()]
    assert any('created' in i for i in idx), f'TTL index missing. Indexes: {idx}'
    print('Table and index OK')
"`
- **Expected:** `Table and index OK`
- **Failure means:** Migration not added to VERSIONED_MIGRATIONS, or schema.py not updated for fresh installs

### S7: DB dedup module imports cleanly

- **What:** The new `webhook_dedup.py` DB module exports the two required functions
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app.db.webhook_dedup import check_and_insert_dedup_key, cleanup_expired_keys; print('OK')"`
- **Expected:** `OK` printed
- **Failure means:** Module not created or has wrong function names

### S8: Sentry env vars documented in .env.example

- **What:** All four Sentry config vars are present in .env.example
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && grep -c "SENTRY_DSN" .env.example && grep -c "SENTRY_TRACES_SAMPLE_RATE" .env.example && grep -c "SENTRY_ENVIRONMENT" .env.example && grep -c "LOG_FORMAT" .env.example`
- **Expected:** Each grep returns 1 or more (exit code 0 for all)
- **Failure means:** Task 2 of Plan 05-02 not completed

### S9: Existing pytest suite passes with zero failures

- **What:** No regressions introduced by phase 5 changes
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest --tb=short -q`
- **Expected:** All tests pass, 0 failures, 0 errors (warnings permitted)
- **Failure means:** A phase 5 change broke an existing behavior — identify and fix before proceeding

**Sanity gate:** ALL nine sanity checks must pass. Any failure blocks progression to proxy evaluation.

---

## Level 2: Proxy Metrics

**Purpose:** Behavioral verification of the three OBS requirements. These are the closest available automated approximations to the phase success criteria. They are "proxy" rather than "full" because they test against a locally running server with a controlled test payload, not under production load or with a real Sentry project.

**IMPORTANT:** All proxy metrics are automated integration tests, not unit tests. They require starting a local server instance. Commands below assume the backend runs on `localhost:20000`.

### P1: JSON log output contains all required fields

- **What:** Every application log line during an API request is valid JSON with the five required fields: timestamp, level, logger, message, request_id
- **How:** Make a single API call to a logged endpoint. Capture log output. Parse each JSON line and verify field presence.
- **Command:**
  ```bash
  # Start server in background, capture logs
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend
  LOG_FORMAT=json uv run python run.py > /tmp/agented_logs.jsonl 2>&1 &
  SERVER_PID=$!
  sleep 2
  curl -s http://localhost:20000/health/readiness > /dev/null
  sleep 0.5
  kill $SERVER_PID

  # Verify every non-empty line is valid JSON with required fields
  python3 -c "
  import json, sys
  required = {'asctime', 'levelname', 'name', 'message', 'request_id'}
  lines = [l.strip() for l in open('/tmp/agented_logs.jsonl') if l.strip()]
  json_lines = []
  for line in lines:
      try:
          obj = json.loads(line)
          json_lines.append(obj)
      except:
          pass
  if not json_lines:
      print('FAIL: no JSON log lines found')
      sys.exit(1)
  missing = [l for l in json_lines if not required.issubset(l.keys())]
  if missing:
      print(f'FAIL: {len(missing)} lines missing required fields. Sample: {missing[0]}')
      sys.exit(1)
  print(f'PASS: {len(json_lines)} JSON log lines, all have required fields')
  "
  ```
- **Target:** 100% of JSON log lines contain all five required fields
- **Evidence:** OBS-01 requirement and 05-PLAN-01 success criteria — these are the literal fields specified in `configure_logging()` format string
- **Correlation with full metric:** HIGH — directly measures the same property as OBS-01
- **Blind spots:** Does not check log output under concurrent requests (greenlet context leakage). Does not validate log output for non-JSON format (LOG_FORMAT=text). Both covered by P2 and deferred.
- **Validated:** No — awaiting post-execution confirmation

### P2: Request ID is consistent across all log lines for a single API request

- **What:** All log lines produced during a single HTTP request share the same request_id UUID value — no cross-request contamination, no null values during active requests
- **How:** Make an API call that touches multiple log call sites (e.g., a route that calls service methods). Collect the X-Request-ID header from the response. Grep log output for lines containing that exact UUID. Verify count >= 2 (more than one log line produced for that request) and no other request_id values on those lines.
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend
  LOG_FORMAT=json uv run python run.py > /tmp/req_logs.jsonl 2>&1 &
  SERVER_PID=$!
  sleep 2

  # Make a call and capture the X-Request-ID header
  REQ_ID=$(curl -s -D /tmp/headers.txt http://localhost:20000/admin/triggers && grep -i x-request-id /tmp/headers.txt | awk '{print $2}' | tr -d '\r')
  sleep 0.2
  kill $SERVER_PID

  # Verify: all lines containing REQ_ID share the same value
  python3 -c "
  import json, sys
  req_id = open('/tmp/headers.txt').read()
  import re
  m = re.search(r'[Xx]-[Rr]equest-[Ii][Dd]: ([0-9a-f-]+)', req_id)
  if not m:
      print('FAIL: X-Request-ID header not found in response')
      sys.exit(1)
  rid = m.group(1).strip()
  print(f'Checking for request_id: {rid}')
  lines = [json.loads(l) for l in open('/tmp/req_logs.jsonl') if l.strip() and l.startswith('{')]
  matched = [l for l in lines if l.get('request_id') == rid]
  if len(matched) < 2:
      print(f'FAIL: expected >= 2 log lines with request_id={rid}, found {len(matched)}')
      sys.exit(1)
  wrong = [l for l in matched if l.get('request_id') != rid]
  if wrong:
      print(f'FAIL: {len(wrong)} lines have wrong request_id value')
      sys.exit(1)
  print(f'PASS: {len(matched)} log lines all share request_id={rid}')
  "
  ```
- **Target:** >= 2 log lines for the request, all sharing the same UUID; X-Request-ID header present in response
- **Evidence:** 05-RESEARCH.md Experiment Design #1 (Request ID correlation test). The ContextVar propagation pattern is documented to provide this guarantee under gevent >= 20.5.
- **Correlation with full metric:** HIGH — directly measures OBS-01 success criterion #1 and #2
- **Blind spots:** Tests only one request at a time. Does not verify isolation between two concurrent requests (covered by DEFER-05-01).
- **Validated:** No — awaiting post-execution confirmation

### P3: Two consecutive requests produce different request IDs (no leakage)

- **What:** Greenlet context is correctly cleared between requests; two sequential API calls do not share a request_id
- **How:** Make two sequential API calls. Collect both X-Request-ID headers. Assert they are different UUIDs.
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend
  LOG_FORMAT=json uv run python run.py > /dev/null 2>&1 &
  SERVER_PID=$!
  sleep 2

  RID1=$(curl -s -D - http://localhost:20000/health/readiness 2>/dev/null | grep -i x-request-id | awk '{print $2}' | tr -d '\r\n')
  RID2=$(curl -s -D - http://localhost:20000/health/readiness 2>/dev/null | grep -i x-request-id | awk '{print $2}' | tr -d '\r\n')
  kill $SERVER_PID

  python3 -c "
  r1, r2 = '$RID1', '$RID2'
  if not r1 or not r2:
      print(f'FAIL: Missing headers. r1={r1!r}, r2={r2!r}')
      exit(1)
  if r1 == r2:
      print(f'FAIL: Both requests share the same request_id: {r1}')
      exit(1)
  print(f'PASS: r1={r1}, r2={r2} — different UUIDs')
  "
  ```
- **Target:** Two requests produce two distinct UUIDs
- **Evidence:** 05-RESEARCH.md Pitfall 1 (gevent greenlet context leakage). The `teardown_request` handler calling `request_id_var.set(None)` is the mitigation. This test verifies the mitigation is effective.
- **Correlation with full metric:** HIGH — tests the exact failure mode described in RESEARCH.md Pitfall 1
- **Blind spots:** Sequential only; does not test concurrent requests. Covered by DEFER-05-01.
- **Validated:** No — awaiting post-execution confirmation

### P4: LOG_FORMAT=text produces human-readable plaintext output

- **What:** The `log_format` parameter on `configure_logging()` correctly switches to plaintext format
- **How:** Start server with LOG_FORMAT=text. Make one API call. Verify that log lines are NOT valid JSON (i.e., the text formatter is in use, not the JSON formatter).
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend
  LOG_FORMAT=text uv run python run.py > /tmp/text_logs.txt 2>&1 &
  SERVER_PID=$!
  sleep 2
  curl -s http://localhost:20000/health/readiness > /dev/null
  sleep 0.2
  kill $SERVER_PID

  python3 -c "
  import json, sys
  lines = [l.strip() for l in open('/tmp/text_logs.txt') if l.strip()]
  json_count = sum(1 for l in lines if l.startswith('{'))
  if json_count > 0:
      print(f'FAIL: {json_count} JSON lines found with LOG_FORMAT=text — formatter not switching correctly')
      sys.exit(1)
  if not lines:
      print('FAIL: No log lines produced')
      sys.exit(1)
  print(f'PASS: {len(lines)} plaintext log lines, 0 JSON lines with LOG_FORMAT=text')
  "
  ```
- **Target:** 0 JSON-formatted lines when LOG_FORMAT=text; at least 1 plaintext line produced
- **Evidence:** 05-PLAN-01 must_haves: "Setting LOG_FORMAT=text reverts to human-readable plaintext logging format"
- **Correlation with full metric:** HIGH — directly tests the must_have truth
- **Blind spots:** Does not verify the plaintext format matches the original format string. Minor risk.
- **Validated:** No — awaiting post-execution confirmation

### P5: DB-backed dedup: second delivery within TTL is rejected

- **What:** Sending the same webhook payload twice within 10 seconds results in only one execution — the second delivery is deduplicated via INSERT OR IGNORE
- **How:** Unit test using isolated_db fixture. Call `check_and_insert_dedup_key()` twice with the same arguments within the TTL window. Assert first call returns True, second returns False.
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "
  import tempfile, os, time
  # Use a temp DB so this is self-contained
  with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
      tmp_db = f.name

  import app.database as db_module
  original_path = db_module.DB_PATH
  db_module.DB_PATH = tmp_db

  import app.db.connection as conn_module
  original_conn_path = getattr(conn_module, 'DB_PATH', None)
  conn_module.DB_PATH = tmp_db

  from app.database import init_db
  init_db()

  from app.db.webhook_dedup import check_and_insert_dedup_key

  result1 = check_and_insert_dedup_key('trigger-test', 'hash-abc', ttl_seconds=10)
  result2 = check_and_insert_dedup_key('trigger-test', 'hash-abc', ttl_seconds=10)
  result3 = check_and_insert_dedup_key('trigger-test', 'hash-xyz', ttl_seconds=10)  # different payload

  os.unlink(tmp_db)

  assert result1 == True, f'FAIL: First insert should return True, got {result1}'
  assert result2 == False, f'FAIL: Second insert (duplicate) should return False, got {result2}'
  assert result3 == True, f'FAIL: Different payload should return True, got {result3}'
  print('PASS: Dedup INSERT OR IGNORE behavior correct')
  "
  ```
- **Target:** result1=True, result2=False, result3=True
- **Evidence:** 05-RESEARCH.md Pattern 4 and RESEARCH.md Experiment Design #3. The INSERT OR IGNORE atomic behavior is documented in SQLite docs.
- **Correlation with full metric:** HIGH — tests the core dedup mechanism directly
- **Blind spots:** Does not test the full webhook dispatch path (ExecutionService integration). That is covered by P6.
- **Validated:** No — awaiting post-execution confirmation

### P6: DB-backed dedup survives server restart (three-delivery test)

- **What:** Send payload once (executes), send again within TTL (deduplicated), restart server, send again within TTL (still deduplicated because key is in DB). This is the OBS-03 success criterion.
- **How:** This test requires a running server, a real trigger configured, and the ability to send a webhook that maps to a trigger. Since bots require CLI tools to execute, we test at the service layer rather than end-to-end. Use `check_and_insert_dedup_key()` directly across a "restart" simulation: write to DB, reinitialize the module, verify the key is still found.
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "
  import tempfile, os, time

  with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
      tmp_db = f.name

  import app.database as db_module
  db_module.DB_PATH = tmp_db
  import app.db.connection as conn_module
  conn_module.DB_PATH = tmp_db

  from app.database import init_db
  init_db()

  from app.db.webhook_dedup import check_and_insert_dedup_key

  # Delivery 1: should succeed (new key)
  r1 = check_and_insert_dedup_key('trigger-restart-test', 'payload-hash-restart', ttl_seconds=30)

  # Delivery 2: should be deduplicated (same key within TTL)
  r2 = check_and_insert_dedup_key('trigger-restart-test', 'payload-hash-restart', ttl_seconds=30)

  # Simulate restart: reimport the module (the key is in the DB — this is what survives)
  import importlib
  import app.db.webhook_dedup as dedup_mod
  importlib.reload(dedup_mod)

  # Delivery 3 after 'restart': should still be deduplicated
  r3 = dedup_mod.check_and_insert_dedup_key('trigger-restart-test', 'payload-hash-restart', ttl_seconds=30)

  os.unlink(tmp_db)

  assert r1 == True, f'Delivery 1 should succeed, got {r1}'
  assert r2 == False, f'Delivery 2 should be deduped, got {r2}'
  assert r3 == False, f'Delivery 3 (post-restart) should still be deduped, got {r3}'
  print('PASS: Dedup persists across module reload (simulating restart)')
  "
  ```
- **Target:** r1=True, r2=False, r3=False
- **Evidence:** OBS-03 success criterion — the three-delivery restart test is the literal requirement
- **Correlation with full metric:** MEDIUM — tests DB persistence correctly but simulates restart via module reload rather than full process restart. Full process restart test is DEFER-05-03.
- **Blind spots:** Module reload is not the same as process restart. The DB file path must be the same across restarts. The real test requires a full server restart.
- **Validated:** No — awaiting post-execution confirmation

### P7: TTL expiry allows re-delivery after the window

- **What:** Sending the same payload after the TTL has expired results in a new insertion (treat as new, not duplicate)
- **How:** Insert a key, manually set its created_at to a time past the TTL, then call check_and_insert_dedup_key again and verify it returns True.
- **Command:**
  ```bash
  cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "
  import tempfile, os, time

  with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
      tmp_db = f.name

  import app.database as db_module
  db_module.DB_PATH = tmp_db
  import app.db.connection as conn_module
  conn_module.DB_PATH = tmp_db

  from app.database import init_db
  init_db()

  from app.db.webhook_dedup import check_and_insert_dedup_key
  from app.db.connection import get_connection

  # Insert a key with an artificially old created_at (30 seconds ago, past the 10s TTL)
  old_time = time.time() - 30
  with get_connection() as conn:
      conn.execute(
          'INSERT OR IGNORE INTO webhook_dedup_keys (trigger_id, payload_hash, created_at) VALUES (?, ?, ?)',
          ('trigger-ttl-test', 'payload-ttl-hash', old_time)
      )
      conn.commit()

  # Now call check_and_insert: the expired entry should be deleted and new one inserted
  result = check_and_insert_dedup_key('trigger-ttl-test', 'payload-ttl-hash', ttl_seconds=10)

  os.unlink(tmp_db)

  assert result == True, f'FAIL: Expired key should allow re-delivery, got {result}'
  print('PASS: TTL expiry correctly allows re-delivery')
  "
  ```
- **Target:** result=True (expired key treated as new)
- **Evidence:** 05-PLAN-03 success criteria #3; 05-RESEARCH.md Experiment Design #4 (dedup TTL test)
- **Correlation with full metric:** HIGH — tests the exact TTL cleanup logic in check_and_insert_dedup_key()
- **Blind spots:** Does not test the APScheduler cleanup job, only the per-key TTL check on insert. APScheduler cleanup is DEFER-05-04.
- **Validated:** No — awaiting post-execution confirmation

---

## Level 3: Deferred Validations

**Purpose:** Full validations that require external infrastructure (Sentry DSN), full process restart (not module reload), or sustained load not appropriate for CI.

### D1: Sentry event delivery within 60 seconds — DEFER-05-01

- **What:** Deliberately triggering an unhandled exception in the running server causes an event to appear in the Sentry dashboard within 60 seconds
- **How:** Configure a Sentry test project. Set SENTRY_DSN in .env. Start the server. Hit a route that raises an unhandled exception (or use the Sentry debug endpoint `sentry_sdk.capture_message("test")`). Check the Sentry dashboard for the event.
- **Why deferred:** Requires a real Sentry account, real DSN, and network access to sentry.io. Cannot be automated without CI infrastructure that stores Sentry credentials securely.
- **Validates at:** Manual human verification during or after plan 05-02 execution
- **Depends on:** Sentry project created, SENTRY_DSN set, network access to sentry.io
- **Target:** Event appears in Sentry dashboard within 60 seconds of exception trigger
- **Risk if unmet:** OBS-02 is not met. Sentry SDK may be misconfigured — check DSN format, init placement, and FlaskIntegration auto-detection.
- **Fallback:** If Sentry delivery fails, investigate: (1) is DSN correctly formatted? (2) is `sentry_sdk.init()` called before `create_app()`? (3) does the route raise an unhandled exception (not a Flask 500 handler catch)?

### D2: SSE endpoints produce no Sentry transactions — DEFER-05-02

- **What:** Opening an SSE stream endpoint (`/admin/executions/{id}/stream`) does not create a performance transaction in the Sentry performance dashboard
- **How:** With SENTRY_DSN configured, open an SSE endpoint, let it stream for 10 seconds, close it. Check Sentry performance dashboard for transactions matching the SSE URL pattern.
- **Why deferred:** Requires a running Sentry project and an active execution to stream. Cannot be automated without a real Sentry environment.
- **Validates at:** Manual human verification during or after plan 05-02 execution (same session as DEFER-05-01)
- **Depends on:** SENTRY_DSN configured, active execution available to stream
- **Target:** Zero transactions with "/stream" or "/sessions/" in the transaction name
- **Risk if unmet:** Sentry quota drain and distorted p99 latency metrics. The `before_send_transaction` filter may not be triggering.
- **Fallback:** Add URL pattern logging to `_filter_sse_transactions()` to confirm the filter is being called. Check that FlaskIntegration creates transactions (traces_sample_rate > 0).

### D3: Dedup survives real process restart (full server restart test) — DEFER-05-03

- **What:** The three-delivery OBS-03 scenario tested with full process kill and restart, not module reload
- **How:** Start server. POST a test webhook payload. Verify it processed. POST same payload again — verify deduplicated. Kill the server process (SIGTERM). Restart the server. POST same payload a third time — verify it is still deduplicated.
- **Why deferred:** Requires a real trigger configured, a webhook route that maps to it, and process-level restart machinery. The proxy test (P6) uses module reload as a simulation. This is the real test.
- **Validates at:** Manual or scripted integration test after full phase 05 execution
- **Depends on:** All three plans (05-01, 05-02, 05-03) complete; server startable via `just dev-backend`; a webhook trigger configured that uses the dedup path
- **Target:** Third delivery (post-restart) is deduplicated — zero additional executions created
- **Risk if unmet:** OBS-03 literal requirement is not met. DB_PATH environment variable may differ between runs. Check that the dedup DB is the same file across restarts.
- **Fallback:** Verify the DB_PATH used by the running server by inspecting the SQLite file used. Check webhook_dedup_keys table contents before and after restart.

### D4: Dedup table size stable under sustained webhook volume — DEFER-05-04

- **What:** After sustained webhook traffic for 1 hour, the webhook_dedup_keys table does not grow unboundedly — the APScheduler cleanup job keeps it bounded
- **How:** Run a load test that POSTs 1 webhook per second for 1 hour (3,600 total). Measure table row count at t=0, t=30min, t=60min.
- **Why deferred:** 1-hour load test is not appropriate for per-phase evaluation. This is an operational health check.
- **Validates at:** Operational review after production deployment
- **Depends on:** Production or staging environment; load testing tool (e.g., k6, locust, or shell loop)
- **Target:** Row count at t=60min < 2 * (row count at t=5min) — table is not growing unboundedly. Given 10-second TTL and 60-second cleanup, expected steady-state row count is approximately (webhook rate * TTL) = ~10 rows.
- **Risk if unmet:** Table grows without bound and impacts SQLite write performance. Fix by reducing cleanup interval or verifying cleanup job is registered in APScheduler.
- **Fallback:** Manually run `SELECT COUNT(*) FROM webhook_dedup_keys` during load test. If growing, verify APScheduler is initializing the cleanup job (check `if SchedulerService._scheduler:` guard in `__init__.py`).

---

## Ablation Plan

No ablation plan — this phase implements three independent infrastructure components (logging, error tracking, deduplication), each satisfying a single discrete requirement. There are no algorithmic sub-components to isolate or compare. Each plan (05-01, 05-02, 05-03) is independently verifiable and does not have internal variants.

The only meaningful "ablation" is the already-specified LOG_FORMAT=text fallback test (P4), which verifies the configurability of the JSON formatter rather than comparing competing approaches.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views. All files modified by plans 05-01, 05-02, and 05-03 are backend Python files (logging_config.py, middleware.py, run.py, gunicorn.conf.py, pyproject.toml, db/webhook_dedup.py, db/schema.py, db/migrations.py, execution_service.py).

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| request_id presence | Percentage of log lines with request_id field | 0% (no request IDs currently) | CONCERNS.md Section 4.2 |
| Sentry integration | Error tracking in place | None (no Sentry currently) | CONCERNS.md Section 4.2 |
| Dedup survival across restart | Does dedup survive server restart? | FAILS (in-memory dict lost) | CONCERNS.md Section 5.1 |
| Existing test suite | pytest pass rate | All passing (current state) | Regression baseline |

All baselines derived from codebase analysis (CONCERNS.md). BENCHMARKS.md contains no pre-existing numeric baselines for this phase — it was initialized as an empty template.

---

## Evaluation Scripts

**Location of evaluation code:**

Proxy metric commands are self-contained one-liners and shell scripts defined inline in the P1–P7 sections above. No separate evaluation script files are required for this phase.

**How to run all Level 1 sanity checks in sequence:**

```bash
BASE=/Users/edward.seo/dev/private/project/harness/Agented/backend

# S1
cd $BASE && uv run python -c "from pythonjsonlogger.json import JsonFormatter; print('S1 PASS')"

# S2
cd $BASE && uv run python -c "from app.logging_config import configure_logging, request_id_var, RequestIdFilter; configure_logging(); print('S2 PASS')"

# S3
cd $BASE && uv run python -c "from app.middleware import init_request_middleware; print('S3 PASS')"

# S4
cd $BASE && uv run python -c "import sentry_sdk; from sentry_sdk.integrations.flask import FlaskIntegration; print('S4 PASS')"

# S5
cd $BASE && SENTRY_DSN="" uv run python -c "from run import application; print('S5 PASS')"

# S6
cd $BASE && uv run python -c "
from app.database import init_db; from app.db.connection import get_connection; init_db()
with get_connection() as conn:
    t = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
    assert 'webhook_dedup_keys' in t, f'FAIL: {t}'
    print('S6 PASS')
"

# S7
cd $BASE && uv run python -c "from app.db.webhook_dedup import check_and_insert_dedup_key, cleanup_expired_keys; print('S7 PASS')"

# S8
cd $BASE && grep -q "SENTRY_DSN" .env.example && grep -q "SENTRY_TRACES_SAMPLE_RATE" .env.example && grep -q "LOG_FORMAT" .env.example && echo "S8 PASS"

# S9
cd $BASE && uv run pytest --tb=short -q && echo "S9 PASS"
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: python-json-logger import | [PASS/FAIL] | | |
| S2: logging_config exports | [PASS/FAIL] | | |
| S3: middleware import | [PASS/FAIL] | | |
| S4: sentry-sdk import | [PASS/FAIL] | | |
| S5: server starts without DSN | [PASS/FAIL] | | |
| S6: webhook_dedup_keys table | [PASS/FAIL] | | |
| S7: webhook_dedup DB module | [PASS/FAIL] | | |
| S8: .env.example docs | [PASS/FAIL] | | |
| S9: pytest regression | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: JSON log fields | 100% lines with 5 required fields | | [MET/MISSED] | |
| P2: Request ID consistency | >= 2 lines sharing same UUID | | [MET/MISSED] | |
| P3: No request ID leakage | Two requests produce different UUIDs | | [MET/MISSED] | |
| P4: LOG_FORMAT=text fallback | 0 JSON lines in text mode | | [MET/MISSED] | |
| P5: INSERT OR IGNORE dedup | r1=True, r2=False, r3=True | | [MET/MISSED] | |
| P6: Dedup survives module reload | r1=True, r2=False, r3=False | | [MET/MISSED] | |
| P7: TTL expiry allows re-delivery | result=True after TTL | | [MET/MISSED] | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-05-01 | Sentry event delivery within 60s | PENDING | Manual verification after 05-02 execution |
| DEFER-05-02 | SSE endpoints absent from Sentry transactions | PENDING | Manual verification after 05-02 execution |
| DEFER-05-03 | Dedup survives real process restart | PENDING | Integration test after full phase 05 execution |
| DEFER-05-04 | Dedup table size stable under load | PENDING | Operational review post-deployment |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 9 checks covering all new modules, the DB schema, env var documentation, and regression. Every check has an exact runnable command.
- Proxy metrics: Well-evidenced — P1-P4 directly test OBS-01 success criteria using the same observable outputs specified in the requirements. P5-P7 directly test OBS-03 behavioral properties using the exact function being implemented. All proxy targets derive from explicit requirement statements, not invented thresholds.
- Deferred coverage: Comprehensive for what can be deferred — DEFER-05-01 and DEFER-05-02 cover OBS-02 (Sentry) which is entirely deferred due to requiring external infrastructure. DEFER-05-03 upgrades P6 from simulated to real restart. DEFER-05-04 is an operational health check, not a correctness check.

**What this evaluation CAN tell us:**
- Whether all three new modules import correctly and the DB schema is correct (S1-S9)
- Whether JSON logging produces the exact fields required by OBS-01 (P1)
- Whether request IDs are consistent within a request and isolated between requests (P2, P3)
- Whether the LOG_FORMAT fallback works (P4)
- Whether the SQLite INSERT OR IGNORE dedup logic is correct at the function level (P5, P7)
- Whether dedup keys persist in the DB across a module reload (P6)
- Whether the existing test suite is not broken (S9)

**What this evaluation CANNOT tell us:**
- Whether Sentry actually delivers events to the dashboard (DEFER-05-01 — requires real DSN and network)
- Whether SSE endpoints are correctly filtered from Sentry transactions (DEFER-05-02 — same constraint)
- Whether dedup truly survives a full `kill -SIGTERM` + process restart (DEFER-05-03 — P6 simulates this with module reload)
- Whether the APScheduler cleanup job prevents table growth under real webhook load (DEFER-05-04 — requires sustained load)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-02-28*
