# Evaluation Plan: Phase 16 — Frontend Quality & User Experience

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Vue 3 error boundaries (onErrorCaptured), centralized API error handling (STATUS_MAP), shared SSE composable (useEventSource), Promise.allSettled sidebar coordination, build-time env validation (@julr/vite-plugin-validate-env), OpenAPI docstring completion
**Reference papers:** No academic papers — all patterns sourced from Vue 3 official docs, codebase analysis, and established UX engineering practices (see 16-RESEARCH.md#sources)

---

## Evaluation Overview

This phase is a consistency and consolidation effort, not a capability expansion. The individual building blocks already exist: `apiFetch` with retry, `createAuthenticatedEventSource` with backpressure, `useToast`, `LoadingState`, `ErrorState`, `EmptyState`. The work is wiring them together correctly in ~21 views and 3 composables, while adding two new files (ErrorBoundary.vue, error-handler.ts) and consolidating SSE boilerplate into useEventSource.

Because the deliverables are frontend code quality changes rather than algorithmic improvements, there are no benchmark scores or numerical performance targets to hit. Evaluation is instead structured around three questions: (1) Does the code compile and pass type checking? (2) Do the new units behave as specified? (3) Do all async views now surface errors and loading states correctly to users?

Proxy metrics are available and meaningful for this phase: test coverage of the four new units (ErrorBoundary, error-handler, useEventSource, AppErrorHandling) is a direct measure of behavioral verification, and structural grep checks on the codebase confirm that the consolidation patterns were applied uniformly. Deferred items are limited to full manual UX walkthroughs under network throttling, which require a running browser session and are not automatable.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Frontend build passes (vue-tsc + vite) | CLAUDE.md verification requirement | Proves no TypeScript regressions; all plan verification sections require this |
| Backend tests pass (pytest) | CLAUDE.md verification requirement | Plan 16-03 only modifies docstrings; any failure indicates accidental logic change |
| Unit test count for new components | 16-04-PLAN.md success criteria | Plan specifies minimum test counts: ErrorBoundary 5+, error-handler 8+, useEventSource 10+, AppErrorHandling 8+ |
| formatApiError returns ERR-{code} for all STATUS_MAP entries | 16-01-PLAN.md, 16-04-PLAN.md | Core behavioral contract for UX-06 (actionable error messages with codes) |
| handleApiError consolidated usage across 16 EntityLayout views | 16-05-PLAN.md | Coverage proxy for UX-01 and UX-04 |
| No console.warn in App.vue catch blocks | 16-01-PLAN.md verification gate | 6 silent failures documented at baseline; all must be replaced with handleApiError toasts |
| useConversation/useAiChat/useProjectSession import from useEventSource | 16-02-PLAN.md | Structural proxy for UX-03 code deduplication |
| No createAuthenticatedEventSource in consumer composables | 16-02-PLAN.md | Confirms SSE lifecycle delegation is complete |
| OpenAPI docstring coverage = 100% | 16-03-PLAN.md | Baseline is 398/416 (95%); target is 416/416 (100%) |
| env.ts schema marks VITE_ALLOWED_HOSTS as optional | 16-03-PLAN.md | Guards against breaking existing deployments |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 18 | Build/type/test pass gates and structural code pattern checks |
| Proxy (L2) | 5 | Coverage metrics and grep-based conformance checks |
| Deferred (L3) | 3 | Full manual UX walkthrough requiring running browser |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: Frontend production build

- **What:** vue-tsc type checking + Vite production bundle compile
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run build 2>&1 | tail -10`
- **Expected:** Build exits with code 0; output contains "built in" with no TypeScript errors
- **Failure means:** A new file introduced a type error, a missing import, or broke an existing type contract. Block progression; find and fix the type error before any other checks.

### S2: Full frontend test suite passes

- **What:** All 29 existing test files (344 tests at baseline) plus the 4 new test files from plan 16-04 pass
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run 2>&1 | tail -10`
- **Expected:** Output shows all test files passed, zero failures. New file count should be at least 33 test files total (29 existing + 4 new).
- **Failure means:** Either a new test caught a behavioral bug (good — fix it), or a refactor broke an existing consumer (regression — fix it without losing the test).

### S3: Backend pytest passes

- **What:** All backend Python tests pass after plan 16-03 docstring additions
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest 2>&1 | tail -5`
- **Expected:** All tests pass, no failures. Docstring-only changes should produce zero test impact.
- **Failure means:** An accidental logic change was made to a route handler while editing docstrings. Revert the logic portion and keep only the docstring.

### S4: ErrorBoundary component file exists with onErrorCaptured

- **What:** The ErrorBoundary.vue file exists and contains the Vue 3 error capture hook
- **Command:** `grep -l 'onErrorCaptured' /Users/neo/Developer/Projects/Agented/frontend/src/components/base/ErrorBoundary.vue && echo OK`
- **Expected:** `OK` — file exists and contains `onErrorCaptured`
- **Failure means:** Plan 16-01 task 1 did not execute or ErrorBoundary was not created.

### S5: ErrorBoundary wraps router-view in App.vue (not entire App)

- **What:** App.vue uses ErrorBoundary around router-view but NOT around the sidebar or toast container
- **Command:** `grep -n 'ErrorBoundary\|router-view\|AppSidebar' /Users/neo/Developer/Projects/Agented/frontend/src/App.vue | head -20`
- **Expected:** ErrorBoundary appears in the file; router-view appears inside/adjacent to ErrorBoundary; AppSidebar is NOT nested inside ErrorBoundary lines
- **Failure means:** Incorrect placement — if sidebar is inside ErrorBoundary, a sidebar crash disables the error boundary fallback itself.

### S6: error-handler.ts exports formatApiError and handleApiError

- **What:** The centralized error handler module exists with both required exports
- **Command:** `grep -E 'export (function|const) (formatApiError|handleApiError)' /Users/neo/Developer/Projects/Agented/frontend/src/services/api/error-handler.ts`
- **Expected:** Two matching lines, one for each export
- **Failure means:** Plan 16-01 task 1 is incomplete; the STATUS_MAP module was not fully created.

### S7: formatApiError returns ERR codes for all 9 known status codes

- **What:** Each entry in STATUS_MAP produces a string containing its error code
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && node -e "
const { formatApiError } = require('./src/services/api/error-handler.ts');
const cases = [[0,'ERR-TIMEOUT'],[401,'ERR-401'],[403,'ERR-403'],[404,'ERR-404'],[409,'ERR-409'],[422,'ERR-422'],[429,'ERR-429'],[500,'ERR-500'],[503,'ERR-503']];
cases.forEach(([s,code]) => { const r = formatApiError(s); if (!r.includes(code)) console.error('FAIL:', s, code, r); else console.log('OK:', s, code); });
" 2>&1`
- **Expected:** 9 `OK:` lines; alternatively, this is verified by the unit tests in S2 which run the same assertions via Vitest
- **Failure means:** STATUS_MAP is incomplete or formatApiError has a bug in code generation.

### S8: No console.warn in App.vue sidebar catch blocks

- **What:** All 6 silent sidebar failure warnings have been replaced with handleApiError toasts
- **Command:** `grep 'console.warn.*Sidebar.*Failed' /Users/neo/Developer/Projects/Agented/frontend/src/App.vue | wc -l`
- **Expected:** `0` — no matches
- **Failure means:** Plan 16-01 task 2 did not complete the catch block replacement. The baseline had 6 such lines; any remaining count is a regression in UX-04 coverage.

### S9: App.vue uses Promise.allSettled for sidebar loading

- **What:** Sidebar fetches are coordinated via Promise.allSettled rather than independent calls
- **Command:** `grep -c 'Promise.allSettled' /Users/neo/Developer/Projects/Agented/frontend/src/App.vue`
- **Expected:** At least `1`
- **Failure means:** Sidebar loading is still uncoordinated; sidebarLoading state will never settle correctly.

### S10: useEventSource composable exists and is imported by all 3 SSE consumers

- **What:** The shared composable file exists and each consumer uses it
- **Command:** `ls /Users/neo/Developer/Projects/Agented/frontend/src/composables/useEventSource.ts && grep -l 'useEventSource' /Users/neo/Developer/Projects/Agented/frontend/src/composables/useConversation.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useAiChat.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useProjectSession.ts`
- **Expected:** 4 lines — the useEventSource.ts path, then all 3 consumer paths
- **Failure means:** Plan 16-02 did not complete one or more refactors. Missing consumer will still manage its own SSE lifecycle, meaning SSE connection leaks on rapid navigation remain for that composable.

### S11: No direct createAuthenticatedEventSource calls in SSE consumers

- **What:** The 3 consumer composables no longer call createAuthenticatedEventSource directly (they delegate to useEventSource)
- **Command:** `grep 'createAuthenticatedEventSource' /Users/neo/Developer/Projects/Agented/frontend/src/composables/useConversation.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useAiChat.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useProjectSession.ts`
- **Expected:** Zero matches (empty output)
- **Failure means:** The refactor was incomplete; SSE boilerplate remains duplicated in at least one consumer.

### S12: env.ts schema file exists with optional VITE_ALLOWED_HOSTS

- **What:** The environment validation schema exists and marks the only current env var as optional
- **Command:** `grep 'VITE_ALLOWED_HOSTS' /Users/neo/Developer/Projects/Agented/frontend/src/env.ts && grep 'optional' /Users/neo/Developer/Projects/Agented/frontend/src/env.ts`
- **Expected:** Both lines match — the var is defined AND marked optional (preventing breakage of existing deploys)
- **Failure means:** Either the schema file was not created (plan 16-03 task 1 incomplete) or the var was marked required (breaking existing deployments that don't set it).

### S13: ValidateEnv plugin is active in vite.config.ts

- **What:** The env validation plugin is registered in the Vite build config
- **Command:** `grep 'ValidateEnv' /Users/neo/Developer/Projects/Agented/frontend/vite.config.ts`
- **Expected:** At least one match showing the plugin import or usage
- **Failure means:** Plan 16-03 task 1 did not update vite.config.ts; env validation will not run at build time.

### S14: OpenAPI docstring coverage reaches 100%

- **What:** All public route handler functions have docstrings serving as OpenAPI summaries
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python3 -c "
import ast, os
routes_dir = 'app/routes'
total, with_doc = 0, 0
missing = []
for f in sorted(os.listdir(routes_dir)):
    if not f.endswith('.py') or f == '__init__.py': continue
    tree = ast.parse(open(os.path.join(routes_dir, f)).read())
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and not n.name.startswith('_'):
            total += 1
            if ast.get_docstring(n): with_doc += 1
            else: missing.append(f'{f}:{n.name}')
print(f'{with_doc}/{total} ({100*with_doc//total}%)')
if missing: print('Missing:', missing)
"`
- **Expected:** `416/416 (100%)` with no missing list
- **Failure means:** Plan 16-03 task 2 left some route handlers without docstrings. The baseline was 398/416 (95%); 18 handlers needed additions.

### S15: All 16 EntityLayout views import handleApiError

- **What:** Every EntityLayout-based view has the centralized error handler wired to its loadEntity function
- **Command:** `for f in AgentDesignPage AuditDetail BackendDetailPage GenericTriggerDashboard GenericTriggerHistory McpServerDetailPage PluginDetailPage ProductSettingsPage ProjectPlanningPage ProjectSettingsPage SkillDetailPage SuperAgentPlayground TeamBuilderPage TeamDashboard TeamSettingsPage WorkflowBuilderPage; do grep -l 'handleApiError' /Users/neo/Developer/Projects/Agented/frontend/src/views/${f}.vue 2>/dev/null || echo "MISSING: ${f}"; done`
- **Expected:** 16 file paths printed; zero `MISSING:` lines
- **Failure means:** One or more EntityLayout views will silently swallow API errors without toast notifications (UX-04 incomplete for those views).

### S16: No EntityLayout view incorrectly imports LoadingState

- **What:** EntityLayout views must not add duplicate loading UI on top of EntityLayout's native loading spinner
- **Command:** `for f in AgentDesignPage AuditDetail BackendDetailPage GenericTriggerDashboard GenericTriggerHistory McpServerDetailPage PluginDetailPage ProductSettingsPage ProjectPlanningPage ProjectSettingsPage SkillDetailPage SuperAgentPlayground TeamBuilderPage TeamDashboard TeamSettingsPage WorkflowBuilderPage; do grep -l 'LoadingState' /Users/neo/Developer/Projects/Agented/frontend/src/views/${f}.vue 2>/dev/null && echo "WRONG PATTERN: ${f}"; done`
- **Expected:** Zero `WRONG PATTERN:` lines (no output)
- **Failure means:** The wrong loading pattern was applied; views will show nested spinners (EntityLayout spinner + a second LoadingState) creating visual glitches.

### S17: SketchChatPage has full loading/error pattern

- **What:** The one non-EntityLayout view with blocking initial fetches has LoadingState, ErrorState, and handleApiError
- **Command:** `grep -l 'LoadingState' /Users/neo/Developer/Projects/Agented/frontend/src/views/SketchChatPage.vue && grep -l 'ErrorState' /Users/neo/Developer/Projects/Agented/frontend/src/views/SketchChatPage.vue && grep -l 'handleApiError' /Users/neo/Developer/Projects/Agented/frontend/src/views/SketchChatPage.vue && echo "ALL OK"`
- **Expected:** `ALL OK`
- **Failure means:** SketchChatPage still shows blank content during initial load or shows no error UI when the projects/sketches API fails.

### S18: main.ts sets app.config.errorHandler for defense-in-depth logging

- **What:** Uncaught Vue errors (from event handlers, not caught by ErrorBoundary) are logged
- **Command:** `grep 'app.config.errorHandler' /Users/neo/Developer/Projects/Agented/frontend/src/main.ts`
- **Expected:** At least one match
- **Failure means:** Event handler errors that escape the ErrorBoundary will be silently swallowed rather than logged to the console.

**Sanity gate:** ALL 18 sanity checks must pass. Any failure blocks progression and must be resolved before reporting the phase as complete.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of quality/performance.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full evaluation. Treat results with appropriate skepticism.

### P1: Unit test coverage for new Phase 16 components

- **What:** Test coverage percentage for the four new/modified files that are the core deliverables of this phase
- **How:** Run Vitest with coverage and extract per-file coverage for ErrorBoundary.vue, error-handler.ts, useEventSource.ts, and AppErrorHandling integration
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:coverage 2>&1 | grep -E "ErrorBoundary|error-handler|useEventSource|AppErrorHandling"`
- **Target:** Each of the four new files achieves >= 80% statement coverage
- **Evidence:** Plan 16-04 specifies minimum test counts (5+, 8+, 10+, 8+ cases respectively), which mathematically implies >= 80% if the test cases are well-designed. The behavioral contracts in the plan's `must_haves` leave no major branches unexercised.
- **Correlation with full metric:** HIGH — test coverage directly measures whether the specified behaviors were implemented and verified. Low coverage means untested edge cases in error boundary recovery or SSE cleanup.
- **Blind spots:** Coverage does not verify that the error boundary displays correct text or that toasts are visually readable. It also does not verify that SSE connections actually close on unmount in a real browser (only in jsdom).
- **Validated:** No — awaiting deferred validation D1 for the real-browser SSE leak check.

### P2: Zero raw inject('showToast') usage in modified views

- **What:** All 21 modified views use the `useToast()` composable, not the raw inject pattern
- **How:** Grep for the inject pattern in all files modified by plans 16-01, 16-05
- **Command:** `grep -r "inject('showToast')\|inject(\"showToast\")" /Users/neo/Developer/Projects/Agented/frontend/src/views/ /Users/neo/Developer/Projects/Agented/frontend/src/App.vue | wc -l`
- **Target:** `0` — zero matches
- **Evidence:** The codebase convention documented in RESEARCH.md and repeated in all plan verification sections explicitly bans raw inject. useToast() is the established pattern. One known violation was SuperAgentPlayground.vue which plan 16-05 specifically calls out as needing the composable added.
- **Correlation with full metric:** HIGH — this is a direct structural check, not an approximation. Zero matches means the convention was followed uniformly.
- **Blind spots:** Does not check components outside the modified view set. Does not catch cases where showToast was obtained via a different mechanism (e.g., `provide`/`inject` with a different key name).
- **Validated:** No — this is itself a sanity-level check elevated to proxy because it spans 21 files and captures cross-cutting convention adherence.

### P3: SSE duplication reduction — no manual onUnmounted SSE cleanup in consumers

- **What:** The ~60 lines of duplicated SSE setup across useConversation, useAiChat, useProjectSession are replaced by delegation to useEventSource
- **How:** Grep for manual onUnmounted calls that reference SSE-related variables in the three consumer files
- **Command:** `grep -n 'onUnmounted' /Users/neo/Developer/Projects/Agented/frontend/src/composables/useConversation.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useAiChat.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useProjectSession.ts`
- **Target:** Zero lines referencing SSE-related variable cleanup in onUnmounted (useEventSource handles cleanup automatically)
- **Evidence:** The RESEARCH.md pitfall section explicitly documents SSE connection leaks on rapid navigation as the key risk this refactor prevents. The useEventSource composable calls `onUnmounted(close)` internally, making manual cleanup in consumers redundant and its absence confirmable.
- **Correlation with full metric:** MEDIUM — grep for onUnmounted absence confirms cleanup delegation but does not verify the cleanup actually fires. Actual leak prevention requires browser Network tab inspection (see D2).
- **Blind spots:** A consumer might still have an unUnmounted call for non-SSE cleanup (e.g., timers). The grep should look for SSE-specific patterns (eventSource, source, stream references in the onUnmounted callback), not just any onUnmounted call.
- **Validated:** No — awaiting deferred validation D2 for real browser SSE leak test.

### P4: OpenAPI coverage visible in Swagger UI

- **What:** All route summaries appear in the auto-generated OpenAPI spec at /docs
- **How:** Fetch the OpenAPI JSON and count paths with non-empty summary fields
- **Command:** `curl -s http://localhost:20000/openapi/openapi.json 2>/dev/null | python3 -c "import json,sys; spec=json.load(sys.stdin); paths=spec.get('paths',{}); total=sum(len(v) for v in paths.values()); with_summary=sum(1 for p in paths.values() for op in p.values() if isinstance(op,dict) and op.get('summary')); print(f'{with_summary}/{total} operations have summary')" || echo "Backend not running — run: just dev-backend"`
- **Target:** >= 416/416 operations have a non-empty summary field (100%)
- **Evidence:** flask-openapi3 generates the `summary` field from function docstrings. The AST-based count in S14 measures the same thing at the source level; this metric measures the generated artifact. Both should agree.
- **Correlation with full metric:** HIGH — the spec is directly derived from docstrings; coverage in the spec reflects docstring coverage.
- **Blind spots:** Requires backend running. Does not verify the quality or accuracy of summaries (only their presence). SSE protocol documentation in multi-line docstrings may be truncated in the summary field.
- **Validated:** No — full developer experience validation deferred to D3.

### P5: Triggers.py run_trigger documents all 10 prompt placeholders

- **What:** The highest-risk documentation gap (undocumented prompt placeholder syntax) is closed
- **How:** Check that the run_trigger docstring contains all 10 placeholder names
- **Command:** `python3 -c "
import ast
src = open('/Users/neo/Developer/Projects/Agented/backend/app/routes/triggers.py').read()
tree = ast.parse(src)
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name == 'run_trigger':
        doc = ast.get_docstring(n) or ''
        placeholders = ['{trigger_id}','{bot_id}','{paths}','{message}','{pr_url}','{pr_number}','{pr_title}','{pr_author}','{repo_url}','{repo_full_name}']
        missing = [p for p in placeholders if p not in doc]
        if missing: print('MISSING:', missing)
        else: print('ALL 10 PLACEHOLDERS DOCUMENTED')
"`
- **Target:** `ALL 10 PLACEHOLDERS DOCUMENTED`
- **Evidence:** Plan 16-03 task 2 explicitly lists all 10 placeholders from `PromptRenderer._KNOWN_PLACEHOLDERS` and requires each appears in the docstring. This is the single most important documentation deliverable because developers building custom triggers currently have no reference for available placeholders.
- **Correlation with full metric:** HIGH — this directly checks the documentation content, not a proxy for it.
- **Blind spots:** Does not verify the descriptions are accurate (only that the placeholder names are present). Does not verify the Swagger UI renders the multi-line docstring correctly.
- **Validated:** No — accurate placeholder documentation requires human review of the rendered /docs page (see D3).

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring integration or resources not available now.

### D1: Manual UX walkthrough across all async views under slow network — DEFER-16-01

- **What:** Every async view (approximately 60+ views total) shows a visible loading indicator during data fetch, shows a meaningful error message with error code when the fetch fails, and provides a retry mechanism where applicable
- **How:** In Chrome DevTools, throttle to "Slow 3G". Navigate to each view listed in the phase scope. For each: (a) verify a spinner or skeleton appears immediately on navigation, (b) block the network and verify an error state appears with an error code (ERR-4xx format), (c) click retry and verify only the failed section re-fetches
- **Why deferred:** Requires a running dev server, a human tester, and browser DevTools. Cannot be automated with the current test setup (Vitest + happy-dom does not simulate network throttling or real browser rendering).
- **Validates at:** Manual testing session after all 5 plans complete
- **Depends on:** All 5 plans executed, `just dev-backend` and `just dev-frontend` running
- **Target:** 100% of async views show loading states; 100% of API errors produce a toast with an ERR-code; 100% of error states have a functioning retry that is per-section (not full page reload)
- **Risk if unmet:** Some views may still show blank content during slow loads (UX-01 gap) or show raw HTTP error messages without codes (UX-06 gap). These are UX regressions that affect user confidence in the product.
- **Fallback:** If issues are found, file targeted fixes in a follow-up plan scoped to the specific views that failed the walkthrough.

### D2: SSE connection leak test in real browser — DEFER-16-02

- **What:** Rapid navigation between SSE-using views (SuperAgentPlayground → ProjectDashboard → back) does not accumulate open EventSource connections
- **How:** Open Chrome DevTools Network tab. Navigate rapidly between three SSE-enabled views. After 10 navigations, verify the Network tab shows at most 1 active EventSource connection per view type (not 10 stacked connections).
- **Why deferred:** jsdom (Vitest's DOM environment) does not support real EventSource connections. The unit tests in plan 16-04 mock createAuthenticatedEventSource and verify that close() is called, but cannot verify that the underlying network connection actually terminates.
- **Validates at:** Manual testing session (same session as D1)
- **Depends on:** Plan 16-02 complete (useEventSource refactor), running dev environment
- **Target:** Zero accumulated EventSource connections after rapid navigation (at most 1 active per SSE-enabled view currently on screen)
- **Risk if unmet:** Memory and connection leaks in production; server-side SSE handler may accumulate open streams per user session, leading to resource exhaustion. This is the highest-risk deferred item.
- **Fallback:** If leaks are confirmed, check that `onUnmounted` fires correctly in the router context. Vue router's `beforeEach` hook may need to explicitly close SSE connections if component unmounting is deferred.

### D3: Developer experience review of /docs Swagger UI — DEFER-16-03

- **What:** A developer unfamiliar with the codebase can understand what each endpoint does, what format to use for SSE consumers, and what placeholder syntax to use for trigger prompts — from reading the Swagger UI alone
- **How:** A human reviewer (not the implementer) navigates to http://localhost:20000/docs, finds the trigger execution endpoint, reads the prompt placeholder documentation, and confirms they can construct a valid trigger prompt without consulting source code. Same check for SSE streaming endpoints: confirm the event types and payload format are documented inline.
- **Why deferred:** Documentation quality is a subjective human judgment call. The proxy metrics (S14, P4, P5) verify presence and completeness mechanically, but not readability or usefulness.
- **Validates at:** Code review or developer onboarding session
- **Depends on:** Plan 16-03 complete, backend running
- **Target:** A developer can construct a valid trigger prompt with custom placeholders and consume an SSE stream after reading /docs only (no source code consultation needed)
- **Risk if unmet:** Documentation exists but is not useful; developers continue to consult source code for placeholder syntax, defeating the purpose of UX-07 and UX-09.
- **Fallback:** If the Swagger UI renders multi-line docstrings poorly, consider adding a dedicated `/docs/protocols` page with richer documentation.

---

## Ablation Plan

**Purpose:** Isolate component contributions to verify each deliverable adds independent value.

### A1: ErrorBoundary scope validation

- **Condition:** Temporarily remove ErrorBoundary from App.vue and throw a rendering error in a child component
- **Expected impact:** SPA crashes to blank screen without ErrorBoundary; recovery UI appears with it. This confirms the boundary is functional at its declared scope.
- **Command:** `# Manual test: add 'throw new Error("test")' to a child component render function, toggle ErrorBoundary wrapper`
- **Evidence:** Vue 3 official docs on onErrorCaptured guarantee boundary behavior when return value is false

### A2: Silent failure baseline comparison

- **Condition:** Revert App.vue catch blocks to original console.warn (not handleApiError) and block sidebar API with browser DevTools
- **Expected impact:** Six sidebar sections fail silently with no visual feedback; after change, each produces a toast notification with an ERR-code
- **Command:** `# Manual test: block /admin/triggers in DevTools network tab, compare before/after App.vue catch block`
- **Evidence:** Baseline audit documented 6 console.warn calls in App.vue; this ablation verifies the replacement produces visible feedback

### A3: SSE composable code reduction measurement

- **Condition:** Count lines of SSE-related code (connect, reconnect, cleanup) in the three consumer composables before and after plan 16-02
- **Expected impact:** ~60 lines of boilerplate removed from consumer composables, replaced by useEventSource delegation. Verify the shared composable is ~80 lines total, net reduction of ~-40 lines.
- **Command:** `wc -l /Users/neo/Developer/Projects/Agented/frontend/src/composables/useConversation.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useAiChat.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useProjectSession.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useEventSource.ts`
- **Evidence:** RESEARCH.md baseline estimate: "~60 lines duplicated across 3 files". Reduction in individual file line counts plus new shared file should show net savings.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Frontend test count | 29 test files, 344 tests passing | 344 tests pass | Measured 2026-03-04 via `npm run test:run` |
| Backend docstring coverage | 95% (398/416 functions) | 416/416 after phase | Measured 2026-03-04 via AST script |
| console.warn in App.vue sidebar | 6 silent failure locations | 0 after phase | Grep baseline 2026-03-04 |
| Overall test coverage | 12.26% statements (project-wide) | >= 12% maintained; new files >= 80% | Measured 2026-03-04 via `npm run test:coverage` |
| composables coverage | 24.6% statements | Maintained or improved | Measured 2026-03-04 |
| services/api coverage | 30.21% statements | Maintained or improved | Measured 2026-03-04 |

---

## Evaluation Scripts

**Location of evaluation code:**

New test files created by plan 16-04:
```
frontend/src/components/base/__tests__/ErrorBoundary.test.ts
frontend/src/services/__tests__/error-handler.test.ts
frontend/src/composables/__tests__/useEventSource.test.ts
frontend/src/views/__tests__/AppErrorHandling.test.ts
```

**How to run full evaluation:**

```bash
# 1. All sanity checks — run these in sequence
cd /Users/neo/Developer/Projects/Agented/frontend && npm run build
cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest

# 2. Structural grep checks (S4-S18 batch)
grep -l 'onErrorCaptured' /Users/neo/Developer/Projects/Agented/frontend/src/components/base/ErrorBoundary.vue
grep 'console.warn.*Sidebar.*Failed' /Users/neo/Developer/Projects/Agented/frontend/src/App.vue | wc -l
grep -c 'Promise.allSettled' /Users/neo/Developer/Projects/Agented/frontend/src/App.vue
grep 'createAuthenticatedEventSource' /Users/neo/Developer/Projects/Agented/frontend/src/composables/useConversation.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useAiChat.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useProjectSession.ts

# 3. OpenAPI coverage (S14)
cd /Users/neo/Developer/Projects/Agented/backend && python3 -c "
import ast, os
routes_dir = 'app/routes'
total, with_doc = 0, 0
for f in sorted(os.listdir(routes_dir)):
    if not f.endswith('.py') or f == '__init__.py': continue
    tree = ast.parse(open(os.path.join(routes_dir, f)).read())
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and not n.name.startswith('_'):
            total += 1
            if ast.get_docstring(n): with_doc += 1
print(f'{with_doc}/{total} ({100*with_doc//total}%)')
"

# 4. Proxy metrics (P2, P3, P5)
grep -r "inject('showToast')" /Users/neo/Developer/Projects/Agented/frontend/src/views/ /Users/neo/Developer/Projects/Agented/frontend/src/App.vue | wc -l
grep -n 'onUnmounted' /Users/neo/Developer/Projects/Agented/frontend/src/composables/useConversation.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useAiChat.ts /Users/neo/Developer/Projects/Agented/frontend/src/composables/useProjectSession.ts
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Frontend build | [PASS/FAIL] | | |
| S2: All frontend tests pass | [PASS/FAIL] | | New file count: |
| S3: Backend pytest | [PASS/FAIL] | | |
| S4: ErrorBoundary has onErrorCaptured | [PASS/FAIL] | | |
| S5: ErrorBoundary wraps router-view only | [PASS/FAIL] | | |
| S6: error-handler.ts exports both functions | [PASS/FAIL] | | |
| S7: formatApiError returns ERR codes | [PASS/FAIL] | | Checked via unit tests in S2 |
| S8: Zero console.warn in sidebar catch blocks | [PASS/FAIL] | Count: | Baseline: 6 |
| S9: Promise.allSettled in App.vue | [PASS/FAIL] | | |
| S10: useEventSource imported by all 3 consumers | [PASS/FAIL] | | |
| S11: No direct SSE calls in consumers | [PASS/FAIL] | | |
| S12: env.ts marks VITE_ALLOWED_HOSTS optional | [PASS/FAIL] | | |
| S13: ValidateEnv in vite.config.ts | [PASS/FAIL] | | |
| S14: 100% OpenAPI docstring coverage | [PASS/FAIL] | Count: /416 | Baseline: 398/416 |
| S15: All 16 EntityLayout views have handleApiError | [PASS/FAIL] | | Missing: |
| S16: No EntityLayout view imports LoadingState | [PASS/FAIL] | | |
| S17: SketchChatPage has full loading/error pattern | [PASS/FAIL] | | |
| S18: main.ts sets app.config.errorHandler | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Coverage of new files | >= 80% each | | [MET/MISSED] | |
| P2: Zero raw inject('showToast') | 0 matches | | [MET/MISSED] | |
| P3: No manual SSE onUnmounted in consumers | 0 matches | | [MET/MISSED] | |
| P4: OpenAPI operations with summary | 416/416 | | [MET/MISSED] | Requires backend running |
| P5: run_trigger has all 10 placeholders | ALL 10 DOCUMENTED | | [MET/MISSED] | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: ErrorBoundary scope | Crash without / recovery with | | |
| A2: Silent failure baseline | Toast vs. silent | | |
| A3: SSE code reduction | Net line reduction | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-16-01 | Manual UX walkthrough (loading + error states across 60+ views) | PENDING | Manual test session post-execution |
| DEFER-16-02 | SSE connection leak test in real browser | PENDING | Manual test session post-execution |
| DEFER-16-03 | Developer experience review of /docs Swagger UI | PENDING | Code review or onboarding session |

---

## WebMCP Tool Definitions

**Purpose:** Define WebMCP tools the grd-verifier should use to validate frontend health after phase execution.

### Generic Checks

| Tool | Purpose | Expected |
|------|---------|----------|
| hive_get_health_status | Backend is responding after changes | status: healthy |
| hive_check_console_errors | No new JavaScript errors from ErrorBoundary or SSE refactor | No new errors since phase start |
| hive_get_page_info | App renders without blank screen (ErrorBoundary not triggered on load) | Page loads with sidebar and router-view content |

### Page-Specific Tools

| Tool | Page | Purpose | Expected |
|------|------|---------|----------|
| hive_check_sidebar_loading | / (App root) | Sidebar loading spinner appears briefly then data loads | Sidebar renders entity lists after load; no persistent spinner |
| hive_check_entity_layout_error | /agents/{id} (with invalid id) | EntityLayout error state shows with ERR-code toast | Toast notification visible with ERR-404 code; EntityLayout renders error UI with retry |
| hive_check_sketch_chat_loading | /sketch | SketchChatPage shows loading state on initial render | LoadingState component visible before projects/sketches API responds |

### useWebMcpTool() Definitions

```js
// Generic health checks
useWebMcpTool("hive_get_health_status", {})
useWebMcpTool("hive_check_console_errors", { since: "phase_start" })
useWebMcpTool("hive_get_page_info", {})

// Sidebar loading coordination check
useWebMcpTool("hive_check_sidebar_loading", {
  url: "/",
  checks: ["sidebar renders entity lists", "no persistent loading spinner after 3s"]
})

// EntityLayout error state with toast check
useWebMcpTool("hive_check_entity_layout_error", {
  url: "/agents/agent-invalid-id-test",
  checks: ["toast notification contains ERR-404", "error UI visible with retry button"]
})

// SketchChatPage loading state check
useWebMcpTool("hive_check_sketch_chat_loading", {
  url: "/sketch",
  checks: ["LoadingState visible on initial render", "content renders after load completes"]
})
```

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**

- **Sanity checks:** Adequate and complete. The 18 sanity checks cover every behavioral contract stated in the five plan `must_haves` and `success_criteria` sections. Each check has an exact command. All are runnable without browser automation or a live user session.
- **Proxy metrics:** Well-evidenced. All five proxy metrics are structural checks or direct coverage measurements with clear pass/fail thresholds. They are not approximations — P2, P3, and P5 are exact structural tests, and P1 is a standard quantitative metric.
- **Deferred coverage:** Partial but honest. Three items are deferred — two manual testing items (D1, D2) and one subjective quality review (D3). D2 (SSE leak test) carries the highest risk because it cannot be caught by any automated check in the current test infrastructure. The deferred items are correctly classified and cannot be promoted to proxy status without real browser automation tooling.

**What this evaluation CAN tell us:**
- Whether the new code compiles and is type-safe (S1, frontend build)
- Whether ErrorBoundary, error-handler, useEventSource, and sidebar coordination behave as specified (S2, unit tests)
- Whether the SSE refactor was applied consistently to all three consumer composables (S10, S11, P3)
- Whether error messages include the required ERR-code format for all 9 HTTP status codes (S7, P1)
- Whether all 16 EntityLayout views will surface API errors as toasts (S15)
- Whether the OpenAPI documentation gap (398→416 functions) was closed (S14, P4)
- Whether the environment validation plugin is active and non-breaking (S12, S13)

**What this evaluation CANNOT tell us:**
- Whether loading states are actually visible to users on real network connections (deferred to D1 — manual walkthrough under Slow 3G)
- Whether SSE connections actually close at the network level on rapid navigation (deferred to D2 — requires browser Network tab inspection; jsdom cannot test this)
- Whether the Swagger UI documentation is understandable to a developer new to the codebase (deferred to D3 — requires human judgment)
- Whether the ErrorBoundary catches errors from async event handlers (it cannot, by Vue design; this is documented as a known limitation in RESEARCH.md pitfall 1)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
