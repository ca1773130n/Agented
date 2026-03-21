# Evaluation Plan: Phase 1 — Backend + State Machine Foundation

**Designed:** 2026-03-21
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** XState v5 state machine, Flask app_meta backend endpoint, Vue 3 composable persistence layer
**Reference:** 01-RESEARCH.md (XState v5 persistence docs, @xstate/vue README, Flask health endpoint pattern)

## Evaluation Overview

This phase establishes the tour engine infrastructure with no visible user-facing output. The XState v5 state machine, localStorage persistence layer, instance_id backend endpoint, guard system stubs, and z-index CSS scale are all invisible until Phase 2 adds visual components. This makes direct quality evaluation impossible at this stage.

What CAN be verified: correctness of state transitions (deterministic, unit-testable), schema migrations, API endpoint contract, TypeScript compilation, and CSS property presence. What CANNOT be verified: whether the z-index scale prevents actual layering conflicts (needs Phase 2 components), whether guard API calls produce correct skip behavior in a running app (needs Phase 2+ integration), and whether persistence survives a real browser reload (needs running app).

No performance benchmarks exist for this project yet (STATE.md shows "Not yet evaluated" for all metrics). Targets in this plan are derived from the RESEARCH.md experiment design and product-level targets stated in STATE.md (step transition < 300ms, welcome page load < 200ms).

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Invalid state transitions: 0 | RESEARCH.md#recommended-metrics | Core correctness — state machine must have no undefined transitions |
| Snapshot restore fidelity: 100% | RESEARCH.md#recommended-metrics | Persistence contract — reload must resume exact state |
| Guard evaluation latency < 500ms | RESEARCH.md#recommended-metrics, STATE.md (step transition < 300ms) | UX — guard checks happen at tour boot before first step renders |
| Snapshot size < 2KB | RESEARCH.md#recommended-metrics | localStorage budget — prevent quota errors |
| Migration idempotency | Engineering standard | Migration 96 must be safe to run multiple times |
| `/health/instance-id` UUID format | 01-01-PLAN.md#truths | Backend contract — frontend expects RFC 4122 UUID string |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 8 | Basic functionality and format verification |
| Proxy (L2) | 3 | Automated indirect quality measurements |
| Deferred (L3) | 4 | Full evaluation requiring Phase 2+ components or running browser |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding to Phase 2.

### S1: Build passes with new files
- **What:** TypeScript compiles and Vite builds successfully with tourMachine.ts and useTourMachine.ts added
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented && just build`
- **Expected:** Exit code 0, no TypeScript errors, no `any` type warnings in tour files
- **Failure means:** Type errors in machine definition or composable — implementation has a type bug

### S2: Backend tests pass with migration 96
- **What:** Existing pytest suite still passes after adding app_meta table to schema and migration 96
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/backend && uv run pytest -x -q`
- **Expected:** All existing tests pass, migration 96 runs without error in isolated_db fixture
- **Failure means:** Migration SQL is broken, or app_meta table conflicts with existing schema

### S3: Frontend tests pass
- **What:** Existing Vitest suite unaffected by new XState dependencies and files
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm run test:run`
- **Expected:** All existing tests pass
- **Failure means:** New npm dependencies broke a test, or an import side-effect is disrupting test state

### S4: XState machine exports are valid
- **What:** tourMachine.ts exports compile to a real XState v5 machine (not v4 patterns)
- **Command:** `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && node -e "const { tourMachine } = require('./src/machines/tourMachine'); console.log(tourMachine.id, Object.keys(tourMachine.states))"`
- **Expected:** Prints `tour` and the state name array — no `interpret is not a function` errors
- **Failure means:** v4 API used (interpret, Machine(), createMachine without setup), or import paths wrong. Note: may need `tsx` or `ts-node` instead of bare `node` — adjust command to `npx tsx -e "..."` if needed.

### S5: /health/instance-id endpoint returns UUID
- **What:** The new endpoint returns a UUID-format string without authentication
- **Command:** `curl -s http://localhost:20000/health/instance-id | python3 -c "import sys, json, re; d=json.load(sys.stdin); assert re.match(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', d['instance_id']), 'not a UUID'; print('PASS:', d['instance_id'])"`
- **Expected:** `PASS: <uuid>` with valid RFC 4122 format
- **Failure means:** Endpoint missing, not authenticated correctly, or UUID generation SQL failed
- **Note:** Requires running backend (`just dev-backend`). Skip if CI-only run; covered by backend pytest via test for the endpoint.

### S6: instance_id is stable across restarts
- **What:** Same instance_id is returned on repeated calls (persists in DB, not regenerated each request)
- **Command:** `ID1=$(curl -s http://localhost:20000/health/instance-id | python3 -c "import sys,json; print(json.load(sys.stdin)['instance_id'])") && ID2=$(curl -s http://localhost:20000/health/instance-id | python3 -c "import sys,json; print(json.load(sys.stdin)['instance_id'])") && [ "$ID1" = "$ID2" ] && echo "PASS: stable" || echo "FAIL: differs"`
- **Expected:** `PASS: stable`
- **Failure means:** instance_id is being regenerated on every request — persistence is broken

### S7: z-index CSS custom properties present in App.vue
- **What:** All five tour z-index custom properties exist in App.vue style section
- **Command:** `grep -c "\-\-z-tour-" /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/App.vue`
- **Expected:** 5 (one per property: --z-tour-overlay, --z-tour-spotlight, --z-tour-tooltip, --z-tour-controls, --z-tour-progress)
- **Failure means:** Properties not added to App.vue, or wrong naming convention used

### S8: XState machine has no invalid state reachability
- **What:** Every state in the machine has at least one defined transition that can reach it (no orphan states), and the `complete` state is reachable from `idle` via a sequence of NEXT events
- **Command:** Write and run a unit test — see Proxy section for automated coverage. For manual sanity: `cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npx tsx -e "import { createActor } from 'xstate'; import { tourMachine } from './src/machines/tourMachine'; const a = createActor(tourMachine); a.start(); a.send({type:'START'}); console.log(a.getSnapshot().value);"`
- **Expected:** Prints `welcome` (machine transitioned from idle to welcome on START event)
- **Failure means:** Machine definition has incorrect initial state or START event not wired

**Sanity gate:** ALL 8 sanity checks must pass. Any failure blocks progression to Phase 2.

---

## Level 2: Proxy Metrics

**Purpose:** Automated indirect evaluation of quality properties that cannot be fully assessed until Phase 2+ integration.
**IMPORTANT:** These proxy metrics are NOT validated substitutes for full evaluation.

### P1: State machine branch coverage via unit tests
- **What:** What percentage of (state, event) combinations produce defined transitions — measures whether the machine handles all expected inputs without entering undefined/error states
- **How:** Write unit tests that send each event from each state and assert the resulting state. Count covered branches.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Workspaces/projects/Agented/frontend
  npm run test:run -- --coverage --reporter=verbose 2>&1 | grep -E "useTourMachine|tourMachine|coverage"
  ```
- **Target:** >= 80% branch coverage on `src/machines/tourMachine.ts` and `src/composables/useTourMachine.ts`
- **Evidence:** RESEARCH.md#verification-strategy recommends unit testing all transition combinations. ROADMAP.md Phase 10 targets >= 90% branch coverage for the full test phase — 80% is an appropriate proxy target for Phase 1 foundation work.
- **Correlation with full metric:** MEDIUM — coverage measures paths exercised in tests, not correctness under real API conditions. A machine can have 80% coverage but still fail guard edge cases.
- **Blind spots:** Does not catch async timing bugs in guard checks, does not validate persistence format compatibility with future machine versions, does not test real API responses.
- **Validated:** No — awaiting deferred validation at phase-10-integration-testing

### P2: Snapshot serialization round-trip correctness
- **What:** `actor.getPersistedSnapshot()` produces output that when passed back to `createActor(tourMachine, { snapshot: restored })` restores the identical state value and context
- **How:** Unit test that advances machine through several states, serializes, deserializes, and compares `snapshot.value` and `snapshot.context` fields
- **Command:**
  ```bash
  cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npx vitest run --reporter=verbose src/composables/useTourMachine.test.ts 2>&1 | grep -E "PASS|FAIL|snapshot"
  ```
  (Test file to be written during phase execution targeting this behavior)
- **Target:** 100% field match on `snapshot.value` and `snapshot.context` for all tested state positions
- **Evidence:** RESEARCH.md#recommendation-2 cites XState v5 persistence docs: `getPersistedSnapshot()` returns a JSON-serializable object and `createActor(machine, { snapshot: restored }).start()` restores state. This is the documented contract.
- **Correlation with full metric:** HIGH — this directly measures the persistence contract. The proxy IS the metric (serialization correctness is a deterministic property, not stochastic). Correlation is HIGH because we are testing the exact behavior that must work in production.
- **Blind spots:** Does not test persistence through actual localStorage (tests mock it). Does not test behavior when `schemaVersion` is incremented between serialization and restoration.
- **Validated:** No — awaiting deferred validation at phase-02-visual-layer (first real browser usage)

### P3: Snapshot size under budget
- **What:** The JSON-serialized persisted snapshot is within the 2KB localStorage budget
- **How:** After advancing through a representative path in unit tests, measure `JSON.stringify(actor.getPersistedSnapshot()).length`
- **Command:**
  ```bash
  cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npx tsx -e "
  import { createActor } from 'xstate';
  import { tourMachine } from './src/machines/tourMachine';
  const a = createActor(tourMachine);
  a.start();
  ['START','NEXT','NEXT','NEXT','NEXT'].forEach(t => a.send({type:t}));
  const size = JSON.stringify(a.getPersistedSnapshot()).length;
  console.log('Snapshot size:', size, 'bytes', size < 2048 ? 'PASS' : 'FAIL - over budget');
  "
  ```
- **Target:** < 2048 bytes (2KB)
- **Evidence:** RESEARCH.md#recommended-metrics sets 2KB target based on localStorage reliability concerns. localStorage quota is typically 5-10MB but snapshot growth scales with machine complexity.
- **Correlation with full metric:** HIGH — byte count is a direct measurement. The risk is that `completedSteps` array grows with step count; this check validates the baseline.
- **Blind spots:** Measures baseline snapshot size. After all 8+ steps are completed and `completedSteps` array is full, size will be larger — test should also measure terminal state size.
- **Validated:** No — awaiting deferred validation at phase-04-core-step-content (when all step names are added to completedSteps)

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring Phase 2+ components or a running browser.

### D1: z-index layering correctness — DEFER-01-01
- **What:** Tour overlay (z-index 10000-10004) actually renders above all app UI elements — sidebar (100), header (100), dropdowns (200), modals (200), toasts (1000) — and no app element bleeds through the overlay
- **How:** Visual screenshot comparison with overlay active against a baseline with sidebar open, a modal open, and a toast visible simultaneously
- **Why deferred:** The CSS properties are defined in Phase 1 but the visual components that USE them (TourOverlay.vue, TourSpotlight.vue) are not built until Phase 2
- **Validates at:** phase-02-visual-layer
- **Depends on:** TourOverlay and TourSpotlight components that reference `var(--z-tour-overlay)` etc.
- **Target:** Tour overlay visually above all app content in all test scenarios; no z-index conflicts with existing values found in App.vue (100, 100, 200, 199, 101, 10000, 1000, 9999)
- **Risk if unmet:** Existing element at z-index 9999 (identified in App.vue line 1638) may conflict with tour overlay at 10000 — requires investigation. Budget: 1 additional fix plan in Phase 2 if conflict found.
- **Fallback:** Increase tour overlay base from 10000 to 100000 if conflicts are found

### D2: Persistence across real browser reload — DEFER-01-02
- **What:** Advancing tour to step 3, reloading the browser tab (Cmd+R), and verifying the tour resumes at step 3 — not step 1
- **How:** Manual browser test OR Playwright test: navigate tour forward, reload, assert `localStorage.getItem('agented-tour-state')` contains expected state value, assert tour composable initializes to correct step
- **Why deferred:** Requires a running frontend with Phase 2 visual components to provide observable feedback on what step the tour is at after reload
- **Validates at:** phase-02-visual-layer (first point where tour has visible output)
- **Depends on:** TourOverlay component to visually show current step; useTourMachine composable correctly initializing from persisted snapshot
- **Target:** Tour resumes at exact step (including substep for backends) after reload — 100% fidelity
- **Risk if unmet:** Persistence is broken — core UX requirement fails. This would require debugging the `getPersistedSnapshot()` / restore flow. Budget: 1 additional fix plan.
- **Fallback:** If `getPersistedSnapshot()` format is incompatible with `useActor`, fall back to manually serializing `snapshot.value` and `snapshot.context` as separate fields

### D3: instance_id mismatch triggers tour reset — DEFER-01-03
- **What:** Simulating a DB reset (delete agented.db, restart backend) causes the frontend to detect the new instance_id, clear tour localStorage, and start from the welcome state on next page load
- **How:** Manual test: complete tour to step 3, stop backend, delete DB file, restart backend, reload frontend, verify tour starts from step 1 (or idle). OR automated test with mocked fetch returning a different instance_id.
- **Why deferred:** Requires running backend and frontend together. The unit test (P2) covers the logic but not the integration.
- **Validates at:** phase-02-visual-layer (first integration of composable with visible output)
- **Depends on:** useTourMachine composable + running backend with new instance_id endpoint
- **Target:** Tour state clears and resets to idle/welcome within one page load of DB reset
- **Risk if unmet:** Users who reset their database will be stuck with "tour complete" state — they cannot redo onboarding. High severity UX bug.
- **Fallback:** Add a manual "Reset tour" button in settings as escape hatch (already planned for Phase 9)

### D4: Guard auto-skip with real backend state — DEFER-01-04
- **What:** When workspace IS already configured (before starting tour), the workspace step is automatically skipped. When Claude backend account exists, the backends.claude substep is auto-skipped.
- **How:** Set up backend with workspace configured via `/api/settings/workspace_root`. Start tour. Verify machine jumps from `welcome` directly to `backends` (skipping `workspace`). Requires running app.
- **Why deferred:** Guard API calls require running backend with configured data. Unit tests cover the logic with mocked responses (P1 proxy via test coverage), but real API integration is not testable without running the full stack.
- **Validates at:** phase-04-core-step-content (when step content defines real guard conditions)
- **Depends on:** Running backend, configured workspace setting, useTourMachine composable guard implementations
- **Target:** Zero false-positive step displays — if workspace is set, workspace step never shown. Zero false-negative skips — if workspace is not set, workspace step always shown.
- **Risk if unmet:** Guard API is hitting wrong endpoint or auth is failing silently. Users would be shown already-completed setup steps.
- **Fallback:** Guards default to `false` (show the step) on any error — safe fallback already specified in RESEARCH.md anti-patterns

---

## Ablation Plan

**No ablation plan** — This phase implements two independent components (backend endpoint and frontend machine) that cannot be usefully ablated against each other. The machine definition itself has no sub-components to ablate; all states are required by the tour flow specification.

The one meaningful ablation — "flat state machine vs. hierarchical" for the `backends` step — is captured as a design decision (hierarchical chosen) in RESEARCH.md#recommended-patterns and is not worth A/B testing since the hierarchical approach directly maps to the product requirement (4 substeps with individual navigation).

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views.

Phase 1 adds CSS custom properties to App.vue and creates new .ts files (machine definition, composable) but does not modify any user-visible views or routes. The first user-visible change happens in Phase 2 (TourOverlay component).

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Backend test suite | All existing pytest tests | 100% pass rate | Current state (pre-phase) |
| Frontend test suite | All existing Vitest tests | 100% pass rate | Current state (pre-phase) |
| Build | vue-tsc + vite build | Exit code 0 | Current state (pre-phase) |
| Step transition time | Target for composed tour | < 300ms | STATE.md#current-baseline |
| Guard evaluation latency | Time from tour boot to first step | < 500ms | RESEARCH.md#recommended-metrics |

**No performance baseline established** — this is the first phase of the v0.5.0 milestone. No prior tour timing data exists.

---

## Evaluation Scripts

**Location of evaluation code:**
```
frontend/src/composables/useTourMachine.test.ts   (to be created during phase execution)
backend/tests/test_app_meta.py                     (to be created during phase execution)
```

**How to run full Level 1 + Level 2 evaluation:**
```bash
# All three checks from project verification requirements
cd /Users/neo/Developer/Workspaces/projects/Agented && just build
cd /Users/neo/Developer/Workspaces/projects/Agented/backend && uv run pytest -x -q
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npm run test:run

# Snapshot size check (once machine is implemented)
cd /Users/neo/Developer/Workspaces/projects/Agented/frontend && npx tsx -e "
import { createActor } from 'xstate';
import { tourMachine } from './src/machines/tourMachine';
const a = createActor(tourMachine);
a.start();
['START','NEXT','NEXT','NEXT','NEXT'].forEach(t => a.send({type:t}));
const size = JSON.stringify(a.getPersistedSnapshot()).length;
console.log('Snapshot size:', size, 'bytes', size < 2048 ? 'PASS' : 'FAIL');
"

# z-index property count check
grep -c "\-\-z-tour-" /Users/neo/Developer/Workspaces/projects/Agented/frontend/src/App.vue
# Expected: 5
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Build passes | | | |
| S2: Backend tests pass | | | |
| S3: Frontend tests pass | | | |
| S4: XState machine exports valid | | | |
| S5: /health/instance-id returns UUID | | | |
| S6: instance_id stable across restarts | | | |
| S7: z-index CSS properties present (5) | | | |
| S8: Machine transitions from idle to welcome | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Branch coverage (machine + composable) | >= 80% | | | |
| P2: Snapshot round-trip fidelity | 100% field match | | | |
| P3: Snapshot size at representative state | < 2048 bytes | | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-01-01 | z-index layering correctness | PENDING | phase-02-visual-layer |
| DEFER-01-02 | Persistence across real browser reload | PENDING | phase-02-visual-layer |
| DEFER-01-03 | instance_id mismatch triggers tour reset | PENDING | phase-02-visual-layer |
| DEFER-01-04 | Guard auto-skip with real backend state | PENDING | phase-04-core-step-content |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM

**Justification:**
- Sanity checks: Adequate — 8 checks covering build, tests, API contract, CSS properties, and basic machine behavior. Commands are specific and executable. S5/S6 require a running server but are independently covered by backend pytest.
- Proxy metrics: Moderately evidenced — P2 (snapshot round-trip) has HIGH correlation because it IS the metric. P1 (branch coverage) is a MEDIUM proxy because coverage does not guarantee correctness under real conditions. P3 (snapshot size) is HIGH correlation for the baseline but may not capture the fully-populated terminal state.
- Deferred coverage: Comprehensive for this phase — all four deferred items are critical Phase 1 behaviors (z-index, persistence, reset detection, guards) that have explicit validates_at references and fallback plans.

**What this evaluation CAN tell us:**
- Whether the XState v5 API was used correctly (TypeScript + runtime checks)
- Whether the Flask migration and endpoint are structurally correct
- Whether the machine topology handles all defined transitions without errors
- Whether the serialization contract holds for mock/unit-test conditions
- Whether the CSS property names and values match the agreed convention

**What this evaluation CANNOT tell us:**
- Whether z-index values prevent actual visual conflicts (deferred to phase-02-visual-layer)
- Whether persistence works through a real browser reload cycle (deferred to phase-02-visual-layer)
- Whether guard API calls succeed against real backend endpoints under auth edge cases (deferred to phase-04-core-step-content)
- Whether `@xstate/vue` `useActor` correctly accepts a pre-created actor with restored snapshot (open question in RESEARCH.md — needs runtime validation during implementation)
- Tour completion time (no visual components to measure against until Phase 2+)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-21*
