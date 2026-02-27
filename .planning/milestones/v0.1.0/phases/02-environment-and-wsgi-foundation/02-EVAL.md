# Evaluation Plan: Phase 2 — Environment and WSGI Foundation

**Designed:** 2026-02-28
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Gunicorn + gevent deployment, python-dotenv configuration loading, SECRET_KEY persistence, process supervisor configuration
**Reference sources:** Flask docs (Gunicorn deployment), Gunicorn ggevent.py source, python-dotenv README, APScheduler User Guide, codebase CONCERNS.md Sections 1.7, 4.4, 6.2, 7.1, 7.2

---

## Evaluation Overview

This phase is operational infrastructure — not algorithm or feature work. There are no paper metrics or benchmark datasets. The "evaluation" is: does the server start correctly under Gunicorn with gevent workers, does configuration load from `.env`, does `SECRET_KEY` survive restarts, and do process supervisor configs restart the process after a crash?

All of these questions are verifiable in-phase through direct observation. The phase RESEARCH.md explicitly identifies this as a Level 1 (Sanity) verification domain: every success criterion maps to a concrete, automated check with a binary pass/fail. There are no meaningful proxy metrics for infrastructure work of this kind — "SSE event delivery latency" and "restart time" are the real metrics, and both are directly measurable.

The primary risks this evaluation guards against are: (1) gevent monkey patching breaking APScheduler or subprocess execution, (2) `workers > 1` creeping in and silently fragmenting in-memory SSE state, and (3) `preload_app = True` causing unpatched module references. These are all detectable via sanity checks and a targeted subprocess/SSE smoke test.

This phase has no frontend modifications. WebMCP tool definitions are not applicable.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Gunicorn process visible in `ps aux` | ROADMAP.md Success Criterion 1 | Directly verifies DEP-01 (server runs on Gunicorn) |
| SECRET_KEY identical across restarts | ROADMAP.md Success Criterion 2 | Directly verifies ENV-01 (stable SECRET_KEY) |
| `.env.example` covers all env vars | ROADMAP.md Success Criterion 3 | Directly verifies ENV-02 (all env vars documented) |
| `gunicorn.conf.py` enforces workers=1 + gevent | ROADMAP.md Success Criterion 4 | Directly verifies DEP-02 (configuration file) |
| Process supervisor restarts within 5s | ROADMAP.md Success Criterion 5 | Directly verifies DEP-04 (restart-on-crash) |
| `just deploy` uses Gunicorn | ROADMAP.md Success Criterion 1 | Directly verifies DEP-03 (deploy target updated) |
| Backend tests pass with no regressions | Pre-existing baseline 911/911 | Confirms gevent monkey patching does not break test suite |
| APScheduler initializes and fires | RESEARCH.md Pitfall 1 | APScheduler missing from pyproject.toml; silently disables itself if absent |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 12 | Direct verification of every success criterion; all are immediately executable |
| Proxy (L2) | 0 | None applicable — all real metrics are directly measurable in this domain |
| Deferred (L3) | 2 | Load testing with concurrent SSE connections; multi-worker deployment |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding to Phase 3.

---

### S1: Dependencies installed and importable

- **What:** All four new dependencies (gevent, python-dotenv, APScheduler, pytz) are present in `pyproject.toml` and importable after `uv sync`
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv sync && uv run python -c "import gevent; import dotenv; import apscheduler; import pytz; print('All imports OK')"`
- **Expected:** Exits 0, prints "All imports OK"
- **Failure means:** Missing dependency in pyproject.toml or `uv sync` failure. Check that all four lines were added to the `dependencies` list.

---

### S2: Gunicorn configuration file is valid

- **What:** `backend/gunicorn.conf.py` exists and passes Gunicorn's built-in config validation
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run gunicorn --check-config -c gunicorn.conf.py`
- **Expected:** Exits 0 with no error output
- **Failure means:** Syntax error in gunicorn.conf.py, missing wsgi_app reference, or gevent worker class not found (gevent not installed)

---

### S3: gunicorn.conf.py enforces workers=1 and worker_class=gevent

- **What:** Configuration values are correct and the single-worker constraint rationale is documented
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "exec(open('gunicorn.conf.py').read()); assert workers == 1, f'workers={workers}, expected 1'; assert worker_class == 'gevent', f'worker_class={worker_class}'; print('Config values OK')"`
- **Expected:** Prints "Config values OK"
- **Failure means:** Wrong worker count (breaks in-memory SSE state) or wrong worker class (breaks SSE concurrency). Neither is acceptable.

---

### S4: preload_app is NOT set in gunicorn.conf.py

- **What:** `preload_app = True` is absent from gunicorn.conf.py (this setting breaks gevent monkey patching order; see RESEARCH.md Pitfall 3)
- **Command:** `grep -n "^preload_app" /Users/edward.seo/dev/private/project/harness/Agented/backend/gunicorn.conf.py && echo "FAIL: preload_app is set" || echo "OK: preload_app not set"`
- **Expected:** Prints "OK: preload_app not set"
- **Failure means:** Monkey patching will be applied after the app loads in the master process, causing unpatched module references in workers. Must remove `preload_app = True`.

---

### S5: load_dotenv() called before create_app() in run.py

- **What:** `run.py` calls `load_dotenv()` at the top, before importing or calling `create_app()`
- **Command:** `grep -n "load_dotenv\|create_app\|from app" /Users/edward.seo/dev/private/project/harness/Agented/backend/run.py`
- **Expected:** `load_dotenv` line number appears BEFORE the `from app import create_app` and `create_app()` line numbers
- **Failure means:** `.env` variables won't be available when the app factory runs. `SECRET_KEY` and `CORS_ALLOWED_ORIGINS` won't load from `.env`.

---

### S6: SECRET_KEY is stable across two consecutive create_app() calls

- **What:** The `_get_secret_key()` function persists the key to `.secret_key` on first run and reads it on subsequent runs, producing identical keys
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run python -c "from app import create_app; k1 = create_app().config['SECRET_KEY']; k2 = create_app().config['SECRET_KEY']; assert k1 == k2, f'Keys differ: {k1[:8]}... != {k2[:8]}...'; print(f'SECRET_KEY stable: {len(k1)} chars')"`
- **Expected:** Prints "SECRET_KEY stable: 64 chars" (64 hex chars = 32 bytes)
- **Failure means:** SECRET_KEY is still auto-regenerated on each call. Check that `_get_secret_key()` was implemented in `app/__init__.py` and that the old `secrets.token_hex(32)` fallback was replaced.

---

### S7: .env and .secret_key are gitignored

- **What:** `.gitignore` contains entries for both `.env` and `backend/.secret_key` (or `.secret_key`)
- **Command:** `grep -E "^\.env$|^backend/\.secret_key$|^\.secret_key$" /Users/edward.seo/dev/private/project/harness/Agented/.gitignore`
- **Expected:** At least two matching lines (one for `.env`, one for `.secret_key` or `backend/.secret_key`)
- **Failure means:** Secrets could be accidentally committed. Blocks all further work until fixed.

---

### S8: .env.example exists and covers all known environment variables

- **What:** `backend/.env.example` documents all environment variables used in the codebase, organized with section headers
- **Command:** `grep -c "SECRET_KEY\|GUNICORN_BIND\|CORS_ALLOWED_ORIGINS\|AGENTED_DB_PATH\|GITHUB_WEBHOOK_SECRET\|ANTHROPIC_API_KEY\|LOG_LEVEL\|SSE_REPLAY_LIMIT\|STALE_CONVERSATION\|STALE_EXECUTION" /Users/edward.seo/dev/private/project/harness/Agented/backend/.env.example`
- **Expected:** Returns 10 (all 10 listed variables are present)
- **Failure means:** ENV-02 not met. New developers copying `.env.example` to `.env` won't know about critical variables.

---

### S9: just deploy uses Gunicorn (not python run.py)

- **What:** The `deploy` recipe in `justfile` references `gunicorn` and NOT `python run.py`
- **Commands:**
  - `grep -c "gunicorn" /Users/edward.seo/dev/private/project/harness/Agented/justfile`
  - `awk '/^deploy:/,/^[a-z]/' /Users/edward.seo/dev/private/project/harness/Agented/justfile | grep "python run.py" && echo "FAIL: deploy still uses python run.py" || echo "OK: deploy does not use python run.py"`
- **Expected:** First command returns >= 1; second command prints "OK: deploy does not use python run.py"
- **Failure means:** DEP-03 not met. Deploy still uses Flask dev server.

---

### S10: dev-backend recipe preserved (still uses python run.py --debug)

- **What:** The `dev-backend` recipe still uses `python run.py --debug` so developer workflow is not broken
- **Command:** `grep -A 3 "^dev-backend" /Users/edward.seo/dev/private/project/harness/Agented/justfile`
- **Expected:** Output includes `python run.py --debug` (or `run.py -d`)
- **Failure means:** Developer hot-reload workflow is broken. Dev-backend is the correct path for local development; Gunicorn is for deployment only.

---

### S11: Backend test suite passes with no regressions

- **What:** All existing backend tests pass after the changes in this phase. Baseline: 911/911 tests passing (from STATE.md)
- **Command:** `cd /Users/edward.seo/dev/private/project/harness/Agented/backend && uv run pytest --tb=short -q`
- **Expected:** All tests pass, exit code 0. Zero new failures or errors.
- **Failure means:** The phase introduced a regression. Likely causes: (a) `from pathlib import Path` import missing in `app/__init__.py`, (b) `_get_secret_key()` function definition breaks existing test fixtures, (c) `load_dotenv()` in `run.py` interferes with test environment setup. Check `conftest.py`'s `isolated_db` fixture.

---

### S12: Process supervisor config files exist with correct restart semantics

- **What:** `deploy/agented.service` and `deploy/com.agented.backend.plist` exist with the restart-on-crash directives required to meet the 5-second restart success criterion
- **Commands:**
  - `grep "Restart=on-failure" /Users/edward.seo/dev/private/project/harness/Agented/deploy/agented.service && grep "RestartSec=3" /Users/edward.seo/dev/private/project/harness/Agented/deploy/agented.service && echo "systemd OK"`
  - `grep -c "KeepAlive" /Users/edward.seo/dev/private/project/harness/Agented/deploy/com.agented.backend.plist && echo "launchd OK"`
- **Expected:** Both print their respective "OK" suffix. `RestartSec=3` satisfies the 5-second restart requirement with margin.
- **Failure means:** DEP-04 not met. Process supervisor won't automatically restart on crash.

---

**Sanity gate:** ALL 12 sanity checks must pass. Any failure blocks progression to Phase 3.

---

## Level 2: Proxy Metrics

### No Proxy Metrics

**Rationale:** This phase implements infrastructure plumbing — process management, configuration loading, and file-system persistence. Every success criterion from the ROADMAP is directly and immediately verifiable via exact commands with binary outcomes. There is no indirect measure that would be more informative than the direct measures above.

Specifically:
- "Gunicorn is running" is verified by `ps aux | grep gunicorn` — there is no useful proxy for this
- "SECRET_KEY is stable" is verified by comparing two consecutive keys — no proxy needed
- "Restart happens within 5s" is verified by `kill -9` + `ps aux` timing — directly measurable
- "APScheduler fires" is verified by checking startup logs — directly observable

Constructing proxy metrics for infrastructure work often produces false confidence. A proxy like "gunicorn.conf.py has the right values" is weaker than actually starting Gunicorn and checking `ps aux`. The sanity checks above ARE the real metrics.

**Recommendation:** Rely entirely on sanity checks (Level 1). All 12 checks together constitute a complete verification of all 7 requirements (ENV-01 through DEP-04).

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring conditions not available during this phase.

---

### D1: Concurrent SSE load test — DEFER-02-01

- **What:** Verify that gevent's cooperative scheduling allows one worker to serve 10+ simultaneous SSE subscribers without connection drops or event delivery failures
- **How:** Open 10 concurrent SSE connections to `/admin/executions/{id}/stream`, trigger a single execution, count events received on each connection vs. events emitted
- **Why deferred:** Requires a running Gunicorn process, active execution, and a load testing client (wrk, locust, or a custom SSE client). Not worth setting up in this phase; concurrency correctness is guaranteed by gevent's design for `workers=1`
- **Validates at:** phase-05-observability-and-process-reliability (Phase 5 adds structured logging that makes SSE delivery observable via logs; load testing is a natural fit for the observability phase)
- **Depends on:** Phase 2 complete (Gunicorn running), Phase 3 complete (SSE auth in place, since unauthenticated SSE will be blocked)
- **Target:** 10/10 SSE connections receive all events; no `WORKER TIMEOUT` in Gunicorn logs; no connection drops within 5 minutes
- **Risk if unmet:** If gevent's cooperative scheduler is blocked by a C extension or non-monkey-patched I/O call, SSE delivery will silently fail for all subscribers. The single-worker design means one blocking greenlet freezes all connections simultaneously. Mitigation: RESEARCH.md documents that all I/O in the codebase uses monkey-patchable Python stdlib modules.
- **Fallback:** Switch to `gthread` worker class (real OS threads, no monkey patching) at the cost of limiting SSE concurrency to `worker_threads` connections

---

### D2: Multi-process scaling readiness — DEFER-02-02

- **What:** Document and test that the `workers=1` constraint is enforced with a startup assertion, preventing accidental misconfiguration when deploying to production
- **How:** Attempt to set `workers=2` in a test `gunicorn.conf.py` override and verify the application either rejects it or documents the failure mode clearly
- **Why deferred:** This is a safety net for future operators, not a correctness check for Phase 2. The constraint is documented in gunicorn.conf.py; enforcement via assertion is a Phase 6 concern
- **Validates at:** phase-06-code-quality-and-maintainability (QUAL phase is where startup assertions and guard rails belong)
- **Depends on:** Phase 2 complete (gunicorn.conf.py exists), Phase 5 complete (structured logging to make the assertion visible in production logs)
- **Target:** A startup assertion `assert workers == 1, "workers > 1 is unsafe until Redis pub/sub replaces in-memory SSE state"` exists in gunicorn.conf.py or app factory
- **Risk if unmet:** A future operator sets `workers=4` thinking it will improve performance. All in-memory SSE state fragments silently. SSE subscribers on worker 0 miss events sent to worker 1. No error is produced.
- **Fallback:** Document in README and `.env.example` that `workers=1` is mandatory

---

## Ablation Plan

**No ablation plan** — This phase implements independent infrastructure components (Gunicorn config, dotenv loading, SECRET_KEY persistence, process supervisor) with no sub-components to trade off against each other. Each component either works (sanity checks pass) or does not (sanity checks fail). There is no comparative analysis required.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views. All changes are backend-only: `pyproject.toml`, `backend/run.py`, `backend/app/__init__.py`, `backend/gunicorn.conf.py`, `backend/.env.example`, `justfile`, `deploy/agented.service`, `deploy/com.agented.backend.plist`, `.gitignore`.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Backend test pass rate | All existing backend tests passing | 911/911 (100%) | STATE.md performance metrics |
| Frontend build | vue-tsc + vite build with zero errors | 0 errors | STATE.md performance metrics |
| Frontend test pass rate | All frontend tests passing | 344/344 (100%) | STATE.md performance metrics |

Phase 2 must not regress any of these baselines. The phase makes no frontend changes, so the frontend baseline should be trivially preserved. The backend baseline (911/911) is the critical regression check.

---

## Evaluation Scripts

**Location of evaluation code:** No dedicated eval scripts needed — all checks use standard CLI tools (`grep`, `uv run python`, `uv run gunicorn --check-config`).

**How to run full sanity evaluation:**

```bash
# Run from project root: /Users/edward.seo/dev/private/project/harness/Agented

# S1: Dependencies
cd backend && uv sync && uv run python -c "import gevent; import dotenv; import apscheduler; import pytz; print('S1 PASS: All imports OK')"

# S2: Gunicorn config valid
cd backend && uv run gunicorn --check-config -c gunicorn.conf.py && echo "S2 PASS: Config valid"

# S3: workers=1 and worker_class=gevent
cd backend && uv run python -c "exec(open('gunicorn.conf.py').read()); assert workers == 1; assert worker_class == 'gevent'; print('S3 PASS: Config values correct')"

# S4: preload_app not set
grep -n "^preload_app" backend/gunicorn.conf.py && echo "S4 FAIL: preload_app is set" || echo "S4 PASS: preload_app not set"

# S5: load_dotenv before create_app
grep -n "load_dotenv\|from app\|create_app" backend/run.py

# S6: SECRET_KEY stability
cd backend && uv run python -c "from app import create_app; k1 = create_app().config['SECRET_KEY']; k2 = create_app().config['SECRET_KEY']; assert k1 == k2, 'FAIL'; print(f'S6 PASS: SECRET_KEY stable ({len(k1)} chars)')"

# S7: gitignore entries
grep -E "^\.env$|^backend/\.secret_key$|^\.secret_key$" .gitignore && echo "S7 PASS: secrets gitignored"

# S8: .env.example completeness
count=$(grep -c "SECRET_KEY\|GUNICORN_BIND\|CORS_ALLOWED_ORIGINS\|AGENTED_DB_PATH\|GITHUB_WEBHOOK_SECRET\|ANTHROPIC_API_KEY\|LOG_LEVEL\|SSE_REPLAY_LIMIT\|STALE_CONVERSATION\|STALE_EXECUTION" backend/.env.example); echo "S8: $count/10 vars documented"

# S9 + S10: justfile deploy and dev-backend
grep "gunicorn" justfile && echo "S9 PASS: deploy uses gunicorn"
grep -A 3 "^dev-backend" justfile

# S11: Backend test suite
cd backend && uv run pytest --tb=short -q

# S12: Process supervisor files
grep "Restart=on-failure" deploy/agented.service && grep "RestartSec=3" deploy/agented.service && echo "S12a PASS: systemd restart config correct"
grep -c "KeepAlive" deploy/com.agented.backend.plist && echo "S12b PASS: launchd KeepAlive set"
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Dependencies importable | [PASS/FAIL] | | |
| S2: Gunicorn config valid | [PASS/FAIL] | | |
| S3: workers=1, worker_class=gevent | [PASS/FAIL] | | |
| S4: preload_app not set | [PASS/FAIL] | | |
| S5: load_dotenv before create_app | [PASS/FAIL] | | |
| S6: SECRET_KEY stable across restarts | [PASS/FAIL] | | |
| S7: .env and .secret_key gitignored | [PASS/FAIL] | | |
| S8: .env.example completeness (10 vars) | [PASS/FAIL] | [count]/10 | |
| S9: just deploy uses Gunicorn | [PASS/FAIL] | | |
| S10: dev-backend preserved | [PASS/FAIL] | | |
| S11: Backend tests (no regression) | [PASS/FAIL] | [N]/911 | |
| S12: Process supervisor restart config | [PASS/FAIL] | | |

### Proxy Results

None — see "No Proxy Metrics" rationale above.

### Ablation Results

Not applicable — no ablation plan.

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-02-01 | Concurrent SSE load test (10 connections) | PENDING | phase-05-observability-and-process-reliability |
| DEFER-02-02 | workers=1 startup assertion enforcement | PENDING | phase-06-code-quality-and-maintainability |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 12 checks map 1:1 to the 7 requirements and 5 success criteria in ROADMAP.md. Every check has an exact executable command with a binary outcome. Infrastructure phases like this one are fully verifiable via sanity checks alone.
- Proxy metrics: None needed — the honest choice for infrastructure work. All real metrics are directly measurable without proxy approximation.
- Deferred coverage: Partial but appropriate — the two deferred items (SSE load testing, workers=1 assertion) are genuinely out-of-scope for this phase, not avoided. They are placed in the phases where they naturally belong (5 and 6 respectively).

**What this evaluation CAN tell us:**
- Whether all deliverables from Plan 01 and Plan 02 exist and are structurally correct
- Whether gevent, python-dotenv, APScheduler, and pytz are correctly declared and importable
- Whether SECRET_KEY persistence logic is implemented (two-call stability test)
- Whether the deploy target was updated and the dev target was preserved
- Whether existing tests pass without regression (gevent monkey patching does not break test suite)
- Whether process supervisor configs have the correct restart directives

**What this evaluation CANNOT tell us:**
- Whether gevent's monkey patching causes subtle timing issues with APScheduler under production load — requires runtime monitoring in Phase 5
- Whether the process supervisor configs actually work in a real systemd/launchd environment — requires deployment to a Linux/macOS server with the supervisor running
- Whether `workers=1` is sufficient for the expected load — requires Phase 5 load testing
- Whether SSE event delivery is reliable under 10+ concurrent connections — deferred to DEFER-02-01

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-02-28*
