# Roadmap: v0.5.0 — Production-Level Onboarding Experience

## Overview

Replace the current flat-index tour system (`useTour.ts` + `TourOverlay.vue`) with a production-grade onboarding experience backed by XState v5, Floating UI, and custom Vue overlay components. The roadmap progresses from backend infrastructure and state machine foundation through visual components, step content, form guidance, navigation controls, accessibility, error handling, post-tour experience, and finally integration testing. A new user should complete workspace setup, register at least one AI backend account, and run their first bot in under 3 minutes.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

**Phase Types:** survey | implement | evaluate | integrate

- [ ] **Phase 1: Backend + State Machine Foundation** - XState machine, persistence, instance ID validation, guard system, z-index scale `implement`
- [ ] **Phase 2: Visual Layer** - Overlay, spotlight, tooltip, and progress bar components with dark theme integration `implement`
- [ ] **Phase 3: Welcome Flow + Tour Entry** - Welcome page retention, API key generation, transition to guided tour `implement`
- [ ] **Phase 4: Core Step Content** - Workspace setup, backend account registration with substeps, token monitoring, harness verification `implement`
- [ ] **Phase 5: Form Field Guidance** - Auto-discovery of form fields, sequential highlighting, help text extraction, submit button guidance `implement`
- [ ] **Phase 6: Navigation Controls** - Bottom bar, substep labels, skip confirmation, dismissal prevention, keyboard navigation `implement`
- [ ] **Phase 7: Loading + Error Resilience** - Route prefetching, spinner during transitions, missing element fallback, modal coordination `implement`
- [ ] **Phase 8: Accessibility** - Reduced motion, focus trapping, ARIA live announcements, keyboard-only completion `implement`
- [ ] **Phase 9: Post-Tour Experience** - Completion celebration, sidebar checklist, restart tour, product/project/team creation steps `implement`
- [ ] **Phase 10: Integration Testing** - Unit tests for state machine and components, E2E full tour flow, build verification `integrate`

## Phase Details

### Phase 1: Backend + State Machine Foundation
**Goal**: The tour engine infrastructure is in place — XState state machine manages flow, persistence survives reloads, DB resets invalidate stale state, guards determine step completion, and z-index CSS properties prevent layering conflicts
**Type**: implement
**Depends on**: Nothing (first phase)
**Requirements**: OB-04, OB-05, OB-06, OB-07, OB-08, OB-43
**Verification Level**: sanity
**Success Criteria** (what must be TRUE):
  1. XState v5 state machine handles forward, backward, and skip transitions between all tour states without entering invalid states
  2. Tour progress persists to localStorage on every transition and resumes at the exact step/substep after browser reload
  3. When backend `instance_id` changes (DB reset), all tour localStorage is cleared and user starts fresh from welcome
  4. Guard functions query backend APIs and auto-skip already-completed steps (e.g., workspace already set, Claude account exists)
  5. CSS custom properties for z-index scale (`--z-tour-overlay` through `--z-tour-progress`) are defined in App.vue
**Plans**: TBD

Plans:
- [ ] 01-01: Backend instance_id endpoint and XState machine definition
- [ ] 01-02: Persistence layer and guard system

### Phase 2: Visual Layer
**Goal**: All tour visual components render correctly — overlay dims background without blocking pointer events, spotlight tracks target elements through resize/scroll, tooltips position with Floating UI and auto-flip at viewport edges, and all components use the app's dark theme CSS custom properties
**Type**: implement
**Depends on**: Phase 1
**Requirements**: OB-09, OB-10, OB-11, OB-12, OB-13, OB-14, OB-15, OB-16
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Background is dimmed via box-shadow technique and highlighted elements remain fully interactive (clickable, typeable)
  2. Spotlight repositions within one animation frame when target moves due to resize, scroll, or content reflow
  3. Tooltips are always fully visible within the viewport — never clipped at any edge
  4. Step transitions use CSS transitions (opacity + transform, 200ms) with no flicker or jump
  5. All tour components use CSS custom properties from App.vue — zero hardcoded color values in tour styles
**Plans**: TBD

Plans:
- [ ] 02-01: TourOverlay and TourSpotlight components
- [ ] 02-02: TourTooltip with Floating UI and TourProgressBar

### Phase 3: Welcome Flow + Tour Entry
**Goal**: First-time users land on the welcome page, generate an API key, and transition smoothly into the guided tour — no dashboard flash, no intermediate blank screens
**Type**: implement
**Depends on**: Phase 1, Phase 2
**Requirements**: OB-01, OB-02, OB-03
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. First-time visitor sees `/welcome` within 200ms of app load with no dashboard flash
  2. API key generates via backend call, displays in monospace with copy button, and shows "will not be shown again" warning
  3. Transition from keygen completion to first tour step takes < 500ms with no visual glitch — welcome fades out, tour overlay fades in
**Plans**: TBD

Plans:
- [ ] 03-01: Welcome page integration and API key flow with tour entry transition

### Phase 4: Core Step Content
**Goal**: The tour navigates users through the essential setup steps — workspace directory, four backend account substeps (Claude/Codex/Gemini/OpenCode), token monitoring, and harness plugin verification — with correct route navigation and target element highlighting
**Type**: implement
**Depends on**: Phase 2, Phase 3
**Requirements**: OB-17, OB-18, OB-19, OB-20, OB-21
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Tour navigates to `/settings#general` and highlights workspace input — user can type a valid path
  2. Tour cycles through 4 backend pages with individually skippable substeps; completing one backend satisfies the step requirement
  3. Per-backend form fields are highlighted sequentially with actionable help text after clicking "Add Account"
  4. Tour navigates to monitoring settings for token configuration and to harness page for plugin verification
**Plans**: TBD

Plans:
- [ ] 04-01: Workspace and backend account step definitions with substep sequences
- [ ] 04-02: Token monitoring and harness verification steps

### Phase 5: Form Field Guidance
**Goal**: The TourFormGuide component auto-discovers `.form-group` elements on any page, highlights fields one by one in DOM order, shows contextual help text derived from labels, and ends with submit button guidance
**Type**: implement
**Depends on**: Phase 2, Phase 4
**Requirements**: OB-25, OB-26, OB-27, OB-28
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. `TourFormGuide` discovers all `.form-group` elements on a page without hardcoded selectors
  2. Fields are highlighted one at a time in DOM order — user can type/select in the highlighted field
  3. Help text is extracted from `<label>` and `.form-help`/`.form-description` elements, with `data-tour-help` override
  4. Submit button (`button[type="submit"]`, `.btn-primary`, or `data-tour="submit-btn"`) is the last element highlighted
**Plans**: TBD

Plans:
- [ ] 05-01: TourFormGuide component with auto-discovery and sequential field highlighting

### Phase 6: Navigation Controls
**Goal**: The bottom progress bar shows correct step/substep labels and counts, skip confirmation appears for meaningful steps, the tour cannot be accidentally dismissed, and keyboard navigation works throughout
**Type**: implement
**Depends on**: Phase 2, Phase 4
**Requirements**: OB-29, OB-30, OB-31, OB-32, OB-33
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Bottom bar displays step label, step counter ("Step 2 of 8"), Skip and Next buttons — Skip only visible on skippable steps
  2. During substeps, label shows substep context (e.g., "Claude Code (1/4)") and counter shows parent step number
  3. Skipping meaningful steps (backends, product/project) shows confirmation dialog; trivial skips do not
  4. No X button or close button exists — clicking dimmed overlay does not dismiss the tour
  5. Enter advances, Escape skips (when allowed), Tab is trapped within tooltip + highlighted element
**Plans**: TBD

Plans:
- [ ] 06-01: TourProgressBar with step/substep rendering and skip confirmation
- [ ] 06-02: Dismissal prevention and keyboard navigation

### Phase 7: Loading + Error Resilience
**Goal**: Tour handles lazy-loaded routes gracefully with spinners and timeouts, missing target elements trigger scoped MutationObserver with fallback UI, routes are prefetched at tour start, and modals that open during tour steps remain interactive
**Type**: implement
**Depends on**: Phase 4, Phase 6
**Requirements**: OB-40, OB-41, OB-42, OB-44
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Loading spinner appears within tour overlay during lazy route loads; after 5s timeout, "Skip/Retry" fallback shows
  2. Missing target elements trigger scoped MutationObserver (not document.body); fallback appears after 3s
  3. After first step, no loading spinner appears for standard step transitions (routes prefetched via dynamic import)
  4. Modals opening during tour steps (e.g., "Add Account") are interactive — overlay adjusts to allow modal interaction
**Plans**: TBD

Plans:
- [ ] 07-01: Route prefetching, loading spinners, and missing element fallback
- [ ] 07-02: Modal coordination during tour

### Phase 8: Accessibility
**Goal**: The tour is fully accessible — animations respect reduced-motion preference, focus is trapped within tooltip + target, step changes announce via ARIA live regions, and the entire tour can be completed keyboard-only
**Type**: implement
**Depends on**: Phase 6
**Requirements**: OB-36, OB-37, OB-38, OB-39
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. With `prefers-reduced-motion: reduce`, no animations play — spotlight, tooltip, and glow are instant, tour remains fully functional
  2. Focus is trapped within tooltip controls + highlighted target element; Tab does not escape to background
  3. ARIA live region updates on every step change with "Step N of M: [title]. [message]"
  4. A keyboard-only user can complete the full tour — all controls reachable via Tab/Shift+Tab and activatable via Enter/Space
**Plans**: TBD

Plans:
- [ ] 08-01: Reduced motion, focus trapping, and ARIA announcements

### Phase 9: Post-Tour Experience
**Goal**: Tour completion shows a celebration screen with summary of configured/skipped items, a persistent sidebar checklist tracks setup progress, the tour can be restarted from settings, and optional steps (product, project, team) guide entity creation
**Type**: implement
**Depends on**: Phase 4, Phase 6
**Requirements**: OB-22, OB-23, OB-24, OB-34, OB-35, OB-35a
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Completion screen shows congratulatory message, lists configured and skipped items with navigation links
  2. Sidebar "Setup" checklist persists after tour, reflects actual completion state, and links to relevant settings pages
  3. "Restart Setup Guide" in Settings clears tour state and begins from first incomplete step (re-evaluates guards)
  4. Product, project, and team creation steps guide users through entity creation and are individually skippable
**Plans**: TBD

Plans:
- [ ] 09-01: Completion celebration and sidebar setup checklist
- [ ] 09-02: Product, project, and team creation steps with restart capability

### Phase 10: Integration Testing
**Goal**: Comprehensive test coverage validates the full tour system — unit tests for state machine and all visual components, E2E Playwright tests for complete flows, and the entire codebase passes vue-tsc + Vite build
**Type**: integrate
**Depends on**: Phase 1-9
**Requirements**: OB-45, OB-46, OB-47, OB-48
**Verification Level**: full
**Success Criteria** (what must be TRUE):
  1. State machine unit tests achieve >= 90% branch coverage on `useTourMachine.ts` — all transitions, substeps, persistence, guards, and edge cases
  2. Visual component unit tests cover primary rendering states and interactions for TourOverlay, TourTooltip, TourProgressBar, TourFormGuide, TourSpotlight
  3. Playwright E2E tests pass for: complete tour flow, skip-all flow, persistence across reload, keyboard-only navigation, reduced motion, focus trapping
  4. `just build` passes with zero vue-tsc errors and no `any` types in tour composables or components
**Plans**: TBD

Plans:
- [ ] 10-01: Unit tests for state machine and guard system
- [ ] 10-02: Unit tests for visual components
- [ ] 10-03: E2E Playwright tests for full tour flows
- [ ] 10-04: Build verification and type safety audit

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Backend + State Machine Foundation | 0/2 | Not started | - |
| 2. Visual Layer | 0/2 | Not started | - |
| 3. Welcome Flow + Tour Entry | 0/1 | Not started | - |
| 4. Core Step Content | 0/2 | Not started | - |
| 5. Form Field Guidance | 0/1 | Not started | - |
| 6. Navigation Controls | 0/2 | Not started | - |
| 7. Loading + Error Resilience | 0/2 | Not started | - |
| 8. Accessibility | 0/1 | Not started | - |
| 9. Post-Tour Experience | 0/2 | Not started | - |
| 10. Integration Testing | 0/4 | Not started | - |

## Deferred Validations

| Deferred From | Validation | Must Resolve By | Status |
|---------------|-----------|-----------------|--------|
| Phase 2 | Full visual regression across all step types | Phase 10 | Pending |
| Phase 4 | End-to-end tour flow with real backend accounts | Phase 10 | Pending |
| Phase 6 | Keyboard navigation through complete tour | Phase 10 | Pending |
| Phase 8 | Screen reader compatibility validation | Phase 10 | Pending |
