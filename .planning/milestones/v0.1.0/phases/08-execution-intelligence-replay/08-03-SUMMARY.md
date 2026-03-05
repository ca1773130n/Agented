---
phase: 08-execution-intelligence-replay
plan: 03
subsystem: api, services, database
tags: [sse, collaborative, presence, comments, sqlite, threading]

requires:
  - phase: 08-01
    provides: ExecutionLogService SSE fan-out pattern (_broadcast, _subscribers)
provides:
  - CollaborativeViewerService with presence tracking and inline commenting
  - viewer_comments SQLite table with CRUD operations
  - 7 API endpoints for collaborative execution viewing
affects: [frontend collaborative viewer UI, execution detail page]

tech-stack:
  added: []
  patterns: [ephemeral in-memory presence with SSE broadcast, persistent comments with line-number anchoring]

key-files:
  created:
    - backend/app/services/collaborative_viewer_service.py
    - backend/app/models/collaborative.py
    - backend/app/db/viewer_comments.py
    - backend/app/routes/collaborative.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/db/__init__.py
    - backend/app/services/execution_log_service.py
    - backend/app/routes/__init__.py

key-decisions:
  - "Viewer presence is ephemeral in-memory state (not persisted to SQLite) per 08-RESEARCH.md"
  - "Comments anchor to stdout line numbers (immutable once execution completes) per 08-RESEARCH.md Open Question 3"
  - "Heartbeats are silent (update last_seen only, no broadcast) to minimize SSE traffic"
  - "cleanup_stale_viewers() wired into finish_execution() to prevent Queue subscriber memory leaks"

patterns-established:
  - "Ephemeral presence tracking: class-level Dict with threading.Lock, heartbeat-based staleness detection"
  - "Comment persistence pattern: DB CRUD + SSE broadcast for real-time delivery with historical retrieval"

duration: 10min
completed: 2026-03-05
---

# Phase 8 Plan 3: Collaborative Viewer Summary

**Collaborative execution viewer with real-time presence tracking for 2+ simultaneous viewers and persistent inline commenting anchored to stdout line numbers**

## Performance

- **Duration:** 10 min
- **Started:** 2026-03-05T07:14:51Z
- **Completed:** 2026-03-05T07:25:09Z
- **Tasks:** 2/2
- **Files modified:** 9

## Accomplishments

- CollaborativeViewerService tracks viewer presence with join/leave/heartbeat lifecycle, supporting 2+ simultaneous viewers per execution
- Inline comments persisted to viewer_comments SQLite table with stdout line number anchoring, surviving server restarts
- All presence and comment events broadcast via existing SSE fan-out pattern (no WebSockets introduced)
- Stale viewer cleanup (30s heartbeat interval, 2 miss threshold) wired into finish_execution() to prevent memory leaks
- 7 API endpoints registered under /admin with collaborative tag in Swagger UI

## Task Commits

Each task was committed atomically:

1. **Task 1: Collaborative viewer service with presence tracking and comment persistence** - `feeeb3c` (feat)
2. **Task 2: Collaborative viewer API endpoints** - `8b7401b` (feat)

## Files Created/Modified

- `backend/app/services/collaborative_viewer_service.py` - Core service with presence tracking, heartbeat cleanup, and comment broadcasting
- `backend/app/models/collaborative.py` - Pydantic v2 models for ViewerInfo, PresenceEvent, InlineComment, CommentEvent
- `backend/app/db/viewer_comments.py` - CRUD for viewer_comments table (create, get, delete, list by execution/line)
- `backend/app/routes/collaborative.py` - APIBlueprint with 7 endpoints for presence and comment management
- `backend/app/db/schema.py` - Added viewer_comments table with execution_id and (execution_id, line_number) indexes
- `backend/app/db/migrations.py` - Migration v66 for viewer_comments table
- `backend/app/db/__init__.py` - Re-exported viewer_comments CRUD functions
- `backend/app/services/execution_log_service.py` - Wired cleanup_stale_viewers() into finish_execution()
- `backend/app/routes/__init__.py` - Registered collaborative_bp with rate limiting

## Decisions Made

- Viewer presence kept ephemeral in-memory (not SQLite) per 08-RESEARCH.md recommendation -- accepts that presence is lost on restart
- Comments anchor to stdout line numbers which are immutable once execution completes (Open Question 3 resolution)
- Heartbeats are silent (no SSE broadcast) -- only update last_seen timestamp to minimize traffic at ~1 msg/30s/viewer
- Stale viewer cleanup invoked from finish_execution() with lazy import to avoid circular dependency
- No separate SSE endpoint for collaborative viewing -- viewers subscribe to existing execution stream with new event types

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pre-existing test failure in test_post_execution_hooks.py::test_import_error_handled_gracefully (NotificationService now exists, making the "not importable" test invalid). Not caused by this plan's changes -- confirmed by running test against pre-change code.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Backend collaborative viewing infrastructure complete
- Frontend can now implement collaborative UI by subscribing to existing SSE stream and calling the 7 new endpoints
- Comments API enables both live and historical comment viewing

## Self-Check: PASSED

---
*Phase: 08-execution-intelligence-replay*
*Completed: 2026-03-05*
