# Evaluation Plan: Phase 20 — GRD Frontend Wiring

**Designed:** 2026-06-13
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** GrdResearchSessionHandler (new backend); research/grdOuroboros/harness-evolution API modules; ProjectResearchPage + life-harness panels + PlanningCommandBar manifest (frontend wiring); i18n parity sweep
**Reference papers:** N/A — feature-wiring phase. Bar is the house gates defined in CLAUDE.md.

---

## Evaluation Overview

Phase 20 has one genuinely new backend slice (20-01: autoresearch handler + routes) and five frontend-wiring sub-plans (20-02..06). The evaluation strategy reflects that asymmetry: the backend handler is testable in isolation against fakes; the frontend components are testable with mounted-component unit tests; and the full "operator clicks button → gd research streams output" loop must be deferred because it requires a live GRD workspace, the `gd` binary on path, and a running Litestar server.

There are no ML metrics, benchmark datasets, or PSNR-class measures. The proxy tier is therefore dominated by automated test results, type-checker passes, and structural code assertions (handler registered, routes present, i18n keys key-identical across locales). These proxies have a HIGH correlation with the real outcome (working feature) because they directly exercise the integration seams; the only gap they leave is live streaming behaviour and actual UX, which the deferred tier covers.

Success criteria 1–6 map as follows:

| Success Criterion | Tier(s) |
|---|---|
| SC-1: Autoresearch reachable from backend (REQ-14) | L1-S3, L2-P1, L2-P2 |
| SC-2: Frontend API modules wired (REQ-14/15) | L1-S4, L2-P3 |
| SC-3: Research page mounts + functions (REQ-15) | L1-S5, L2-P4 |
| SC-4: Life-harness surfaces exist (REQ-16) | L1-S5, L2-P5 |
| SC-5: PlanningCommandBar exposes full manifest (REQ-17) | L1-S5, L2-P6 |
| SC-6: All 4 locales key-identical (REQ-18) | L1-S6, L2-P7 |

### Verification Level Summary

| Level | Count | Purpose |
|---|---|---|
| Sanity (L1) | 6 | Basic functionality — type-check, format, imports, tests exist |
| Proxy (L2) | 7 | Automated quality measures — test suites, structural assertions, i18n diff |
| Deferred (L3) | 3 | Live integration — real SSE stream, operator walkthrough, visual UX |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. ALL must pass before progression.

### S1: Vue-tsc type-check + vite build
- **What:** TypeScript compilation succeeds for all new .vue/.ts files; Vite produces a build artifact.
- **Command:** `cd /Users/neo/Developer/Projects/Agented && just build`
- **Expected:** Exit code 0. No `error TS` lines. `dist/` directory updated.
- **Maps to:** All plans (type errors in any new file fail this gate).
- **Failure means:** A new component/module has a type error or import that doesn't resolve.

### S2: Python ruff format check
- **What:** New and modified backend files pass ruff formatting (line-length=100, py310).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check app/services/execution_type_handler.py app/services/grd_cli_service.py app_litestar/routes/grd_routes.py`
- **Expected:** Exit code 0. Output: "N files already formatted" (no diffs reported).
- **Maps to:** 20-01.
- **Failure means:** Backend code was not formatted before commit.

### S3: Backend import smoke — new handler importable
- **What:** Python can import the new handler and the registry key exists without a real database.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.execution_type_handler import HANDLER_REGISTRY; h = HANDLER_REGISTRY.get('grd_research'); assert h is not None, 'grd_research not registered'; print('OK:', type(h).__name__)"`
- **Expected:** `OK: GrdResearchSessionHandler` printed. Exit code 0.
- **Maps to:** SC-1 / 20-01.
- **Failure means:** Handler class not defined or not registered in HANDLER_REGISTRY.

### S4: Frontend API module import smoke
- **What:** New TypeScript API modules resolve cleanly when imported (no broken barrel exports).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && node --input-type=module -e "import('./src/services/api/index.ts').then(m => { console.log('research:', typeof m.researchApi); console.log('ouroboros:', typeof m.grdOuroborosApi); })"`
  - Note: if ts-node is not available, the type-check gate (S1) subsumes this check — S1 failure would surface the same broken import.
- **Expected:** `research: object` and `ouroboros: object` (or the exported names from 20-02). Exit code 0.
- **Maps to:** SC-2 / 20-02.
- **Failure means:** Barrel re-export missing or module has a circular import.

### S5: New test files exist and are discovered by the test runner
- **What:** Each plan's new test file is present and collected by the test runner (zero collection errors).
- **Backend command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest --collect-only tests/test_grd_research_handler.py tests/test_grd_research_routes.py 2>&1 | grep -E "(ERROR|collected)"`
- **Frontend command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vitest --run --reporter=verbose 2>&1 | grep -E "FAIL|cannot find|SyntaxError" | head -20`
- **Expected backend:** Lines show `collected N items`, no `ERROR` lines.
- **Expected frontend:** No `FAIL` lines that are NEW (beyond the 7 baseline failures).
- **Maps to:** 20-01 through 20-05.
- **Failure means:** Test file missing, syntax error in test file, or import error at collection time.

### S6: Locale files are valid JSON and contain the new namespace keys
- **What:** All four locale files parse as valid JSON and contain at least one key from the new surfaces (e.g. `research.*` namespace from 20-03; `harness.*` from 20-04; `commandBar.*` from 20-05).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && node -e "const fs=require('fs'); ['en','ko','ja','zh'].forEach(l => { const d=JSON.parse(fs.readFileSync('src/locales/'+l+'.json','utf8')); const has=k=>Object.keys(d).some(x=>x.startsWith(k)); console.log(l,'research:',has('research'),'harness:',has('harness'),'commandBar:',has('commandBar')); })"`
- **Expected:** Four lines, each showing `true true true`.
- **Maps to:** SC-6 / 20-06.
- **Failure means:** A locale file was not updated, contains invalid JSON, or a key namespace is missing.

**Sanity gate:** ALL six checks must pass. Any failure blocks proxy evaluation.

---

## Level 2: Proxy Metrics

**Purpose:** Automated quality approximations that stand in for full integration testing.
**IMPORTANT:** These metrics do not exercise the live `gd` binary, real SSE streams, or actual browser rendering. Treat results as HIGH-confidence indicators with the specific blind spots noted.

### P1: Backend handler test suite — 20-01 handler tests green
- **What:** `test_grd_research_handler.py` asserts that `GrdResearchSessionHandler.start` calls `create_session` with `execution_type='grd_research'`, `stream_json=True`, `use_pty=False`, and the prompt contains `json.dumps(question)` (prompt-injection hardening from phase 19-04).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_grd_research_handler.py -v`
- **Target:** All tests pass. Exit code 0. Zero failures, zero errors.
- **Evidence:** Mirrors the proven `test_grd_chat_handler.py` pattern; the plan explicitly requires these assertions in `must_haves.truths`.
- **Correlation with SC-1:** HIGH — directly exercises the handler contract.
- **Blind spots:** Does not exercise PSM subprocess lifecycle; does not test the actual `gd` binary output.
- **Validated:** No — awaiting deferred validation at phase-20-integration-live.

### P2: Backend route test suite — 20-01 route tests green
- **What:** `test_grd_research_routes.py` asserts `POST /research/start` returns `{session_id}`, `GET /research/threads` returns `[]` for a missing directory and parses `THREAD.md` frontmatter when present, `GET /research/threads/{id}` returns a bundle with THREAD/HYPOTHESES/FINDING (each None-safe).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_grd_research_routes.py -v`
- **Target:** All tests pass. Exit code 0.
- **Evidence:** 20-01 `predicted_outcome` explicitly names these assertions.
- **Correlation with SC-1:** HIGH — covers all five new routes.
- **Blind spots:** Uses `isolated_db` + monkeypatching; does not test real disk I/O against a live `.planning/research/threads/` tree.
- **Validated:** No.

### P3: Frontend API module tests green (20-02)
- **What:** Per-method unit tests for `research.ts` and `grdOuroboros.ts` pass. These mock `apiFetch` and assert correct URL patterns, HTTP methods, and response shapes.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vitest --run src/services/api/research.test.ts src/services/api/grdOuroboros.test.ts`
- **Target:** All tests pass. Zero new failures. Exit code 0.
- **Evidence:** Mirrors existing `triggers.test.ts` / `budgets.test.ts` pattern — apiFetch mock + URL assertion is the established approach.
- **Correlation with SC-2:** HIGH — directly tests the API surface the components consume.
- **Blind spots:** Does not exercise network; does not test against a real Litestar server.
- **Validated:** No.

### P4: Research page mounts without error (20-03)
- **What:** `ProjectResearchPage.vue` and its child components mount in Vitest/happy-dom with stub props and do not throw. The route entry exists in the Vue Router config.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vitest --run src/pages/research/ src/components/research/`
- **Target:** All component tests pass. No `[Vue warn]` errors in test output. Zero new failures beyond the 7 baseline.
- **Evidence:** Every other page in the codebase has a `.test.ts` that mounts with stubs and asserts rendered content; this follows that pattern.
- **Correlation with SC-3:** HIGH (mount-without-error) / MEDIUM (functional correctness — UX deferred).
- **Blind spots:** Happy-dom does not exercise real browser rendering, ResizeObserver, or streaming EventSource behaviour.
- **Validated:** No.

### P5: Life-harness panels mount without error (20-04)
- **What:** `AutonomyEditor.vue`, `RoundList.vue`, `RoundDetail.vue`, `SharedForgeBrowser.vue`, and the 7 GRD-route panels all mount in Vitest. The `/harness` route entry exists in the router config.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vitest --run src/pages/harness/ src/components/harness/`
- **Target:** All component tests pass. No `[Vue warn]` errors. Zero new failures.
- **Evidence:** Panels wire existing backend contracts (no new backend in 20-04); mount-without-error confirms import graph is correct.
- **Correlation with SC-4:** HIGH (surface exists) / MEDIUM (confirm-guarded revert UX deferred).
- **Blind spots:** Does not test that the confirm-guard actually prevents an API call without confirmation; does not verify 16-route coverage exhaustively.
- **Validated:** No.

### P6: PlanningCommandBar manifest coverage (20-05)
- **What:** `planningCommands.ts` exports groups covering Plan/Execute/Verify/Research/Harness/Misc. A unit test imports the manifest and asserts: (a) all six groups are present by key, (b) the total command count equals or exceeds the current count + new GRD commands, (c) every command has a non-empty `label` and `command` field. The `PlanningCommandBar.vue` test mounts and asserts at least one item per group appears in the rendered list.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vitest --run src/composables/planningCommands.test.ts src/components/PlanningCommandBar.test.ts`
- **Target:** All assertions pass. Group count >= 6. Zero new failures.
- **Evidence:** 20-05 describes a declarative `commandGroups` array — structural assertion directly validates the manifest contract.
- **Correlation with SC-5:** HIGH (manifest exists and is structurally correct) / MEDIUM (invoke routing tested by unit; real CLI invocation deferred).
- **Blind spots:** Does not verify that invoking a command actually fires the correct API call end-to-end.
- **Validated:** No.

### P7: i18n parity — zero key diff across all four locales
- **What:** The key sets of `en.json`, `ko.json`, `ja.json`, `zh.json` are identical. Zero keys present in one locale but absent in another.
- **How:** Extract sorted key lists from each file and diff them.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/frontend && node -e "
  const fs = require('fs');
  const locales = ['en','ko','ja','zh'];
  const keys = locales.map(l => {
    const obj = JSON.parse(fs.readFileSync('src/locales/'+l+'.json','utf8'));
    const flatten = (o, prefix='') => Object.entries(o).flatMap(([k,v]) =>
      typeof v === 'object' && v !== null ? flatten(v, prefix+k+'.') : [prefix+k]);
    return { locale: l, keys: new Set(flatten(obj)) };
  });
  let diffs = 0;
  const ref = keys[0];
  keys.slice(1).forEach(({locale, keys: ks}) => {
    ref.keys.forEach(k => { if (!ks.has(k)) { console.log('MISSING in '+locale+': '+k); diffs++; } });
    ks.forEach(k => { if (!ref.keys.has(k)) { console.log('EXTRA in '+locale+': '+k); diffs++; } });
  });
  console.log('Total diff count:', diffs);
  process.exit(diffs > 0 ? 1 : 0);
  "
  ```
- **Target:** `Total diff count: 0`. Exit code 0.
- **Evidence:** CLAUDE.md and MEMORY.md state i18n parity is mandatory and enforced; 20-06 explicitly makes this the key-diff CI test.
- **Correlation with SC-6:** HIGH — directly measures the parity requirement.
- **Blind spots:** Does not verify translation quality or that strings render correctly in the UI.
- **Validated:** No.

### Proxy gate: Overall no-regression gate
- **What:** The full frontend test suite shows no new failures beyond the 7 known baseline.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run 2>&1 | tail -20`
- **Target:** Failure count <= 7. The 7 known failures are: RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas. Any failure outside these names is a NEW failure and blocks merge.
- **Evidence:** Directly stated in CLAUDE.md house gate 3.
- **Correlation:** HIGH with "did not break existing functionality."
- **Blind spots:** The 7 known failures mask any regression in those specific files.
- **Validated:** No.

---

## Level 3: Deferred Validations

**Purpose:** Full validation that requires a live GRD workspace, running Litestar server, or human operator.

### D1: Live autoresearch SSE stream — DEFER-20-01
- **What:** `POST /api/projects/{id}/research/start` responds with `{session_id}`, the SSE stream at `/api/sessions/{session_id}/stream` emits `grd_research` events, and the Research page in a real browser renders hypothesis entries as they arrive.
- **How:** Start the backend with `just dev-backend`; run `just dev-frontend`; open the Research page for a real project; submit a question; observe the SSE stream in DevTools Network tab; verify hypothesis rows appear incrementally.
- **Why deferred:** Requires the `gd` binary on PATH, a `.planning/` workspace, a live Litestar server, and a real browser — none of which are available in the unit-test environment.
- **Validates at:** phase-20-integration-live (manual QA session after merge)
- **Depends on:** L1 + L2 all green; `gd` binary available; backend running on :20000
- **Target:** Session starts within 3 seconds of POST; at least one SSE event received within 30 seconds; Research page shows live status update; no 500 errors in backend logs.
- **Risk if unmet:** The handler may have a subprocess-lifecycle bug not caught by the fake-PSM tests. Fallback: port the `GrdChatSessionHandler` integration test pattern to cover `grd_research`.
- **Maps to:** SC-1 / REQ-14.

### D2: Operator walkthrough — life-harness panels drive the CLI — DEFER-20-02
- **What:** An operator uses the Agented frontend to: (a) view autonomy level and update it via AutonomyEditor, (b) browse and revert a round via RoundDetail confirm-guard, (c) browse shared-forge entries via SharedForgeBrowser, (d) trigger at least two of the 16 GRD routes (e.g. plan-phase, verify-phase) from the Harness panels and observe SSE output.
- **Why deferred:** Requires real project data, a real GRD workspace with round history, and human judgment of UX correctness.
- **Validates at:** phase-20-ux-walkthrough (scheduled after merge, before v0.8.0 tag)
- **Depends on:** Life-harness panel tests green; real project with at least 2 completed rounds
- **Target:** Zero 4xx/5xx errors during walkthrough; confirm-guard prevents revert without explicit confirmation; all 16 route panels render without blank/error states.
- **Risk if unmet:** A panel may be wired to a wrong route URL or use wrong HTTP method. Fallback: add route-URL assertion tests to the panel test files.
- **Maps to:** SC-4 / REQ-16.

### D3: Visual and UX review of localized surfaces — DEFER-20-03
- **What:** A human reviewer switches the app locale to ko/ja/zh and verifies: (a) no layout overflow or truncation on Research page, life-harness panels, and PlanningCommandBar; (b) no untranslated `[key]` placeholders visible; (c) the command bar groups are legible in all four locales.
- **Why deferred:** Visual rendering defects (text overflow, font rendering, RTL edge cases) are not detectable by key-diff or happy-dom tests.
- **Validates at:** phase-20-ux-walkthrough
- **Depends on:** i18n parity gate (P7) green; frontend running in dev or built mode
- **Target:** Zero untranslated placeholders visible; no text overflow breaking layout in any of the four locales.
- **Risk if unmet:** A long Korean or Japanese string may break the command bar dropdown layout. Fallback: add `max-width: 100%; overflow: hidden; text-overflow: ellipsis` to the affected containers.
- **Maps to:** SC-6 / REQ-18.

---

## Ablation Plan

**No ablation plan.** Phase 20 is a feature-wiring phase with no sub-components that need isolated contribution analysis. The handler either works (handler tests green) or it does not; the frontend panels either mount or they do not. There are no hyperparameters, no model architecture choices, and no algorithmic alternatives being compared.

---

## WebMCP Tool Definitions

Phase 20 modifies frontend views (ProjectResearchPage.vue, harness panels, PlanningCommandBar). WebMCP availability is not confirmed in this environment. Definitions are provided for use if WebMCP is available at verification time.

### Generic Checks

| Tool | Purpose | Expected |
|---|---|---|
| hive_get_health_status | Backend is responding after frontend changes | status: healthy |
| hive_check_console_errors | No new JavaScript errors from new components | No new errors |
| hive_get_page_info | App root renders after bundle changes | Page loads with expected content |

### Page-Specific Tools

| Tool | Page | Purpose | Expected |
|---|---|---|---|
| hive_check_research_page_mount | /projects/:id/research | Research page renders without blank state or Vue warn | Page contains research input form or thread list |
| hive_check_harness_route_mount | /harness | Harness route renders AutonomyEditor and panel list | Page contains autonomy-level control |
| hive_check_command_bar_groups | Any page with command bar | PlanningCommandBar shows all 6 groups | Research and Harness groups visible in dropdown |

### useWebMcpTool() Definitions

```js
// Generic health checks
useWebMcpTool("hive_get_health_status", {})
useWebMcpTool("hive_check_console_errors", { since: "phase_start" })
useWebMcpTool("hive_get_page_info", {})

// Research page
useWebMcpTool("hive_check_research_page_mount", {
  url: "/projects/test-project-id/research",
  checks: ["no Vue warn in console", "form or thread-list element present"]
})

// Harness route
useWebMcpTool("hive_check_harness_route_mount", {
  url: "/harness",
  checks: ["autonomy editor element present", "no 404 route warning"]
})

// Command bar
useWebMcpTool("hive_check_command_bar_groups", {
  url: "/",
  checks: ["Research group label present", "Harness group label present", "6 groups total"]
})
```

---

## Baselines

| Baseline | Description | Expected Score | Source |
|---|---|---|---|
| Frontend test suite | Known pre-existing failures | 7 failures, all in named areas | CLAUDE.md house gate 3 |
| Build clean | vue-tsc + vite with no new TS errors | 0 new errors | CLAUDE.md house gate 1 |
| Backend suite (targeted) | Existing handler + route tests pass | 0 regressions in tests touched by 20-01 | CLAUDE.md house gate 2 |
| i18n parity | Locale key diff before phase 20 | 0 diff (established invariant) | MEMORY.md / CLAUDE.md |

---

## Evaluation Scripts

**How to run the full proxy evaluation suite (in order):**

```bash
# S1 + S2: type-check and format
cd /Users/neo/Developer/Projects/Agented && just build
cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check app/services/execution_type_handler.py app/services/grd_cli_service.py app_litestar/routes/grd_routes.py

# S3: import smoke
cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.execution_type_handler import HANDLER_REGISTRY; h=HANDLER_REGISTRY.get('grd_research'); assert h is not None; print('OK:', type(h).__name__)"

# S6 + P7: i18n parity
cd /Users/neo/Developer/Projects/Agented/frontend && node -e "
const fs=require('fs'); const locales=['en','ko','ja','zh'];
const keys=locales.map(l=>{const obj=JSON.parse(fs.readFileSync('src/locales/'+l+'.json','utf8'));
const flatten=(o,p='')=>Object.entries(o).flatMap(([k,v])=>typeof v==='object'&&v!==null?flatten(v,p+k+'.'):[ p+k]);
return{locale:l,keys:new Set(flatten(obj))};});
let diffs=0; const ref=keys[0];
keys.slice(1).forEach(({locale,keys:ks})=>{ref.keys.forEach(k=>{if(!ks.has(k)){console.log('MISSING in '+locale+': '+k);diffs++;}});ks.forEach(k=>{if(!ref.keys.has(k)){console.log('EXTRA in '+locale+': '+k);diffs++;}});});
console.log('Total diff count:',diffs); process.exit(diffs>0?1:0);"

# P1 + P2: backend tests
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_grd_research_handler.py tests/test_grd_research_routes.py -v

# P3 + P4 + P5 + P6 + proxy gate: frontend tests
cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|---|---|---|---|
| S1: just build | | | |
| S2: ruff format | | | |
| S3: handler import smoke | | | |
| S4: api module import smoke | | | |
| S5: test files discovered | | | |
| S6: locale JSON valid + keys present | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|---|---|---|---|---|
| P1: handler tests | All pass | | | |
| P2: route tests | All pass | | | |
| P3: API module tests | All pass | | | |
| P4: Research page mount | All pass, 0 new failures | | | |
| P5: Life-harness panel mount | All pass, 0 new failures | | | |
| P6: Command bar manifest | All pass, >= 6 groups | | | |
| P7: i18n parity diff | diff count = 0 | | | |
| Proxy gate: no-regression | failures <= 7 | | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|---|---|---|---|
| DEFER-20-01 | Live autoresearch SSE stream | PENDING | phase-20-integration-live |
| DEFER-20-02 | Operator life-harness walkthrough | PENDING | phase-20-ux-walkthrough |
| DEFER-20-03 | Visual/UX review localized surfaces | PENDING | phase-20-ux-walkthrough |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: adequate — type-checker + import smoke cover all integration seams before running any tests.
- Proxy metrics: well-evidenced — every proxy directly tests a stated `must_haves.truths` contract from the plan files; i18n diff is deterministic and binary.
- Deferred coverage: partial but honest — the three deferred items cover exactly what cannot be faked (live subprocess, real browser, human UX judgment).

**What this evaluation CAN tell us:**
- Whether the handler is registered and its contract matches the plan's truths.
- Whether all five new routes respond with expected shapes.
- Whether the frontend components mount without import errors or Vue warnings.
- Whether all four locales have identical key sets.
- Whether existing tests were not broken (no-regression gate).

**What this evaluation CANNOT tell us:**
- Whether the `gd` binary actually streams research output correctly through the PSM/SSE pipeline (addressed by DEFER-20-01).
- Whether the confirm-guard UX in RoundDetail behaves correctly under real user interaction (addressed by DEFER-20-02).
- Whether long translated strings overflow the command bar or panel layouts (addressed by DEFER-20-03).

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-13*
