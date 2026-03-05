---
phase: 11-enterprise-integrations-governance
plan: 05
title: "GitOps Sync Engine"
subsystem: backend
tags: [gitops, sync, config-as-code, yaml, git]
dependency_graph:
  requires: ["11-03 (config export/import with upsert)"]
  provides: ["GitOps repo management", "Automated config sync from git", "Conflict detection"]
  affects: ["trigger management", "audit trail"]
tech_stack:
  added: ["git subprocess calls", "content hashing for conflict detection"]
  patterns: ["GitOps git-wins policy", "polling via APScheduler", "deferred imports"]
key_files:
  created:
    - backend/app/db/gitops.py
    - backend/app/services/gitops_sync_service.py
    - backend/app/routes/gitops.py
    - backend/app/models/gitops.py
    - backend/tests/test_gitops.py
    - backend/app/services/config_export_service.py
    - backend/app/models/config_export.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/db/__init__.py
    - backend/app/routes/__init__.py
decisions:
  - "Git-wins conflict resolution: when both DB and Git changed, Git version is applied with warning logged"
  - "Content hashing (SHA-256) for change detection instead of timestamps"
  - "Deferred import of config_export_service in sync to avoid circular imports"
  - "Local clone cache under backend/.gitops-cache/{repo_id}/ (filesystem, not DB)"
  - "Brought in config_export_service.py from 11-03 worktree as dependency (Rule 3 auto-fix)"
metrics:
  duration: "8min"
  completed: "2026-03-05"
---

# Phase 11 Plan 05: GitOps Sync Engine Summary

GitOps sync engine that watches configured git repositories for YAML trigger configurations and automatically applies changes to the database, with content-hash conflict detection and git-wins resolution policy.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | GitOps database layer and sync service | 628ee5b | gitops.py, gitops_sync_service.py, schema.py, migrations.py |
| 2 | GitOps routes and tests | 10766a1 | routes/gitops.py, models/gitops.py, test_gitops.py |

## Implementation Details

### Database Layer
- **gitops_repos** table: stores watched repository configs (URL, branch, config path, poll interval, last sync state)
- **gitops_sync_log** table: append-only history of sync operations with file counts and status
- Migration v57 adds both tables with proper indexes and foreign keys
- CRUD functions in `db/gitops.py` with gop- prefixed IDs

### Sync Engine (GitOpsSyncService)
- `sync_repo(repo_id, dry_run=False)`: Main sync method
  - Clones (first time) or fetches+resets (subsequent) via subprocess git calls
  - Skips sync if HEAD SHA unchanged from last_commit_sha
  - Scans `config_path/*.yaml` and `*.yml` files
  - Compares git config hash vs DB export hash (SHA-256)
  - Applies changes via `import_trigger(config_str, upsert=True)` -- upsert prevents duplicates
  - Detects conflicts (both sides changed) and logs warning; Git version wins
  - Updates sync state and creates sync log entry
- `start_polling()` / `stop_polling()`: APScheduler job management
- `init()`: Called from create_app() to start polling on server start

### API Routes
- `POST /admin/gitops/repos` -- create watched repo
- `GET /admin/gitops/repos` -- list all repos
- `GET /admin/gitops/repos/<id>` -- repo detail
- `PUT /admin/gitops/repos/<id>` -- update config
- `DELETE /admin/gitops/repos/<id>` -- remove repo
- `POST /admin/gitops/repos/<id>/sync` -- trigger manual sync
- `POST /admin/gitops/repos/<id>/sync?dry_run=true` -- dry-run preview
- `GET /admin/gitops/repos/<id>/logs` -- sync history

### Test Coverage
26 tests covering:
- DB CRUD (8 tests): create, get, list, update, delete, sync state, sync logs
- Sync service (8 tests): new config detection, skip unchanged, upsert updates, dry-run, conflict detection, disabled repo, nonexistent repo, sync log creation
- Routes (10 tests): all CRUD endpoints, sync trigger, dry-run sync, sync logs, error cases

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing config_export_service.py dependency**
- **Found during:** Task 1
- **Issue:** Plan references `ConfigExportService.import_trigger(upsert=True)` from Plan 11-03, but that code exists in a sibling worktree (agent-a2b9899c) not yet merged
- **Fix:** Copied config_export_service.py and config_export.py model from the 11-03 worktree as a direct dependency
- **Files added:** backend/app/services/config_export_service.py, backend/app/models/config_export.py
- **Commit:** 628ee5b

## Verification Results

- 26/26 gitops tests pass
- 966/966 total backend tests pass (zero regressions)
- Frontend build succeeds (vue-tsc + vite)

## Self-Check: PASSED
