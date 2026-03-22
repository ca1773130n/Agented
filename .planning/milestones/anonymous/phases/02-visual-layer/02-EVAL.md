# Evaluation Plan: Phase 2 — Visual Layer

**Designed:** 2026-03-22
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** TourSpotlight (box-shadow dimming), TourTooltip (Floating UI useFloating + Virtual Element Bridge), TourProgressBar (bottom controls bar), TourOverlay orchestrator refactor
**Reference:** 02-RESEARCH.md (Floating UI useFloating docs, box-shadow dimming technique, CSS transitions), 02-01-PLAN.md, 02-02-PLAN.md

## Evaluation Overview

This phase delivers all visual tour components. Two plans execute in sequence: Plan 01 extracts TourSpotlight and replaces hardcoded colors/z-index values with CSS custom properties; Plan 02 adds TourTooltip (Floating UI positioned) and TourProgressBar, wiring all three as children of TourOverlay.

What CAN be verified at this stage: TypeScript compilation correctness, unit test behavior of all components under mock conditions, static analysis of source files for hardcoded color/z-index violations, presence of required architectural patterns (ResizeObserver, useFloating import, Virtual Element Bridge), and structural properties (pointer-events: none on overlay, CSS transition presence). What CANNOT be verified without a running browser: whether the tooltip never clips at real viewport edges (depends on actual layout + Floating UI runtime), whether CSS transitions are visually smooth (requires a rendered browser, not jsdom), whether the spotlight accurately tracks elements through real resize/scroll events, and whether box-shadow dimming does not interfere with real user interactions.

No performance benchmarks file exists for this project. Targets are derived from the requirements in 02-01-PLAN.md and 02-02-PLAN.md success criteria, and the phase goal stated in eval_context. The Floating UI library is the authoritative reference for tooltip positioning correctness — if flip() and shift() middleware are configured correctly per the research recommendations, viewport-edge handling is guaranteed by the library.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Zero hardcoded hex/rgb/rgba in tour `<style>` blocks | 02-01-PLAN.md#truths, 02-02-PLAN.md#truths | Required invariant — theme change resilience |
| Zero hardcoded z-index numbers in tour `<style>` blocks | 02-01-PLAN.md#truths, 02-02-PLAN.md#truths | Required invariant — stacking context controlled via CSS vars |
| `@floating-ui/vue ^1.1.11` present in package.json | 02-01-PLAN.md#success_criteria | Dependency correctness |
| `useFloating` imported in TourTooltip | 02-02-PLAN.md#truths | Architecture correctness — tooltip MUST use Floating UI |
| ResizeObserver present in TourOverlay | 02-01-PLAN.md#success_criteria | Spotlight reflow tracking requirement |
| All tour unit tests green | 02-01-PLAN.md#verification, 02-02-PLAN.md#verification | Component behavior contracts |
| `just build` passes (vue-tsc + vite) | 02-01-PLAN.md#verification, 02-02-PLAN.md#success_criteria | TypeScript type correctness end-to-end |
| Backend tests unaffected | 02-02-PLAN.md#verify | Non-regression: pure frontend phase |
| Tooltip viewport-edge handling (flip + shift) | 02-RESEARCH.md#recommendation-1 | Deferred — requires real browser rendering |
| Step transition smoothness (no flicker) | Phase goal, 02-02-PLAN.md#truths | Deferred — requires running app with step definitions |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 10 | Basic functionality, static analysis, structural checks |
| Proxy (L2) | 3 | Automated unit tests and build — indirect quality evidence |
| Deferred (L3) | 4 | Full visual/interaction validation requiring running browser |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before progression to Phase 3.

### S1: @floating-ui/vue installed in package.json
- **What:** The dependency is present at the correct version range
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm ls @floating-ui/vue`
- **Expected:** `@floating-ui/vue@1.1.x` appears in the output (no unmet peer warnings)
- **Failure means:** Plan 01 Task 1 was not completed — TourTooltip will fail at import time

### S2: Tour CSS custom properties defined in App.vue
- **What:** The 7 tour-specific CSS custom properties added in Plan 01 Task 1 are present in `:root`
- **Command:** `grep -c 'tour-overlay-dim\|tour-spotlight-radius\|tour-spotlight-padding\|tour-glow-color\|tour-glow-dim\|tour-glow-bright\|tour-transition-speed' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/App.vue`
- **Expected:** `7` (all seven properties present)
- **Failure means:** Plan 01 Task 1 App.vue edits were skipped or partial — components will fall back to browser defaults

### S3: Zero hardcoded color values across all four tour components
- **What:** No `#hex`, `rgb(`, or `rgba(` literals appear in the `<style>` blocks of any tour component
- **Command:** `grep -rn '#[0-9a-fA-F]\{3,\}\|rgba\?\s*(' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourOverlay.vue /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourSpotlight.vue /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourTooltip.vue /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourProgressBar.vue 2>/dev/null`
- **Expected:** No output (zero matches)
- **Failure means:** Hardcoded color value slipped through — theme will break in light mode or when CSS vars change

### S4: Zero hardcoded z-index numbers across all four tour components
- **What:** No `z-index: [number]` appears in any tour component `<style>` block
- **Command:** `grep -rn 'z-index:\s*[0-9]' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourOverlay.vue /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourSpotlight.vue /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourTooltip.vue /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourProgressBar.vue 2>/dev/null`
- **Expected:** No output (zero matches)
- **Failure means:** Hardcoded z-index bypasses the `--z-tour-*` scale — stacking conflicts will not be fixable via CSS vars

### S5: TourSpotlight exists and is imported by TourOverlay
- **What:** TourSpotlight.vue was created and TourOverlay imports it
- **Command:** `test -f /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourSpotlight.vue && grep -c 'TourSpotlight' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourOverlay.vue`
- **Expected:** File exists (exit code 0) + grep returns `>= 1`
- **Failure means:** Plan 01 Task 2 was not completed — TourOverlay still contains the spotlight inline

### S6: TourOverlay imports all three child components
- **What:** TourOverlay is the orchestrator rendering TourSpotlight + TourTooltip + TourProgressBar
- **Command:** `grep -c 'TourSpotlight\|TourTooltip\|TourProgressBar' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourOverlay.vue`
- **Expected:** `3` (all three imports present; each grep match counted)
- **Failure means:** Plan 02 Task 2 integration was not completed

### S7: TourTooltip uses useFloating from @floating-ui/vue
- **What:** Tooltip positioning is done via Floating UI, not manual coordinate math
- **Command:** `grep -c 'useFloating' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourTooltip.vue`
- **Expected:** `>= 1`
- **Failure means:** Tooltip was implemented with manual positioning — viewport-edge handling will be fragile

### S8: ResizeObserver present in TourOverlay for content reflow tracking
- **What:** Spotlight repositioning on content reflow uses ResizeObserver (not just scroll/resize listeners)
- **Command:** `grep -c 'ResizeObserver' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourOverlay.vue`
- **Expected:** `>= 1`
- **Failure means:** Spotlight will not reposition when lazy-loaded content pushes the target element — violates success criterion 2

### S9: CSS transition present on spotlight for step movement
- **What:** Spotlight uses CSS transitions (not JS animation) for smooth step-to-step movement
- **Command:** `grep -c 'transition' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourSpotlight.vue`
- **Expected:** `>= 1`
- **Failure means:** Step changes will cause an abrupt jump in spotlight position

### S10: Backend unaffected (no Python changes)
- **What:** Phase 2 is pure frontend — backend tests must still pass with zero regressions
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/backend && uv run pytest -x -q`
- **Expected:** All tests pass, exit code 0
- **Failure means:** An unintended backend file was modified, or the test environment has a regression from Phase 1

**Sanity gate:** ALL ten sanity checks must pass. Any failure blocks progression to Phase 3.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evidence of implementation correctness through automated testing and build verification.
**IMPORTANT:** These proxy metrics measure structural and behavioral correctness in a jsdom environment. They do NOT validate visual appearance, real browser rendering, or actual tooltip clipping behavior. Treat results with appropriate skepticism for visual requirements.

### P1: Full build passes (vue-tsc + vite)
- **What:** TypeScript type-checking and Vite production build complete without errors
- **How:** Run the project-standard build command
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented && just build`
- **Target:** Exit code 0, no TypeScript errors, no type: `any` escapes in tour component types, build artifact produced
- **Evidence:** `02-01-PLAN.md#verification` and `02-02-PLAN.md#success_criteria` both specify this as a required verification. TypeScript correctness of the `useFloating` composable types, `DOMRect | null` prop types, and Virtual Element Bridge pattern are only verified at compile time.
- **Correlation with full metric:** HIGH — TypeScript type errors predict runtime failures. If Floating UI types resolve correctly, the composable is called correctly.
- **Blind spots:** Build passing does not verify visual correctness. A component can compile correctly and still position a tooltip wrong. jsdom-based type checking does not test CSS property inheritance at runtime.
- **Validated:** No — visual correctness deferred to DEFER-02-03 and DEFER-02-04

### P2: All tour unit tests pass
- **What:** Vitest unit test suite for all tour components runs green — TourOverlay, TourSpotlight, TourTooltip, TourProgressBar
- **How:** Run the frontend test suite
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm run test:run`
- **Target:** All tests pass, zero failures. Tests cover: TourSpotlight (does not render when targetRect null, renders with correct inline styles, box-shadow present, pointer-events: none, CSS custom property compliance), TourTooltip (does not render when invisible or targetRect null, renders title/message, arrow element present, useFloating called), TourProgressBar (step counter shows "STEP N OF M", skip button conditional on skippable prop, next/skip emits), TourOverlay updated (TourSpotlight/TourTooltip/TourProgressBar as children, behavioral tests preserved)
- **Evidence:** Unit tests for each component are mandated by 02-01-PLAN.md and 02-02-PLAN.md. The CSS custom property compliance test in each test file reads the `.vue` source and asserts zero hardcoded color values — this is a static analysis check embedded in the test suite per the research verification strategy.
- **Correlation with full metric:** MEDIUM — jsdom does not render CSS, so tests verify component structure and props/emits behavior, not visual output. Floating UI is mocked in TourTooltip tests, so actual positioning middleware is not exercised.
- **Blind spots:** Tests cannot verify: actual overlay dimming effect, spotlight position accuracy in a real viewport, tooltip flip behavior at real viewport edges, transition smoothness, or pointer-events pass-through behavior (requires real browser events).
- **Validated:** No — visual/interaction correctness deferred to DEFER-02-03 and DEFER-02-04

### P3: CSS custom property static analysis embedded in tests
- **What:** TourSpotlight, TourTooltip, and TourProgressBar each include a test that reads the `.vue` source file and asserts zero hardcoded `#hex`/`rgb()`/`rgba()` matches in the `<style>` block
- **How:** Each test file (per 02-01-PLAN.md and 02-02-PLAN.md specifications) implements a static analysis check by reading the source at `fs.readFileSync(path.resolve(...TourSpotlight.vue))` and searching for color patterns
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm run test:run -- --reporter=verbose`
- **Target:** All CSS compliance assertions pass — count of hardcoded color matches is 0 for each component
- **Evidence:** The research verification strategy (02-01-PLAN.md Task 2 verify section) explicitly specifies this pattern. The `grep -rn '#[0-9a-fA-F]\{3,\}\|rgba\?\s*('` check is the canonical source-of-truth validation.
- **Correlation with full metric:** HIGH — if source contains no hardcoded color values, the CSS custom properties requirement is met by definition
- **Blind spots:** Does not check inline styles on template elements (JavaScript-computed styles). Inline styles for spotlight position (top/left/width/height) are expected — those are coordinate values, not color values.
- **Validated:** No — only confirms source compliance, not that CSS vars resolve to correct values at runtime

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring a running browser, real DOM layout, and visual inspection.

### D1: Spotlight accurately tracks target elements through resize and scroll — DEFER-02-01
- **What:** The spotlight highlight rect matches the target element's viewport position within 1px tolerance after window resize, parent scroll, and content reflow events
- **How:** Manual inspection in a running app: resize the browser window while a tour is active, scroll the page, trigger content reflow (e.g., expand an accordion above the target), verify spotlight repositions correctly within one animation frame
- **Why deferred:** Requires a running app with active tour steps. TourOverlay's scroll/resize/ResizeObserver listeners cannot be tested in jsdom — JSDOM does not fire real scroll events or compute real layout.
- **Validates at:** `phase-10-integration-testing`
- **Depends on:** Phase 4 (step definitions — need actual tour steps targeting real elements) + running dev server
- **Target:** Spotlight rect within 1px of `element.getBoundingClientRect()` within 16ms (one animation frame at 60fps) of any position-changing event
- **Risk if unmet:** Users see the spotlight highlighting an empty area while the actual element has moved. This is a critical UX failure — requires revisiting the tracking implementation (possibly switching to `autoUpdate` for spotlight as well as tooltip).
- **Fallback:** Add `autoUpdate` from @floating-ui/dom to spotlight tracking as an alternative to manual scroll/resize listeners

### D2: Tooltip never clipped at any viewport edge — DEFER-02-02
- **What:** TourTooltip remains fully visible in the viewport regardless of where the target element is — top-left corner, top-right corner, bottom edge, left/right edges, small viewport
- **How:** With a running app and step definitions: manually move through steps whose targets are near each viewport edge. Also test at narrow viewport (375px mobile width). Verify tooltip auto-flips to the opposite side and never overflows the viewport.
- **Why deferred:** Requires real browser rendering with actual CSS layout. Floating UI's flip() and shift() middleware only compute positions when `computePosition` runs against a real DOM. jsdom does not compute layout.
- **Validates at:** `phase-10-integration-testing`
- **Depends on:** Phase 4 (step definitions with targets at various screen positions) + running dev server in a real browser
- **Target:** Zero tooltip clipping events across all defined tour steps at 1440px and 375px viewport widths
- **Risk if unmet:** Tooltip text is hidden behind viewport edge during tour — users cannot read step instructions. Medium probability (Floating UI middleware is well-tested, but misconfiguration of offset/padding values is possible).
- **Fallback:** Adjust middleware parameters (offset distance, shift padding) — no architectural change needed, only configuration tuning

### D3: Step transition smoothness — no flicker or jump — DEFER-02-03
- **What:** When advancing from one tour step to the next, the spotlight smoothly animates to the new position and the tooltip fades out/in without flickering or teleporting
- **How:** Visual inspection with a running app. Advance through all defined tour steps and verify: spotlight slides from old to new position over ~200ms, tooltip fades out before position update and fades back in, no intermediate frames show tooltip at wrong position
- **Why deferred:** CSS transition smoothness requires a rendered browser with a running compositor. Requires Phase 4 step definitions with multiple steps to advance through.
- **Validates at:** `phase-10-integration-testing`
- **Depends on:** Phase 4 (step definitions) + Phase 2 visual components integrated
- **Target:** No frame with tooltip at incorrect position between steps (verified by video frame inspection if needed). Transition duration between 180-250ms (visually perceptible as smooth, not instant or slow).
- **Risk if unmet:** Flickering during step transitions is a noticeable UX defect. Low-medium probability — the two-phase opacity approach specified in 02-02-PLAN.md is designed to prevent this, but timing coordination between fade-out and position update may need tuning.
- **Fallback:** Adjust `--tour-transition-speed` value or add a `nextTick()` await between fade phases if timing is off

### D4: pointer-events pass-through — highlighted elements remain interactive — DEFER-02-04
- **What:** Elements highlighted by the spotlight are fully clickable and typeable — the overlay does not intercept mouse or keyboard events. Tour UI controls (buttons) still respond to clicks.
- **How:** With a running app: during an active tour step, click on the highlighted element (e.g., a button, input field). Verify the click registers. Also verify that typing into a highlighted form input works. Then click the tour's Next/Skip buttons to verify controls respond.
- **Why deferred:** Real pointer event behavior cannot be tested in jsdom. `pointer-events: none` CSS behavior requires a real browser event system.
- **Validates at:** `phase-10-integration-testing`
- **Depends on:** Phase 4 (step definitions targeting interactive elements) + running app
- **Target:** 100% of highlighted element interactions succeed (no blocked clicks or typed characters lost). 100% of tour control clicks register.
- **Risk if unmet:** The entire tour premise fails — users cannot complete the actions the tour instructs. High impact if unmet. Low probability — the `pointer-events: none` on overlay with `pointer-events: auto` on controls is a well-established pattern already proven in the original TourOverlay.vue.
- **Fallback:** Audit z-index stacking and pointer-events declarations; the pattern is proven, so failure likely indicates a CSS ordering bug introduced during refactor

---

## Ablation Plan

**Purpose:** Isolate which architectural decisions contribute to correctness.

### A1: Verify Virtual Element Bridge is necessary (not just `ref` on a DOM element)
- **Condition:** Remove the `computed` Virtual Element wrapper in TourTooltip; instead try passing the DOM element directly to `useFloating` as a ref
- **Expected impact:** Tooltip stops updating when targetRect changes across steps — position gets stale
- **Command:** `# Manual code change + visual test — not automatable without running browser`
- **Evidence:** 02-RESEARCH.md Recommendation 1 explains that tooltip cannot hold a direct ref to the target element (it doesn't own the target); 02-02-PLAN.md Research Pitfall 3 identifies this as a common mistake
- **Note:** This ablation is only relevant if DEFER-02-02 reveals stale positioning. It is described here for debugging reference, not routine execution.

### A2: Verify box-shadow dimming vs. full-viewport overlay
- **Condition:** Replace box-shadow technique with a full-viewport `rgba(0,0,0,0.7)` div plus a transparent cutout (SVG clip-path) for the spotlight
- **Expected impact:** Similar visual result but significantly more complex — no performance or quality gain
- **Evidence:** 02-RESEARCH.md Alternatives Considered: "SVG clip-path can create precise cutouts but is harder to animate, doesn't support border-radius as easily, and adds complexity."
- **Note:** This ablation is documented to confirm the box-shadow choice is justified. No implementation needed — box-shadow technique is already proven in the existing codebase.

---

## WebMCP Tool Definitions

This phase modifies frontend components: TourOverlay.vue, TourSpotlight.vue (new), TourTooltip.vue (new), TourProgressBar.vue (new). These are overlay/tour components rendered on top of all views — they do not constitute a standalone page, but they render within the existing app shell.

WebMCP tool definitions skipped — MCP availability not confirmed in eval context. The phase modifies tour overlay components which are not independently accessible as a page URL; they require active tour state to render. Visual verification is deferred to DEFER-02-01 through DEFER-02-04 in the integration testing phase.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Current TourOverlay.vue hardcoded color count | Existing component has 19 color matches before refactor | 0 after Phase 2 (100% reduction) | `grep -c '#[0-9a-fA-F]\|rgba\?\s*(' frontend/src/components/tour/TourOverlay.vue` pre-phase result |
| Current TourOverlay.vue z-index count | Existing component has 4 hardcoded z-index values | 0 after Phase 2 (100% reduction) | `grep -n 'z-index:\s*[0-9]' frontend/src/components/tour/TourOverlay.vue` pre-phase |
| Frontend test count (pre-phase) | 1 test file for TourOverlay | 4 test files (TourOverlay + TourSpotlight + TourTooltip + TourProgressBar) after Phase 2 | `ls frontend/src/components/tour/__tests__/` pre-phase |
| Backend test suite | Established in Phase 1 | Same pass rate (no regressions) | `cd backend && uv run pytest -q` |

---

## Evaluation Scripts

**Location of evaluation code:**
```
frontend/src/components/tour/__tests__/TourOverlay.test.ts
frontend/src/components/tour/__tests__/TourSpotlight.test.ts       (created in 02-01)
frontend/src/components/tour/__tests__/TourTooltip.test.ts         (created in 02-02)
frontend/src/components/tour/__tests__/TourProgressBar.test.ts     (created in 02-02)
```

**How to run full evaluation:**
```bash
# Sanity gate — static checks (run from project root)
cd /Users/neo/Developer/Workspaces/projects/Agented

# S1: Dependency check
cd frontend && npm ls @floating-ui/vue && cd ..

# S3 + S4: Hardcoded color/z-index static analysis
grep -rn '#[0-9a-fA-F]\{3,\}\|rgba\?\s*(' frontend/src/components/tour/TourOverlay.vue frontend/src/components/tour/TourSpotlight.vue frontend/src/components/tour/TourTooltip.vue frontend/src/components/tour/TourProgressBar.vue
grep -rn 'z-index:\s*[0-9]' frontend/src/components/tour/TourOverlay.vue frontend/src/components/tour/TourSpotlight.vue frontend/src/components/tour/TourTooltip.vue frontend/src/components/tour/TourProgressBar.vue

# P1: Full build
just build

# P2 + P3: Unit tests (includes CSS compliance static analysis)
cd frontend && npm run test:run

# S10: Backend non-regression
cd backend && uv run pytest -x -q
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: @floating-ui/vue installed | [PASS/FAIL] | | |
| S2: Tour CSS custom properties in App.vue | [PASS/FAIL] | count: | |
| S3: Zero hardcoded colors in tour components | [PASS/FAIL] | matches: | |
| S4: Zero hardcoded z-index in tour components | [PASS/FAIL] | matches: | |
| S5: TourSpotlight exists + imported | [PASS/FAIL] | | |
| S6: TourOverlay imports all three children | [PASS/FAIL] | count: | |
| S7: TourTooltip uses useFloating | [PASS/FAIL] | count: | |
| S8: ResizeObserver in TourOverlay | [PASS/FAIL] | count: | |
| S9: CSS transition in TourSpotlight | [PASS/FAIL] | count: | |
| S10: Backend tests pass | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Build passes | Exit 0, no TS errors | | [MET/MISSED] | |
| P2: All tour unit tests pass | 0 failures | | [MET/MISSED] | |
| P3: CSS compliance tests embedded | 0 hardcoded color assertions fail | | [MET/MISSED] | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Virtual Element Bridge necessity | N/A — deferred to debugging reference | N/A | Documented, not executed |
| A2: box-shadow vs SVG clip-path | N/A — confirmed by research | N/A | box-shadow choice confirmed |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-02-01 | Spotlight tracks through resize/scroll/reflow | PENDING | phase-10-integration-testing |
| DEFER-02-02 | Tooltip never clipped at viewport edges | PENDING | phase-10-integration-testing |
| DEFER-02-03 | Step transition smoothness (no flicker) | PENDING | phase-10-integration-testing |
| DEFER-02-04 | pointer-events pass-through — elements interactive | PENDING | phase-10-integration-testing |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM-HIGH

**Justification:**
- Sanity checks: Adequate — 10 automated checks cover all required architectural properties and static code invariants. Commands are exact and runnable without a browser.
- Proxy metrics: Well-evidenced — build + unit tests + embedded static analysis are the appropriate automated verification layer for a Vue component refactor. The limitation is that jsdom cannot render CSS or fire real pointer events, which is an inherent constraint of the testing environment, not a gap in the evaluation design.
- Deferred coverage: Comprehensive — all four success criteria that require a running browser are covered by DEFER-02-01 through DEFER-02-04, each with explicit validates_at references to phase-10-integration-testing.

**What this evaluation CAN tell us:**
- Whether the component architecture matches the specification (4 components, correct import graph, orchestrator pattern)
- Whether all hardcoded color and z-index values have been replaced with CSS custom properties
- Whether TypeScript types are correct for Floating UI composable usage and prop interfaces
- Whether component behavior under mock conditions (jsdom) matches the spec (step counter, conditional buttons, emits, conditional rendering)
- Whether @floating-ui/vue is installed and useable

**What this evaluation CANNOT tell us:**
- Whether the tooltip actually stays within the viewport at real screen edges (answered at DEFER-02-02 / phase-10)
- Whether the spotlight accurately tracks target elements through real scroll and resize (answered at DEFER-02-01 / phase-10)
- Whether CSS transitions are visually smooth or exhibit flicker in a real browser (answered at DEFER-02-03 / phase-10)
- Whether pointer-events pass-through works correctly so highlighted elements are clickable (answered at DEFER-02-04 / phase-10)

The four deferred items are inherent to visual/interactive UI work — no automated test short of Playwright/Cypress browser testing can validate them. Phase 10 integration testing addresses all four.

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-22*
