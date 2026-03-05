---
phase: 12-specialized-automation-bots
plan: 01
subsystem: backend-automation-bots
tags: [triggers, fts5, search, predefined-bots]
dependency_graph:
  requires: []
  provides: [predefined-triggers, fts5-search, execution-search-api]
  affects: [execution-logs, trigger-seeding]
tech_stack:
  added: [sqlite-fts5, bm25-ranking]
  patterns: [fts5-content-sync-triggers, static-service-class]
key_files:
  created:
    - backend/app/models/execution_search.py
    - backend/app/services/execution_search_service.py
    - backend/app/routes/execution_search.py
  modified:
    - backend/app/db/triggers.py
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/db/seeds.py
    - backend/app/routes/__init__.py
    - backend/tests/test_github_webhook.py
    - backend/tests/test_trigger_team_integration.py
decisions:
  - FTS5 with porter tokenizer for natural language search over execution logs
  - Content sync via 3 SQLite triggers (INSERT, UPDATE, DELETE) per 12-RESEARCH.md Pitfall 1
  - Migration v72 rebuilds FTS index from existing execution_logs data for existing databases
metrics:
  duration: 11min
  completed: 2026-03-05
---

# Phase 12 Plan 01: Predefined Trigger Definitions and FTS5 Search Infrastructure Summary

Registered 7 new predefined automation bot triggers and built FTS5 full-text search infrastructure with BM25-ranked results and snippet highlighting for the execution log search bot.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add 7 predefined trigger definitions and FTS5 schema | 0597584 | triggers.py, schema.py, migrations.py, seeds.py |
| 2 | Build ExecutionSearchService and search API endpoint | 515e0c5 | execution_search_service.py, execution_search.py (route + model) |

## Implementation Details

### Task 1: Predefined Triggers and FTS5 Schema

Added 7 new bot trigger definitions to `PREDEFINED_TRIGGERS`:
- **bot-vuln-scan** (scheduled weekly, Mon 02:00) -- Dependency Vulnerability Scanner
- **bot-code-tour** (manual) -- Code Tour Generator
- **bot-test-coverage** (github) -- Test Coverage Gap Detector
- **bot-postmortem** (manual) -- Incident Postmortem Assistant
- **bot-changelog** (manual) -- Changelog Generator
- **bot-pr-summary** (github) -- PR Summary
- **bot-log-search** (manual) -- Execution Log Search

Created FTS5 virtual table `execution_logs_fts` with porter tokenizer indexing `stdout_log`, `stderr_log`, and `prompt` columns. Three SQLite sync triggers keep the FTS index automatically synchronized with the `execution_logs` table on INSERT, UPDATE, and DELETE operations.

Updated `seed_predefined_triggers()` to handle `schedule_type`, `schedule_time`, and `schedule_day` columns for both INSERT and UPDATE paths.

### Task 2: ExecutionSearchService and API

Built `ExecutionSearchService` with static `search()` method that:
- Queries FTS5 with MATCH and BM25 ranking via `ORDER BY rank`
- Returns highlighted context snippets using `snippet()` FTS5 function
- Supports optional `trigger_id` filtering
- Gracefully handles malformed FTS5 queries (returns empty list)

API endpoints:
- `GET /admin/execution-search?q=<query>&limit=50&trigger_id=<id>` -- BM25-ranked search results
- `GET /admin/execution-search/stats` -- Index statistics (document count)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated tests for new github trigger count**
- **Found during:** Task 1
- **Issue:** `test_get_triggers_by_trigger_source` expected 1 github trigger (bot-pr-review only), but we added bot-test-coverage and bot-pr-summary. `test_github_dispatch_delegates_to_team` expected 1 orchestration call but got 3.
- **Fix:** Updated test assertions to account for 3 github triggers total
- **Files modified:** tests/test_github_webhook.py, tests/test_trigger_team_integration.py
- **Commit:** 0597584

## Verification

- Backend tests: 1212 passed (1 pre-existing failure in test_post_execution_hooks excluded)
- Frontend build: Passed (vue-tsc + vite)
- Trigger definitions verified: All 9 bot-* triggers present in PREDEFINED_TRIGGER_IDS

## Self-Check: PASSED
