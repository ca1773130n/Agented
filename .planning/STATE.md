# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-21)

**Core value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard
**Current focus:** Phase 4 — Core Step Content
**Primary hypothesis:** A guided onboarding tour can bring new users from zero to first bot execution in under 3 minutes

## Current Position

Phase: 4 of 10 (Core Step Content)
Plan: 2 of 2 in current phase
Status: Phase Complete
Last activity: 2026-03-22 — Completed 04-02-PLAN.md

Progress: [####------] 40%

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
- Total plans completed: 9
- Average duration: 7min
- Total execution time: 1.02 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-backend-state-machine-foundation | 2/2 | 25min | 13min |
| 02-visual-layer | 2/2 | 9min | 5min |
| 03-welcome-flow-tour-entry | 1/1 | 7min | 7min |
| 04-core-step-content | 2/2 | 12min | 6min |
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
- 02-01: CSS custom property padding reads from --tour-spotlight-padding with fallback to 8px
- 02-01: Glow animation uses opacity-based box-shadow per Research Pitfall 6
- 02-01: Accent color switched from indigo to --accent-cyan to match app design language
- 02-01: Static analysis test pattern: read .vue source, extract style block, grep for hardcoded values
- 02-02: Virtual Element Bridge pattern: computed returns fresh object per targetRect change for Floating UI reactivity
- 02-02: Middleware chain: offset(12) + flip() + shift({padding:8}) + arrow() for viewport-safe tooltip positioning
- 02-02: Two-phase transition on position change: fade out, recompute, fade in to prevent tooltip flicker
- 02-02: TourProgressBar uses filter:brightness(1.15) for hover instead of hardcoded color value
- 03-01: TOUR_STEP_META flat Record maps machine state names to TourOverlay display metadata
- 03-01: Computed bridge layer in App.vue translates machine state to StepLike interface
- 03-01: Direct navigation from WelcomePage to /settings#general (no /?tour=start redirect)
- 03-01: totalTourSteps=3 hardcoded (workspace, backends, verification) pending Phase 4
- 04-01: Monitoring step targets token-monitoring card on /settings#general
- 04-01: Verification step changed to harness-plugins on /settings#harness (not /plugins)
- 04-01: OpenCode substep targets opencode-info note (add-account-btn hidden for OpenCode)
- 04-01: totalTourSteps updated to 4 (workspace, backends, monitoring, verification)
- 04-02: No code changes needed -- 04-01 already updated all test files for monitoring state

### Pending Todos

None yet.

### Blockers/Concerns

- RESOLVED: XState v5 + `@xstate/vue` integration — implemented via manual createActor + shallowRef (01-02)
- RESOLVED: `app_meta.instance_id` endpoint accessible before auth (implemented in 01-01)

## Session Continuity

Last session: 2026-03-22
Stopped at: Completed 04-02-PLAN.md (Phase 04 complete)
Resume file: None
