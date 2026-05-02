# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-21)

**Core value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard
**Current focus:** Phase 5 — Form Field Guidance
**Primary hypothesis:** A guided onboarding tour can bring new users from zero to first bot execution in under 3 minutes

## Current Position

Phase: 4 of 10 (Core Step Content) — **COMPLETE**
Phase 1: COMPLETE
Phase 2: COMPLETE
Phase 3: COMPLETE
Plan: phase-4/04-01 shipped
Status: Phase 5 ready to plan
Last activity: 2026-05-03 — Phase 4 plan 04-01 setup-status guards

Phase 4 deliverables (plan 04-01):
- OB-17 ✓ (workspace step) — `[data-tour="workspace-root"]` already in
  GeneralSettings.vue:187, route + target wired in tourSteps.ts; verified.
- OB-18 ✓ (4 backend substeps with auto-skip-completed) — wired
  `useTourMachine.initActor()` to GET /health/setup-status and walk past
  completed steps via synthetic SKIP events (`autoSkipCompletedSteps`).
  Closes the deferred Phase 1 followup.
- OB-19 (form field guidance) — Phase 4's job is to leave the user on the
  backend page with the Add Account button highlighted. Auto-discovery
  is Phase 5.
- OB-20 ✓ (token monitoring) — `[data-tour="token-monitoring"]` in
  GeneralSettings.vue:247.
- OB-21 ✓ (harness verification) — `[data-tour="harness-plugins"]` in
  HarnessSettings.vue:122.
- 11 new frontend tests covering fetchSetupStatus + setupStatusToCompleted +
  autoSkipCompletedSteps walker (granular per-backend + full walk +
  no-op cases).

Phase 1 status (verified during Phase 2 discovery):
- The XState machine + composable shipped in earlier "tour wave" commits
  (`src/machines/tourMachine.ts`, `src/composables/useTourMachine.ts`).
- Phase 1 plan 01-01's frontend half (`src/tour/`) was duplicate code; deleted.
- Phase 1 plan 01-01's backend half — `GET /health/setup-status` endpoint —
  is shipped and tested. Wiring `useTourMachine` to consume it (instead of
  the stubbed `() => false` guards) is a Phase 1 follow-up captured in the
  Phase 2 plan doc's "Out of scope" section.

Phase 3 deliverables (plan 03-01):
- OB-01 ✓ (welcome page with bento grid + CTA — pre-existing; verified the
  router guard prevents dashboard flash)
- OB-02 ✓ (keygen + monospace key display + copy button + warning copy —
  pre-existing; added unit tests for warning visibility + clipboard write)
- OB-03 ✓ (smooth transition; tightened phase-fade enter 250ms + leave 150ms
  = 400ms total to fit comfortably under the 500ms criterion)
- Stale `v0.4.0` version label in welcome header bumped to `v0.5.0`
- 3 new unit tests in `WelcomePage.test.ts` (warning visible, copy →
  clipboard, transition class applied)

Phase 2 deliverables (plan 02-01):
- OB-09 ✓ (TourSpotlight box-shadow dimming — pre-existing)
- OB-10 ✓ (TourOverlay ResizeObserver + scroll listener — pre-existing)
- OB-11 ✓ (element-adaptive padding + border-radius via
   `frontend/src/components/tour/spotlightGeometry.ts`)
- OB-12 ✓ (TourTooltip @floating-ui/vue offset/flip/shift/arrow + autoUpdate — pre-existing)
- OB-13 ✓ (TourCompletionScreen hardcoded colors replaced with
   `--tour-overlay-dim`, `--tour-success-pulse-from/to`)
- OB-14 ✓ (Vue Transition + 200ms CSS — pre-existing)
- OB-15 ✓ (pulsing glow with `prefers-reduced-motion` — pre-existing)
- OB-16 ✓ (TourProgressBar — pre-existing)
- 13 new frontend tests (spotlightGeometry + TourSpotlight cases)

Progress: [##--------] 20%

## Current Baseline

| Metric | Value | Target | Delta | Phase |
|--------|-------|--------|-------|-------|
| Tour completion time | N/A | < 3 min | - | - |
| Welcome page load | N/A | < 200ms | - | - |
| Step transition time | N/A | < 300ms | - | - |
| State machine branch coverage | 0% | >= 90% | - | Phase 10 |

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
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

## Accumulated Context

### Decisions

- Roadmap: Drop driver.js, use XState v5 + Floating UI + focus-trap
- Roadmap: Existing WelcomePage.vue is approved — build on it, do not rewrite
- Roadmap: Backend needs `app_meta` table with `instance_id` for DB reset detection

### Pending Todos

None yet.

### Blockers/Concerns

- XState v5 + `@xstate/vue` integration needs early spike (snapshot serialization format for persistence)
- `app_meta.instance_id` endpoint must be accessible before auth (runs during tour boot)

## Session Continuity

Last session: 2026-03-21
Stopped at: Roadmap created, ready to plan Phase 1
Resume file: None
