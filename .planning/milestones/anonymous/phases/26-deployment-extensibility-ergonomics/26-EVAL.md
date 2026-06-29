# Evaluation Plan: Phase 26 — Deployment & Extensibility Ergonomics

**Designed:** 2026-06-30
**Designer:** Claude (grd-eval-planner)
**Methods evaluated:** Postgres DB-API shim (REQ-38), Render blueprint + install.sh + self-update (REQ-39), YAML authoring service (REQ-40), AGENTED_SERVER_NO_LLM_KEYS isolation flag (REQ-41)
**Reference plans:** 26-01-PLAN.md, 26-02-PLAN.md, 26-03-PLAN.md, 26-04-PLAN.md

---

## Evaluation Overview

This is a pure engineering phase with four parallel deliverables. There are no numeric baselines, no paper metrics, and no benchmark corpus. All success criteria are binary: green or red, present or absent, zero remaining instances or non-zero. The single most important criterion is the Postgres parity gate (criterion 5): the SAME backend pytest suite must pass on both SQLite (DATABASE_URL unset) and a real Postgres DATABASE_URL. Everything else in this phase is either blocked by that gate or independently verifiable via file presence, parse checks, and targeted unit tests.

Evaluation is structured as: (1) per-plan sanity checks that verify each deliverable independently, then (2) the phase gate that verifies DB parity across backends against the full test suite, then (3) deferred live-infra checks that cannot be done without a real Render deployment.

The full-suite hang documented in CLAUDE.md (stalls at ~40-48% of the serial suite) is a known environmental issue. The watchdog procedure applies at Tier 2: attempt the full suite under a ~12-minute watchdog; on hang, kill it and run a targeted comprehensive set (all suites touched by the phase's changes plus execution/streaming/harness regressions), and DISCLOSE the substitution. A targeted-run result must never be presented as a full-suite result.

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 14 checks | Per-plan unit, lint, parse, grep-guard, file-presence |
| Proxy (L2) | 3 checks | DB parity on both backends, frontend build, no-new-frontend-failures |
| Deferred (L3) | 2 validations | Live Render deploy + live self-update pull |

---

## Level 1: Sanity Checks

**Purpose:** Verify each deliverable independently. ALL must pass before the Tier 2 gate is attempted.

### Plan 26-01 — Postgres Adapter

### S1: DATABASE_URL config exists and defaults to SQLite
- **What:** `config.DATABASE_URL` exists; `_is_pg()` returns False when the var is unset
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import app.config as c; assert hasattr(c,'DATABASE_URL'); from app.db.connection import _is_pg; assert not _is_pg(); print('S1 PASS')"`
- **Expected:** `S1 PASS`
- **Failure means:** config.py or connection.py not updated; SQLite default broken

### S2: _PgConnWrapper and psycopg dep land
- **What:** psycopg[binary] importable; _PgConnWrapper class exists in connection.py
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import psycopg; from app.db.connection import _PgConnWrapper; print('S2 PASS')"`
- **Expected:** `S2 PASS`
- **Failure means:** psycopg[binary] not in pyproject.toml or not installed

### S3: adapter unit tests green (paramstyle + unified errors + init_db smoke)
- **What:** test_pg_adapter.py green; PG cases skip cleanly when no PG available
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_pg_adapter.py -v`
- **Expected:** All tests PASSED (PG cases marked xskip when DATABASE_URL unset — not FAILED)
- **Failure means:** Paramstyle translation broken, error aliasing broken, or testcontainers misconfigured

### S4: No remaining `except sqlite3.IntegrityError` under app/db (sweep complete)
- **What:** All 61 catch sites migrated to `app.db.errors.IntegrityError`
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && result=$(grep -rl "except sqlite3.IntegrityError" app/db 2>/dev/null); [ -z "$result" ] && echo "S4 PASS" || echo "REMAINING: $result"`
- **Expected:** `S4 PASS`
- **Failure means:** One or more catch sites not swept; those sites will silently miss PG UniqueViolation

### S5: Ruff clean on all 26-01 touched modules
- **What:** No lint errors on the new/modified DB-layer modules
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff check app/config.py app/db/connection.py app/db/errors.py app/db/migrations/_runner.py app/db/schema/__init__.py`
- **Expected:** Exit 0, no output
- **Failure means:** Style/import issues in new code

### Plan 26-02 — Render blueprint + install.sh + self-update

### S6: render.yaml parses and declares required services
- **What:** render.yaml exists at repo root, parses as valid YAML, and declares services or databases keys
- **Command:** `cd /Users/neo/Developer/Projects/Agented && uv run python -c "import yaml,sys; d=yaml.safe_load(open('render.yaml')); assert 'services' in d or 'databases' in d, 'missing services/databases'; print('S6 PASS')"`
- **Expected:** `S6 PASS`
- **Failure means:** render.yaml absent, malformed, or missing the required blueprint sections

### S7: install.sh passes shellcheck and --dry-run
- **What:** install.sh is shellcheck-clean and --dry-run prints commands without executing
- **Command:** `cd /Users/neo/Developer/Projects/Agented && shellcheck install.sh && bash install.sh --dry-run | head -5 && echo "S7 PASS"`
- **Expected:** `S7 PASS` (docker compose commands printed, nothing executed)
- **Failure means:** install.sh has shell errors or --dry-run flag not implemented

### S8: `just self-update` target present
- **What:** justfile has a self-update target
- **Command:** `cd /Users/neo/Developer/Projects/Agented && just --list | grep -q self-update && echo "S8 PASS"`
- **Expected:** `S8 PASS`
- **Failure means:** self-update target missing from justfile

### S9: deploy docs exist and README carries deploy reference
- **What:** docs/deploy.md and docs/deploy.ko.md both exist (i18n parity); README mentions Render
- **Command:** `cd /Users/neo/Developer/Projects/Agented && test -f docs/deploy.md && test -f docs/deploy.ko.md && grep -qi render README.md && echo "S9 PASS"`
- **Expected:** `S9 PASS`
- **Failure means:** Deploy doc or Korean sibling missing, or README missing the deploy button/reference

### Plan 26-03 — YAML authoring service

### S10: YAML round-trip and invalid-YAML tests green
- **What:** test_yaml_authoring.py green — round-trip equivalence + invalid YAML rejected before any DB write
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_yaml_authoring.py -v`
- **Expected:** All tests PASSED
- **Failure means:** load/materialize/export pipeline broken, or partial-state guard not implemented

### S11: import-yaml route present in routes/teams.py
- **What:** The import-yaml path is registered in the teams router
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "import app_litestar.routes.teams as t; assert 'import-yaml' in open(t.__file__).read(); print('S11 PASS')"`
- **Expected:** `S11 PASS`
- **Failure means:** Route not wired; the API endpoint is unreachable

### S12: Ruff clean on yaml_authoring_service + teams route
- **What:** No lint errors on new service and modified route
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff check app/services/yaml_authoring_service.py app_litestar/routes/teams.py`
- **Expected:** Exit 0, no output
- **Failure means:** Style/import issues in new code

### Plan 26-04 — AGENTED_SERVER_NO_LLM_KEYS

### S13: No-LLM-keys flag tests green (flag-on ignores poison key + flag-off regression + grep-guard)
- **What:** test_server_no_llm_keys.py green — all three guard clauses block the poison key when flag is on; behavior unchanged when flag is off; grep-guard asserts no NEW unguarded raw-key reads
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_server_no_llm_keys.py -v`
- **Expected:** All tests PASSED
- **Failure means:** Guard clause missing at one of the three sites, or a fourth unguarded raw-key read was introduced

### S14: AGENTED_SERVER_NO_LLM_KEYS documented in CLAUDE.md
- **What:** CLAUDE.md env-table contains the new flag
- **Command:** `grep -q AGENTED_SERVER_NO_LLM_KEYS /Users/neo/Developer/Projects/Agented/CLAUDE.md && echo "S14 PASS"`
- **Expected:** `S14 PASS`
- **Failure means:** Operator has no documented path to enable the key-isolation split

**Sanity gate:** ALL 14 sanity checks must pass. Any failure blocks the Tier 2 proxy gate.

---

## Level 2: Proxy Metrics

**Purpose:** Phase gate — verify DB parity across backends and that the full frontend+backend build remains green.

**IMPORTANT:** All proxy results are binary pass/fail. There are no numeric targets; there is no baseline to beat. The headline criterion is S3/Postgres (criterion 5).

### P1: HEADLINE — Backend pytest suite green on Postgres (criterion 5)

- **What:** The same backend test suite that passes on SQLite also passes with `DATABASE_URL` pointing at a real Postgres 16 instance
- **How:** Run the full suite under a ~12-minute watchdog against a testcontainers or CI postgres:16 service
- **Command (attempt full suite first):**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && \
    DATABASE_URL="postgresql://test:test@localhost:5432/test" \
    timeout 720 uv run pytest --timeout=60 -x 2>&1 | tail -20
  ```
- **On hang (>40-48% stall, consistent with the known issue):** Kill and run targeted set with DISCLOSED substitution:
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && \
    DATABASE_URL="postgresql://test:test@localhost:5432/test" \
    uv run pytest tests/test_pg_adapter.py tests/test_yaml_authoring.py \
      tests/test_server_no_llm_keys.py \
      tests/ -k "db or migration or service or conversation or execution or streaming or harness" \
      -v --timeout=60
  ```
  **DISCLOSE:** "Full suite hang triggered at ~X%; targeted comprehensive set run in substitution per CLAUDE.md procedure."
- **Target:** All tests PASSED on Postgres; zero new failures vs SQLite baseline
- **Evidence:** 26-01-PLAN.md §verification S3 — same suite is the defined gate; parametrized isolated_db runs both backends
- **Correlation with full success:** HIGH — this is the defining criterion, not a proxy for something else
- **Blind spots:** A targeted-run substitution cannot detect failures in untouched test modules; disclosed when substituted
- **Validated:** No — awaiting deferred live-infra Postgres confirmation (DEFER-26-01)

### P2: Backend pytest suite green on SQLite (criterion 5, regression arm)

- **What:** DATABASE_URL unset; zero-config default path is byte-for-byte unchanged
- **How:** Run the full suite (same watchdog procedure) with DATABASE_URL unset
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && \
    timeout 720 uv run pytest --timeout=60 -x 2>&1 | tail -20
  ```
  On hang: targeted set as above but without DATABASE_URL.
- **Target:** All tests PASSED; no regressions vs pre-phase baseline
- **Evidence:** 26-01-PLAN.md §verification S3b — this arm proves zero-config default intact
- **Correlation with full success:** HIGH — regression on SQLite means the shim corrupts the existing path
- **Blind spots:** Same watchdog-substitution caveat as P1
- **Validated:** No — baseline confirmation at phase close

### P3: `just build` frontend + type-check passes (repo gate)

- **What:** vue-tsc type check + vite production build succeeds; no NEW frontend test failures
- **How:** Run both frontend gates
- **Commands:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented && just build
  cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
  ```
- **Target:** `just build` exits 0; frontend test run has no NEW failures beyond the 7 known pre-existing failures (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas)
- **Evidence:** CLAUDE.md — all three gates (just build, backend pytest, frontend test:run) must pass before any task is complete
- **Correlation with full success:** HIGH — type errors indicate frontend-breaking backend API changes; new test failures indicate regression
- **Blind spots:** Does not cover WebMCP browser-level validation (not applicable — this phase has no frontend view changes)
- **Validated:** No — confirmed at phase execution time

---

## Level 3: Deferred Validations

**Purpose:** Full validation requiring live infrastructure not available at authoring time.

### D1: Real Render blueprint deploy succeeds — DEFER-26-01

- **What:** A live Render deployment using render.yaml builds successfully, wires the managed Postgres DATABASE_URL, and the app health endpoint responds
- **How:** Push render.yaml to a Render account; trigger a blueprint deploy; confirm the build context resolves the sibling ai-accounts/ tree (the documented risk from 26-02-PLAN.md research pitfall #5)
- **Why deferred:** Requires a live Render account, a pushed Docker image at ghcr.io/ca1773130n/agented, and network access to a Render environment
- **Validates at:** phase-26-verification (post-merge manual sign-off)
- **Depends on:** ghcr image published and accessible; Render account with blueprint access; sibling build-context workaround (if needed) documented and applied
- **Target:** Blueprint deploys without error; `GET /health` returns 200; DATABASE_URL is set from managed Postgres connectionString
- **Risk if unmet:** The render.yaml may be syntactically valid but functionally non-deployable due to the sibling-dir build context. Fallback: document the build-arg/vendored-copy workaround in deploy.md and ship as "configuration required" until the Dockerfile build context issue is resolved upstream
- **Fallback:** Treat render.yaml as a documentation/template artifact; the install.sh + docker compose path remains the primary deploy mechanism

### D2: `just self-update` pulls a newer image and restarts cleanly — DEFER-26-02

- **What:** Running `just self-update` on an installed instance with a stale image pulls the latest tag and brings the compose stack back up without downtime or data loss
- **How:** Deploy two versions (old → new); run `just self-update` on the old; confirm the new version is running and the DB schema survived
- **Why deferred:** Requires two distinct tagged images at ghcr.io/ca1773130n/agented and a running compose stack
- **Validates at:** phase-26-verification (post-merge manual sign-off)
- **Depends on:** DEFER-26-01 successful (compose stack must be running); ghcr image with at least two tags
- **Target:** `docker compose pull` reports a newer digest pulled; `docker compose up -d` exits 0; app health endpoint responds; no DB schema errors in logs
- **Risk if unmet:** self-update may leave the stack in a partial state if the compose file or startup order is wrong. Low probability (the command is standard Docker); medium impact (operators cannot self-update without manual intervention)
- **Fallback:** Document manual update procedure (pull + restart) in deploy.md

---

## Ablation Plan

**No ablation plan** — this phase implements four independent infrastructure deliverables (DB adapter, deploy artifacts, YAML service, key-isolation flag). No sub-components to isolate within any plan; each plan is already a minimal targeted addition.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views. All files_modified in the four plans are backend Python, config, shell, YAML, and documentation files. No HTML, JSX, TSX, Vue, Svelte, CSS, or frontend route files are touched.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| SQLite test suite | Full backend pytest suite before phase, DATABASE_URL unset | All green (no failures before the known hang) | CLAUDE.md |
| Frontend test suite | npm run test:run before phase | 7 known pre-existing failures; no additional failures | CLAUDE.md |
| just build | vue-tsc + vite build before phase | Exit 0 | CLAUDE.md |

---

## Evaluation Scripts

**Per-plan sanity (run in order):**
```bash
# S1-S5: Postgres adapter
cd /Users/neo/Developer/Projects/Agented/backend
uv run python -c "import app.config as c; assert hasattr(c,'DATABASE_URL'); from app.db.connection import _is_pg; assert not _is_pg(); print('S1 PASS')"
uv run python -c "import psycopg; from app.db.connection import _PgConnWrapper; print('S2 PASS')"
uv run pytest tests/test_pg_adapter.py -v
result=$(grep -rl "except sqlite3.IntegrityError" app/db 2>/dev/null); [ -z "$result" ] && echo "S4 PASS" || echo "REMAINING: $result"
uv run ruff check app/config.py app/db/connection.py app/db/errors.py app/db/migrations/_runner.py app/db/schema/__init__.py

# S6-S9: Deploy artifacts
cd /Users/neo/Developer/Projects/Agented
uv run python -c "import yaml; d=yaml.safe_load(open('render.yaml')); assert 'services' in d or 'databases' in d; print('S6 PASS')"
shellcheck install.sh && bash install.sh --dry-run | head -5 && echo "S7 PASS"
just --list | grep -q self-update && echo "S8 PASS"
test -f docs/deploy.md && test -f docs/deploy.ko.md && grep -qi render README.md && echo "S9 PASS"

# S10-S12: YAML authoring
cd /Users/neo/Developer/Projects/Agented/backend
uv run pytest tests/test_yaml_authoring.py -v
uv run python -c "import app_litestar.routes.teams as t; assert 'import-yaml' in open(t.__file__).read(); print('S11 PASS')"
uv run ruff check app/services/yaml_authoring_service.py app_litestar/routes/teams.py

# S13-S14: Key isolation flag
uv run pytest tests/test_server_no_llm_keys.py -v
grep -q AGENTED_SERVER_NO_LLM_KEYS /Users/neo/Developer/Projects/Agented/CLAUDE.md && echo "S14 PASS"
```

**Tier 2 gate (run after all sanity checks pass):**
```bash
# P1: Postgres backend suite (attempt full, fall back to targeted on hang)
cd /Users/neo/Developer/Projects/Agented/backend
DATABASE_URL="postgresql://test:test@localhost:5432/test" timeout 720 uv run pytest --timeout=60 -x 2>&1 | tail -20

# P2: SQLite regression arm
cd /Users/neo/Developer/Projects/Agented/backend
timeout 720 uv run pytest --timeout=60 -x 2>&1 | tail -20

# P3: Frontend gate
cd /Users/neo/Developer/Projects/Agented && just build
cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: DATABASE_URL + _is_pg() | | | |
| S2: psycopg + _PgConnWrapper importable | | | |
| S3: test_pg_adapter.py | | | |
| S4: No remaining sqlite3.IntegrityError | | | |
| S5: Ruff clean (26-01 modules) | | | |
| S6: render.yaml parses | | | |
| S7: install.sh shellcheck + --dry-run | | | |
| S8: just self-update present | | | |
| S9: deploy docs + README | | | |
| S10: test_yaml_authoring.py | | | |
| S11: import-yaml route wired | | | |
| S12: Ruff clean (yaml service + teams route) | | | |
| S13: test_server_no_llm_keys.py | | | |
| S14: CLAUDE.md documents flag | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Backend suite on Postgres | All PASSED | | | Full suite or targeted (disclose substitution) |
| P2: Backend suite on SQLite | All PASSED (no regressions) | | | |
| P3: just build + frontend tests | Build exit 0; no NEW failures | | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-26-01 | Real Render blueprint deploy | PENDING | phase-26-verification |
| DEFER-26-02 | just self-update live pull + restart | PENDING | phase-26-verification |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: adequate — 14 checks with exact commands, each maps directly to a verifiable artifact or test in the four plans
- Proxy metrics: well-evidenced — the Postgres proxy (P1) IS the defining success criterion per 26-01-PLAN.md; no approximation required; correlation is effectively 1.0 for the DB parity goal
- Deferred coverage: comprehensive for the two items that need live infra; everything else is verifiable in-phase

**What this evaluation CAN tell us:**
- Whether the DB-API shim is structurally correct (paramstyle, error aliasing, RETURNING, dialect branches)
- Whether the full test suite passes on both SQLite and Postgres (binary, within watchdog constraints)
- Whether all four deliverable artifacts are present and individually functional
- Whether existing behavior is unaffected (regressions on SQLite, frontend gate)

**What this evaluation CANNOT tell us (deferred):**
- Whether render.yaml actually deploys on Render infrastructure (sibling build-context risk — must be confirmed or documented at phase-26-verification)
- Whether `just self-update` survives a real version transition on a live compose stack (DEFER-26-02, phase-26-verification)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-30*
