---
phase: 20-grd-frontend-wiring
plan: 02
subsystem: frontend/api-client
tags: [grd, research, harness, api-client, frontend, REQ-15, REQ-16]
requires:
  - 20-01 — five /api/projects/{id}/research/* routes (route contracts)
  - client.ts apiFetch + createAuthenticatedEventSource
  - harness_evolution.py /admin routes (fixed contracts — not modified)
  - grd_routes.py 16 GRD CLI-wrapper routes (fixed contracts — not modified)
provides:
  - researchApi (5 methods incl. SSE streamResearch)
  - grdHarnessApi (16 GRD routes + 11 /admin harness routes)
  - barrel re-exports of both + their types
affects:
  - frontend/src/services/api/index.ts
tech-stack:
  added: []
  patterns: [per-domain-api-module, apiFetch-path-method-body, admin-base-routing, generic-session-sse-reuse]
key-files:
  created:
    - frontend/src/services/api/research.ts
    - frontend/src/services/api/research.test.ts
    - frontend/src/services/api/grdHarness.ts
    - frontend/src/services/api/grdHarness.test.ts
  modified:
    - frontend/src/services/api/index.ts
decisions:
  - "Admin auth = same apiFetch credentials (X-API-Key + bearer/cookie + CSRF); Group B is distinguished ONLY by the /admin base path, which the global ApiKey middleware gates — no special admin header exists in client.ts"
  - "research SSE reuses the generic /sessions/{id}/output stream URL (grdApi.streamSession), not a research-specific endpoint (per 20-01)"
  - "[Rule 1] renamed research ListThreadsResponse -> ResearchThreadsResponse to clear a barrel duplicate-identifier collision"
metrics:
  duration: ~16min
  completed: 2026-06-13
---

# Phase 20 Plan 02: GRD Frontend API Modules Summary

Two new per-domain api-client modules give every phase-20 UI surface (plans
20-03/20-04) a typed, fully-tested contract over the autoresearch + life-harness
backends — without touching any existing api module or backend route.

## What shipped

### `research.ts` — `researchApi` (REQ-15 plumbing)

The contract 20-03 consumes:

| Method | Route | Returns |
|--------|-------|---------|
| `startResearch(projectId, question, opts?)` | POST `/api/projects/{id}/research/start` | `{ session_id }` |
| `resumeThread(projectId, threadId, opts?)` | POST `/api/projects/{id}/research/{threadId}/resume` | `{ session_id }` |
| `listThreads(projectId)` | GET `/api/projects/{id}/research/threads` | `{ threads: ResearchThread[] }` |
| `getThread(projectId, threadId)` | GET `/api/projects/{id}/research/threads/{threadId}` | `ResearchThreadBundle` (None-safe thread/hypotheses/finding) |
| `streamResearch(projectId, sessionId, options?)` | SSE `/api/projects/{id}/sessions/{sid}/stream` | `AuthenticatedEventSource` |

`opts` (`{ max_iterations?, no_gates? }`) is appended to the body only when
provided. `streamResearch` returns an EventSource directly (not a Promise),
mirroring `grdApi.streamSession`, because research reuses the generic session SSE.

### `grdHarness.ts` — `grdHarnessApi` (REQ-16 plumbing)

**Group A — 16 GRD routes** (`/api/projects/{id}/grd/*`, X-API-Key):
`getHealth, think, addDeadEnd, promoteDeadEnds, listDeadEnds, getGenome,
snapshotGenome, listGenomeSnapshots, latestGenomeSnapshot, verifyMechanical,
listPhaseReflections, verdictCounts, startEvolve, listEvolveRuns, getEvolveRun,
stopEvolveRun`.

**Group B — 11 harness-evolution routes** (`/admin/*`, admin-gated):
`getAutonomy, setAutonomy, listProjectRounds, listAllRounds, getRoundDetail,
getRoundImpact, approveRound, abortRound, revertRound, listSharedForge,
adoptShared`. `setAutonomy` wraps the body as `{ policy }` (matches
`set_autonomy_config`); `revertRound`/`abortRound` send `{ force }`/`{ reason }`
only when set.

### `index.ts` — barrel

`researchApi`, `grdHarnessApi`, and their types re-exported alongside `grdApi`
so `import { researchApi, grdHarnessApi } from '../services/api'` resolves.

## Admin-auth resolution (the §2 gotcha)

20-RESEARCH flagged that Group B hits `/admin` and "must carry admin auth".
Verified against `client.ts`: `apiFetch` already injects **the same**
credentials on every call — `X-API-Key` (sessionStorage), the HttpOnly
session cookie + `Authorization: Bearer` (legacy), and `X-CSRF-Token` on
mutating methods. The `/admin` Litestar router is gated by that same global
ApiKey/bearer middleware; there is **no separate admin header** in the client.
So Group B is correctly authed purely by routing to the `/admin` base path
(Group A goes to `/api/projects/...`). Tests explicitly assert every Group B
method's URL starts with `/admin/`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Barrel duplicate-identifier collision**
- **Found during:** Task 3 (vue-tsc S1 gate)
- **Issue:** `research.ts` exported `ListThreadsResponse`, which already exists
  elsewhere in the barrel — `vue-tsc` failed with TS2300 (Duplicate identifier).
- **Fix:** Renamed to `ResearchThreadsResponse` (type + usage + barrel export).
- **Files modified:** `research.ts`, `index.ts`
- **Commit:** 9e5a514163

(Also installed `frontend/node_modules` — this fresh worktree had none; not a
code change.)

## Experiment Results

### Parameters
| Parameter | Value |
|-----------|-------|
| modules added | research.ts, grdHarness.ts |
| methods (research) | 5 |
| methods (grdHarness) | 27 (16 Group A + 11 Group B) |
| verification_level | proxy |

### Results
| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| research.test.ts | api-tests green | 0 fail | 7 passed | PASS |
| grdHarness.test.ts | api-tests green | 0 fail | 29 passed | PASS |
| bot-health.test.ts (regression) | green | green | passed | PASS |
| vue-tsc (S1) | 1 pre-existing err | no NEW err | 1 err (AnswerGroundednessCard, PR #212) | PASS |
| barrel import smoke (S4) | n/a | exports resolve | resolves | PASS |

### Analysis
Both new suites green (36 tests); the baseline api test still passes. vue-tsc
reports exactly one error — the documented pre-existing `AnswerGroundednessCard.vue`
TS2345 (STATE.md / PR #212), in a file this plan did not touch. Level 3 (real
network calls against a live Litestar server) is deferred per the plan
(DEFER-20-02 walkthrough).

### Artifacts
- `frontend/src/services/api/research.ts`, `research.test.ts`
- `frontend/src/services/api/grdHarness.ts`, `grdHarness.test.ts`
- `frontend/src/services/api/index.ts` (barrel)

## Self-Check: PASSED
- FOUND: frontend/src/services/api/research.ts
- FOUND: frontend/src/services/api/research.test.ts
- FOUND: frontend/src/services/api/grdHarness.ts
- FOUND: frontend/src/services/api/grdHarness.test.ts
- FOUND: frontend/src/services/api/index.ts (researchApi + grdHarnessApi exports)
- FOUND commits: 8b9796276a, a6366eca07, 9e5a514163
