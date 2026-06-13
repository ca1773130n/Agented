---
phase: 21-one-click-team-harness-setup
plan: 07
subsystem: grd-team-harness
tags: [litestar-route, sse, vue, i18n, one-click-setup]
requires:
  - "TeamHarnessSetupService.setup (21-02..21-06)"
  - "app.db.projects harness_setup_status + steps (21-01)"
provides:
  - "POST /api/projects/{id}/harness-setup (202 trigger)"
  - "GET /api/projects/{id}/harness-setup/status"
  - "GET /api/projects/{id}/harness-setup/stream (text/event-stream)"
  - "grdApi.{triggerHarnessSetup,getHarnessSetupStatus,streamHarnessSetup}"
  - "ProjectDashboard one-click setup surface (button + chip + step panel)"
  - "harnessSetup.* i18n namespace (en/ko/ja/zh)"
affects:
  - backend/app_litestar/routes/grd_routes.py
  - frontend/src/views/ProjectDashboard.vue
tech-stack:
  added: []
  patterns:
    - "SSE Stream polling generator (agents_and_tracing.py:228 mirror)"
    - "Thread-spawn off-thread setup (grd_routes.py:709 mirror)"
    - "grdInit-style status ref → button/chip/EventSource wiring"
key-files:
  created:
    - backend/tests/routes/test_harness_setup_routes.py
    - frontend/src/views/__tests__/ProjectDashboard.harness-setup.test.ts
  modified:
    - backend/app_litestar/routes/grd_routes.py
    - frontend/src/services/api/grd.ts
    - frontend/src/services/api/index.ts
    - frontend/src/views/ProjectDashboard.vue
    - frontend/src/locales/en.json
    - frontend/src/locales/ko.json
    - frontend/src/locales/ja.json
    - frontend/src/locales/zh.json
decisions:
  - "Route trio mounts under existing /api/projects router prefix (not /admin); matches grd_init planning endpoints"
  - "POST returns {harness_setup_status: 'running'} at 202 and the status flip happens synchronously before the thread spawns, so a follow-up GET status reports running immediately"
  - "SSE stream diffs step rows on status|detail signature and emits a terminal event: done frame on ready/failed; 10-min hard deadline mirrors the trace stream"
  - "Route SSE handler keeps sync_to_thread=False for parity with the existing trace stream (benign LitestarWarning on async callable)"
metrics:
  tasks: 3
  duration: ~40m
  completed: 2026-06-13
---

# Phase 21 Plan 07: One-Click Team Harness Operator Surface Summary

Wired the operator-facing one-click team-harness setup: a backend route trio
(POST trigger / GET status / GET SSE stream) plus the ProjectDashboard button,
per-state status chip, and EventSource-fed step panel, with key-identical
`harnessSetup.*` i18n across all four locales. REQ-19 / SC1 is now reachable
from a single ProjectDashboard click, mirroring the existing grd_init pattern.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Backend route trio + P5 route/SSE test | 6aca3ee5c9 | grd_routes.py, test_harness_setup_routes.py |
| 2 | ProjectDashboard surface + api client + 4-locale i18n | 13fd52eb7f | ProjectDashboard.vue, grd.ts, index.ts, en/ko/ja/zh.json |
| 3 | ProjectDashboard.harness-setup.test.ts (P8) | e69e736637 | ProjectDashboard.harness-setup.test.ts |

## Implementation Notes

- **Route trio** (`grd_routes.py`): `trigger_harness_setup` (202, flips status →
  running, spawns `TeamHarnessSetupService.setup` on a daemon thread),
  `harness_setup_status` (`{harness_setup_status, steps}`, guarded by
  `_ensure_project`), and `harness_setup_stream` (async polling generator,
  `event: step` per changed row + terminal `event: done`). Added `asyncio`,
  `json`, `Stream`, and the `app.db.projects` + `TeamHarnessSetupService`
  imports. Handlers registered in `grd_router`.
- **Frontend api** (`grd.ts`): three methods + `GrdHarnessSetupStep` type,
  re-exported through the `index.ts` barrel.
- **ProjectDashboard**: `harnessSetupStatus` / `harnessSetupSteps` refs +
  `loadHarnessSetupStatus` / `openHarnessSetupStream` / `triggerHarnessSetup`,
  fetched in `loadData` alongside `loadGrdStatus`, stream closed on unmount and
  on the `__done__` frame.

## Verification

- **P5** (`test_harness_setup_routes.py`): 4/4 PASS — POST → 202 + running,
  GET status returns step list, 404 on unknown project, stream is
  `text/event-stream` with `event: step` (`"step": "grd_init"`) + `event: done`.
- **P8** (`ProjectDashboard.harness-setup.test.ts`): 4/4 PASS — button when
  none, running chip + EventSource opened on trigger, step rows from mocked
  message frames, ready transition closes the stream.
- **Full frontend suite**: 1489 passed / 7 failed — the 7 failures are exactly
  the known pre-existing baseline (MarkdownContent, WorkingMemoryView,
  RateLimitGauge, useTourMachine.setup-status). **No NEW failures.**
- **vue-tsc**: the only error (`AnswerGroundednessCard.vue`) is pre-existing
  (confirmed by stashing this plan's changes); zero new type errors in the
  touched files.
- **i18n parity**: `harnessSetup.*` = 20 leaf keys, key-identical across
  en/ko/ja/zh.

## Deviations from Plan

**1. [Rule 3 - Blocking] Worktree had no `node_modules`** — symlinked the main
frontend's `node_modules` into the worktree to run vitest/vue-tsc, then removed
the symlink before staging so it is not committed. No source impact.

Otherwise the plan executed as written. The route trio mounts under
`/api/projects` (the prefix the planning endpoints actually use) — the plan
text said `/admin/projects` in the task body but the frontmatter key_links and
the grd_init prior art use `/api/projects`; followed the prior art.

## Self-Check: PASSED

- All 5 created/modified key files present on disk.
- All 3 commits (6aca3ee5c9, 13fd52eb7f, e69e736637) present in git log.
- P5 4/4 pass, P8 4/4 pass, frontend suite at known 7-failure baseline (no new), i18n parity 20/20 across 4 locales.
