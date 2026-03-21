# Project Research Summary

**Project:** Agented v0.5.0 — Onboarding Tour Redesign
**Domain:** Web application onboarding UX — guided setup tour for a developer-facing bot automation platform
**Researched:** 2026-03-21
**Confidence:** HIGH

## Executive Summary

Agented's onboarding tour needs a ground-up redesign. The current implementation (custom `TourOverlay.vue` + `useTour.ts` + `WelcomePage.vue`) has validated failures: spotlight misalignment, X button confusion, unguarded step skipping, no per-field form guidance, page-load race conditions, and localStorage conflicts after DB resets. These are not polish issues — they are architectural failures that cosmetic fixes cannot resolve. The v0.5.0 milestone must replace the flat index-tracking composable with a proper state machine, introduce a tiered progressive-disclosure model, and build a form-field auto-discovery system.

Research into best-in-class onboarding (Linear, Vercel, Stripe, Figma, Notion, Railway) reveals a clear playbook for developer tools: single-purpose steps, always-available escape, learn-by-doing over learn-by-reading, smart defaults over manual entry, and a persistent setup checklist that outlives the guided tour. The recommended Agented flow is: welcome screen → workspace directory → backend account registration (with per-field guidance) → token monitoring → first bot execution. This should complete in under 3 minutes and leave users with a working, runnable bot.

The technical approach is settled: drop driver.js (too many validated issues), implement a custom overlay system backed by XState v5 for flow control, Floating UI for tooltip positioning, and ResizeObserver-based spotlight tracking. The only new runtime dependencies are `@floating-ui/vue` (~3 KB), `xstate` + `@xstate/vue` (~15 KB), and `focus-trap` (~10 KB). The existing `driver.js` dependency should be removed. All animation needs are satisfied by Vue `<Transition>` and CSS `@keyframes` — no animation library is needed. Backend changes are minimal: add an `app_meta` table with an `instance_id` field used to detect DB resets and invalidate stale localStorage state.

## Key Findings

### Recommended Stack

| Category | Choice | Notes |
|---|---|---|
| Tour flow control | XState v5 + `@xstate/vue` | Hierarchical states handle substeps, conditional skipping, and form field sequences |
| Tooltip positioning | `@floating-ui/vue` (~3 KB) | Auto-flip, viewport-aware, handles the scroll/resize tracking driver.js fails at |
| Spotlight overlay | Custom CSS `box-shadow` approach | Keep current technique, replace broken parts |
| Element tracking | `ResizeObserver` + `MutationObserver` (scoped) | Replace the full-document polling currently in `TourOverlay.vue` |
| Focus trapping | `focus-trap` (~10 KB) | Activated on tooltip mount, deactivated on step change |
| Animations | Vue `<Transition>` + CSS `@keyframes` | No library needed; all three required animation types are covered |
| Progress persistence | localStorage + backend instance ID validation | Detect DB resets via `app_meta.instance_id`; backend sync is a later enhancement |
| Unit tests | Vitest (already installed) + mock driver layer | Mock the visual layer; test composable logic and state transitions |
| E2E tests | Playwright (already installed) | Full tour flow, persistence, reduced-motion, focus-trap validation |

**Remove:** `driver.js` (installed but unused; validated issues with click-blocking, X button interference, stagePadding misalignment).

**New dependencies:**
```bash
npm uninstall driver.js
npm install @floating-ui/vue xstate @xstate/vue focus-trap
```

Total new bundle impact: ~28 KB gzipped.

### Expected Features

**Table stakes (must have for v0.5.0):**
- Skip/defer option on every step, with labeled "Exit Tour" distinct from "Skip Step"
- Step progress indicator ("Step 2 of 5" or equivalent progress bar)
- Persistent progress — resume from where the user left off after page reload or revisit
- Keyboard navigation: Arrow keys to advance/retreat, Escape to defer, Tab trapped within popover
- Every step navigates to the relevant page automatically
- Workspace + at least one backend account as the critical setup path (essential tier)
- Post-tour setup checklist accessible from sidebar/settings, clickable to each step's page
- Restart tour option in Settings

**Differentiators for v0.5.0:**
- Per-field form guidance: highlight each field one by one with actionable copy (not just the "Add Account" button)
- Auto-discovery of form fields from `.form-group` DOM patterns — no hardcoded field selectors
- Condition-aware steps: skip backend steps that are already configured
- Phase-based progressive disclosure: Essential (blocking) → Recommended (checklist) → First-run contextual hints
- Dark-theme native styling: use app CSS custom properties throughout, no bolted-on colors
- Backend detection re-scan button: don't rely only on startup detection

**Defer to v2+:**
- Self-segmentation (role-based flow branching)
- Backend state sync to server API
- Contextual everboarding hints for advanced features
- Demo content / prefilled sample bots
- In-app reduced-motion toggle

**Anti-features (explicitly do not build):**
- Unskippable forced tour blocking all UI
- Auto-advancing carousels or video-only walkthroughs
- Confetti or over-celebration on every step
- Showing onboarding to users who have already completed it
- Using jargon in tooltip copy ("configure your webhook endpoint" → "tell us where to send notifications")

### Architecture Approach

The architecture separates concerns into four distinct layers:

**1. State Machine Layer (`useTourMachine.ts` via XState v5)**
Owns all flow logic: which step is current, what transitions are valid, conditional skipping based on API state, persistence, and route navigation side effects. The flat `currentStepIndex` tracking is replaced by a hierarchical state machine with compound states for multi-substep sections (backends, product/project creation).

**2. Visual Layer (custom Vue components)**
```
App.vue
  +-- <OnboardingProvider>       (renderless; owns state machine, provides context)
        +-- <TourOverlay>        (full-screen dimming via box-shadow)
        +-- <TourSpotlight>      (positioned highlight; ResizeObserver tracking)
        +-- <TourTooltip>        (Floating UI anchored popover; focus-trap)
        +-- <TourProgressBar>    (bottom bar or sidebar; consistent with app design tokens)
        +-- <TourFormGuide>      (field-by-field guide; auto-discovery)
```

**3. Step Configuration Layer (`config/tourSteps.ts`)**
Static TypeScript config objects define each step's route, target selector, title, message, skippability, and whether to activate `formGuide` (auto-discovery). Substep sequences (backend registrations) are declared as arrays within parent steps.

**4. Guard Layer (`config/tourGuards.ts`)**
Async functions prefetched at tour start that determine whether each step needs to be shown. Guards query the actual backend API (not just localStorage) so already-configured steps are auto-skipped.

**Key patterns:**
- `provide`/`inject` (`TOUR_INJECTION_KEY`) for context propagation — no prop drilling
- `<Teleport to="body">` for all overlay components — avoids z-index and stacking context collisions
- CSS custom properties from `App.vue` for all tour styling — design integration, not bolted-on
- `ResizeObserver` + `window` scroll listener for spotlight tracking — disconnect immediately after target found
- Dual-layer persistence: `localStorage` (fast, primary) + `app_meta.instance_id` from backend (detect DB resets, invalidate stale state)
- Progressive disclosure: Essential phase blocks until complete; Recommended phase shows as sidebar checklist; First-run phase triggers contextually per page

**Z-index scale (CSS custom properties):**
```
--z-dropdown:     1000
--z-modal:        2000
--z-toast:        3000
--z-tour-overlay: 4000
--z-tour-popover: 5000
```

### Critical Pitfalls

**P1 — Pointer event blocking (currently broken, users can't interact with highlighted form fields)**
The overlay must NOT block pointer events on the highlighted target. Use CSS elevation of the target element above the overlay z-index rather than a full-screen blocking overlay. Every form step must be manually tested by actually filling in the form during development.

**P2 — Race conditions with lazy-loaded routes**
After `router.push()`, the target element doesn't exist until the async component resolves and its API calls complete. The solution is a `tour:ready` event system where page components signal readiness, combined with a 5-second timeout with retry UI ("This step is taking longer than expected. [Retry] [Skip]"). Never rely on `MutationObserver` alone for route-transition element discovery.

**P3 — localStorage conflicts after DB resets**
When `just reset` clears the database, the frontend's localStorage still contains completed tour state, invalid API keys, and completion flags. The fix is an `app_meta.instance_id` in the backend database (generated once, persisted). On every app start, compare the stored instance ID with the backend's response. If they differ, clear all tour-related localStorage. The router guard (not just `WelcomePage.vue`) should enforce this check.

**P4 — Skipping without consequence clarity**
The current "X button skips the entire step" behavior is a validated user complaint. Solution: explicitly labeled "Skip This Step" vs. "Exit Tour" buttons; no ambiguous X; a `skipped[]` array alongside `completed[]` in state; post-skip summary linking to where to complete skipped items later.

**P5 — Design integration failure**
The current tour uses hardcoded colors (`#1a1a2e`, `#818cf8`) instead of the app's CSS custom properties. Tour buttons don't match app button styles. This must be corrected at the CSS level from the start — not patched later. All tour elements should feel like an enhanced state of the normal UI.

**P6 — MutationObserver performance (document-wide observation)**
The current implementation observes `document.body` with `{ childList: true, subtree: true }`, causing jank in a reactive Vue app. Scope observers to the minimum required container, disconnect immediately on target found, and set a max observation duration.

## Implications for Roadmap

### Phase 1: Foundation and Architecture
**Rationale:** All other phases depend on having the state machine, persistence model, auth-ready flow, and component scaffold in place. The pitfalls assigned to "Phase 1 — Architecture" in PITFALLS.md represent correctness failures; getting them wrong invalidates all subsequent work. This phase produces no visible user-facing tour — it produces the infrastructure that the tour runs on.
**Delivers:** XState machine definition, `OnboardingProvider` component scaffold, `useTourPersistence` with instance ID validation, backend `app_meta` table, z-index CSS property system, guard prefetch system, auth-ready flow (no more 401s during tour), form-field auto-discovery utility
**Type:** implement
**Pitfalls addressed:** P2 (race conditions), P3 (localStorage/DB reset conflicts), P4 (auth errors), auto-discovery architecture (4.5), escape hatch (1.2), checklist architecture (1.8)

### Phase 2: Visual Layer and Design Integration
**Rationale:** The visual components — spotlight, tooltip, progress bar — need to be built on top of the Phase 1 scaffold. Design integration (CSS custom properties, typography, button consistency) must be decided before implementation, not patched after. This phase produces a visually complete tour that looks native to the app.
**Delivers:** `TourSpotlight` with ResizeObserver tracking, `TourTooltip` with Floating UI positioning, `TourProgressBar`, focus-trap integration, reduced-motion support, full dark-theme design integration, `skip confirmation` interaction model, correct button hierarchy (Next / Skip This Step / Exit Tour)
**Type:** implement
**Pitfalls addressed:** P1 (pointer event blocking), P5 (design integration), 3.2 (button inconsistency), 3.3 (contrast), 3.4 (popover covers target), 3.5 (bottom bar covers content), 1.9 (dismiss confusion), 1.7 (skip without confirmation)

### Phase 3: Step Content and Form Guidance
**Rationale:** With the scaffold and visual layer ready, the step content and per-field form guidance can be built. This is the most user-visible phase — what users actually read, the fields they interact with, and whether the tour feels helpful or generic.
**Delivers:** All step content (actionable copy for every field, external links to API key dashboards), `TourFormGuide` component with auto-discovery, per-field spotlight and tooltip for every backend registration form, backend detection re-scan, condition guards for all steps, substep sequences for backend registrations
**Type:** implement
**Pitfalls addressed:** 1.3 (generic tooltips), 1.4 (highlight misalignment), 2.4 (MutationObserver performance), 2.5 (z-index wars with modals), 4.1 (spotlight glow), 4.4 (per-field guidance), 4.9 (backend detection)

### Phase 4: Persistence, Checklist, and Polish
**Rationale:** The setup checklist (accessible from sidebar/settings post-tour), restart capability, and end-to-end persistence validation come last because they depend on the complete step sequence being finalized in Phase 3. Memory leak cleanup and final E2E test coverage also belong here.
**Delivers:** Persistent sidebar setup checklist, "Restart Setup Guide" in Settings, memory leak cleanup (`onScopeDispose`, AbortController patterns), E2E Playwright test suite covering full tour flow, persistence across reload, reduced motion, and focus trapping
**Type:** implement + integrate
**Pitfalls addressed:** 1.8 (no restart/resume), 2.7 (memory leaks), 4.8 (localStorage persistence)

### Phase Ordering Rationale
- Phase 1 must precede everything: auth flow, state machine, and persistence correctness are load-bearing
- Phase 2 can proceed in parallel with late Phase 1 work (CSS design tokens, component scaffold) but requires the state machine interface to be stable
- Phase 3 requires both Phase 1 (guards, form discovery API) and Phase 2 (spotlight, tooltip) to be functional
- Phase 4 is the integration and hardening phase — depends on Phase 3 being feature-complete

### Research Flags
- **Phase 1:** XState v5 integration with Vue — `@xstate/vue`'s `useActor` and `snapshot` API should be spiked early; the manual FSM fallback (Option B from ARCHITECTURE.md) is a valid hedge if XState proves too complex for the team
- **Phase 2:** Floating UI placement edge cases — test on small viewports and when targets are near screen edges; the auto-flip middleware should handle most cases but needs validation
- **Phase 3:** Auto-discovery robustness — the `discoverFormFields()` utility depends on `.form-group` DOM patterns being consistent across all forms; audit all backend registration forms before building
- **All phases:** The no-SSR assumption is safe for now (Vite SPA); document `onMounted`-gating patterns in case the app ever moves to Nuxt

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Library choices are well-researched with clear rationale; driver.js removal is based on validated failures not speculation |
| Features | HIGH | Patterns drawn from 200+ onboarding flow analyses and direct comparison with Linear, Vercel, Stripe, Figma; Agented-specific patterns are explicitly mapped |
| Architecture | HIGH | Component decomposition, state machine design, and persistence strategy are fully specified with working TypeScript code; key decisions (drop driver.js, use XState + Floating UI) are well-argued |
| Pitfalls | HIGH | The most critical pitfalls (P1–P6) are validated from actual Agented user testing, not theoretical risk — 10 concrete memory feedback items are documented in PITFALLS.md |
| Landscape | MEDIUM | No LANDSCAPE.md was produced (not applicable: this is a UX redesign, not a research/ML domain); onboarding pattern research is thorough but based on secondary sources (published case studies, not A/B test data) |

**Gaps to address during planning:**
- Exact XState v5 machine snapshot serialization format for persistence (needs a spike)
- Whether `app_meta.instance_id` endpoint should be public (`/api/`) or admin-only (`/admin/`) given it runs before auth
- The bottom bar vs. sidebar checklist UX decision is partially resolved (keep bottom bar for active guidance, add sidebar checklist for post-tour) but should be validated against the actual viewport layout on common screen sizes

## Sources

### Primary (HIGH confidence — validated against Agented codebase)
- User testing feedback (10 concrete items): spotlight misalignment, X button interference, skip confirmation missing, no per-field guidance, auto-discovery requirement, race conditions, DB reset conflicts, 401 errors, backend detection inaccuracy
- Existing codebase: `TourOverlay.vue`, `useTour.ts`, `WelcomePage.vue` — implementation analysis

### Primary (HIGH confidence — direct product analysis)
- [Linear Onboarding Deep Dive](https://www.growthdives.com/p/the-onboarding-linear-built-without) — $1.25B philosophy without A/B testing
- [Vercel Getting Started](https://vercel.com/docs/getting-started-with-vercel) — single-action deploy wizard
- [Stripe Account Checklist](https://docs.stripe.com/get-started/account/checklist) — progressive activation model
- Figma, Notion, Railway, Supabase, Canva, Asana — direct product usage

### Secondary (MEDIUM confidence — analysis/survey sources)
- [The 14 Types of Onboarding UX/UI](https://designerup.co/blog/the-14-types-of-onboarding-ux-ui-used-by-top-apps-and-how-to-copy-them/) — 200+ flow analysis
- [SaaS Onboarding UX: Best Practices 2026](https://www.designstudiouiux.com/blog/saas-onboarding-ux/) — pattern survey
- [15 Onboarding Micro-Interactions](https://userguiding.com/blog/onboarding-microinteractions) — dark theme micro-interaction patterns
- [Common onboarding mistakes](https://productfruits.com/blog/common-user-onboarding-mistakes) — anti-pattern catalogue
- driver.js, shepherd.js, v-onboarding, @vueuse/motion, @oku-ui/motion — npm/GitHub direct evaluation
- XState v5 docs, Floating UI docs, focus-trap docs — library capability assessment

---
*Research completed: 2026-03-21*
*Ready for roadmap: yes*
