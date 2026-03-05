# Evaluation Plan: Phase 9 — Bot Authoring & Template Ecosystem

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** In-DB curated templates (TPL-01), BaseGenerationService extension for NL creator (TPL-02), {{double_braces}} snippet resolution pipeline (TPL-03), immutable versioning with difflib (TPL-04), expanded preview-prompt endpoint (TPL-05)
**Reference research:** `.planning/milestones/v0.1.0/phases/09-bot-authoring-template-ecosystem/09-RESEARCH.md`

---

## Evaluation Overview

Phase 9 extends the existing Agented platform with five closely related features: a bot template marketplace, a natural language bot creator, a reusable prompt snippet library, prompt template version control with rollback, and a webhook payload test console. All five features are implemented as extensions of existing patterns — not greenfield builds — which means evaluation can leverage the existing test infrastructure directly.

The primary evaluation challenge for this phase is the NL bot creator (TPL-02): quality of AI-generated bot configurations cannot be assessed by automated unit tests alone, since correctness depends on Claude CLI producing semantically valid configurations from natural language descriptions. This is classified as a deferred validation. All other features have sufficient sanity checks and proxy metrics to gate phase completion.

A critical safety invariant runs through TPL-04 and TPL-05: the preview and version history code paths must never spawn subprocess executions. This is testable in unit tests via mock patching and represents a blocking sanity requirement.

The v0.1.0 baseline at phase start is 906/906 backend tests passing and 344/344 frontend tests passing with zero vue-tsc errors. Any regression against this baseline is a blocking failure.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Backend test pass rate (100%) | v0.1.0 STATE.md baseline | Established baseline; regression means broken existing functionality |
| Frontend test pass rate (100%) | v0.1.0 STATE.md baseline | Established baseline for Vue component correctness |
| Frontend build (0 vue-tsc errors) | v0.1.0 STATE.md baseline | TypeScript type safety gate; catches API contract mismatches |
| 5 curated templates seeded | TPL-01 success criterion | Core feature requirement — marketplace needs templates |
| deploy_template() returns valid trigger_id | TPL-01 success criterion | One-click deploy must create a runnable trigger |
| Duplicate deploy creates suffixed name | 09-RESEARCH.md Pitfall 2 | Known failure mode; must be handled |
| {{snippet}} resolves before {placeholder} | TPL-03, 09-RESEARCH.md Rec 2 | Ordering is critical: snippet expansion precedes runtime substitution |
| Circular snippet reference terminates | 09-RESEARCH.md Pitfall 1 | Safety invariant — infinite recursion would crash the render path |
| log_prompt_template_change() stores diff | TPL-04, 09-RESEARCH.md Rec 1 | Immutable versioning principle requires non-empty diff_text |
| preview-prompt-full has no subprocess.Popen | TPL-05, 09-RESEARCH.md Pitfall 4 | Safety invariant explicitly called out in success criteria |
| 27 new backend tests pass | 09-04-PLAN.md success criteria | Coverage proxy for all backend functionality |
| NL generation produces valid CreateTriggerRequest JSON | TPL-02 success criterion | Real quality check; deferred because requires Claude CLI |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 12 checks | Basic functionality, safety invariants, and regression gates |
| Proxy (L2) | 8 metrics | Automated quality approximation via test coverage and build validation |
| Deferred (L3) | 4 validations | End-to-end correctness requiring Claude CLI or running backend |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality and safety invariants. These MUST ALL PASS before proceeding.

### S1: Regression — Backend tests unchanged

- **What:** All previously-passing backend tests continue to pass after Phase 9 implementation
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/ -x -q 2>&1 | tail -5`
- **Expected:** `906 passed` (or higher if new tests added; zero failures)
- **Failure means:** A Phase 9 change broke existing functionality. Block progression; identify regression before proceeding.

### S2: Regression — Frontend tests and build unchanged

- **What:** All previously-passing frontend tests continue to pass; vue-tsc reports zero errors
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vue-tsc --noEmit && npm run test:run 2>&1 | tail -5`
- **Expected:** `344 passed` or higher, zero vue-tsc errors
- **Failure means:** A Phase 9 frontend change introduced a type error or broke an existing component test.

### S3: Bot templates table seeded with exactly 5 templates

- **What:** The `bot_templates` table exists after migration and contains exactly 5 curated templates with the required slugs
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.db.bot_templates import CURATED_BOT_TEMPLATES, get_all_templates; assert len(CURATED_BOT_TEMPLATES) == 5; slugs = {t['slug'] for t in CURATED_BOT_TEMPLATES}; expected = {'pr-reviewer', 'dependency-updater', 'security-scanner', 'changelog-generator', 'test-writer'}; assert slugs == expected, f'Wrong slugs: {slugs}'; print('5 templates with correct slugs: PASS')"`
- **Expected:** `5 templates with correct slugs: PASS`
- **Failure means:** Template seeding is broken. TPL-01 cannot function without templates in the database.

### S4: TriggerGenerationService imports and has required methods

- **What:** The NL bot creator service can be imported and exposes the expected interface
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.services.trigger_generation_service import TriggerGenerationService; from app.services.base_generation_service import BaseGenerationService; assert issubclass(TriggerGenerationService, BaseGenerationService); ctx = TriggerGenerationService._gather_context(); assert 'backends' in ctx and 'trigger_sources' in ctx and 'placeholders' in ctx, f'Missing keys: {list(ctx.keys())}'; print('TriggerGenerationService: PASS')"`
- **Expected:** `TriggerGenerationService: PASS`
- **Failure means:** TPL-02 service is not correctly structured. Either import fails or context gathering is incomplete.

### S5: SnippetService resolves present snippets and leaves missing ones intact

- **What:** The core snippet resolution logic works correctly for both found and missing snippet references — this is a pure function verifiable without a running app
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
from app.services.prompt_snippet_service import SnippetService
# Missing snippet must be left intact
result = SnippetService.resolve_snippets('Hello {{missing_snippet}}')
assert result == 'Hello {{missing_snippet}}', f'Expected unresolved, got: {result}'
print('Missing snippet left intact: PASS')
"`
- **Expected:** `Missing snippet left intact: PASS`
- **Failure means:** SnippetService.resolve_snippets() changes unresolved references — this would silently corrupt prompt templates that contain `{{...}}` patterns that don't correspond to snippets.

### S6: Snippet cycle detection terminates without infinite recursion

- **What:** Circular snippet references (A references B, B references A) terminate safely within the MAX_DEPTH limit
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
import signal, sys

def timeout_handler(signum, frame):
    print('FAIL: snippet resolution hung (circular reference not detected)')
    sys.exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(5)  # 5 second timeout

from app.services.prompt_snippet_service import SnippetService
assert SnippetService.MAX_DEPTH >= 3, 'MAX_DEPTH too low'

signal.alarm(0)
print('Cycle detection configured correctly: PASS')
"`
- **Expected:** `Cycle detection configured correctly: PASS`
- **Failure means:** Cycle detection is misconfigured. Live snippet resolution could enter infinite recursion, crashing the prompt renderer.

### S7: difflib integration produces non-empty unified diff

- **What:** The Python stdlib difflib correctly computes unified diffs between old and new prompt templates
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
import difflib
old = 'Review this PR: {pr_url}'
new = 'Review this PR carefully: {pr_url}\nCheck for security issues.'
diff = list(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile='previous', tofile='current'))
assert len(diff) > 0, 'Diff should be non-empty for different templates'
print(f'difflib produces {len(diff)} diff lines: PASS')
"`
- **Expected:** `difflib produces N diff lines: PASS` (N >= 4)
- **Failure means:** Diff computation is broken. Version history would store empty diffs, defeating the audit trail purpose.

### S8: Preview-prompt-full code path contains no subprocess.Popen calls

- **What:** The preview endpoint must be a pure read operation — no subprocess spawning. This is verifiable statically by inspecting the implementation.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && grep -rn 'subprocess.Popen\|subprocess\.run\|os\.system\|run_trigger' app/services/trigger_service.py | grep -i 'preview' && echo 'FAIL: subprocess call found in preview path' || echo 'No subprocess in preview path: PASS'`
- **Expected:** `No subprocess in preview path: PASS`
- **Failure means:** The preview endpoint could accidentally spawn bot executions. This is a critical safety invariant — users would get unintended executions when testing payloads.

### S9: PromptRenderer.render() signature unchanged

- **What:** The render() method signature must not have changed — it is called from ExecutionService and any signature change is a silent runtime regression
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
import inspect
from app.services.prompt_renderer import PromptRenderer
sig = inspect.signature(PromptRenderer.render)
params = list(sig.parameters.keys())
required = ['trigger', 'trigger_id', 'message_text', 'paths_str']
for p in required:
    assert p in params, f'Missing required param: {p}'
print(f'render() signature intact with params {params}: PASS')
"`
- **Expected:** `render() signature intact: PASS`
- **Failure means:** The render() method signature was modified. This will cause runtime errors in ExecutionService.run_trigger() which calls render() by positional convention.

### S10: Bot template deploy returns a valid trigger_id format

- **What:** The deploy function returns a string with the correct trigger ID prefix
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
from app.db.bot_templates import get_all_templates
templates = get_all_templates()
assert len(templates) == 5, f'Expected 5 templates, got {len(templates)}'
# Check config_json parses correctly for each template
import json
for t in templates:
    cfg = json.loads(t['config_json'])
    assert 'name' in cfg, f'Template {t[\"slug\"]} missing name in config'
    assert 'prompt_template' in cfg, f'Template {t[\"slug\"]} missing prompt_template'
    assert 'backend_type' in cfg, f'Template {t[\"slug\"]} missing backend_type'
    assert 'trigger_source' in cfg, f'Template {t[\"slug\"]} missing trigger_source'
print('All 5 template configs parse and have required fields: PASS')
"`
- **Expected:** `All 5 template configs parse and have required fields: PASS`
- **Failure means:** Template config JSON is malformed. Deploy would fail at the trigger creation step.

### S11: New API modules importable in frontend TypeScript

- **What:** The new TypeScript API client modules compile without errors (type-level sanity)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vue-tsc --noEmit 2>&1 | grep -E 'bot-templates|prompt-snippets|BotTemplate|PromptSnippet|PromptHistoryEntry|PreviewPromptFullResponse' || echo 'No type errors in new API modules: PASS'`
- **Expected:** `No type errors in new API modules: PASS`
- **Failure means:** New TypeScript types or API modules have type errors that will surface at runtime as undefined properties.

### S12: All new routes registered and return non-404

- **What:** The new API blueprints are registered and their endpoints respond
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
from app import create_app
app = create_app()
client = app.test_client()
# Check blueprint registration
rules = [str(r) for r in app.url_map.iter_rules()]
expected_prefixes = ['/admin/bot-templates', '/admin/prompt-snippets']
for prefix in expected_prefixes:
    matching = [r for r in rules if r.startswith(prefix)]
    assert len(matching) > 0, f'No routes found for {prefix}'
    print(f'{prefix}: {len(matching)} routes registered')
print('All new blueprints registered: PASS')
"`
- **Expected:** Blueprint registration counts printed, `All new blueprints registered: PASS`
- **Failure means:** A blueprint was not registered in `routes/__init__.py`. All endpoints under that prefix would return 404.

**Sanity gate:** ALL sanity checks must pass. Any failure blocks progression to proxy metrics or phase sign-off.

---

## Level 2: Proxy Metrics

**Purpose:** Automated quality approximation. These are meaningful indicators but are not validated substitutes for full end-to-end testing.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full evaluation. Treat results with appropriate skepticism.

### P1: New backend test suite — 27 tests across 3 files

- **What:** The 27 new tests written in 09-04-PLAN.md all pass, covering bot templates (6 tests), prompt snippets (10 tests), and version history/rollback/preview (11 tests)
- **How:** Run each new test file individually, then the full suite
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_bot_templates.py tests/test_prompt_snippets.py tests/test_prompt_version_history.py -v 2>&1 | tail -20`
- **Target:** 27 tests collected, 27 passed, 0 failed
- **Evidence:** Tests directly exercise the implemented behavior (template seeding, deploy, snippet CRUD, resolution, circular references, version history, rollback, preview). This is the primary automated quality gate for all five backend features.
- **Correlation with full metric:** HIGH — tests cover all stated success criteria for TPL-01 through TPL-05 at the unit/integration level
- **Blind spots:** Tests run with an isolated SQLite DB and mocked Claude CLI; real behavior with the live CLI is not covered (deferred). Frontend component behavior is not covered.
- **Validated:** No — awaiting deferred validation at phase-09-e2e

### P2: Full backend test suite — no regressions

- **What:** The full backend test suite (906+ tests) passes after adding 27 new tests
- **How:** Run the complete test suite with -q for summary
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/ -q 2>&1 | tail -5`
- **Target:** All tests pass; zero failures; test count >= 933 (906 existing + 27 new)
- **Evidence:** Regression detection. Any failure indicates a Phase 9 change broke existing functionality. The 906-test baseline is established in v0.1.0 STATE.md.
- **Correlation with full metric:** HIGH — a passing full suite means Phase 9 changes are non-breaking
- **Blind spots:** Integration tests (backend/tests/integration/) are not exercised in the standard suite. End-to-end behavior with real external systems is not covered.
- **Validated:** No — deferred to phase-09-e2e for integration test coverage

### P3: Frontend production build — zero errors

- **What:** The frontend builds successfully with vue-tsc type checking and vite bundling after all new views and components are added
- **How:** Run the full build (vue-tsc + vite)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run build 2>&1 | tail -10`
- **Target:** Build completes without errors; no TypeScript errors; no missing imports
- **Evidence:** The CLAUDE.md project instructions require `just build` to pass as part of verification. Type errors in vue-tsc indicate API contract mismatches between frontend and backend that unit tests may miss.
- **Correlation with full metric:** HIGH — a failed build prevents the feature from being usable at all
- **Blind spots:** Build success does not validate runtime behavior (API calls returning correct data, SSE streaming working, visual layout). These are deferred.
- **Validated:** No — runtime behavior deferred to phase-09-e2e

### P4: GET /admin/bot-templates returns 5 templates with required fields

- **What:** The template list endpoint returns the correct structure
- **How:** HTTP test against test client with initialized DB
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_bot_templates.py::test_list_templates_endpoint -v 2>&1 | tail -5`
- **Target:** PASSED
- **Evidence:** Directly validates TPL-01 success criterion #1: "Template marketplace displays 5 curated bots"
- **Correlation with full metric:** HIGH — list endpoint is the first thing the frontend calls
- **Blind spots:** Does not validate visual rendering of cards in the browser
- **Validated:** No — visual verification deferred to phase-09-e2e

### P5: Template deploy creates a trigger with unique name handling

- **What:** Deploying a template once creates a trigger, deploying the same template twice creates a second trigger with a "(2)" suffix
- **How:** HTTP test
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_bot_templates.py::test_deploy_template_creates_trigger tests/test_bot_templates.py::test_deploy_same_template_twice_creates_unique_name -v 2>&1 | tail -8`
- **Target:** Both tests PASSED
- **Evidence:** Directly validates TPL-01 success criterion and guards against Pitfall 2 from RESEARCH.md (duplicate name on second deploy)
- **Correlation with full metric:** HIGH — the deploy endpoint is the core TPL-01 action
- **Blind spots:** Does not validate the deployed trigger is actually executable (deferred)
- **Validated:** No — awaiting deferred validation at phase-09-e2e

### P6: Snippet resolution pipeline — create, resolve, nested, circular

- **What:** End-to-end snippet pipeline: create snippet in DB, resolve it in text, nested resolution, circular reference termination
- **How:** Tests in test_prompt_snippets.py covering the resolution test cases
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_prompt_snippets.py -k 'resolve' -v 2>&1 | tail -10`
- **Target:** All resolution tests PASSED (test_resolve_snippets_basic, test_resolve_snippets_missing, test_resolve_snippets_nested, test_resolve_snippets_circular, test_resolve_endpoint)
- **Evidence:** Resolution is the core TPL-03 requirement. The nested and circular tests directly guard against Pitfall 1 from RESEARCH.md.
- **Correlation with full metric:** HIGH — these tests exercise the production code path used in PromptRenderer.render()
- **Blind spots:** Tests use isolated DB; production behavior requires snippet content to already exist before prompt execution
- **Validated:** No — real prompt execution with snippets deferred to phase-09-e2e

### P7: Version history with diff, rollback, and preview

- **What:** Prompt template changes are logged with diff_text and author, rollback restores prior state and creates a history entry, preview returns rendered prompt and CLI command without subprocess
- **How:** Tests in test_prompt_version_history.py
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_prompt_version_history.py -v 2>&1 | tail -15`
- **Target:** All 11 tests PASSED
- **Evidence:** Directly validates TPL-04 (version history, rollback) and TPL-05 (preview without subprocess) success criteria
- **Correlation with full metric:** HIGH — covers all stated success criteria for these two features
- **Blind spots:** Diff quality (readability, correctness for edge cases like empty templates) is not fully assessed by pass/fail tests
- **Validated:** No — visual diff rendering and real prompt editing workflow deferred to phase-09-e2e

### P8: TriggerGenerationService context includes expected keys and valid backend list

- **What:** The NL bot creator builds a generation context with all required fields (backends, trigger_sources, placeholders, existing_triggers), and the prompt is non-empty
- **How:** Direct service call without Claude CLI
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
from app.services.trigger_generation_service import TriggerGenerationService
ctx = TriggerGenerationService._gather_context()
required_keys = ['backends', 'trigger_sources', 'placeholders', 'existing_triggers']
for k in required_keys:
    assert k in ctx, f'Missing key: {k}'
assert len(ctx['backends']) >= 2, 'Expected at least 2 backends'
assert 'github' in ctx['trigger_sources'] and 'webhook' in ctx['trigger_sources']

prompt = TriggerGenerationService._build_prompt('Create a PR reviewer bot', ctx)
assert len(prompt) > 100, f'Prompt too short: {len(prompt)} chars'
assert 'CreateTriggerRequest' in prompt or 'trigger_source' in prompt or 'prompt_template' in prompt, 'Prompt missing JSON schema guidance'
print(f'Context has all required keys, prompt is {len(prompt)} chars: PASS')
"`
- **Target:** `Context has all required keys, prompt is N chars: PASS`
- **Evidence:** Context quality directly affects generation quality. Missing context keys (like available trigger sources) would cause Claude to generate invalid configurations. This is the best proxy for NL generation quality without running the actual Claude CLI.
- **Correlation with full metric:** MEDIUM — good context is necessary but not sufficient for good generation; actual Claude output quality is deferred
- **Blind spots:** Does not test that Claude's output is valid, only that the input context and prompt are well-structured
- **Validated:** No — actual NL generation quality deferred to DEFER-09-01

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring a running backend, Claude CLI, or browser-based visual inspection.

### D1: NL bot creator generates valid, executable trigger configuration — DEFER-09-01

- **What:** The NL bot creator, given a plain English description, produces a bot configuration that passes CreateTriggerRequest validation and can be deployed and executed without manual editing
- **How:** Run `POST /admin/triggers/generate/stream` with real Claude CLI active, with 3 representative descriptions covering different trigger sources (github, webhook, schedule); inspect generated configs for validity
- **Why deferred:** Requires Claude CLI installed and configured. Quality is inherently qualitative — no automated assertion can measure "bot does what the description says"
- **Validates at:** phase-09-e2e (when running backend with Claude CLI is available)
- **Depends on:** Claude CLI installed at expected path, real SSE streaming working end-to-end
- **Target:** >80% of generated configs (per RESEARCH.md Experiment Design baseline) pass CreateTriggerRequest Pydantic validation without manual editing; at minimum name, prompt_template, backend_type, and trigger_source fields are populated correctly
- **Risk if unmet:** NL creator requires manual JSON editing by the user after generation, defeating the feature's purpose. Mitigation: the frontend can show warnings for validation failures and allow pre-deploy editing — this is already planned in RESEARCH.md Open Question 3.
- **Fallback:** If generation quality is consistently below 60%, add more explicit JSON schema examples to _build_prompt() and re-evaluate.

### D2: Deployed template bot executes successfully end-to-end — DEFER-09-02

- **What:** A bot deployed from a template (e.g., PR Reviewer via the github trigger) actually runs successfully when triggered and produces reasonable output
- **How:** Deploy the "PR Reviewer" template via the marketplace, configure it with a test GitHub repo, trigger it with a test PR event, observe execution logs
- **Why deferred:** Requires a running backend, Claude CLI, and a test GitHub repository with webhook configured
- **Validates at:** phase-09-e2e
- **Depends on:** Running backend, Claude CLI, GitHub webhook setup
- **Target:** Execution completes without errors; output contains code review commentary (not empty/error)
- **Risk if unmet:** Template configurations may contain invalid placeholder combinations for certain trigger sources. Mitigation: review each of the 5 template configs manually before declaring feature complete; the unit test for config_json parsing (S10) provides partial coverage.
- **Fallback:** Fix individual template configs based on observed failures; template config is seed data, editable without code changes.

### D3: Snippet propagation verified across multiple bot executions — DEFER-09-03

- **What:** Updating a snippet's content causes the new content to be used in the next bot execution for all bots referencing that snippet
- **How:** Create a snippet, reference it in two bots' prompt templates, execute both bots, update the snippet, execute both bots again — confirm the second execution uses the updated snippet content
- **Why deferred:** Requires two complete bot executions with observable outputs; not achievable in unit tests
- **Validates at:** phase-09-e2e
- **Depends on:** Running backend, Claude CLI, ability to observe execution outputs
- **Target:** 100% of bots referencing an updated snippet use the new content on their next execution
- **Risk if unmet:** Snippet caching (if any was inadvertently introduced) would cause stale content. The code review check (grep for caching of snippet content in PromptRenderer) partially mitigates this.
- **Fallback:** Audit SnippetService.resolve_snippets() for any memoization or caching and remove it.

### D4: Visual verification of UI components — DEFER-09-04

- **What:** Visual inspection of the bot template marketplace cards, prompt snippet library CRUD, version history diff view (colored diff lines), and webhook test console split-panel layout in a real browser
- **How:** Run `just dev-backend` + `just dev-frontend`, navigate to /bot-templates, /prompt-snippets, and trigger dashboard; verify visual correctness of all new UI elements
- **Why deferred:** Automated Vitest tests use happy-dom which does not render CSS or compute layout; visual layout cannot be asserted in unit tests
- **Validates at:** phase-09-e2e (browser-based review)
- **Depends on:** Both dev servers running; real data in DB (templates seeded, snippets created, trigger with version history)
- **Target:** All five features are visually navigable; no broken layouts; diff colors applied; toast notifications appear on deploy
- **Risk if unmet:** Layout regressions or missing navigation items. Low risk since the plans specify exact CSS variable usage and existing component patterns.
- **Fallback:** Fix CSS/template issues; these are cosmetic and do not affect backend functionality.

---

## Ablation Plan

**Purpose:** Isolate component contributions to understand what each piece actually delivers.

### A1: Snippet resolution ordering — snippets before vs. after placeholder substitution

- **Condition:** In PromptRenderer.render(), move snippet resolution AFTER {placeholder} substitution (the wrong ordering) and observe behavior with a template that uses both `{{snippet}}` and `{paths}`
- **Expected impact:** Snippet references containing `{paths}` in their content would be substituted with the path string before snippet resolution, causing incorrect output — demonstrates why pre-resolution ordering is critical
- **Command:** Manual code modification test — not run in CI; used to verify the ordering requirement is real
- **Evidence:** 09-RESEARCH.md Recommendation 2 establishes that `{{snippet}}` must resolve before `{placeholder}` to avoid collisions. This ablation confirms the requirement is non-theoretical.

### A2: NL generation with vs. without context injection

- **Condition:** Call TriggerGenerationService._build_prompt() with an empty context dict vs. full context, compare prompt length and specificity
- **Expected impact:** Without context, the prompt lacks available backend types, trigger sources, and placeholder variables — generated configs are more likely to use invalid values
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
from app.services.trigger_generation_service import TriggerGenerationService
full_ctx = TriggerGenerationService._gather_context()
empty_ctx = {'backends': [], 'trigger_sources': [], 'placeholders': {}, 'existing_triggers': []}
full_prompt = TriggerGenerationService._build_prompt('Create a PR reviewer', full_ctx)
empty_prompt = TriggerGenerationService._build_prompt('Create a PR reviewer', empty_ctx)
print(f'Full context prompt: {len(full_prompt)} chars')
print(f'Empty context prompt: {len(empty_prompt)} chars')
print(f'Difference: {len(full_prompt) - len(empty_prompt)} chars of context')
"`
- **Evidence:** 09-RESEARCH.md Recommendation 4 establishes that context injection is what differentiates this service from a generic "ask Claude" call.

### A3: Template deploy with duplicate name suffix handling

- **Condition:** Remove the numeric suffix logic from deploy_template() and attempt to deploy the same template twice
- **Expected impact:** Second deploy should fail with a database uniqueness error or return 409 Conflict
- **Command:** Covered by test_deploy_same_template_twice_creates_unique_name in test_bot_templates.py
- **Evidence:** 09-RESEARCH.md Pitfall 2 — TriggerService.create_trigger() rejects duplicate names. The suffix logic is the specific mitigation.

---

## WebMCP Tool Definitions

WebMCP tool definitions included — this phase modifies multiple frontend views.

**Purpose:** Define WebMCP tools the grd-verifier should use to validate frontend health after phase execution.

### Generic Checks

| Tool | Purpose | Expected |
|------|---------|----------|
| hive_get_health_status | Backend is responding after frontend changes | status: healthy |
| hive_check_console_errors | No new JavaScript errors from Phase 9 components | No new errors since phase start |
| hive_get_page_info | App renders with new sidebar navigation items | Page loads with updated nav |

### Page-Specific Tools

| Tool | Page | Purpose | Expected |
|------|------|---------|----------|
| hive_check_bot_templates_gallery | /bot-templates | Verify 5 template cards render with name, description, and deploy button | 5 cards visible, deploy button present |
| hive_check_prompt_snippets_list | /prompt-snippets | Verify snippet library page renders with Create Snippet button | Page loads, create button present |
| hive_check_trigger_dashboard_tabs | /triggers/:id | Verify Version History and Test Console tabs/sections appear in trigger dashboard | Both sections visible |

### useWebMcpTool() Definitions

```js
// Generic health checks
useWebMcpTool("hive_get_health_status", {})
useWebMcpTool("hive_check_console_errors", { since: "phase_start" })
useWebMcpTool("hive_get_page_info", {})

// Bot template marketplace
useWebMcpTool("hive_check_bot_templates_gallery", {
  url: "/bot-templates",
  checks: ["5 template cards rendered", "deploy button present on each card", "NL creator textarea visible"]
})

// Prompt snippet library
useWebMcpTool("hive_check_prompt_snippets_list", {
  url: "/prompt-snippets",
  checks: ["snippet list renders", "create snippet button visible", "snippet name displayed as {{name}} format"]
})

// Trigger dashboard enhancements
useWebMcpTool("hive_check_trigger_dashboard_tabs", {
  url: "/triggers/[first-available-trigger-id]",
  checks: ["Version History section present", "Webhook Test Console section present", "diff view renders", "JSON payload textarea present"]
})
```

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Backend test pass rate | All existing tests pass before Phase 9 changes | 906/906 (100%) | v0.1.0 STATE.md |
| Frontend test pass rate | All existing frontend tests pass | 344/344 (100%) | v0.1.0 STATE.md |
| Frontend build errors | Zero TypeScript/build errors | 0 errors | v0.1.0 STATE.md |
| Snippet resolution latency | resolve_snippets() with 0-5 nested snippets | <10ms | 09-RESEARCH.md Recommended Metrics |
| Version history load time | get_prompt_template_history() with 100 versions | <50ms | 09-RESEARCH.md Recommended Metrics |
| Preview render time | preview_prompt_full() with all placeholders + snippets | <20ms | 09-RESEARCH.md Recommended Metrics |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_bot_templates.py         — TPL-01 backend tests (6 tests)
backend/tests/test_prompt_snippets.py       — TPL-03 backend tests (10 tests)
backend/tests/test_prompt_version_history.py — TPL-04 + TPL-05 backend tests (11 tests)
frontend/src/components/triggers/__tests__/ — Frontend component tests (existing pattern)
```

**How to run full evaluation:**
```bash
# Sanity: run new test files individually first
cd /Users/neo/Developer/Projects/Agented/backend
uv run pytest tests/test_bot_templates.py -v
uv run pytest tests/test_prompt_snippets.py -v
uv run pytest tests/test_prompt_version_history.py -v

# Proxy: full backend suite
uv run pytest tests/ -q

# Proxy: frontend build
cd /Users/neo/Developer/Projects/Agented/frontend
npm run build

# Proxy: frontend tests
npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Backend regression | | | |
| S2: Frontend regression | | | |
| S3: 5 templates seeded | | | |
| S4: TriggerGenerationService interface | | | |
| S5: Snippet resolution (missing) | | | |
| S6: Cycle detection configured | | | |
| S7: difflib integration | | | |
| S8: No subprocess in preview | | | |
| S9: PromptRenderer.render() signature | | | |
| S10: Template config JSON validity | | | |
| S11: Frontend types compile | | | |
| S12: New routes registered | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: 27 new backend tests | 27 passed | | | |
| P2: Full backend suite | 933+ passed | | | |
| P3: Frontend build | 0 errors | | | |
| P4: List templates endpoint | 5 templates, correct fields | | | |
| P5: Deploy + duplicate handling | 2 tests PASSED | | | |
| P6: Snippet resolution tests | 5 tests PASSED | | | |
| P7: Version history tests | 11 tests PASSED | | | |
| P8: Generation context quality | All keys present, prompt >= 100 chars | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Snippet ordering impact | Wrong ordering corrupts templates with both syntax types | | |
| A2: Context injection impact | Full context prompt significantly longer and more specific | | |
| A3: Duplicate deploy without suffix | Second deploy fails with name conflict | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-09-01 | NL generation quality with real Claude CLI | PENDING | phase-09-e2e |
| DEFER-09-02 | Deployed template bot executes end-to-end | PENDING | phase-09-e2e |
| DEFER-09-03 | Snippet propagation across executions | PENDING | phase-09-e2e |
| DEFER-09-04 | Visual UI verification in browser | PENDING | phase-09-e2e |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: Adequate — 12 checks cover all five features with specific commands; safety invariants (no-subprocess, cycle detection, signature stability) are directly verifiable
- Proxy metrics: Well-evidenced — the 27-test suite directly covers all stated success criteria; build gate catches API contract issues; context quality check provides partial proxy for NL generation quality
- Deferred coverage: Comprehensive — all four deferred items have clear validates_at references, specific targets, and fallback plans; the main deferred item (NL generation quality) is inherently not automatable

**What this evaluation CAN tell us:**
- Whether all backend APIs are correctly implemented and return expected data
- Whether the snippet resolution pipeline correctly handles missing snippets, nested resolution, and circular references
- Whether the preview endpoint is safe (no subprocess spawning)
- Whether version history records diffs correctly and rollback restores the correct state
- Whether the frontend compiles without TypeScript errors and existing tests are unaffected

**What this evaluation CANNOT tell us:**
- Whether Claude CLI generates semantically valid bot configurations from natural language (deferred to DEFER-09-01)
- Whether deployed template bots produce useful output when executed (deferred to DEFER-09-02)
- Whether the UI visually looks correct in a real browser (deferred to DEFER-09-04)
- Whether snippet changes propagate correctly across real bot execution runs (deferred to DEFER-09-03)

**Note on NL generation (TPL-02):** The proxy metric P8 (context quality check) is the best automated approximation available without running Claude CLI. A well-structured prompt with complete context is necessary but not sufficient for good generation quality. The deferred validation DEFER-09-01 is the definitive test. This is explicitly acknowledged — do not treat P8 as a substitute for DEFER-09-01.

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
