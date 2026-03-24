# v0.5.0 Requirements: Production-Level Onboarding Experience

## Overview

Replace the current flat-index tour composable (`useTour.ts` + `TourOverlay.vue` + `WelcomePage.vue`) with a production-grade onboarding system. The current implementation has validated failures: spotlight misalignment, X button interference, no per-field form guidance, race conditions on lazy-loaded routes, and localStorage conflicts after DB resets. These are architectural issues, not cosmetic bugs.

**Goal:** A new user completes workspace setup, registers at least one AI backend account (with per-field guidance), and runs their first bot in under 3 minutes.

**Stack:** XState v5 (`@xstate/vue`), `@floating-ui/vue`, `focus-trap`, custom Vue overlay components. Remove `driver.js`.

---

## v1 Requirements (Must-Have)

### Welcome & First Impression

**OB-01: Welcome page with clear value proposition**
The Welcome page (`/welcome`) displays on first visit (no API key exists). It shows the Agented product name, a concise value statement, visual bento grid of capabilities (AI backends, bot orchestration, harness/plugins), and a single "Begin setup" CTA. No navigation chrome is visible. The page must not flash the dashboard before redirecting.

- Acceptance: First-time visitor sees `/welcome` within 200ms of app load. No dashboard flash.
- Tested by: E2E test asserting `/welcome` route on fresh state, no layout shift.

**OB-02: API key generation with copy-to-clipboard**
After clicking "Begin setup", a keygen card appears with a "Generate Admin Key" button. On click, an API key is generated via `POST /admin/api-keys`, displayed in a monospace field with a "Copy" button, and a "Continue" button appears. The key is shown exactly once. A warning states the key will not be shown again.

- Acceptance: Key displays, copy button copies to clipboard, "Continue" advances to tour.
- Tested by: Unit test for keygen state transitions; E2E test for full generate-copy-continue flow.

**OB-03: Smooth transition from welcome to guided tour**
After API key generation, clicking "Continue" transitions to the first tour step (workspace directory). The Welcome page fades out, the tour overlay fades in, and the router navigates to `/settings#general`. No intermediate blank screen or spinner lasting more than 300ms.

- Acceptance: Transition from keygen to first tour step takes < 500ms with no visual glitch.
- Tested by: E2E test measuring transition timing and asserting overlay visibility.

---

### Tour Engine & Architecture

**OB-04: Hierarchical state machine for tour flow**
Replace `currentStepIndex`/`currentSubstepIndex` flat tracking with an XState v5 state machine. The machine uses compound states for multi-substep sections (backends with 4 substeps, product/project creation). States: `idle -> welcome -> setup -> complete`, where `setup` contains child states for each step.

- Acceptance: State machine handles forward/backward/skip transitions without invalid states.
- Tested by: Unit tests covering all state transitions, including edge cases (skip from substep, backward from first substep).

**OB-05: Persistence across page reloads**
Tour progress is saved to `localStorage` on every state transition. On app load, if saved state exists, the tour resumes from the exact step/substep where the user left off. Navigation to the correct route happens automatically.

- Acceptance: Reload browser mid-tour, tour resumes at same step with correct route.
- Tested by: Unit test for save/restore; E2E test reloading mid-tour and verifying step.

**OB-06: Persistence invalidation on DB reset**
The backend provides an `instance_id` in an `app_meta` table (or `/health` endpoint). When the app loads, the stored `instance_id` in localStorage is compared to the backend's current value. If they differ (DB was reset/recreated), all tour progress is cleared and the user starts fresh.

- Acceptance: After DB reset, tour restarts from welcome page regardless of localStorage state.
- Tested by: Unit test simulating mismatched instance IDs; E2E test with mock `/health` response.

**OB-07: Conditional step skipping via guard functions**
Each step has an optional async guard function (`tourGuards.ts`) that queries the backend API to determine if the step is already complete (e.g., workspace already set, Claude account already registered). Guards are prefetched at tour start to avoid loading spinners mid-tour. Already-complete steps are auto-skipped.

- Acceptance: If Claude Code account exists, the Claude substep is skipped. If workspace is set, workspace step is skipped.
- Tested by: Unit tests for each guard with mocked API responses.

**OB-08: Resume from last incomplete step**
On app reload or tour restart, the state machine evaluates all guards and advances to the first incomplete step, not just the stored step index. This handles the case where a user manually completed a step outside the tour.

- Acceptance: User manually sets workspace in settings, reloads, tour skips workspace step.
- Tested by: Unit test with pre-configured state and guard evaluation.

---

### Visual Layer

**OB-09: Full-screen overlay with box-shadow dimming**
A `TourOverlay` component covers the entire viewport using `box-shadow: 0 0 0 9999px rgba(0,0,0,0.6)` on a positioned element around the target. This dims everything except the highlighted element. The overlay does NOT use a full-screen `<div>` with a cutout (which blocks pointer events).

- Acceptance: Background is dimmed, highlighted element is fully interactive (clickable, typeable).
- Tested by: E2E test clicking/typing in highlighted form fields during tour.

**OB-10: Spotlight positioning with ResizeObserver tracking**
A `TourSpotlight` component reads the target element's `getBoundingClientRect()` and positions itself around it. A `ResizeObserver` and scroll listener track position changes. When the target moves (window resize, scroll, content reflow), the spotlight updates within one animation frame.

- Acceptance: Spotlight stays aligned with target during resize and scroll.
- Tested by: E2E test resizing viewport and verifying spotlight position.

**OB-11: Element-adaptive padding and border-radius**
The spotlight reads the target element's computed `border-radius` and applies matching border-radius. Padding varies by element type: inputs = 4px, buttons = 6px, cards/sections = 12px. Elements can override via `data-tour-padding` attribute.

- Acceptance: Spotlight visually matches the shape of each target element type.
- Tested by: Visual regression test (manual) for each step; unit test for padding calculation logic.

**OB-12: Tooltip positioning with Floating UI**
A `TourTooltip` component uses `@floating-ui/vue` to anchor popovers to the target element. Tooltips auto-flip when near viewport edges. Preferred placement is `bottom` with `top`, `left`, `right` as fallbacks. The tooltip contains the step title, message, and navigation controls.

- Acceptance: Tooltip is always fully visible within the viewport, never clipped.
- Tested by: E2E test verifying tooltip visibility at all four viewport edges.

**OB-13: Dark theme native styling**
All tour components use the app's existing CSS custom properties (`--color-bg`, `--color-text`, `--color-border`, `--color-accent`, etc.) from `App.vue`. No hardcoded colors. The overlay, tooltip, spotlight, and progress bar look native to the dark theme, not bolted-on.

- Acceptance: Tour components pass a visual review confirming consistent use of CSS custom properties.
- Tested by: Grep for hardcoded color values in tour component styles (must find none).

**OB-14: Smooth transitions between steps**
Step changes use Vue `<Transition>` with CSS transitions (opacity + transform, 200ms ease). The old tooltip fades out, the spotlight moves to the new target, and the new tooltip fades in. All animations use `will-change: transform, opacity` for GPU acceleration.

- Acceptance: Step transitions are visually smooth with no flicker or jump.
- Tested by: E2E test advancing through 3+ steps with no visual artifacts (manual verification).

**OB-15: Pulsing glow on highlighted elements**
The spotlight includes a CSS `@keyframes` pulsing glow effect (subtle box-shadow pulse, 2s cycle). The glow uses the app's accent color. The animation respects `prefers-reduced-motion: reduce` (see OB-36).

- Acceptance: Highlighted elements have a visible pulse; pulse is absent when reduced motion is preferred.
- Tested by: Unit test asserting CSS class application; manual visual check.

**OB-16: Progress indicator**
A bottom bar (fixed, 48-56px height) shows: current step label, step counter ("Step 2 of 8"), navigation buttons (Skip, Next). When in a substep, the label shows the substep context (e.g., "Claude Code (1/4)"). The main content area adds `padding-bottom` equal to the bar height to prevent content occlusion.

- Acceptance: Progress bar displays correct step/substep counts. Bottom content is not hidden.
- Tested by: Unit test for step counter rendering; E2E test verifying no content hidden behind bar.

---

### Step Content & Flow

**OB-17: Workspace directory setup (Step 1)**
Target: `[data-tour="workspace-root"]` on `/settings#general`. Message explains this is the root directory where repos are cloned. User must set a valid directory path. Step is non-skippable (essential tier).

- Acceptance: Tour navigates to settings, highlights workspace input, user can type a path.
- Tested by: E2E test completing workspace setup during tour.

**OB-18: Backend account registration with substeps (Step 2)**
Target: `[data-tour="add-account-btn"]` on each backend page. Four substeps: Claude Code (`/backends/backend-claude`), Codex CLI (`/backends/backend-codex`), Gemini CLI (`/backends/backend-gemini`), OpenCode (`/backends/backend-opencode`). Each substep is individually skippable. The parent step completes when at least one backend account is registered.

- Acceptance: Tour cycles through 4 backend pages. Skipping one advances to the next. Completing one satisfies the requirement.
- Tested by: E2E test registering one account and skipping three.

**OB-19: Per-backend form field guidance (substeps of Step 2)**
When the user clicks "Add Account" on a backend page, the tour enters form field guidance mode. Fields are highlighted one by one: account name, email, config path, API key env var, then the Save button. Each field shows actionable help text (e.g., "Enter a name to identify this account, like 'personal' or 'work'"). See OB-25 through OB-28 for the auto-discovery mechanism.

- Acceptance: After clicking "Add Account", each form field is highlighted sequentially with relevant help text.
- Tested by: E2E test filling all fields via form guidance for one backend.

**OB-20: Token monitoring configuration (Step 3)**
Target: `[data-tour="token-monitor"]` on `/settings#monitoring` (or relevant page). Message explains token usage tracking. Step is skippable.

- Acceptance: Tour navigates to monitoring settings and highlights the configuration area.
- Tested by: E2E test navigating to and completing/skipping token monitoring step.

**OB-21: Harness plugin verification (Step 4)**
Target: `[data-tour="harness-status"]` on the plugins/harness page. Message confirms harness plugin is installed and operational. If not installed, provides guidance. Step is skippable.

- Acceptance: Tour navigates to harness page and shows installation status.
- Tested by: E2E test verifying harness step displays correct status.

**OB-22: Product creation (Step 5, skippable)**
Target: product creation form/button. Guides user through creating their first product. Step is skippable (recommended tier, not essential).

- Acceptance: Tour navigates to products page, highlights creation flow.
- Tested by: E2E test creating a product or skipping the step.

**OB-23: Project creation (Step 6, skippable)**
Target: project creation form/button. Guides user through creating their first project. Step is skippable (recommended tier).

- Acceptance: Tour navigates to projects page, highlights creation flow.
- Tested by: E2E test creating a project or skipping the step.

**OB-24: Team assignment (Step 7, skippable)**
Target: team creation/assignment form. Guides user through creating a team and assigning agents. Step is skippable (recommended tier).

- Acceptance: Tour navigates to teams page, highlights creation flow.
- Tested by: E2E test creating a team or skipping the step.

---

### Form Field Guidance

**OB-25: Auto-discovery of `.form-group` elements**
A `TourFormGuide` component scans the current page's DOM for `.form-group` elements when form guidance mode is activated. It builds an ordered list of fields based on DOM order. No hardcoded field selectors are required for standard forms.

- Acceptance: On any page with `.form-group` elements, the guide discovers all fields without configuration.
- Tested by: Unit test rendering a mock form with `.form-group` elements and verifying discovery.

**OB-26: Per-field sequential highlighting**
After auto-discovery, fields are highlighted one at a time in DOM order. The spotlight moves to the current field's input/select/textarea. The user can interact with the highlighted field (type, select). Advancing to the next field happens via the "Next" button or by pressing Enter/Tab.

- Acceptance: Each field is highlighted individually. User can type in the highlighted field.
- Tested by: E2E test tabbing through form fields during guidance.

**OB-27: Help text extraction from form labels**
The guide reads each `.form-group`'s `<label>` text and any `.form-help` or `.form-description` element text to construct contextual guidance. If a `data-tour-help` attribute exists on the element, it takes precedence. Fallback: generic "Fill in this field" message.

- Acceptance: Tour tooltip shows label-derived or custom help text for each field.
- Tested by: Unit test with mock form groups containing labels and help text.

**OB-28: Submit button guidance**
After all form fields are highlighted, the guide highlights the form's submit button (detected via `button[type="submit"]`, `.btn-primary`, or `data-tour="submit-btn"`). The tooltip says "Save your changes" or equivalent.

- Acceptance: Submit button is the last element highlighted in form guidance mode.
- Tested by: Unit test verifying submit button detection and ordering.

---

### Navigation & Controls

**OB-29: Bottom bar with step counter and controls**
The progress bar displays: step label (left), step counter (center), Skip and Next buttons (right). Skip button is only visible on skippable steps. Next button is always visible. The bar uses `position: fixed; bottom: 0` with the app's z-index scale.

- Acceptance: Bar renders with correct content for skippable and non-skippable steps.
- Tested by: Unit test for TourProgressBar with various step configurations.

**OB-30: Substep labels in progress bar**
When in a substep, the step label shows the substep context: e.g., "Claude Code (1/4)" for the first backend substep. The step counter shows the parent step number.

- Acceptance: Label updates correctly when entering/leaving substeps.
- Tested by: Unit test rendering progress bar during substep states.

**OB-31: Skip confirmation for non-trivial steps**
Skipping a step that involves meaningful setup (backend accounts, product/project creation) shows a confirmation: "Skip [step name]? You can complete this later from the setup checklist." Trivial skips (already-configured steps) do not show confirmation.

- Acceptance: Confirmation appears for meaningful skips, not for trivial ones.
- Tested by: Unit test for skip confirmation logic; E2E test clicking skip on a backend step.

**OB-32: No accidental dismissal**
There is no X/close button on the tour overlay or tooltip. The only ways to exit are: "Skip" (per-step), "Exit Tour" (explicit button in progress bar), or completing all steps. Clicking the dimmed overlay area does NOT dismiss the tour.

- Acceptance: Clicking outside the tooltip/spotlight does not dismiss. No X button exists.
- Tested by: E2E test clicking dimmed area and verifying tour persists.

**OB-33: Keyboard navigation**
`Enter` advances to the next step/substep. `Escape` triggers skip (if step is skippable) or does nothing (if not skippable). `Tab` is trapped within the tooltip + highlighted element. Arrow keys are not used (conflict with form field navigation).

- Acceptance: Enter advances, Escape skips (when allowed), Tab is trapped.
- Tested by: E2E test using keyboard-only navigation through 3+ steps.

---

### Post-Tour Experience

**OB-34: Completion celebration**
After the final step, a completion screen appears showing: congratulatory message, summary of what was configured, list of any skipped steps with links, and a "Go to Dashboard" button. The celebration uses a subtle animation (not confetti).

- Acceptance: Completion screen lists configured and skipped items with correct links.
- Tested by: E2E test completing all steps and verifying completion screen content.

**OB-35: Setup checklist in sidebar**
A persistent "Setup" item in the sidebar navigation shows a checklist of all onboarding steps with completed/pending status. Each item links to the relevant settings page. The checklist is visible after tour completion and updates when steps are completed outside the tour.

- Acceptance: Sidebar checklist reflects actual completion state. Clicking an item navigates to the correct page.
- Tested by: E2E test verifying checklist after partial tour completion.

**OB-35a: Restart tour option**
A "Restart Setup Guide" button in Settings resets tour progress and starts from the first incomplete step (re-evaluating guards). It does not reset the API key.

- Acceptance: Clicking restart clears tour state and begins from the first incomplete step.
- Tested by: E2E test restarting tour after partial completion.

---

### Accessibility

**OB-36: Reduced motion support**
All tour animations (spotlight movement, tooltip transitions, pulsing glow) are disabled when `prefers-reduced-motion: reduce` is active. Elements still appear/disappear but without animation. Uses `@media (prefers-reduced-motion: reduce)` in CSS.

- Acceptance: With reduced motion enabled, no animations play. Tour is still fully functional.
- Tested by: E2E test with `prefers-reduced-motion: reduce` emulated.

**OB-37: Focus trapping in tour tooltips**
When a tooltip is visible, keyboard focus is trapped within the tooltip and the highlighted target element using the `focus-trap` library. Focus moves between the tooltip controls and the target's interactive elements. Focus is released when the step advances.

- Acceptance: Tab key cycles only within tooltip + target. Focus does not escape to background.
- Tested by: E2E test tabbing through tooltip and verifying focus containment.

**OB-38: ARIA live announcements**
Step changes announce the new step title and message via an `aria-live="polite"` region. Screen readers hear "Step 2 of 8: AI Backend Accounts. Register accounts for each AI backend." on each transition.

- Acceptance: ARIA live region updates on every step change with correct content.
- Tested by: Unit test verifying `aria-live` region text content after state transitions.

**OB-39: Keyboard-only full tour completion**
The entire tour can be completed using only the keyboard (no mouse required). All form fields, buttons, and navigation controls are reachable via Tab/Shift+Tab and activatable via Enter/Space.

- Acceptance: A keyboard-only user can complete the full tour.
- Tested by: E2E test completing tour with keyboard-only input.

---

### Loading & Error States

**OB-40: Spinner during route transitions**
When the tour navigates to a lazy-loaded route, a loading spinner appears within the tour overlay (not replacing it). The spinner has a timeout of 5 seconds, after which a message appears: "This page is taking longer than expected. [Skip] [Retry]".

- Acceptance: Spinner appears during route load. After 5s, fallback message with Skip/Retry shows.
- Tested by: E2E test with artificially delayed route load.

**OB-41: Graceful handling of missing target elements**
If the target element for a step is not found after route load + `nextTick()` + 100ms delay, a `MutationObserver` watches for it (scoped to the route's root element, not `document.body`). If still not found after 3 seconds, the step shows a fallback: "We couldn't find [element name]. [Skip] [Retry]".

- Acceptance: Missing element triggers scoped MutationObserver, then fallback after 3s.
- Tested by: Unit test with missing target selector; E2E test with intentionally missing element.

**OB-42: Route prefetching for tour steps**
On tour start, all routes that the tour will visit are prefetched via dynamic `import()` calls. This eliminates loading delays for the majority of step transitions.

- Acceptance: No loading spinner appears for standard step transitions after the first step.
- Tested by: E2E test measuring transition time between steps (must be < 300ms after first step).

---

### Z-Index Coordination

**OB-43: Centralized z-index scale**
Tour components use CSS custom properties for z-index values, consistent with the app's existing z-index scale:
- `--z-dropdown: 1000`
- `--z-modal: 2000`
- `--z-toast: 3000`
- `--z-tour-overlay: 4000`
- `--z-tour-spotlight: 4001`
- `--z-tour-tooltip: 4002`
- `--z-tour-progress: 4003`

- Acceptance: No z-index conflicts between tour components and app modals/dropdowns/toasts.
- Tested by: E2E test opening a modal during a tour step and verifying both are interactive.

**OB-44: Modal coordination during tour**
When a modal opens during a tour step (e.g., "Add Account" modal), the tour overlay temporarily reduces dimming or adjusts to allow modal interaction. The modal's z-index is between the overlay and tooltip. After modal closes, tour dimming resumes.

- Acceptance: User can interact with modals that open during tour steps.
- Tested by: E2E test opening and completing a modal form during the backends step.

---

### Testing

**OB-45: Unit tests for state machine**
Vitest unit tests cover: all state transitions (forward, backward, skip), substep navigation, persistence save/restore, guard evaluation, instance ID mismatch handling, and edge cases (skip from last substep, backward from first step).

- Acceptance: >= 90% branch coverage on `useTourMachine.ts`.
- Tested by: `npm run test:run` passes all state machine tests.

**OB-46: Unit tests for visual components**
Vitest + `@vue/test-utils` unit tests for: `TourOverlay` (renders, dims correctly), `TourTooltip` (content, positioning props), `TourProgressBar` (step counter, button visibility), `TourFormGuide` (field discovery, sequential highlighting), `TourSpotlight` (position calculation, padding).

- Acceptance: Each component has tests for its primary rendering states and user interactions.
- Tested by: `npm run test:run` passes all component tests.

**OB-47: E2E tests for full tour flow**
Playwright E2E tests cover: complete tour from welcome to completion, skip-all flow, persistence across reload, keyboard-only navigation, reduced motion, focus trapping, and modal interaction during tour.

- Acceptance: Playwright test suite passes in CI.
- Tested by: `npx playwright test` passes all tour E2E tests.

**OB-48: Build verification**
All tour code passes `vue-tsc` type checking and Vite production build without errors. No `any` types in tour composables or components.

- Acceptance: `just build` passes.
- Tested by: CI build step.

---

## v2 Requirements (Deferred)

These requirements are explicitly out of scope for v0.5.0 and documented for future consideration.

**OB-D01: Self-segmentation (role-based branching)**
Ask users their role (developer, team lead, admin) and customize the tour flow. Deferred because the current user base is homogeneous.

**OB-D02: Backend state sync to server API**
Persist tour progress to the backend database instead of localStorage. Enables multi-device resume. Deferred because single-user instances don't need this.

**OB-D03: Contextual everboarding hints**
After initial tour, show contextual tips when users encounter features for the first time (e.g., first time opening the bot editor). Deferred to avoid scope creep.

**OB-D04: Demo content / prefilled sample bots**
Create sample bots and configurations during onboarding so users can see the platform in action immediately. Deferred due to complexity of maintaining demo content.

**OB-D05: In-app reduced-motion toggle**
Add an in-app setting to toggle reduced motion (in addition to OS-level `prefers-reduced-motion`). Deferred because OS-level support covers the accessibility requirement.

**OB-D06: Analytics and telemetry**
Track tour completion rates, drop-off points, and step durations. Deferred because the platform is self-hosted and telemetry adds privacy concerns.

**OB-D07: Internationalization (i18n)**
All tour content hardcoded in English. Deferred because the entire app is English-only.

---

## Dependency Summary

| Package | Purpose | Size |
|---|---|---|
| `xstate` + `@xstate/vue` | State machine for tour flow | ~15 KB |
| `@floating-ui/vue` | Tooltip positioning | ~3 KB |
| `focus-trap` | Focus trapping in tooltips | ~10 KB |

**Remove:** `driver.js` (unused, validated issues).

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OB-01 | Phase 3: Welcome Flow + Tour Entry | Pending |
| OB-02 | Phase 3: Welcome Flow + Tour Entry | Pending |
| OB-03 | Phase 3: Welcome Flow + Tour Entry | Pending |
| OB-04 | Phase 1: Backend + State Machine Foundation | Pending |
| OB-05 | Phase 1: Backend + State Machine Foundation | Pending |
| OB-06 | Phase 1: Backend + State Machine Foundation | Pending |
| OB-07 | Phase 1: Backend + State Machine Foundation | Pending |
| OB-08 | Phase 1: Backend + State Machine Foundation | Pending |
| OB-09 | Phase 2: Visual Layer | Pending |
| OB-10 | Phase 2: Visual Layer | Pending |
| OB-11 | Phase 2: Visual Layer | Pending |
| OB-12 | Phase 2: Visual Layer | Pending |
| OB-13 | Phase 2: Visual Layer | Pending |
| OB-14 | Phase 2: Visual Layer | Pending |
| OB-15 | Phase 2: Visual Layer | Pending |
| OB-16 | Phase 2: Visual Layer | Pending |
| OB-17 | Phase 4: Core Step Content | Pending |
| OB-18 | Phase 4: Core Step Content | Pending |
| OB-19 | Phase 4: Core Step Content | Pending |
| OB-20 | Phase 4: Core Step Content | Pending |
| OB-21 | Phase 4: Core Step Content | Pending |
| OB-22 | Phase 9: Post-Tour Experience | Pending |
| OB-23 | Phase 9: Post-Tour Experience | Pending |
| OB-24 | Phase 9: Post-Tour Experience | Pending |
| OB-25 | Phase 5: Form Field Guidance | Pending |
| OB-26 | Phase 5: Form Field Guidance | Pending |
| OB-27 | Phase 5: Form Field Guidance | Pending |
| OB-28 | Phase 5: Form Field Guidance | Pending |
| OB-29 | Phase 6: Navigation Controls | Pending |
| OB-30 | Phase 6: Navigation Controls | Pending |
| OB-31 | Phase 6: Navigation Controls | Pending |
| OB-32 | Phase 6: Navigation Controls | Pending |
| OB-33 | Phase 6: Navigation Controls | Pending |
| OB-34 | Phase 9: Post-Tour Experience | Pending |
| OB-35 | Phase 9: Post-Tour Experience | Pending |
| OB-35a | Phase 9: Post-Tour Experience | Pending |
| OB-36 | Phase 8: Accessibility | Pending |
| OB-37 | Phase 8: Accessibility | Pending |
| OB-38 | Phase 8: Accessibility | Pending |
| OB-39 | Phase 8: Accessibility | Pending |
| OB-40 | Phase 7: Loading + Error Resilience | Pending |
| OB-41 | Phase 7: Loading + Error Resilience | Pending |
| OB-42 | Phase 7: Loading + Error Resilience | Pending |
| OB-43 | Phase 1: Backend + State Machine Foundation | Pending |
| OB-44 | Phase 7: Loading + Error Resilience | Pending |
| OB-45 | Phase 10: Integration Testing | Pending |
| OB-46 | Phase 10: Integration Testing | Pending |
| OB-47 | Phase 10: Integration Testing | Pending |
| OB-48 | Phase 10: Integration Testing | Pending |
