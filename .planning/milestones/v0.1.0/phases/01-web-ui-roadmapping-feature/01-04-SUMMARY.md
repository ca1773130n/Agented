---
phase: 01-web-ui-roadmapping-feature
plan: 04
status: completed
subsystem: backend/services
tags: [grd, auto-init, session-sync, background-tasks]
decisions:
  - "Session-completion sync runs synchronously before SSE broadcast to prevent race condition"
  - "Auto-init uses polling loop (2s interval, 10min timeout) to wait for PTY session completion"
  - "Clone-wait thread polls DB for clone_status before triggering auto-init"
  - "GRD sync guard checks grd_init_status to skip non-GRD sessions (avoids overhead)"
  - "project_id lookup in _handle_session_exit queries DB since session_info is in-memory only"
metrics:
  tests_before: 911
  tests_after: 911
  files_modified: 4
  lines_added: ~281
key_files:
  backend/app/services/grd_planning_service.py: "auto_init_project(), _run_init_session()"
  backend/app/services/grd_sync_service.py: "sync_on_session_complete()"
  backend/app/services/project_session_manager.py: "GRD sync hook in _handle_session_exit()"
  backend/app/routes/projects.py: "Auto-init trigger in create_project()"
---

# Plan 04 Summary: Backend Auto-Init & Session-Completion Sync

## What was built

1. **GrdPlanningService.auto_init_project()** -- Background GRD initialization after project creation. Runs in a daemon thread. Two paths:
   - If `.planning/` exists: syncs directly to DB via GrdSyncService
   - If no `.planning/`: runs `map-codebase` then `new-project` via sequential PTY sessions

2. **GrdPlanningService._run_init_session()** -- Helper that creates a PTY session via the direct execution handler, polls for completion every 2s with 10-minute timeout, returns success/failure.

3. **GrdSyncService.sync_on_session_complete()** -- Syncs `.planning/` files to DB after any planning session completes. Resolves project local_path, checks for `.planning/` directory, delegates to `sync_project()`.

4. **Session-completion hook in ProjectSessionManager._handle_session_exit()** -- Inserted before the SSE `complete` broadcast. Guarded by `grd_init_status` check (only runs for projects with `initializing` or `ready` status). Also calls `GrdPlanningService.unregister_session()` for cleanup.

5. **Auto-init trigger in create_project() route** -- Two cases:
   - `local_path` provided: triggers `auto_init_project()` immediately
   - `github_repo` provided: spawns background thread that waits for clone completion, then triggers init
   - Response includes `grd_init_status` field

## Key integration points

- `GrdPlanningService.auto_init_project()` -> `GrdSyncService.sync_project()` (after init sessions complete)
- `GrdPlanningService.auto_init_project()` -> `update_project(grd_init_status=...)` (status transitions)
- `ProjectSessionManager._handle_session_exit()` -> `GrdSyncService.sync_on_session_complete()` (before broadcast)
- `projects.py create_project()` -> `GrdPlanningService.auto_init_project()` (post-creation trigger)
