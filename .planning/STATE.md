# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-21)

**Core value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard
**Current focus:** Phase 1 — Backend + State Machine Foundation
**Primary hypothesis:** A guided onboarding tour can bring new users from zero to first bot execution in under 3 minutes

## Current Position

Phase: 10 of 10 (Integration Testing)
Plan: 3 of 4 in current phase
Status: In Progress
Last activity: 2026-03-22 — Completed 10-03-PLAN.md

Progress: [####------] 18%

## Current Baseline

| Metric | Value | Target | Delta | Phase |
|--------|-------|--------|-------|-------|
| Tour completion time | N/A | < 3 min | - | - |
| Welcome page load | N/A | < 200ms | - | - |
| Step transition time | N/A | < 300ms | - | - |
| State machine branch coverage | 0% | >= 90% | 5% | Phase 10 |
| useTourMachine branch coverage | 0% | >= 90% | 5% | Phase 10 |

**Last evaluated:** Not yet
**Trend:** Not enough data

## Pending Validations

| From Phase | Validation | Resolve By | Priority |
|-----------|-----------|------------|----------|
| Phase 2 | Full visual regression across all step types | Phase 10 | Medium |
| Phase 4 | End-to-end tour flow with real backend accounts | Phase 10 | High |
| Phase 6 | Keyboard navigation through complete tour | Phase 10 | Medium |
| Phase 8 | Screen reader compatibility validation | Phase 10 | Medium |

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 10min
- Total execution time: 0.55 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-backend-state-machine-foundation | 2/2 | 25min | 13min |
| 10-integration-testing | 3/4 | 13min | 4min |

## Accumulated Context

### Decisions

- Roadmap: Drop driver.js, use XState v5 + Floating UI + focus-trap
- Roadmap: Existing WelcomePage.vue is approved — build on it, do not rewrite
- Roadmap: Backend needs `app_meta` table with `instance_id` for DB reset detection
- 01-01: Used SQLite hex(randomblob()) for UUID — no Python uuid dependency in SQL
- 01-01: XState v5 setup() API with string-referenced guards for type safety
- 01-01: backends is hierarchical state; parent NEXT handles transition to verification
- 01-02: Singleton XState actor pattern — shared across components, survives route changes
- 01-02: Async guard checks in composable, not machine — keeps tourMachine.ts pure
- 01-02: Toast z-index conflict (hardcoded 10000 = --z-tour-overlay) deferred to Phase 7
- 10-01: Pure actor testing with createActor — no Vue, no DOM, no mocks
- 10-01: Guard override via machine.provide() for SKIP_ALL testing
- 10-02: vi.resetModules + dynamic import pattern for singleton composable testing
- 10-02: getSnapshotAtState helper creates valid XState snapshots for persistence tests
- 10-02: Mutable mockApiKey for testing X-API-Key header inclusion
- 10-03: Tour fixture extends base.ts (not @playwright/test) to inherit global API mocks
- 10-03: Accessibility tests use graceful degradation — document gaps rather than hard-fail
- 10-03: Instance-id mismatch documented as useTour limitation (only useTourMachine checks it)

### Pending Todos

None yet.

### Blockers/Concerns

- RESOLVED: XState v5 + `@xstate/vue` integration — implemented via manual createActor + shallowRef (01-02)
- RESOLVED: `app_meta.instance_id` endpoint accessible before auth (implemented in 01-01)

## Session Continuity

Last session: 2026-03-22
Stopped at: Completed 10-03-PLAN.md
Resume file: None
