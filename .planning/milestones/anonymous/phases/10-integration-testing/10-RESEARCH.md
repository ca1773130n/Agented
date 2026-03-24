# Phase 10: Integration Testing - Research

**Researched:** 2026-03-22
**Domain:** Vitest unit testing (XState v5 + Vue 3 components), Playwright E2E testing, v8 coverage, vue-tsc type safety
**Confidence:** HIGH

## Summary

This phase adds comprehensive test coverage for the onboarding tour system built in Phases 1-9. The testing scope splits into four distinct areas: (1) unit tests for the XState v5 state machine (`tourMachine.ts`) and its Vue composable wrapper (`useTourMachine.ts`), targeting >= 90% branch coverage; (2) unit tests for visual tour components (`TourOverlay.vue` and any other tour components created in Phases 2-9); (3) Playwright E2E tests validating full tour flows against the running application; and (4) a build/type-safety audit confirming `just build` passes with zero vue-tsc errors and no `any` types in tour code.

The project already has a mature test infrastructure: 63 Vitest test files with 820 tests, a fully configured Playwright setup (v1.58.2) with 16+ E2E spec files, custom fixtures (`base.ts` with API mocking, `live-backend.ts` for real backend), a page-object pattern (`SidebarPage`), and `@vitest/coverage-v8` configured with text/json/html reporters. The existing tour tests (17 passing tests across `useTour.test.ts` and `TourOverlay.test.ts`) cover the legacy composable but not the XState machine or `useTourMachine.ts` composable.

**Primary recommendation:** Write state machine tests using XState v5's `createActor()` directly (no Vue wrapper needed for pure machine tests), mock `localStorage` and `fetch` for `useTourMachine.ts` composable tests, extend the existing Playwright base fixture with tour-specific API mocks for E2E tests, and use `vitest run --coverage` with per-file branch threshold assertions.

## User Constraints (from prior decisions)

### Locked Decisions
- XState v5 `setup()` API with string-referenced guards (from Phase 1)
- Singleton XState actor pattern shared across components (from Phase 1)
- Async guard checks in composable, not machine -- keeps `tourMachine.ts` pure (from Phase 1)
- Vitest + happy-dom + @vue/test-utils for unit tests (existing infrastructure)
- Playwright for E2E tests (existing infrastructure, v1.58.2)
- `just build` must pass (vue-tsc + vite build) as final gate

### Claude's Discretion
- Test file organization within `__tests__/` directories
- Specific test case granularity and naming conventions
- Playwright E2E test structure (new spec file vs. extending existing)
- Whether to create a tour-specific Playwright page object
- Coverage threshold enforcement strategy (vitest config vs. CI assertion)

### Deferred Ideas (OUT OF SCOPE)
- Visual regression testing with screenshot comparison (too fragile for initial setup)
- Performance benchmarking of tour transitions
- Cross-browser Playwright testing beyond Chromium (only Chromium configured)

## Paper-Backed Recommendations

### Recommendation 1: Test XState Machines by Creating Actors Directly
**Recommendation:** Test `tourMachine.ts` by creating actors with `createActor(tourMachine)`, sending events, and asserting on `actor.getSnapshot()`. Do not involve Vue components or composables for pure machine tests.

**Evidence:**
- XState v5 official testing docs (stately.ai/docs/testing) -- Recommends creating actors directly for unit tests: `const actor = createActor(machine); actor.start(); actor.send({ type: 'EVENT' }); expect(actor.getSnapshot().value).toBe('expected')`.
- XState v5 `createActor` docs -- `createActor(machine, { snapshot })` allows testing persistence restoration without localStorage.
- Existing `tourMachine.ts` is a pure machine definition with no side effects -- it imports only `setup` and `assign` from xstate, making it directly testable without mocking.

**Confidence:** HIGH -- Official XState v5 documentation, verified against actual codebase.
**Expected improvement:** Tests cover all state transitions, guards, and actions without Vue or DOM dependencies, running in < 100ms.
**Caveats:** Guards defined in the machine (`isWorkspaceConfigured`, `hasClaudeAccount`, `hasAnyBackend`, `canSkipAll`) all return `false` by default. Tests must either provide guard overrides via `createActor(machine.provide({ guards: { ... } }))` or test the default behavior.

### Recommendation 2: Mock `fetch` and `localStorage` for Composable Tests
**Recommendation:** Test `useTourMachine.ts` by mocking `globalThis.fetch`, `localStorage`, and the `api/client` module. Reset the singleton actor between tests by resetting the module via `vi.resetModules()`.

**Evidence:**
- Existing test pattern in `useTour.test.ts` -- Uses `vi.resetModules()` + dynamic `import()` to reset module-level state between tests. Uses `localStorage.clear()` in `beforeEach`.
- Existing test pattern in `WelcomePage.test.ts` -- Uses `vi.mock('../../services/api/client')` to mock the API client module.
- The `useTourMachine.ts` composable has module-level singleton state (`sharedActor`, `sharedInstanceId`, `subscriberCount`, `initPromise`) that must be reset between tests.

**Confidence:** HIGH -- Patterns already established in codebase.
**Caveats:** The `onUnmounted` lifecycle hook in `useTourMachine.ts` requires tests to either mount a Vue component wrapper or mock the Vue lifecycle. The existing `useFocusTrap.test.ts` demonstrates mocking `onUnmounted` via `vi.mock('vue', ...)`.

### Recommendation 3: Extend Existing Playwright Fixtures for Tour E2E Tests
**Recommendation:** Create tour E2E tests using the existing `base.ts` fixture pattern (mocked API mode) for UI flow tests, and `live-backend.ts` fixture for full-stack integration tests. Add tour-specific API mocks (e.g., `/health/instance-id`, `/api/settings`, `/admin/backends/*`) to the mock data.

**Evidence:**
- Existing `frontend/e2e/fixtures/base.ts` -- Provides `page` with pre-mocked API routes, `sidebarPage` fixture, and `mockApi` helper for per-test API overrides.
- Existing `frontend/e2e/fixtures/live-backend.ts` -- Provides un-mocked `page` for real backend integration testing.
- Existing `frontend/e2e/tests/integration/entity-crud-flow.spec.ts` -- Demonstrates the live-backend pattern: create entities via API, then verify UI rendering.
- `playwright.config.ts` already configures two webServers (backend on :20000, frontend on :3000) with `reuseExistingServer` for local dev.

**Confidence:** HIGH -- All infrastructure exists and is proven.

### Recommendation 4: Use v8 Coverage Provider with Per-File Thresholds
**Recommendation:** Use `vitest run --coverage` with the existing `@vitest/coverage-v8` provider. Assert branch coverage >= 90% for `tourMachine.ts` and `useTourMachine.ts` in CI or verification scripts. Use the `coverage.thresholds` config option in `vitest.config.ts` if per-file thresholds are needed.

**Evidence:**
- Existing `vitest.config.ts` -- Already configures `coverage.provider: 'v8'` with `reporter: ['text', 'json', 'html']` and `include: ['src/**/*.{ts,vue}']`.
- Vitest coverage docs (vitest.dev/guide/coverage) -- Supports `coverage.thresholds` with `perFile: true` for per-file enforcement. Also supports `coverage.thresholds['/path/pattern']` for pattern-specific thresholds.
- Current coverage: `useTour.ts` has 57.69% branch coverage from existing 9 tests; `tourMachine.ts` has 0% coverage (no dedicated tests yet); `useTourMachine.ts` has 0% coverage (no tests yet).

**Confidence:** HIGH -- Verified against existing vitest.config.ts and measured current coverage.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `vitest` | ^4.0.18 | Unit test runner | Already in use (63 test files, 820 tests). Fast, Vite-native, supports coverage. |
| `@vue/test-utils` | ^2.4.6 | Vue component mounting | Already in use for all Vue component tests. Provides `mount()`, `shallowMount()`, `flushPromises()`. |
| `@vitest/coverage-v8` | ^4.0.18 | Code coverage | Already configured. v8 provider is fastest for TypeScript. |
| `@playwright/test` | ^1.58.2 | E2E browser testing | Already in use (16+ spec files). Full browser automation with auto-waiting. |
| `happy-dom` | ^20.5.0 | Test DOM environment | Already configured in vitest.config.ts. Lighter than jsdom. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `xstate` | ^5.28.0 | State machine (test subject) | Already installed. `createActor()` used directly in machine unit tests. |
| `playwright` | ^1.58.2 | Playwright core library | Already installed alongside `@playwright/test`. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@vitest/coverage-v8` | `@vitest/coverage-istanbul` | Istanbul provides more accurate branch coverage for complex code but is slower. v8 is already configured and sufficient. |
| happy-dom | jsdom | jsdom is more complete but 3-5x slower. happy-dom handles all tour testing needs. |
| Playwright E2E | Cypress | Playwright already configured with 16+ specs. Switching would be wasteful. |

**Installation:**
```bash
# No new dependencies needed -- all are already installed
```

## Architecture Patterns

### Recommended Test File Structure
```
frontend/src/
├── machines/
│   └── __tests__/
│       └── tourMachine.test.ts         # Pure state machine unit tests
├── composables/
│   └── __tests__/
│       └── useTourMachine.test.ts      # Composable tests (mocked fetch/localStorage)
│       └── useTour.test.ts             # Existing legacy composable tests
├── components/tour/
│   └── __tests__/
│       └── TourOverlay.test.ts         # Existing + expanded component tests

frontend/e2e/
├── fixtures/
│   └── tour.ts                         # Tour-specific fixture extending base.ts
├── pages/
│   └── tour.page.ts                    # Tour page object (optional)
├── tests/
│   └── tour-flow.spec.ts              # E2E tour flow tests
│   └── tour-keyboard.spec.ts          # Keyboard navigation E2E tests
│   └── tour-persistence.spec.ts       # Persistence across reload E2E tests
```

### Pattern 1: Pure XState Machine Testing (No Vue)
**What:** Test the `tourMachine` definition by creating actors directly, sending events, and asserting on snapshot values. No Vue component or DOM involvement.
**When to use:** Testing state transitions, guards, actions, hierarchical states, and edge cases.
**Example:**
```typescript
// Source: XState v5 testing docs (stately.ai/docs/testing)
import { createActor } from 'xstate';
import { tourMachine } from '../../machines/tourMachine';

it('transitions from idle to welcome on START', () => {
  const actor = createActor(tourMachine);
  actor.start();
  expect(actor.getSnapshot().value).toBe('idle');
  actor.send({ type: 'START' });
  expect(actor.getSnapshot().value).toBe('welcome');
  actor.stop();
});

it('navigates through backends substeps', () => {
  const actor = createActor(tourMachine);
  actor.start();
  actor.send({ type: 'START' });    // idle -> welcome
  actor.send({ type: 'NEXT' });     // welcome -> workspace
  actor.send({ type: 'NEXT' });     // workspace -> backends.claude
  expect(actor.getSnapshot().value).toEqual({ backends: 'claude' });
  actor.send({ type: 'NEXT' });     // claude -> codex
  expect(actor.getSnapshot().value).toEqual({ backends: 'codex' });
  actor.stop();
});
```

### Pattern 2: Composable Testing with Module Reset
**What:** Test `useTourMachine()` by resetting module state between tests, mocking external dependencies (`fetch`, `localStorage`, API client), and using dynamic imports.
**When to use:** Testing persistence, instance-id validation, guard auto-advance, and reactive computed properties.
**Example:**
```typescript
// Source: Existing useTour.test.ts pattern + useTourMachine.ts analysis
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock Vue lifecycle hooks
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

// Mock API client
vi.mock('../../services/api/client', () => ({
  API_BASE: 'http://localhost:20000',
  getApiKey: () => null,
}));

describe('useTourMachine', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
    // Mock fetch for instance-id
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ instance_id: 'test-uuid' }),
    });
  });

  it('initializes actor in idle state', async () => {
    const { useTourMachine } = await import('../useTourMachine');
    const tour = useTourMachine();
    // Wait for async init
    await vi.waitFor(() => expect(tour.state.value).not.toBeNull());
    expect(tour.state.value).toBe('idle');
  });
});
```

### Pattern 3: Playwright Tour E2E with Page Object
**What:** Create a `TourPage` page object that encapsulates tour overlay interactions (clicking Next, Skip, checking step counter text). Extend the base fixture to mock tour-related API endpoints.
**When to use:** All E2E tour flow tests.
**Example:**
```typescript
// Source: Existing SidebarPage pattern + tour overlay HTML structure
import { type Locator, type Page, expect } from '@playwright/test';

export class TourPage {
  readonly page: Page;
  readonly overlay: Locator;
  readonly nextBtn: Locator;
  readonly skipBtn: Locator;
  readonly stepCounter: Locator;

  constructor(page: Page) {
    this.page = page;
    this.overlay = page.locator('.tour-overlay');
    this.nextBtn = page.locator('.tour-next-btn');
    this.skipBtn = page.locator('.tour-skip-btn');
    this.stepCounter = page.locator('.tour-step-counter');
  }

  async clickNext() {
    await this.nextBtn.click();
  }

  async clickSkip() {
    await this.skipBtn.click();
  }

  async expectStep(stepNumber: number, totalSteps: number) {
    await expect(this.stepCounter).toContainText(`STEP ${stepNumber} OF ${totalSteps}`);
  }
}
```

### Anti-Patterns to Avoid
- **Testing XState machine through Vue components:** Do NOT mount Vue components to test state machine transitions. Test the machine directly with `createActor()`. This is faster, more deterministic, and isolates machine logic from rendering.
- **Not resetting singleton state between tests:** The `useTourMachine.ts` composable uses module-level `sharedActor` and `initPromise`. Every test MUST call `vi.resetModules()` before importing the composable, or tests will share state and produce flaky results.
- **Using `setTimeout` or `sleep` in Playwright tests:** The existing codebase correctly avoids this. Use Playwright's auto-waiting (`expect(locator).toBeVisible()`, `locator.waitFor()`) instead.
- **Testing CSS animations in unit tests:** happy-dom does not support CSS animations. Animation-related tests (glow, transitions, reduced-motion) belong in E2E Playwright tests with `@media` emulation, not unit tests.
- **Mocking XState internals:** Do NOT mock `createActor`, `assign`, or other XState functions. The machine should be tested as a black box: send events, assert on snapshots.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State machine test helpers | Custom transition walker | `createActor()` + `.send()` + `.getSnapshot()` | XState v5 actors are the official test interface. Zero abstraction needed. |
| Coverage threshold enforcement | Manual coverage parsing script | `vitest.config.ts` `coverage.thresholds` | Built-in vitest feature. Set `branches: 90` directly in config. |
| E2E API mocking | Custom fetch interceptor | Playwright `page.route()` via existing fixture | Already implemented in `base.ts`. Proven pattern with 16+ spec files. |
| Browser localStorage in E2E | Direct `page.evaluate(localStorage)` | `page.evaluate(() => localStorage.getItem('key'))` | Standard Playwright API. |
| Reduced-motion testing | Manual CSS override | `page.emulateMedia({ reducedMotion: 'reduce' })` | Built-in Playwright media emulation. |

**Key insight:** The existing test infrastructure is comprehensive. This phase requires writing tests, not building test infrastructure. All tooling (Vitest, Playwright, coverage, fixtures, page objects) is already configured and proven.

## Common Pitfalls

### Pitfall 1: Singleton Actor Leaking Between Tests
**What goes wrong:** `useTourMachine.ts` stores the XState actor in a module-level `sharedActor` variable. If `vi.resetModules()` is not called, the first test's actor persists into subsequent tests, causing false passes or false failures.
**Why it happens:** ES modules are cached by the module system. `import { useTourMachine } from '../useTourMachine'` returns the same module instance across tests unless explicitly reset.
**How to avoid:** Every test file that imports `useTourMachine` must use `vi.resetModules()` in `beforeEach` and use dynamic `import()` to get a fresh module. Follow the exact pattern used in `useTour.test.ts`.
**Warning signs:** Tests pass in isolation but fail when run together, or order-dependent test results.

### Pitfall 2: Async Actor Initialization Race Conditions
**What goes wrong:** `useTourMachine()` triggers `initActor()` which is async (fetches instance-id). Tests that assert on `state.value` immediately after calling `useTourMachine()` get `null` because the actor hasn't started yet.
**Why it happens:** The composable uses `initPromise.then(() => { ... })` to defer actor subscription. The actor is not available synchronously.
**How to avoid:** After calling `useTourMachine()`, use `await vi.waitFor(() => expect(tour.state.value).not.toBeNull())` or await the `initPromise` directly if exposed. Alternatively, mock `fetch` to resolve synchronously.
**Warning signs:** Tests that pass intermittently or have `expect(null).toBe('idle')` failures.

### Pitfall 3: `onUnmounted` Throwing in Non-Component Context
**What goes wrong:** `useTourMachine()` calls `onUnmounted()` which requires an active Vue component instance. Calling it outside a component (e.g., directly in a test) throws "onUnmounted is called when there is no active component instance".
**Why it happens:** Vue lifecycle hooks are context-dependent.
**How to avoid:** Either (a) mock `onUnmounted` via `vi.mock('vue', ...)` as done in `useFocusTrap.test.ts`, or (b) wrap the composable call in a test component mounted with `@vue/test-utils`.
**Warning signs:** "No active component instance" error in test output.

### Pitfall 4: Playwright Tour Tests Blocked by Auth
**What goes wrong:** Navigating to the app in Playwright shows the WelcomePage (first-run auth setup) instead of the main app with tour overlay.
**Why it happens:** The app detects no API keys exist and redirects to the welcome/auth page. The tour starts after auth setup.
**How to avoid:** In mocked-API E2E tests, mock `/health/auth-status` to return `{ needs_setup: false, auth_required: false, authenticated: true }`. In live-backend tests, call `/health/setup` first to create an API key, then set it in localStorage via `page.evaluate()`.
**Warning signs:** Tour overlay never appears, tests time out waiting for `.tour-overlay`.

### Pitfall 5: E2E Tour Target Elements Not Found
**What goes wrong:** The tour overlay shows the spinner/loading state because `data-tour` target elements don't exist on the page.
**Why it happens:** Tour steps navigate to specific routes and look for `[data-tour="workspace-root"]` etc. In mocked-API tests, the page may render differently (empty lists, missing sections).
**How to avoid:** Ensure mock data includes enough entities and settings to render the target elements. Alternatively, test the tour overlay behavior (spinner, step counter, next/skip) without depending on target element positioning.
**Warning signs:** All tour tests show the spinner but never the spotlight.

### Pitfall 6: Coverage Counting Untested Files as 0%
**What goes wrong:** Running `vitest run --coverage` for a specific test file reports 0% coverage for unrelated files, making it hard to verify the 90% branch target.
**Why it happens:** v8 coverage instruments all files matching `coverage.include`, not just files imported by the test.
**How to avoid:** Use `coverage.include` with specific file patterns for targeted coverage reports, or parse the JSON coverage output to extract per-file metrics for tour files only.
**Warning signs:** Coverage report shows hundreds of files at 0%, obscuring the tour file metrics.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Test scope: machine-only tests vs. composable tests vs. component tests vs. E2E tests
- Mocking strategy: fully mocked API vs. live backend for E2E
- Tour flow: complete flow (all steps) vs. skip-all flow vs. partial flow with persistence

**Dependent variables:**
- Branch coverage percentage for `tourMachine.ts` and `useTourMachine.ts`
- Test execution time
- Test stability (flaky test rate)

**Controlled variables:**
- Vitest version (4.0.18)
- Playwright version (1.58.2)
- happy-dom environment
- TypeScript strict mode

**Baseline comparison:**
- Current state: 17 tour tests (9 for `useTour.ts`, 8 for `TourOverlay.vue`), 0% coverage on `tourMachine.ts` and `useTourMachine.ts`
- Target: >= 90% branch coverage on `useTourMachine.ts`, >= 90% branch on `tourMachine.ts`, full E2E coverage of happy path + skip path + persistence

**Validation approach:**
1. Write machine tests first -- measure branch coverage, iterate until >= 90%
2. Write composable tests -- measure branch coverage, iterate until >= 90%
3. Write component tests -- verify all rendering states and interactions
4. Write E2E tests -- verify complete flow, skip flow, persistence, keyboard nav, reduced motion
5. Run `just build` -- verify zero vue-tsc errors
6. Audit for `any` types -- grep tour files for `: any` and `as any`

**Statistical rigor:** Not applicable (deterministic tests, not stochastic).

### Recommended Metrics

| Metric | Why | How to Compute | Target |
|--------|-----|----------------|--------|
| Branch coverage (tourMachine.ts) | OB-45 requirement | `vitest run --coverage`, read v8 JSON output | >= 90% |
| Branch coverage (useTourMachine.ts) | OB-45 requirement | `vitest run --coverage`, read v8 JSON output | >= 90% |
| Component test count | OB-46 requirement | Count tests in tour component `__tests__/` | >= 5 per component |
| E2E test count | OB-47 requirement | Count tests in tour E2E spec files | >= 6 scenarios |
| vue-tsc error count | OB-48 requirement | `vue-tsc -b` exit code + output | 0 errors |
| `any` type count in tour files | OB-48 requirement | `grep -c ': any\|as any' tour files` | 0 occurrences |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Machine transitions cover all states | Level 1 (Sanity) | Deterministic, pure function tests |
| Machine guards (default false) are tested | Level 1 (Sanity) | Simple assertions on snapshot |
| Machine `markStepCompleted` action updates context | Level 1 (Sanity) | Verify context mutation |
| Composable initializes in idle state | Level 1 (Sanity) | Basic async init test |
| Composable persists to localStorage on transition | Level 1 (Sanity) | Mock localStorage, verify setItem |
| Composable restores from localStorage | Level 1 (Sanity) | Pre-populate localStorage, verify state |
| Composable clears state on instance-id mismatch | Level 1 (Sanity) | Mock fetch with different ID |
| Composable clears state on schema version mismatch | Level 1 (Sanity) | Pre-populate with wrong version |
| TourOverlay renders when active | Level 1 (Sanity) | Already tested (existing test) |
| TourOverlay emits next/skip events | Level 1 (Sanity) | Already tested (existing test) |
| Branch coverage >= 90% for machine | Level 2 (Proxy) | Parse coverage output |
| Branch coverage >= 90% for composable | Level 2 (Proxy) | Parse coverage output |
| E2E: complete tour flow | Level 2 (Proxy) | Playwright with mocked API |
| E2E: skip-all flow | Level 2 (Proxy) | Playwright with mocked API |
| E2E: persistence across reload | Level 2 (Proxy) | Playwright reload + verify state |
| E2E: keyboard-only navigation | Level 2 (Proxy) | Playwright keyboard events |
| `just build` passes (vue-tsc clean) | Level 1 (Sanity) | Build command, check exit code |
| No `any` types in tour files | Level 1 (Sanity) | Grep check |
| E2E: reduced motion (no animation) | Level 3 (Deferred) | Requires `page.emulateMedia()` and visual check |
| E2E: focus trapping within tour overlay | Level 3 (Deferred) | Requires full DOM with tour + app content |
| E2E: screen reader compatibility | Level 3 (Deferred) | Requires aria-label audit + screen reader testing |

**Level 1 checks to always include:**
- All machine states are reachable via event sequences
- BACK transitions go to the correct previous state
- SKIP and NEXT from every state go to the correct target
- SKIP_ALL with `canSkipAll` guard returning true reaches `complete`
- RESTART from any state returns to `idle` with cleared context
- `markStepCompleted` adds the current state to `completedSteps`
- Persistence round-trip: persist snapshot, create new actor from snapshot, verify same state
- Instance-id mismatch triggers state reset
- Schema version mismatch triggers state reset

**Level 2 proxy metrics:**
- Coverage threshold met (vitest coverage JSON output)
- E2E tour completes without errors in Playwright
- E2E tour skip-all works in Playwright
- Tour state survives `page.reload()` in Playwright

**Level 3 deferred items:**
- Screen reader compatibility (deferred from Phase 8) -- requires axe-core or manual NVDA testing
- Full visual regression (deferred from Phase 2) -- requires screenshot comparison tooling
- Cross-browser testing beyond Chromium -- requires Playwright project config changes

## Production Considerations

### Known Failure Modes
- **Flaky E2E tests from timing:** Tour overlay uses CSS transitions (300ms for spotlight, 150ms for buttons). E2E tests that click immediately after navigation may miss elements mid-transition.
  - Prevention: Use Playwright auto-waiting (`expect(locator).toBeVisible()`) before interactions. Never use `waitForTimeout()`.
  - Detection: Flaky test in CI. Enable `retries: 2` in playwright.config.ts (already configured for CI).

- **Coverage drop after code changes:** Adding new branches to tour code without tests causes coverage to drop below threshold.
  - Prevention: Set `coverage.thresholds` in vitest.config.ts to fail on threshold violation.
  - Detection: CI failure on coverage check.

### Scaling Concerns
- **Not applicable:** Tests run against a single-user local instance. No scaling concerns for test infrastructure.

### Common Implementation Traps
- **Trap: Testing implementation details instead of behavior:** Do NOT assert on internal XState snapshot structure (e.g., `_nodes`, `_event`). Only assert on `.value`, `.context`, `.matches()`, and `.can()`.
  - Correct approach: Test public API -- state value, context, and event acceptance.

- **Trap: Importing `@xstate/vue` for tests:** The `@xstate/vue` package is in dependencies but unused. Do NOT introduce it in tests. The composable uses manual `createActor` + `shallowRef`.
  - Correct approach: Follow the existing manual pattern in `useTourMachine.ts`.

- **Trap: E2E tests depending on backend state from prior tests:** Tour E2E tests must not depend on entities created in other spec files. Each test should set up its own state.
  - Correct approach: Use `page.evaluate(() => localStorage.setItem(...))` for tour state, and `page.route()` for API mocking.

## Code Examples

### Pure Machine Test: All Forward Transitions
```typescript
// Source: XState v5 testing docs + tourMachine.ts analysis
import { createActor } from 'xstate';
import { tourMachine } from '../../machines/tourMachine';

describe('tourMachine', () => {
  it('completes full forward path', () => {
    const actor = createActor(tourMachine);
    actor.start();

    actor.send({ type: 'START' });
    expect(actor.getSnapshot().value).toBe('welcome');

    actor.send({ type: 'NEXT' });
    expect(actor.getSnapshot().value).toBe('workspace');

    actor.send({ type: 'NEXT' });
    expect(actor.getSnapshot().value).toEqual({ backends: 'claude' });

    actor.send({ type: 'NEXT' });
    expect(actor.getSnapshot().value).toEqual({ backends: 'codex' });

    actor.send({ type: 'NEXT' });
    expect(actor.getSnapshot().value).toEqual({ backends: 'gemini' });

    actor.send({ type: 'NEXT' });
    expect(actor.getSnapshot().value).toEqual({ backends: 'opencode' });

    // From opencode, NEXT goes to the parent backends NEXT -> verification
    actor.send({ type: 'NEXT' });
    expect(actor.getSnapshot().value).toBe('verification');

    actor.send({ type: 'NEXT' });
    expect(actor.getSnapshot().status).toBe('done');

    actor.stop();
  });
});
```

### Composable Test: Persistence and Instance-ID Validation
```typescript
// Source: useTour.test.ts pattern + useTourMachine.ts analysis
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

vi.mock('../../services/api/client', () => ({
  API_BASE: '',
  getApiKey: () => null,
}));

describe('useTourMachine', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ instance_id: 'uuid-1' }),
    }) as unknown as typeof fetch;
  });

  it('clears persisted state when instance_id mismatches', async () => {
    localStorage.setItem('agented-tour-machine-state', JSON.stringify({
      schemaVersion: 1,
      instanceId: 'old-uuid',
      snapshot: { /* some snapshot */ },
    }));
    const { useTourMachine } = await import('../useTourMachine');
    const tour = useTourMachine();
    await vi.waitFor(() => expect(tour.state.value).not.toBeNull());
    expect(tour.state.value).toBe('idle'); // reset, not restored
  });
});
```

### Playwright E2E: Complete Tour Flow
```typescript
// Source: Existing base.ts fixture pattern + tour overlay HTML structure
import { test, expect } from '../../fixtures/base';

test.describe('Tour Flow', () => {
  test('completes full tour with Next clicks', async ({ page, mockApi }) => {
    // Mock tour-specific endpoints
    await mockApi({
      'health/instance-id': { instance_id: 'test-uuid' },
      'health/auth-status': { needs_setup: false, auth_required: false, authenticated: true },
      'api/settings': { settings: {} },
    });

    // Navigate and start tour
    await page.goto('/?tour=start');

    // Verify tour overlay appears
    await expect(page.locator('.tour-overlay')).toBeVisible();
    await expect(page.locator('.tour-step-counter')).toBeVisible();

    // Click through all steps
    const nextBtn = page.locator('.tour-next-btn');
    while (await nextBtn.isVisible()) {
      await nextBtn.click();
      // Wait for transition
      await page.waitForTimeout(100);
    }
  });
});
```

### Playwright E2E: Persistence Across Reload
```typescript
// Source: Playwright localStorage API + existing E2E patterns
import { test, expect } from '../../fixtures/base';

test('tour state persists across page reload', async ({ page, mockApi }) => {
  await mockApi({
    'health/instance-id': { instance_id: 'test-uuid' },
  });

  // Set initial tour state in localStorage
  await page.goto('/');
  await page.evaluate(() => {
    localStorage.setItem('agented-tour-machine-state', JSON.stringify({
      schemaVersion: 1,
      instanceId: 'test-uuid',
      snapshot: { /* snapshot at workspace step */ },
    }));
  });

  // Reload and verify tour resumes at saved state
  await page.reload();
  await expect(page.locator('.tour-overlay')).toBeVisible();
  // Verify we're at the right step (not back to idle)
});
```

### Playwright E2E: Reduced Motion
```typescript
// Source: Playwright emulateMedia API
import { test, expect } from '../../fixtures/base';

test('tour respects reduced motion preference', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?tour=start');

  // Verify no animations are running
  const spotlightTransition = await page.locator('.tour-spotlight')
    .evaluate(el => getComputedStyle(el).transitionDuration);
  expect(spotlightTransition).toBe('0s');
});
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| XState v4 `interpret()` in tests | XState v5 `createActor()` in tests | XState v5 (2023-12) | Tests use `actor.getSnapshot()` instead of `service.state` |
| Vitest 1.x coverage | Vitest 4.x coverage with v8 | Vitest 4.0 (2025) | Faster coverage collection, better TypeScript support |
| Playwright 1.40 | Playwright 1.58.2 | Current | Improved auto-waiting, better TypeScript integration |

**Deprecated/outdated:**
- `@xstate/test` package: Was used for model-based testing with XState v4. Not updated for v5. Use direct `createActor()` testing instead.
- Vitest `c8` coverage: Replaced by `@vitest/coverage-v8`. The `c8` provider was removed in Vitest 2.0.

## Open Questions

1. **Phases 2-9 component inventory**
   - What we know: The phase description references `TourTooltip`, `TourProgressBar`, `TourFormGuide`, and `TourSpotlight` components. Only `TourOverlay.vue` exists in the codebase currently.
   - What's unclear: Whether Phases 2-9 have been fully executed and created these components, or if the phase description is aspirational. Grep found zero matches for these component names.
   - Recommendation: Plan tests only for components that actually exist at the time of Phase 10 execution. If only `TourOverlay.vue` exists, test that. If additional components are created by Phases 2-9, add tests for each. The planner should list tests per component with a note that the actual component set depends on Phase 2-9 output.

2. **E2E test tour flow triggering mechanism**
   - What we know: `WelcomePage.test.ts` shows the Continue button navigates to `/?tour=start`. The `useTour.ts` composable is activated by the component that reads this query param.
   - What's unclear: How exactly the XState-based `useTourMachine.ts` is triggered to start the tour. The composable exposes `startTour()` which sends `{ type: 'START' }`.
   - Recommendation: In E2E tests, either navigate to `/?tour=start` (if a component watches for this) or manually trigger via `page.evaluate()` to set localStorage state. Test both the trigger mechanism and the flow.

3. **`@xstate/vue` package removal**
   - What we know: `@xstate/vue` is listed in `package.json` dependencies but is not imported anywhere in the codebase. The `useTourMachine.ts` composable uses manual `createActor` + `shallowRef` instead.
   - What's unclear: Whether `@xstate/vue` will be used in future phases or should be removed.
   - Recommendation: Do not introduce `@xstate/vue` in tests. If Phase 10 includes a type audit, flag the unused dependency but do not remove it (out of scope for testing phase).

## Sources

### Primary (HIGH confidence)
- XState v5 official documentation (stately.ai/docs/machines, stately.ai/docs/testing) -- Machine creation, testing patterns, `createActor()` API
- Vitest documentation (vitest.dev/guide/coverage) -- Coverage configuration, v8 provider, threshold settings
- Playwright documentation (playwright.dev/docs/test-fixtures) -- Custom fixtures, `page.route()`, `page.emulateMedia()`
- Existing codebase analysis:
  - `frontend/src/machines/tourMachine.ts` -- 183 lines, pure XState v5 machine definition
  - `frontend/src/composables/useTourMachine.ts` -- 364 lines, singleton actor with persistence and instance-id validation
  - `frontend/src/composables/useTour.ts` -- 287 lines, legacy composable (still in use)
  - `frontend/src/components/tour/TourOverlay.vue` -- 314 lines, overlay component
  - `frontend/src/composables/__tests__/useTour.test.ts` -- 9 tests, existing pattern
  - `frontend/src/components/tour/__tests__/TourOverlay.test.ts` -- 8 tests, existing pattern
  - `frontend/vitest.config.ts` -- Vitest + happy-dom + v8 coverage config
  - `frontend/playwright.config.ts` -- Playwright config with dual webServers
  - `frontend/e2e/fixtures/base.ts` -- Mock fixture pattern
  - `frontend/e2e/fixtures/live-backend.ts` -- Live backend fixture pattern

### Secondary (MEDIUM confidence)
- Vitest per-file coverage thresholds -- Documented in vitest.dev but exact syntax for path-pattern thresholds needs runtime validation.

### Tertiary (LOW confidence)
- None identified.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All tools already installed and configured in the project
- Architecture: HIGH -- Test patterns extracted from 63 existing test files in the codebase
- Recommendations: HIGH -- Based on official XState v5, Vitest, and Playwright documentation, cross-verified with existing codebase patterns
- Pitfalls: HIGH -- Derived from direct analysis of `useTourMachine.ts` singleton pattern and existing test file patterns

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable tooling, 30-day validity)
