# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-21)

**Core value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard
**Current focus:** Phase 9 — Post-Tour Experience
**Primary hypothesis:** A guided onboarding tour can bring new users from zero to first bot execution in under 3 minutes

## Current Position

Phase: 8 of 10 (Accessibility) — **COMPLETE**
Phase 1: COMPLETE
Phase 2: COMPLETE
Phase 3: COMPLETE
Phase 4: COMPLETE
Phase 5: COMPLETE
Phase 6: COMPLETE
Phase 7: COMPLETE
Plan: phase-8/08-01 shipped
Status: Phase 9 ready to plan
Last activity: 2026-05-03 — Phase 8 plan 08-01 accessibility

Phase 8 deliverables (plan 08-01):
- OB-36 ✓ (reduced motion — closed gap by adding @media block to
  TourOverlay disabling `.spinner-icon` animation + `.tour-dim-fallback`
  transition; added presence tests across all 4 tour components)
- OB-37 ✓ (focus trap — already wired via useFocusTrap; added a
  source-import regression guard in TourTooltip.test.ts)
- OB-38 ✓ (ARIA live — pre-satisfied + tested by earlier waves)
- OB-39 ✓ (keyboard-only completion — added tabindex sanity test for
  action-row + confirm-row buttons; full E2E deferred to Phase 10)
- 7 new frontend tests (4 reduced-motion presence + 1 OB-37 wiring +
  2 OB-39 reachability)

Phase 7 deliverables (plan 07-01):
- OB-40 ✓ (5s "page is slow" fallback with Skip/Retry — pre-existing,
  tested)
- OB-41 ✓ (3s element-not-found fallback — pre-existing; this plan
  narrows the MutationObserver scope from `document.body` to
  `#main-content` to satisfy the "scoped to route's root element"
  clause, with a `document.body` fallback for the welcome screen
  layout that has no `<main>`)
- OB-42 ✓ (route prefetch — pre-existing in
  `prefetchTourRoutes()`; this plan adds the missing test asserting
  it settles without throwing)
- OB-44 ✓ (modal coordination — `isModalOpen` prop wired through
  App.vue → TourOverlay → TourSpotlight; this plan adds 3 tests for
  the dim-fallback `.modal-open` class and TourSpotlight `:reduced`
  passthrough)
- 6 new frontend tests (2 useTourTargetBus + 1 useTourMachine + 3
  TourOverlay)

Phase 6 deliverables (plan 06-01):
- OB-29 ✓ (bottom bar with counter + Skip + Next — pre-existing, tested)
- OB-30 ✓ (substep labels — pre-existing, tested)
- OB-31 ✓ (skip confirm; SIGNIFICANT_STEP_TITLES extended from 1 entry to
  4: "AI Backend Accounts", "Create Your First Product", "Create Your
  First Project", "Assign Teams to Project")
- OB-32 ✓ (no X glyph — replaced `✕` in TourProgressBar's dismiss button
  with the labelled "Exit Tour" string; click-on-overlay already
  prevented in TourOverlay.vue:233)
- OB-33 ✓ (keyboard nav — pre-existing, Enter/Escape in TourOverlay,
  focus-trap in TourTooltip)
- 8 new frontend tests (3 progress-bar OB-32 cases + 5 overlay OB-31
  significant-step cases)
- New i18n key `tour.exitTour: "Exit Tour"`

Phase 5 deliverables (plan 05-01):
- OB-25 ✓ (auto-discovery via `.form-group` walk — pre-existing, now tested)
- OB-26 ✓ (sequential nav with nextField/prevField — pre-existing, now tested)
- OB-27 ✓ (help text priority chain: data-tour-help → .form-help → .form-description → small → fallback — pre-existing, now tested)
- OB-28 ✓ (submit button last via button[type=submit] → .inline-form-actions .btn-primary → [data-tour=submit-btn] — pre-existing, now tested)
- 33 new frontend tests covering useFormGuide (28) + TourFormGuide (5)
- Followup captured in plan doc: wire TourFormGuide into the tour flow when AccountWizard opens (a Phase 5 → Phase 4 integration that needs the `@ai-accounts/vue-styled` open/close lifecycle)

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
