# Evaluation Plan: Phase 12 — Specialized Automation Bots

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Predefined trigger pattern, SQLite FTS5 BM25 search, Chain-of-thought skill files, Conventional Commits changelog parsing, gh CLI PR comment pattern
**Reference papers:** Robertson & Zaragoza (2009) BM25; Wei et al. (2022) Chain-of-Thought; Conventional Commits v1.0.0 spec; SQLite FTS5 documentation

---

## Evaluation Overview

Phase 12 ships seven pre-built specialized automation bots — vulnerability triage, code tour generation, test coverage gap detection, incident postmortem drafting, changelog generation, PR summaries, and natural language log search — plus the supporting FTS5 search infrastructure to power BOT-07. The implementation spans three plan waves: backend trigger definitions + FTS5 schema (Plan 01), Claude skill instruction files + SpecializedBotService helpers (Plan 02), and specialized bot API routes + frontend search UI (Plan 03).

The evaluation challenge for this phase is that most bot quality outcomes depend on runtime AI behavior — the Claude LLM executing skill file instructions — which cannot be unit-tested or proxy-evaluated in isolation. What can be verified mechanically is: (1) the infrastructure exists and is wired correctly (triggers seeded, FTS5 schema valid, API endpoints respond, skill files present), and (2) the structural contracts hold (correct prompt templates, correct trigger sources, correct route registrations). Bot output quality — whether the vulnerability scanner actually finds CVEs, whether the code tour actually produces 5 good sections — is deferred to manual integration testing.

The FTS5 search component (BOT-07) is the exception: its correctness is fully mechanical and testable with seeded data. BM25 ranking, snippet generation, and sync trigger behavior can all be verified with deterministic unit tests.

The PR summary bot's 60-second SLA (BOT-06) is a timing constraint that requires a running system with a real GitHub webhook event to measure. It cannot be verified in unit tests.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|-----------------|
| 7 predefined triggers seeded on startup | Phase success criteria #1 (all bots) | Foundation — without correct trigger definitions, no bot executes |
| FTS5 BM25 ranked search returns results | BOT-07 requirement; Robertson & Zaragoza (2009) | BM25 is the evaluation standard for lexical IR; FTS5 implements it natively |
| FTS5 sync triggers fire on INSERT/UPDATE/DELETE | 12-RESEARCH.md Pitfall 1 | Stale index produces incorrect search results |
| Skill files present with substantial content | BOT-01 through BOT-07 requirements | Skill files are the primary bot intelligence |
| PR summary latency <60 seconds | BOT-06 SLA (phase success criteria) | Hard requirement from phase spec |
| Code tour produces >=5 annotated sections | BOT-02 success criteria | Structural output contract |
| Changelog correctly groups PRs by type | BOT-05 success criteria | Verifiable with deterministic mock PR data |
| Backend tests pass at 100% | Codebase convention (CLAUDE.md) | No regressions in existing test suite |
| Frontend builds without TypeScript errors | Codebase convention (CLAUDE.md) | Type safety for new types and components |
| Ruff lint/format passes | Codebase convention (Phase 6 established) | Code quality standard |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 10 | Infrastructure existence, format, and wiring verification |
| Proxy (L2) | 8 | Behavioral correctness via deterministic test data |
| Deferred (L3) | 5 | Live AI output quality, real GitHub integration, production scale |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: All 7 new predefined triggers seeded in database

- **What:** After `seed_predefined_triggers()` runs, all 7 new bot triggers exist alongside the 2 existing ones
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.db.triggers import PREDEFINED_TRIGGERS, PREDEFINED_TRIGGER_IDS
  NEW_IDS = ['bot-vuln-scan', 'bot-code-tour', 'bot-test-coverage', 'bot-postmortem', 'bot-changelog', 'bot-pr-summary', 'bot-log-search']
  for bot_id in NEW_IDS:
      assert bot_id in PREDEFINED_TRIGGER_IDS, f'MISSING: {bot_id}'
  assert len([t for t in PREDEFINED_TRIGGERS if t['id'].startswith('bot-')]) >= 9, 'Expected >=9 bot triggers'
  print('PASS: All 7 new predefined triggers defined')
  "
  ```
- **Expected:** `PASS: All 7 new predefined triggers defined` — no assertion errors
- **Failure means:** Trigger definitions were not added to `PREDEFINED_TRIGGERS` list in `backend/app/db/triggers.py`

### S2: FTS5 virtual table creation SQL is syntactically valid

- **What:** The `execution_logs_fts` virtual table and its 3 sync triggers can be created without SQL errors against a fresh SQLite database
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  import sqlite3, tempfile, os
  db = tempfile.mktemp(suffix='.db')
  conn = sqlite3.connect(db)
  from app.db.schema import create_fresh_schema
  create_fresh_schema(conn)
  cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' OR type='shadow'\")
  names = [r[0] for r in cursor.fetchall()]
  assert 'execution_logs_fts' in names or any('fts' in n for n in names), f'FTS5 table not found in: {names}'
  conn.close(); os.unlink(db)
  print('PASS: FTS5 virtual table created without errors')
  "
  ```
- **Expected:** `PASS: FTS5 virtual table created without errors`
- **Failure means:** SQL syntax error in `create_fresh_schema()` for the FTS5 DDL; check for typos in column names or tokenizer specification

### S3: ExecutionSearchService imports and instantiates without errors

- **What:** The search service module loads cleanly and the class is accessible
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.services.execution_search_service import ExecutionSearchService
  assert hasattr(ExecutionSearchService, 'search'), 'search() method missing'
  assert hasattr(ExecutionSearchService, 'get_search_stats'), 'get_search_stats() method missing'
  print('PASS: ExecutionSearchService importable with expected methods')
  "
  ```
- **Expected:** `PASS: ExecutionSearchService importable with expected methods`
- **Failure means:** Module not created, import error, or method names differ from spec

### S4: SpecializedBotService imports with all required methods

- **What:** The helper service loads cleanly with all 4 expected classmethods
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.services.specialized_bot_service import SpecializedBotService
  for method in ['post_pr_comment', 'list_merged_prs', 'check_gh_auth', 'check_osv_scanner']:
      assert hasattr(SpecializedBotService, method), f'Missing method: {method}'
  print('PASS: SpecializedBotService has all 4 required classmethods')
  "
  ```
- **Expected:** `PASS: SpecializedBotService has all 4 required classmethods`
- **Failure means:** Service not created or methods named differently than plan spec

### S5: All 7 skill instruction files exist with non-trivial content

- **What:** Each bot has a `.claude/skills/<slug>/INSTRUCTIONS.md` file with at least 500 bytes of content
- **Command:**
  ```bash
  SKILLS_DIR=/Users/neo/Developer/Projects/Agented/.claude/skills
  for slug in vulnerability-scan code-tour test-coverage-gaps incident-postmortem generate-changelog pr-summary search-logs; do
      file="$SKILLS_DIR/$slug/INSTRUCTIONS.md"
      if [ ! -f "$file" ]; then echo "MISSING: $file"; exit 1; fi
      size=$(wc -c < "$file")
      if [ "$size" -lt 500 ]; then echo "TOO SMALL ($size bytes): $file"; exit 1; fi
      echo "PASS ($size bytes): $slug"
  done
  echo "All 7 skill files present and non-trivial"
  ```
- **Expected:** 7 `PASS` lines then `All 7 skill files present and non-trivial`
- **Failure means:** Skill file missing or is a stub — the bot will produce garbage output or fail silently

### S6: Backend tests pass without regressions

- **What:** Full pytest suite passes at 100% — no new failures introduced
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest --tb=short -q 2>&1 | tail -5
  ```
- **Expected:** `N passed` with zero failures or errors (N >= existing baseline of ~906)
- **Failure means:** Phase 12 changes broke an existing behavior — regression must be fixed before proceeding

### S7: Ruff lint and format check pass

- **What:** Code style compliance per project conventions (established in Phase 6)
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff check . && uv run ruff format --check . && echo "PASS: lint and format clean"
  ```
- **Expected:** `PASS: lint and format clean`
- **Failure means:** New Python files introduced formatting or lint violations

### S8: Frontend builds without TypeScript errors

- **What:** `just build` completes (vue-tsc type check + vite build) with zero errors — validates all new TS types and Vue components
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented && just build 2>&1 | tail -10
  ```
- **Expected:** Build completes with `✓ built in` message, no TypeScript errors
- **Failure means:** New types in `types.ts`, new Vue component, or API client have type errors

### S9: GET /admin/specialized-bots/status returns valid JSON with 7 bot entries

- **What:** The status endpoint responds with HTTP 200 and a JSON body containing entries for all 7 new bots
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  import json
  from app import create_app
  app = create_app({'TESTING': True})
  client = app.test_client()
  resp = client.get('/admin/specialized-bots/status', headers={'X-API-Key': 'test'})
  assert resp.status_code == 200, f'Expected 200, got {resp.status_code}'
  data = resp.get_json()
  print(json.dumps(data, indent=2)[:500])
  print('PASS: Status endpoint returns 200')
  "
  ```
- **Expected:** HTTP 200 with JSON body (content will vary based on runtime environment)
- **Failure means:** Blueprint not registered, route not found (404), or auth middleware misconfigured

### S10: GET /admin/execution-search responds to a simple query

- **What:** The search endpoint returns HTTP 200 for a well-formed query (even if no results)
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app import create_app
  app = create_app({'TESTING': True})
  client = app.test_client()
  resp = client.get('/admin/execution-search?q=test', headers={'X-API-Key': 'test'})
  assert resp.status_code == 200, f'Expected 200, got {resp.status_code}'
  data = resp.get_json()
  assert 'results' in data, f'Missing results key: {data}'
  assert 'query' in data, f'Missing query key: {data}'
  print(f'PASS: Search endpoint returns 200 with results={data[\"results\"]} query={data[\"query\"]}')
  "
  ```
- **Expected:** `PASS: Search endpoint returns 200 with results=[] query=test`
- **Failure means:** Blueprint not registered, model validation error, or FTS5 table missing

**Sanity gate:** ALL 10 sanity checks must pass. Any failure blocks progression to proxy metrics.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of behavioral correctness using deterministic test data.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full evaluation. Bot output quality requires live AI execution that cannot be unit-tested. Treat structural proxy results with appropriate confidence — they verify contracts, not quality.

### P1: FTS5 BM25 search returns ranked results for seeded data

- **What:** The FTS5 index correctly ingests execution log content and returns BM25-ranked results with highlighted snippets for known keyword queries
- **How:** Seed 5 execution log rows with known content, query with a term present in some rows, verify results are non-empty and contain the expected highlighted snippet
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  import sqlite3, tempfile, os
  db = tempfile.mktemp(suffix='.db')

  import app.config as cfg
  cfg.DB_PATH = db
  from app.database import init_db, seed_predefined_triggers
  init_db()
  seed_predefined_triggers()

  from app.db.connection import get_connection
  with get_connection() as conn:
      # Seed test execution logs with known content
      for i, content in enumerate([
          ('sql-injection vulnerability found in login.py', ''),
          ('all tests passed', ''),
          ('sql injection attack pattern detected in request', ''),
          ('deployment successful', ''),
          ('sql injection CVE-2023-1234 patched', ''),
      ]):
          conn.execute(
              'INSERT INTO execution_logs (execution_id, trigger_id, status, stdout_log, stderr_log, prompt) VALUES (?, ?, ?, ?, ?, ?)',
              (f'exec-{i}', 'bot-security', 'completed', content[0], content[1], 'test prompt')
          )

  from app.services.execution_search_service import ExecutionSearchService
  results = ExecutionSearchService.search('sql injection', limit=10)
  assert len(results) >= 3, f'Expected >=3 results for sql injection query, got {len(results)}'
  assert all('stdout_match' in r or 'stderr_match' in r for r in results), 'Missing snippet fields'
  print(f'PASS: FTS5 returned {len(results)} ranked results for sql injection query')
  for r in results[:3]:
      print(f'  - {r[\"execution_id\"]}: {str(r.get(\"stdout_match\", \"\"))[:80]}')
  os.unlink(db)
  "
  ```
- **Target:** >= 3 results returned for a query matching 3 of 5 seeded rows; results contain `stdout_match` or `stderr_match` with `<mark>` highlighting
- **Evidence from:** 12-RESEARCH.md Recommendation 1 (BM25 ranking); Robertson & Zaragoza (2009) establishes BM25 as reliable for this scale; SQLite FTS5 docs confirm `snippet()` function behavior
- **Correlation with full metric:** HIGH — BM25 ranking behavior is deterministic given the tokenizer and document set; this test directly exercises the production code path
- **Blind spots:** Does not test ranking quality (whether higher-relevance docs rank first) or query robustness for unusual inputs; does not test with 10K+ documents
- **Validated:** No — awaiting deferred validation D1 for scale testing

### P2: FTS5 sync triggers keep index synchronized with source table

- **What:** After an INSERT into `execution_logs`, the FTS index reflects the new content immediately (within the same transaction); after a DELETE, the FTS index removes the entry
- **How:** INSERT a row, verify search finds it; DELETE the row, verify search no longer finds it
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  import tempfile, os
  db = tempfile.mktemp(suffix='.db')
  import app.config as cfg
  cfg.DB_PATH = db

  from app.database import init_db, seed_predefined_triggers
  init_db(); seed_predefined_triggers()

  from app.db.connection import get_connection
  from app.services.execution_search_service import ExecutionSearchService

  # Test INSERT sync
  with get_connection() as conn:
      conn.execute(
          'INSERT INTO execution_logs (execution_id, trigger_id, status, stdout_log, prompt) VALUES (?, ?, ?, ?, ?)',
          ('exec-sync-test', 'bot-security', 'completed', 'unique-xray-term found in log', 'prompt')
      )

  results = ExecutionSearchService.search('unique-xray-term')
  assert len(results) == 1, f'INSERT sync failed: expected 1 result, got {len(results)}'
  print('PASS: INSERT sync trigger fires correctly')

  # Test DELETE sync
  with get_connection() as conn:
      conn.execute('DELETE FROM execution_logs WHERE execution_id = ?', ('exec-sync-test',))

  results = ExecutionSearchService.search('unique-xray-term')
  assert len(results) == 0, f'DELETE sync failed: expected 0 results, got {len(results)}'
  print('PASS: DELETE sync trigger fires correctly')
  os.unlink(db)
  "
  ```
- **Target:** 0 assertion errors; INSERT and DELETE both reflected in FTS index without manual rebuild
- **Evidence from:** 12-RESEARCH.md Pitfall 1 (FTS5 sync requirement with explicit SQLite triggers)
- **Correlation with full metric:** HIGH — if sync triggers are missing or broken, BOT-07 search silently returns stale data; this test catches that directly
- **Blind spots:** Does not test UPDATE sync trigger; does not test concurrent write behavior
- **Validated:** No — awaiting deferred validation D1

### P3: Malformed FTS5 queries return empty results gracefully, not 500 errors

- **What:** Queries with syntax that would cause FTS5 `OperationalError` are caught and return an empty result set rather than propagating as HTTP 500
- **How:** Send malformed FTS5 syntax through the search endpoint via the test client
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app import create_app
  app = create_app({'TESTING': True})
  client = app.test_client()

  # FTS5 syntax error: unmatched quote
  resp = client.get('/admin/execution-search?q=%22unmatched+quote', headers={'X-API-Key': 'test'})
  assert resp.status_code == 200, f'Expected graceful 200, got {resp.status_code}'
  data = resp.get_json()
  assert data['results'] == [], f'Expected empty results for malformed query, got {data[\"results\"]}'
  print('PASS: Malformed FTS5 query handled gracefully')
  "
  ```
- **Target:** HTTP 200 with `results: []` — no 500, no unhandled exception
- **Evidence from:** 12-RESEARCH.md Plan 01 Task 2 (explicit requirement to wrap FTS5 in try/except for `sqlite3.OperationalError`)
- **Correlation with full metric:** HIGH — this tests the exact error handling branch specified in the plan; a missing try/except is immediately visible as a 500
- **Blind spots:** Only tests one malformed pattern; other invalid FTS5 inputs may behave differently
- **Validated:** No

### P4: Trigger filter in search returns only matching trigger's results

- **What:** When `trigger_id` filter is applied, search results contain only executions from that trigger
- **How:** Seed logs from two different triggers, search with trigger_id filter, verify results are scoped
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  import tempfile, os
  db = tempfile.mktemp(suffix='.db')
  import app.config as cfg; cfg.DB_PATH = db
  from app.database import init_db, seed_predefined_triggers
  init_db(); seed_predefined_triggers()

  from app.db.connection import get_connection
  from app.services.execution_search_service import ExecutionSearchService

  with get_connection() as conn:
      conn.execute('INSERT INTO execution_logs (execution_id, trigger_id, status, stdout_log, prompt) VALUES (?, ?, ?, ?, ?)',
          ('exec-sec', 'bot-security', 'completed', 'security vulnerability error detected', 'prompt'))
      conn.execute('INSERT INTO execution_logs (execution_id, trigger_id, status, stdout_log, prompt) VALUES (?, ?, ?, ?, ?)',
          ('exec-pr', 'bot-pr-review', 'completed', 'security review of PR looks clean', 'prompt'))

  # Filter by bot-security only
  results = ExecutionSearchService.search('security', trigger_id='bot-security')
  assert all(r['trigger_id'] == 'bot-security' for r in results), f'Trigger filter leaked: {[r[\"trigger_id\"] for r in results]}'
  assert len(results) == 1, f'Expected 1 result, got {len(results)}'
  print(f'PASS: trigger_id filter correctly scopes results to bot-security')
  os.unlink(db)
  "
  ```
- **Target:** All returned results have `trigger_id == 'bot-security'`; no leakage from other triggers
- **Evidence from:** 12-RESEARCH.md Plan 01 Task 2 (optional trigger_id WHERE clause in search query)
- **Correlation with full metric:** HIGH — filtering is a boolean correctness test, not a quality heuristic
- **Blind spots:** Does not test pagination or limit interaction with trigger filter
- **Validated:** No

### P5: All 7 new triggers seeded correctly into isolated test database

- **What:** `seed_predefined_triggers()` correctly inserts all 7 new triggers (including schedule fields for `bot-vuln-scan`) when called on a fresh test database
- **How:** Use the `isolated_db` pattern from conftest.py to run seed and verify via API
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest -xvs -k "predefined" 2>&1 | tail -20
  # If no test for new bots yet, run direct verification:
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  import tempfile, os
  db = tempfile.mktemp(suffix='.db')
  import app.config as cfg; cfg.DB_PATH = db
  from app.database import init_db, seed_predefined_triggers
  init_db(); seed_predefined_triggers()

  from app.db.connection import get_connection
  with get_connection() as conn:
      cursor = conn.execute('SELECT id, trigger_source, is_predefined FROM triggers WHERE id LIKE \"bot-%\"')
      rows = {r[0]: {'source': r[1], 'is_predefined': r[2]} for r in cursor.fetchall()}

  EXPECTED = {
      'bot-vuln-scan': 'scheduled',
      'bot-code-tour': 'manual',
      'bot-test-coverage': 'github',
      'bot-postmortem': 'manual',
      'bot-changelog': 'manual',
      'bot-pr-summary': 'github',
      'bot-log-search': 'manual',
  }
  for bot_id, expected_source in EXPECTED.items():
      assert bot_id in rows, f'NOT SEEDED: {bot_id}'
      assert rows[bot_id]['source'] == expected_source, f'{bot_id}: expected source={expected_source}, got {rows[bot_id][\"source\"]}'
      assert rows[bot_id]['is_predefined'] == 1, f'{bot_id}: is_predefined not set'
  print(f'PASS: All 7 new triggers seeded with correct trigger_source and is_predefined=1')
  os.unlink(db)
  "
  ```
- **Target:** All 7 triggers present in DB with correct `trigger_source` and `is_predefined=1`
- **Evidence from:** Plan 01 success criteria #1; 12-RESEARCH.md Pitfall 4 (predefined trigger ID conventions)
- **Correlation with full metric:** HIGH — seeding is a deterministic DB operation; either the rows are there or they are not
- **Blind spots:** Does not verify schedule_type/schedule_time/schedule_day fields for `bot-vuln-scan`
- **Validated:** No

### P6: BOT-05 Conventional Commits categorization with mock PR data

- **What:** The changelog skill file's categorization logic (feat/fix/breaking) works correctly when applied to PR title data
- **How:** Since skill files are AI instructions, this proxy tests the SpecializedBotService's `list_merged_prs()` parsing — verifying the infrastructure returns parseable data — and checks the skill file references `feat`, `fix`, and `breaking` keywords
- **Command:**
  ```bash
  # Structural check: skill file references Conventional Commits parsing
  grep -c "feat\|fix\|breaking\|Conventional" /Users/neo/Developer/Projects/Agented/.claude/skills/generate-changelog/INSTRUCTIONS.md
  echo "Changelog skill has expected Conventional Commits references"

  # Structural check: SpecializedBotService.list_merged_prs exists and handles subprocess
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.services.specialized_bot_service import SpecializedBotService
  import inspect
  src = inspect.getsource(SpecializedBotService.list_merged_prs)
  assert 'gh' in src and 'merged' in src, 'list_merged_prs does not invoke gh CLI for merged PRs'
  assert 'json' in src.lower(), 'list_merged_prs does not parse JSON output'
  assert 'except' in src or 'try' in src, 'list_merged_prs has no error handling'
  print('PASS: list_merged_prs references gh CLI with JSON parsing and error handling')
  "
  ```
- **Target:** Skill file contains >= 3 references to Conventional Commits keywords; `list_merged_prs` method invokes `gh` with `merged` flag and parses JSON
- **Evidence from:** 12-RESEARCH.md Recommendation 4 (Conventional Commits spec); Plan 02 Task 1 BOT-05 spec
- **Correlation with full metric:** LOW-MEDIUM — this verifies structural intent but not runtime AI output quality; actual changelog accuracy requires manual review with real PR data
- **Blind spots:** AI categorization behavior for non-conforming PR titles cannot be tested without running Claude; grouping correctness requires live execution
- **Validated:** No — awaiting deferred validation D3

### P7: PR comment posting method handles missing gh CLI gracefully

- **What:** `SpecializedBotService.post_pr_comment()` returns `False` (not raises) when `gh` CLI is not found
- **How:** Mock the subprocess call to simulate `FileNotFoundError` and verify graceful return
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from unittest.mock import patch
  from app.services.specialized_bot_service import SpecializedBotService

  with patch('subprocess.run', side_effect=FileNotFoundError('gh not found')):
      result = SpecializedBotService.post_pr_comment('owner/repo', 1, 'test comment')
  assert result is False, f'Expected False on FileNotFoundError, got {result}'
  print('PASS: post_pr_comment returns False when gh CLI not found')

  with patch('subprocess.run', side_effect=__import__(\"subprocess\").TimeoutExpired(['gh'], timeout=30)):
      result = SpecializedBotService.post_pr_comment('owner/repo', 1, 'test comment')
  assert result is False, f'Expected False on timeout, got {result}'
  print('PASS: post_pr_comment returns False on subprocess timeout')
  "
  ```
- **Target:** Both `FileNotFoundError` and `TimeoutExpired` return `False`, not raise exceptions
- **Evidence from:** 12-RESEARCH.md Production Considerations (gh CLI not authenticated/not installed as known failure modes); Plan 02 Task 2 spec
- **Correlation with full metric:** HIGH — error handling is a boolean correctness test
- **Blind spots:** Does not test the success path with a real `gh pr comment` invocation
- **Validated:** No — success path deferred to D4

### P8: Frontend execution search page route registered and component exists

- **What:** The `/execution-search` route is registered in the router and `ExecutionSearchPage.vue` exists in the views directory
- **How:** File existence check and grep for route registration
- **Command:**
  ```bash
  # Component exists
  test -f /Users/neo/Developer/Projects/Agented/frontend/src/views/ExecutionSearchPage.vue && echo "PASS: ExecutionSearchPage.vue exists" || echo "FAIL: ExecutionSearchPage.vue missing"

  # Route registered
  grep -r "execution-search" /Users/neo/Developer/Projects/Agented/frontend/src/router/ && echo "PASS: Route registered" || echo "FAIL: Route not registered"

  # Sidebar link present
  grep -i "execution.search\|Execution Search" /Users/neo/Developer/Projects/Agented/frontend/src/components/layout/AppSidebar.vue && echo "PASS: Sidebar link present" || echo "FAIL: Sidebar link missing"

  # API client exists and exports searchLogs
  grep "searchLogs" /Users/neo/Developer/Projects/Agented/frontend/src/services/api/specialized-bots.ts && echo "PASS: searchLogs API function present" || echo "FAIL: searchLogs missing"
  ```
- **Target:** All 4 checks output `PASS`
- **Evidence from:** Plan 03 success criteria; codebase convention (frontend routes must be registered in `src/router/`)
- **Correlation with full metric:** MEDIUM — file existence confirms the component was created, but does not verify the UI renders correctly or the API calls succeed
- **Blind spots:** Component may have runtime errors not caught by file existence check; TypeScript type errors in component caught by S8 (build check)
- **Validated:** No — UI behavior deferred to D5

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring live AI execution, real GitHub integration, or production-scale data.

### D1: FTS5 search performance at production scale — DEFER-12-01

- **What:** Search query latency remains <500ms with 10,000+ indexed execution log documents; BM25 ranking quality holds at scale
- **How:** Load test with synthetic execution logs, measure p95 query latency for representative queries
- **Why deferred:** Production-scale log volume does not exist in the test environment; generating 10K+ realistic logs requires either running the system for extended periods or building a log fixture generator
- **Validates at:** Integration/production evaluation phase (when system has been running for 30+ days)
- **Depends on:** 30 days of execution history, or a data fixture generator script
- **Target:** p95 query latency <500ms for queries against 10,000+ documents (per 12-RESEARCH.md production consideration)
- **Risk if unmet:** FTS5 index may need `OPTIMIZE` tuning or log truncation strategy; 12-RESEARCH.md already identifies this and prescribes the mitigation (32KB log truncation, periodic OPTIMIZE)
- **Fallback:** Add `INSERT INTO execution_logs_fts(execution_logs_fts) VALUES('optimize')` to the existing 30-day retention cleanup job; truncate logs at 32KB per 12-RESEARCH.md Pitfall 5

### D2: BOT-06 PR summary latency SLA — DEFER-12-02

- **What:** The PR summary bot posts a PR comment within 60 seconds of a `pull_request.opened` GitHub webhook event, including Claude LLM processing time
- **How:** Set up a test GitHub repository, configure Agented webhook, open a PR, measure wall-clock time from webhook receipt to `gh pr comment` success in execution logs
- **Why deferred:** Requires: (1) running Agented instance with real GitHub webhook delivery, (2) authenticated `gh` CLI, (3) actual Claude execution (not unit-testable), (4) real PR to comment on
- **Validates at:** GitHub integration testing phase (requires deployed instance + configured webhook)
- **Depends on:** Deployed Agented instance, GitHub repo with webhook configured, gh CLI auth, Claude CLI available
- **Target:** Comment posted within 60 seconds for PRs with <500 lines of diff (per phase success criteria and 12-RESEARCH.md Pitfall 3)
- **Risk if unmet:** 60-second SLA may require switching from Claude CLI subprocess to direct API calls (litellm) — budget 1-2 days of additional work; 12-RESEARCH.md Pitfall 3 already identifies this risk and the mitigation strategy
- **Fallback:** Use `litellm` direct API calls instead of CLI subprocess for BOT-06; reduces cold-start from ~10s to <1s

### D3: BOT-05 changelog output quality with real merged PR data — DEFER-12-03

- **What:** Changelog generation produces correctly categorized CHANGELOG entries when run against real merged PRs in a repository with a mix of conventional and non-conventional commit titles
- **How:** Run `bot-changelog` trigger against this repository (Agented) after a set of PRs have been merged; manually review the generated CHANGELOG for correct feat/fix/breaking categorization and completeness
- **Why deferred:** Requires live Claude execution with `gh pr list` access; AI categorization accuracy for non-conforming titles cannot be verified without running Claude; the Agented repo has real merged PRs to use as test data
- **Validates at:** Manual review after Phase 12 is deployed (first changelog run)
- **Depends on:** Deployed Phase 12, authenticated `gh` CLI, merged PRs in target repository
- **Target:** >90% correct categorization for conventional-commit PR titles; reasonable (human-acceptable) AI fallback categorization for non-conforming titles
- **Risk if unmet:** Skill file prompt may need tuning; low risk — output can be reviewed and corrected before committing
- **Fallback:** Manual review and edit of generated CHANGELOG; iterative prompt refinement

### D4: End-to-end bot execution quality for PR-triggered bots — DEFER-12-04

- **What:** BOT-03 (test coverage gaps) and BOT-06 (PR summaries) successfully post meaningful PR comments on real PRs — comments are identifiable as bot-generated, factually accurate, and appropriately concise
- **How:** Open a test PR on a configured repository; observe that both bots trigger, execute, and post comments; manually review comment quality against success criteria
- **Why deferred:** Requires real GitHub webhook events, deployed instance, authenticated gh CLI, and Claude execution — none of which are available in unit testing
- **Validates at:** Integration testing against a test GitHub repository (post-Phase 12 deployment)
- **Depends on:** Deployed Phase 12, GitHub repo with Agented webhook, PR with code changes
- **Target:** PR comment posted within SLA, contains the specified sections (what changed / why / review focus for BOT-06; untested functions table for BOT-03), includes bot identification footer
- **Risk if unmet:** Skill file prompt may need iteration; the `gh pr comment` infrastructure is validated at P7, so failure here isolates to AI output quality
- **Fallback:** Iterative prompt engineering in skill files (no code changes needed); skill files are markdown and can be updated without redeployment

### D5: ExecutionSearchPage UI behavior and search result display — DEFER-12-05

- **What:** The search page loads, accepts queries, displays highlighted results (with `<mark>` tags rendered as visual highlights), and handles empty/error states correctly when running in a real browser against a live backend
- **How:** Manual walkthrough of the `/execution-search` page with a populated FTS5 index; verify search input, result display, trigger filter, loading state, and empty state
- **Why deferred:** Frontend unit tests (Vitest + happy-dom) validate component structure but cannot verify visual rendering of `v-html` with `<mark>` tags, dark theme CSS integration, or actual API calls to the backend
- **Validates at:** Manual UI review after Phase 12 deployment with `just dev-backend` + `just dev-frontend`
- **Depends on:** Running development server with seeded execution logs
- **Target:** Search input responsive, results display within 2 seconds, highlighted terms visible in snippets, sidebar navigation works, empty state message correct
- **Risk if unmet:** CSS dark theme integration issues or `v-html` rendering problems — low risk, fixable with CSS adjustments
- **Fallback:** Add frontend unit tests for component state behavior; adjust CSS if visual issues found

---

## Ablation Plan

**Purpose:** Isolate contribution of key architectural choices to verify they are correct.

### A1: FTS5 porter tokenizer vs. trigram tokenizer for log search

- **Condition:** Change FTS5 tokenizer from `porter unicode61` to `trigram` and re-run P1 (search with "sql injection" query)
- **Expected impact:** Porter tokenizer should handle stemming (e.g., "injected" matches "injection"); trigram may have higher recall for partial matches but slower index build
- **Command:**
  ```bash
  # Modify schema.py temporarily to use trigram tokenizer and re-run P1
  # tokenize='trigram'
  # Compare result counts and relevance ordering
  ```
- **Evidence:** 12-RESEARCH.md Experiment Design — porter vs. trigram tokenizer ablation is explicitly planned; 12-RESEARCH.md recommends `porter unicode61` as the default

### A2: Structured JSON output vs. free-text output for vulnerability scanner (BOT-01)

- **Condition:** Compare skill file output quality when instructed to output structured JSON vs. free-text markdown; check whether `--output-format json` results in parseable structured findings
- **Expected impact:** JSON output should be machine-parseable; free-text requires brittle regex parsing
- **Command:**
  ```bash
  # This ablation requires live Claude execution — classified as deferred verification
  # Run bot-vuln-scan against a test package.json containing lodash@4.17.20 (CVE-2021-23337)
  # Compare: JSON output mode (via --output-format json) vs. markdown mode
  # Target: JSON mode produces parseable findings array; markdown mode requires manual extraction
  ```
- **Evidence:** 12-RESEARCH.md Recommendation 2 (structured JSON output via --output-format json reduces parsing failures from ~15% to <1%)

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Existing test suite | Backend pytest before Phase 12 | ~906 passing tests, 0 failures | v0.1.0 STATE.md (current) |
| Frontend build | vue-tsc + vite build before Phase 12 | 0 TypeScript errors | v0.1.0 STATE.md (current) |
| Frontend tests | Vitest before Phase 12 | ~344 passing tests, 0 failures | v0.1.0 STATE.md (current) |
| FTS5 search latency | SQLite FTS5 with porter tokenizer, <500 entries | <50ms per query expected | 12-RESEARCH.md scaling analysis |
| Manual PR summary | Human writes PR summary | 5-30 minutes per PR | 12-RESEARCH.md Experiment Design |
| Manual vulnerability audit | Human runs npm audit + reviews output | 15-60 minutes per project | 12-RESEARCH.md Experiment Design |
| LIKE search (no FTS5) | Simple text search with LIKE operator | ~30% precision, slow on large tables | 12-RESEARCH.md State of the Art |

---

## Evaluation Scripts

**Location of evaluation code:**
```
# No dedicated eval script directory — evaluations use inline Python commands
# above with isolated_db pattern from conftest.py

# For running the full proxy suite in sequence:
cd /Users/neo/Developer/Projects/Agented

# Sanity checks
cd backend && uv run pytest --tb=short -q           # S6
cd backend && uv run ruff check . && uv run ruff format --check .  # S7
just build                                           # S8

# Proxy checks (run individually per commands in P1-P8 above)
```

**How to run full sanity evaluation:**
```bash
cd /Users/neo/Developer/Projects/Agented/backend
uv run pytest --tb=short -q 2>&1 | tail -5
uv run ruff check . && uv run ruff format --check . && echo "Lint: PASS"
cd .. && just build 2>&1 | tail -5
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: 7 triggers defined | | | |
| S2: FTS5 schema valid SQL | | | |
| S3: ExecutionSearchService importable | | | |
| S4: SpecializedBotService methods present | | | |
| S5: 7 skill files exist (>500 bytes each) | | | |
| S6: Backend tests pass (0 failures) | | | |
| S7: Ruff lint/format clean | | | |
| S8: Frontend build succeeds (0 TS errors) | | | |
| S9: /admin/specialized-bots/status returns 200 | | | |
| S10: /admin/execution-search?q=test returns 200 | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: FTS5 BM25 returns ranked results | >=3 results for "sql injection" on 5-row seed | | | |
| P2: FTS5 sync triggers (INSERT + DELETE) | Index reflects changes immediately | | | |
| P3: Malformed query returns 200, not 500 | HTTP 200, results=[] | | | |
| P4: Trigger filter scopes results | Only matching trigger_id returned | | | |
| P5: 7 triggers seeded with correct sources | All 7 present, correct trigger_source | | | |
| P6: Changelog structural contracts | Skill file refs Conventional Commits; list_merged_prs uses gh+json | | | |
| P7: post_pr_comment graceful on missing gh | Returns False, no exception | | | |
| P8: Search page route + component exist | All 4 file/grep checks pass | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: porter vs. trigram tokenizer | Porter handles stemming better | | |
| A2: JSON vs free-text bot output | JSON parseable, free-text brittle | Deferred to D4 | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-12-01 | FTS5 scale performance (<500ms at 10K+ docs) | PENDING | Production (30+ days uptime) |
| DEFER-12-02 | BOT-06 PR summary <60s SLA | PENDING | GitHub integration testing |
| DEFER-12-03 | BOT-05 changelog quality with real PRs | PENDING | Manual review post-deployment |
| DEFER-12-04 | BOT-03/BOT-06 end-to-end PR comment quality | PENDING | Integration testing with test GitHub repo |
| DEFER-12-05 | ExecutionSearchPage UI rendering and behavior | PENDING | Manual browser walkthrough post-deployment |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM

**Justification:**
- Sanity checks: Adequate — 10 specific checks covering all infrastructure components; all executable without live AI or GitHub access
- Proxy metrics: Partially well-evidenced — FTS5 metrics (P1-P4) are HIGH confidence because search is deterministic and testable; structural/behavioral metrics (P5-P8) are MEDIUM confidence because they verify contracts but not AI output quality
- Deferred coverage: Partial — the 5 deferred items cover the most important quality outcomes (latency SLA, AI output accuracy, UI behavior), but they cannot be addressed until the system is deployed and running

**What this evaluation CAN tell us:**
- Whether the infrastructure exists and is correctly wired (triggers, FTS5 schema, API endpoints, skill files, routes)
- Whether the FTS5 search component works correctly for the BOT-07 natural language search requirement (mechanically testable)
- Whether error handling is correct for external tool failures (gh CLI, osv-scanner)
- Whether the frontend builds and the search page route is registered
- Whether existing tests continue to pass (no regressions)

**What this evaluation CANNOT tell us:**
- Whether bot AI outputs are actually useful (requires live Claude execution — deferred D3, D4)
- Whether BOT-06 meets the 60-second SLA under real conditions (requires GitHub + Claude — deferred D2)
- Whether the vulnerability scanner finds real CVEs in real codebases (requires osv-scanner + live execution — deferred D4)
- Whether the code tour produces actually useful, well-structured walkthroughs (subjective — deferred D4)
- Whether the incident postmortem bot produces complete, accurate documents (requires real incident context — deferred D4)
- Whether the FTS5 search degrades at scale (requires production volume — deferred D1)

**Design note on proxy limitations for AI-powered bots:**

The core evaluation challenge for this phase is that 6 of the 7 bots (all except BOT-07) are primarily implemented as Claude skill files — markdown instruction documents that guide AI behavior. The quality of their output is fundamentally a function of prompt engineering, which cannot be verified mechanically without running the AI. The proxy metrics in this plan verify that the *plumbing* is correct (triggers seeded, skill files present, helper services functional) but explicitly defer judgment about *output quality* to deferred manual evaluations.

This is honest and appropriate for v0.1.0. The skill files can be iterated rapidly (no code changes, no redeployment), so discovering output quality issues at D3/D4 validation time is a low-risk discovery. The infrastructure investments (FTS5 schema, predefined trigger system, SpecializedBotService, search API) are what require careful mechanical verification — and that is what the sanity and proxy tiers cover.

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
