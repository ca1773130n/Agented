# Evaluation Plan: Phase 10 — Integration Testing

**Designed:** 2026-03-22
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** XState v5 unit testing (createActor pattern), Vue composable testing (module-reset pattern), Playwright E2E testing, v8 coverage enforcement, vue-tsc type safety audit
**Reference:** 10-RESEARCH.md (XState v5 testing docs, Vitest coverage, Playwright patterns)

## Evaluation Overview

Phase 10 is the final validation gate for the entire onboarding tour system built across Phases 1-9. Unlike prior phases that deferred evaluation due to missing integration, this phase exists specifically to verify what was deferred. It resolves six deferred validation items from Phases 1, 2, 4, 6, and 8.

The four plans in this phase divide cleanly by verification character. Plans 10-01 and 10-02 (Wave 1) produce measurable, automated proxy metrics: unit test coverage percentages for `tourMachine.ts` and `useTourMachine.ts`. Plan 10-03 (Wave 2) produces the E2E results that resolve the deferred phase validations — complete tour flow, skip-all, persistence, keyboard navigation, reduced motion, and focus trapping in a real browser. Plan 10-04 (Wave 3) locks the type safety and coverage enforcement as a permanent build gate.

What CAN be verified: all state machine transitions and guards via XState actor API, localStorage persistence round-trip, instance_id mismatch detection, component rendering states and emitted events, full browser tour flows including keyboard navigation and page reload, TypeScript strictness, and absence of `any` types. What CANNOT be verified without manual testing: screen reader compatibility beyond programmatic focus assertions, visual design quality of the overlay rendering, and cross-browser behavior beyond Chromium (only Chromium is configured in the existing Playwright setup).

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| >= 90% branch coverage on tourMachine.ts | 10-01-PLAN.md#must_haves, ROADMAP.md Phase 10 target | Direct measure of transition path completeness |
| >= 90% branch coverage on useTourMachine.ts | 10-02-PLAN.md#must_haves | Direct measure of composable logic completeness |
| >= 12 TourOverlay component tests | 10-02-PLAN.md#success_criteria | Covers all rendering states including edge cases |
| >= 7 E2E scenarios across 2 spec files | 10-03-PLAN.md#success_criteria | Resolves all deferred validations from prior phases |
| Zero vue-tsc errors | 10-04-PLAN.md#must_haves | Type safety gate — no `any` escapes |
| All tests pass (backend + frontend) | CLAUDE.md#verification | Non-regression against entire codebase |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 7 | Build, test suite pass, file existence, zero type errors |
| Proxy (L2) | 5 | Coverage thresholds, E2E flow passes, static analysis |
| Deferred (L3) | 2 | Screen reader compatibility, cross-browser visual verification |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before the phase is considered complete.

### S1: Full build passes with zero vue-tsc errors
- **What:** TypeScript strict compilation of all tour files (tourMachine.ts, useTourMachine.ts, TourOverlay.vue, all new test files) succeeds
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented && just build`
- **Expected:** Exit code 0, no TypeScript errors in output
- **Failure means:** A tour file has a type error — likely in a new test file using `as any` or in a type mismatch between composable and machine. Fix before proceeding.

### S2: Backend tests pass (non-regression)
- **What:** No existing backend tests broken by this purely frontend phase
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/backend && uv run pytest -x -q`
- **Expected:** Exit code 0. Note: 01-01-SUMMARY.md flagged pre-existing failures in App.test.ts and WelcomePage.test.ts — these are acceptable if they pre-date this phase.
- **Failure means:** If new failures appear, investigate immediately. Pre-existing failures are documented in 01-01-SUMMARY.md.

### S3: All frontend unit tests pass
- **What:** Entire Vitest suite passes, including the new tour machine and composable tests
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm run test:run`
- **Expected:** Exit code 0, no test failures
- **Failure means:** A new test file has a failing assertion or import error. The most likely culprits are singleton leakage in useTourMachine.test.ts (missing vi.resetModules()) or an XState v5 API mismatch in tourMachine.test.ts.

### S4: tourMachine.test.ts exists with required minimum size
- **What:** The state machine test file was created with substantive test coverage (not a stub)
- **Command:** `wc -l /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/machines/__tests__/tourMachine.test.ts`
- **Expected:** >= 200 lines
- **Failure means:** Plan 10-01 was not completed or test file was truncated

### S5: useTourMachine.test.ts exists with required minimum size
- **What:** The composable test file was created with substantive test coverage
- **Command:** `wc -l /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/composables/__tests__/useTourMachine.test.ts`
- **Expected:** >= 200 lines
- **Failure means:** Plan 10-02 was not completed

### S6: Zero `any` types in tour source files
- **What:** No `: any` or `as any` patterns in the tour source code (tests excluded — `as unknown as Type` is allowed in mocks)
- **Command:** `grep -rn ': any\|as any' /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/machines/tourMachine.ts /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/composables/useTourMachine.ts /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourOverlay.vue`
- **Expected:** No output (zero matches)
- **Failure means:** A tour source file uses `any` — replace with proper type or `unknown`

### S7: E2E spec files exist and parse without errors
- **What:** Playwright spec files are syntactically valid TypeScript and the fixture compiles
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npx playwright test --list e2e/tests/tour-flow.spec.ts e2e/tests/tour-persistence.spec.ts 2>&1 | head -20`
- **Expected:** Lists at least 7 test names, no parse/import errors
- **Failure means:** Spec file has a syntax error, wrong import path for tour fixture, or fixture extends the wrong base

**Sanity gate:** ALL sanity checks must pass. Any failure blocks phase completion.

---

## Level 2: Proxy Metrics

**Purpose:** Automated measurement of quality properties that directly correspond to the phase success criteria.
**IMPORTANT:** Coverage numbers are measured by the v8 provider — they count code branches exercised by tests, not necessarily behavioral correctness under all real-world conditions.

### P1: tourMachine.ts branch coverage >= 90%
- **What:** The percentage of code branches in the XState machine definition exercised by tourMachine.test.ts
- **How:** Run Vitest with coverage, scope to tourMachine.ts, check the branch % in the text report
- **Command:**
  ```bash
  cd /Users/neo/Developer/Workspaces/projects/Agented/frontend
  npx vitest run src/machines/__tests__/tourMachine.test.ts \
    --coverage \
    --coverage.include='src/machines/tourMachine.ts' \
    --reporter=verbose 2>&1 | grep -E "tourMachine|Branch|branch|%"
  ```
- **Target:** >= 90% branch coverage on `src/machines/tourMachine.ts`
- **Evidence:** 10-RESEARCH.md#recommendation-4 — v8 provider measures branch coverage for TypeScript. The machine has exactly 10 states and a fixed set of guard conditions (canSkipAll, markStepCompleted) — 90% is achievable with complete transition coverage. Prior phase 01-EVAL.md set 80% as proxy target; this phase upgrades to 90% as the final gate per ROADMAP.md Phase 10 target.
- **Correlation with full metric:** HIGH — directly measures what the plan requires. Branches in `tourMachine.ts` correspond to individual guard evaluations and transition handlers. Missing branches indicate untested transition paths.
- **Blind spots:** v8 coverage counts syntactic branches, not semantic transition pairs. A test that sends `NEXT` without asserting the resulting state could count as "covered" without validating correctness. Tests MUST include `expect(actor.getSnapshot().value)` assertions.
- **Validated:** No — awaiting confirmation via vitest run during phase execution

### P2: useTourMachine.ts branch coverage >= 90%
- **What:** The percentage of code branches in the composable exercised by useTourMachine.test.ts
- **How:** Run Vitest with coverage, scope to useTourMachine.ts
- **Command:**
  ```bash
  cd /Users/neo/Developer/Workspaces/projects/Agented/frontend
  npx vitest run src/composables/__tests__/useTourMachine.test.ts \
    --coverage \
    --coverage.include='src/composables/useTourMachine.ts' \
    --reporter=verbose 2>&1 | grep -E "useTourMachine|Branch|branch|%"
  ```
- **Target:** >= 90% branch coverage on `src/composables/useTourMachine.ts`
- **Evidence:** 10-RESEARCH.md#recommendation-4 and 10-02-PLAN.md#must_haves. The composable has localStorage read/write paths, fetch success/failure paths, schema version mismatch, instance-id mismatch, and checkAndAutoAdvance API paths — all independently testable via mock injection.
- **Correlation with full metric:** MEDIUM-HIGH — the composable's localStorage and fetch paths are fully mockable, so coverage translates directly to logic path coverage. The one area where coverage overstates quality: async timing in `checkAndAutoAdvance` — a covered branch doesn't guarantee correct timing behavior in a real Vue component lifecycle.
- **Blind spots:** Does not test actual localStorage quota behavior, does not test the composable mounted inside a real Vue component (only via dynamic import pattern), does not test concurrent initialization from two components.
- **Validated:** No — awaiting confirmation via vitest run during phase execution

### P3: Full vitest suite coverage thresholds enforced in config
- **What:** vitest.config.ts has been updated to enforce the >= 90% branch threshold for tour files, making future regressions fail the CI coverage check automatically
- **How:** Inspect vitest.config.ts for the `thresholds` section and confirm targets are set
- **Command:**
  ```bash
  grep -A 20 "thresholds" /Users/neo/Developer/Workspaces/projects/Agented/frontend/vitest.config.ts
  ```
- **Target:** `thresholds` block exists with `branches: 90` for both `src/machines/tourMachine.ts` and `src/composables/useTourMachine.ts`
- **Evidence:** 10-04-PLAN.md#task-1 specifies the exact threshold config. Vitest v4 supports per-file pattern thresholds (vitest.dev/guide/coverage#coverage-thresholds). Current vitest.config.ts has no thresholds — this plan adds them.
- **Correlation with full metric:** HIGH — this is a deterministic structural check, not a stochastic proxy. Either the config contains the thresholds or it doesn't.
- **Blind spots:** Per-file threshold syntax for Vitest v4 may differ from v3 — if the path-pattern form is unsupported, a global threshold floor is acceptable as documented in 10-04-PLAN.md note.
- **Validated:** No — awaiting plan 10-04 execution

### P4: All Playwright E2E tour tests pass in headless mode
- **What:** The 7+ E2E scenarios across tour-flow.spec.ts and tour-persistence.spec.ts all pass with mocked API endpoints
- **How:** Run Playwright against the dev servers (or webServer config) in headless mode
- **Command:**
  ```bash
  cd /Users/neo/Developer/Workspaces/projects/Agented/frontend
  npx playwright test e2e/tests/tour-flow.spec.ts e2e/tests/tour-persistence.spec.ts \
    --reporter=list 2>&1
  ```
- **Target:** All tests pass (exit code 0), specifically: complete flow, skip-all, keyboard navigation, persistence-across-reload, instance-id-mismatch, reduced-motion, focus-trap
- **Evidence:** 10-03-PLAN.md#success_criteria. These tests resolve deferred items from Phases 2, 4, 6, and 8. The mocked API approach (extending base.ts fixture) is the established project pattern used in 16+ existing E2E specs — infrastructure reliability is HIGH.
- **Correlation with full metric:** HIGH for functional flows (complete/skip/keyboard). MEDIUM for accessibility flows (reduced motion, focus trap) — Playwright can verify `transitionDuration: 0s` but cannot replace manual screen reader testing.
- **Blind spots:** Headless mode does not catch visual rendering regressions. The E2E tests use CSS selectors — if component class names change, tests break without reflecting a real functional regression. E2E tests run against mocked APIs — real backend behavior (race conditions, slow responses) is not tested.
- **Validated:** No — requires running dev servers during phase execution

### P5: TourOverlay.test.ts has >= 12 tests and all pass
- **What:** Expanded component tests cover all rendering states including edge cases
- **How:** Run TourOverlay tests with verbose reporter, count test cases
- **Command:**
  ```bash
  cd /Users/neo/Developer/Workspaces/projects/Agented/frontend
  npx vitest run src/components/tour/__tests__/TourOverlay.test.ts --reporter=verbose 2>&1 | grep -E "✓|✗|PASS|FAIL|test"
  ```
- **Target:** >= 12 total tests, all passing (8 existing + >= 4 new from plan 10-02)
- **Evidence:** 10-02-PLAN.md#success_criteria. Existing 8 tests cover core behavior; new tests cover step counter display, substep label presence/absence, rapid click handling, and null step resilience.
- **Correlation with full metric:** MEDIUM — component unit tests in happy-dom do not test actual CSS rendering. They verify emit events and DOM structure but cannot verify visual appearance.
- **Blind spots:** happy-dom does not execute CSS transitions or compute layout. Tests verify that the correct classes/text are present in the rendered DOM but not that they produce a correct visual result.
- **Validated:** No — awaiting plan 10-02 execution

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation that cannot be completed in an automated test environment.

### D1: Screen reader compatibility — DEFER-10-01
- **What:** The tour overlay is fully navigable with VoiceOver (macOS) or NVDA (Windows): step announcements are read, button labels are correctly described, and no focus is lost during transitions
- **How:** Manual test with VoiceOver: start the tour, navigate with VO+arrow keys through the overlay, verify step content is announced, verify Next/Skip button labels are heard, verify focus returns to tour controls after each transition
- **Why deferred:** Playwright can assert `aria-label` attributes and programmatic focus, but it cannot verify what a screen reader actually announces. VoiceOver behavior depends on browser/OS rendering stack not present in headless Chromium.
- **Validates at:** manual-review-post-phase-10
- **Depends on:** Running app with TourOverlay rendered (Phase 2 work), correct `aria-live` regions and `role` attributes on overlay (Phase 8 work)
- **Target:** All step text announced on transition, Next/Skip buttons have descriptive labels, focus does not escape overlay (WCAG 2.1 AA)
- **Risk if unmet:** Accessibility gap reported in user testing or WCAG audit. Phase 8 should have added `aria-live` and `role="dialog"` — if not present, this is a Phase 8 regression, not a Phase 10 regression.
- **Fallback:** Add `aria-live="polite"` to step content container and `aria-label` to control buttons as a minimal fix. Budget 1 additional small plan if a systematic gap is found.

### D2: Cross-browser visual rendering — DEFER-10-02
- **What:** Tour overlay renders correctly in Firefox and Safari (not just Chromium): spotlight sizing, tooltip positioning, CSS transitions, and z-index layering all function
- **How:** Run Playwright tests with Firefox and WebKit projects enabled, then do a manual visual pass on each browser
- **Why deferred:** The Playwright config in `playwright.config.ts` currently only configures Chromium. Running Firefox/WebKit projects requires updating the config — this is explicitly out of scope per 10-RESEARCH.md#deferred-ideas.
- **Validates at:** manual-review-post-phase-10 (or a future phase if cross-browser bugs are found)
- **Depends on:** Playwright config update to include `projects: [{ name: 'firefox' }, { name: 'webkit' }]`
- **Target:** No functional regressions in Firefox/Safari — overlay appears, buttons work, tour completes
- **Risk if unmet:** CSS custom properties and `backdrop-filter` have known Firefox/Safari quirks. Visual glitches are possible but functional correctness is likely fine since the feature doesn't use any Chromium-only APIs.
- **Fallback:** Treat Firefox/Safari as best-effort. The app's primary target is developer tooling — Chromium-based browsers dominate that segment.

---

## Resolves: Prior Phase Deferred Validations

This phase directly resolves the following deferred items from prior evaluation plans:

| Original Defer ID | Original Phase | Metric | Resolves Via |
|------------------|----------------|--------|-------------|
| DEFER-01-02 | Phase 1 | Persistence across real browser reload | E2E: tour-persistence.spec.ts Test 1 |
| DEFER-01-03 | Phase 1 | instance_id mismatch triggers tour reset | E2E: tour-persistence.spec.ts Test 2 |
| DEFER-02-* | Phase 2 | Full visual regression across all step types | E2E: tour-flow.spec.ts (functional path only; visual screenshot regression remains deferred) |
| DEFER-04-* | Phase 4 | End-to-end tour flow with real backend accounts | E2E: tour-flow.spec.ts with mocked backend |
| DEFER-06-* | Phase 6 | Keyboard navigation through complete tour | E2E: tour-flow.spec.ts Test 3 (keyboard nav) |
| DEFER-08-* | Phase 8 | Screen reader compatibility | E2E: tour-persistence.spec.ts Test 3 (reduced motion) + DEFER-10-01 (screen reader manual) |

**Note:** Visual screenshot regression (mentioned in Phase 2 deferred items) is explicitly out of scope per 10-RESEARCH.md#deferred-ideas — "Visual regression testing with screenshot comparison: too fragile for initial setup."

---

## Ablation Plan

**Purpose:** Verify each of the four plans contributes independently.

### A1: Wave 1 independence — plans 10-01 and 10-02 run in any order
- **Condition:** Plans 10-01 and 10-02 are specified with `depends_on: []` — they must not share test file state
- **Expected:** Running plan 10-02 before 10-01 produces the same test outcomes
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npx vitest run src/composables/__tests__/useTourMachine.test.ts --reporter=verbose`
- **Evidence:** 10-RESEARCH.md#pattern-2 uses `vi.resetModules()` per-test — module isolation is explicit. The machine test imports only `createActor` from xstate and `tourMachine` — no shared state.

### A2: Unit tests do not depend on E2E infrastructure
- **Condition:** Plans 10-01 and 10-02 must pass without Playwright or dev servers running
- **Expected:** `npm run test:run` passes even when backend is not running
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm run test:run`
- **Evidence:** Unit tests mock `fetch` via `vi.fn()` and use `localStorage.clear()` — no network calls.

### A3: E2E tests do not depend on existing unit test state
- **Condition:** Plan 10-03 E2E tests must pass fresh even if plans 10-01 and 10-02 haven't run
- **Expected:** E2E tests validate behavior in a real browser — they do not read unit test coverage output
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npx playwright test e2e/tests/tour-flow.spec.ts --reporter=list`
- **Evidence:** E2E tests use the app via browser, not the coverage reports. The only dependency is that the app compiles (which S1 verifies).

---

## WebMCP Tool Definitions

This phase modifies frontend files: `frontend/e2e/fixtures/tour.ts`, `frontend/e2e/tests/tour-flow.spec.ts`, `frontend/e2e/tests/tour-persistence.spec.ts`, and `frontend/vitest.config.ts`. However, none of these are user-visible views (they are test infrastructure files). The tour overlay rendering itself was built in Phase 2. This phase only adds tests that validate Phase 2-9 work.

WebMCP tool definitions skipped — phase modifies test infrastructure files only, not user-visible views or routes. The tour overlay component itself was shipped in Phase 2; this phase does not change its rendering behavior.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| tourMachine.ts branch coverage | Before Phase 10 | 0% | 10-RESEARCH.md#recommendation-4 ("Current coverage: tourMachine.ts has 0%") |
| useTourMachine.ts branch coverage | Before Phase 10 | 0% | 10-RESEARCH.md#recommendation-4 ("useTourMachine.ts has 0%") |
| E2E tour specs | Before Phase 10 | 0 (none exist) | eval_context#current-baseline |
| TourOverlay.test.ts test count | Before Phase 10 | 8 tests passing | eval_context#current-baseline |
| Frontend unit test suite | Before Phase 10 | 820 tests, 63 files | 10-RESEARCH.md#summary |
| useTour.ts branch coverage | Before Phase 10 | 57.69% | 10-RESEARCH.md#recommendation-4 |

---

## Evaluation Scripts

**Location of evaluation code:**
```
frontend/src/machines/__tests__/tourMachine.test.ts           (created in plan 10-01)
frontend/src/composables/__tests__/useTourMachine.test.ts     (created in plan 10-02)
frontend/src/components/tour/__tests__/TourOverlay.test.ts    (expanded in plan 10-02)
frontend/e2e/fixtures/tour.ts                                 (created in plan 10-03)
frontend/e2e/tests/tour-flow.spec.ts                         (created in plan 10-03)
frontend/e2e/tests/tour-persistence.spec.ts                  (created in plan 10-03)
frontend/vitest.config.ts                                     (updated in plan 10-04)
```

**How to run full Level 1 + Level 2 evaluation:**
```bash
# S1: Build verification
cd /Users/neo/Developer/Workspaces/projects/Agented && just build

# S2: Backend tests
cd /Users/neo/Developer/Workspaces/projects/Agented/backend && uv run pytest -x -q

# S3: All frontend unit tests
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm run test:run

# S4 + S5: File size check
wc -l /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/machines/__tests__/tourMachine.test.ts
wc -l /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/composables/__tests__/useTourMachine.test.ts

# S6: Zero `any` in tour source
grep -rn ': any\|as any' \
  /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/machines/tourMachine.ts \
  /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/composables/useTourMachine.ts \
  /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/components/tour/TourOverlay.vue

# S7: E2E spec list
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && \
  npx playwright test --list e2e/tests/tour-flow.spec.ts e2e/tests/tour-persistence.spec.ts

# P1: tourMachine.ts branch coverage
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && \
  npx vitest run src/machines/__tests__/tourMachine.test.ts \
    --coverage --coverage.include='src/machines/tourMachine.ts'

# P2: useTourMachine.ts branch coverage
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && \
  npx vitest run src/composables/__tests__/useTourMachine.test.ts \
    --coverage --coverage.include='src/composables/useTourMachine.ts'

# P3: Verify coverage thresholds in config
grep -A 20 "thresholds" /Users/neo/Developer/Workspaces/projects/Agented/frontend/vitest.config.ts

# P4: E2E flow tests
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && \
  npx playwright test e2e/tests/tour-flow.spec.ts e2e/tests/tour-persistence.spec.ts --reporter=list

# P5: TourOverlay test count
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && \
  npx vitest run src/components/tour/__tests__/TourOverlay.test.ts --reporter=verbose
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: `just build` passes | | | |
| S2: Backend tests pass | | | |
| S3: Frontend unit tests pass | | | |
| S4: tourMachine.test.ts >= 200 lines | | | |
| S5: useTourMachine.test.ts >= 200 lines | | | |
| S6: Zero `any` in tour source | | | |
| S7: E2E specs list without errors | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: tourMachine.ts branch coverage | >= 90% | | | |
| P2: useTourMachine.ts branch coverage | >= 90% | | | |
| P3: Coverage thresholds in vitest.config.ts | Present | | | |
| P4: All E2E tour tests pass | 7+ tests, all pass | | | |
| P5: TourOverlay.test.ts test count | >= 12 tests, all pass | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Plans 10-01 and 10-02 are wave-independent | Both pass in isolation | | |
| A2: Unit tests pass without running backend | Pass with mocked fetch | | |
| A3: E2E tests pass without unit test state | Pass from clean run | | |

### Resolved Deferred Validations

| Original ID | Metric | Resolution | Status |
|-------------|--------|------------|--------|
| DEFER-01-02 | Persistence across real browser reload | E2E test: tour-persistence.spec.ts Test 1 | PENDING |
| DEFER-01-03 | instance_id mismatch triggers reset | E2E test: tour-persistence.spec.ts Test 2 | PENDING |
| DEFER-02-* | Visual regression (functional path) | E2E flow test: tour-flow.spec.ts | PENDING |
| DEFER-04-* | End-to-end flow with mocked backends | E2E flow test: tour-flow.spec.ts | PENDING |
| DEFER-06-* | Keyboard navigation through tour | E2E test: tour-flow.spec.ts Test 3 | PENDING |
| DEFER-08-* | Reduced motion preference | E2E test: tour-persistence.spec.ts Test 3 | PENDING |

### Remaining Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-10-01 | Screen reader compatibility | PENDING | manual-review-post-phase-10 |
| DEFER-10-02 | Cross-browser visual rendering | PENDING | manual-review-post-phase-10 |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 7 checks cover build correctness, test suite integrity, file existence, and static analysis. All commands are specific and executable without running the app (except P4 which needs dev servers, covered by S7 as a pre-check).
- Proxy metrics: Well-evidenced — P1 and P2 directly measure the stated success criteria (>= 90% branch coverage). P3 is a deterministic structural check (config inspection). P4 and P5 directly execute the artifacts produced by this phase. No proxies invented from thin air — every metric traces to a plan's `must_haves` or `success_criteria`.
- Deferred coverage: Honest about what automated testing cannot do. Screen reader and cross-browser validation require manual effort and are explicitly out of scope per 10-RESEARCH.md#deferred-ideas.

**What this evaluation CAN tell us:**
- Whether every documented state machine transition is exercised and produces the correct resulting state
- Whether the composable correctly handles the persistence round-trip, schema version mismatch, and instance_id mismatch under controlled conditions
- Whether the full tour flow — from welcome to complete — functions in a real Chromium browser with mocked API endpoints
- Whether keyboard navigation (Tab, Enter, Space) and page reload persistence work in a real browser
- Whether the codebase compiles cleanly with TypeScript strict mode and no `any` escapes in tour code

**What this evaluation CANNOT tell us:**
- Whether the tour overlay reads correctly with a screen reader (deferred to manual review)
- Whether Firefox or Safari render the overlay identically to Chromium (deferred to cross-browser testing)
- Whether real backend API responses (non-mocked, with auth edge cases) produce correct guard behavior in the tour
- Whether the tour performs correctly under real network latency (E2E tests use synchronous mocks)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-22*
