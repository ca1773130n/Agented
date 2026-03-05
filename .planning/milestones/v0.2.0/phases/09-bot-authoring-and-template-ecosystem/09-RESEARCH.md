# Phase 9: Bot Authoring & Template Ecosystem - Research

**Researched:** 2026-03-04
**Domain:** Bot template management, prompt engineering infrastructure, webhook testing
**Confidence:** HIGH

## Summary

Phase 9 builds five features on top of the existing trigger/bot CRUD system: a bot template marketplace (TPL-01), natural language bot creator (TPL-02), reusable prompt snippet library (TPL-03), prompt template version control (TPL-04), and webhook payload test console (TPL-05). The codebase already provides substantial infrastructure that each requirement can extend rather than build from scratch.

The existing plugin marketplace (`marketplaces` + `marketplace_plugins` tables, `marketplace_bp` routes, `marketplaceApi` frontend client) provides a proven pattern for TPL-01. The `BaseGenerationService` + streaming SSE pattern (used by `PluginGenerationService`, `CommandGenerationService`, `TeamGenerationService`, `RuleGenerationService`, `HookGenerationService`) provides an established pattern for TPL-02. The `trigger_template_history` table and `log_prompt_template_change()` / `get_prompt_template_history()` functions already implement basic version tracking for TPL-04. The `preview-prompt` endpoint on `TriggerService` already renders prompt templates with sample data for TPL-05.

**Primary recommendation:** Extend existing patterns rather than introducing new architectural concepts. Use in-DB curated templates for the marketplace (no external repo needed), extend `BaseGenerationService` for NL bot creation, add a `prompt_snippets` table with `{{snippet_name}}` variable resolution in `PromptRenderer`, enhance `trigger_template_history` with author/diff fields, and expand the `preview-prompt` endpoint to return the full CLI command preview.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Immutable Prompt Versioning with Automatic Change Tracking

**Recommendation:** Store every prompt template edit as an immutable version record with author, timestamp, old/new content, and a computed unified diff. Never mutate historical versions.

**Evidence:**
- [Prompt Versioning Best Practices](https://dev.to/kuldeep_paul/mastering-prompt-versioning-best-practices-for-scalable-llm-development-2mgm) (2024) -- Establishes that immutability is critical: "once a prompt version is created, it should never be modified. If a change is required, a new version is generated." This enables reliable tracing and regression debugging.
- [Braintrust: Best Prompt Versioning Tools](https://www.braintrust.dev/articles/best-prompt-versioning-tools-2025) (2025) -- Confirms that continuous versioning creates "an unbroken audit trail showing how prompts evolved over time, which helps in debugging regressions."
- [Maxim: Prompt Versioning Practices](https://www.getmaxim.ai/articles/prompt-versioning-and-its-best-practices-2025/) (2025) -- Recommends tracking changes with metadata including who made the change, when, and why.
- Python stdlib `difflib.unified_diff` -- Provides zero-dependency unified diff computation, already standard in the Python ecosystem.

**Confidence:** HIGH -- Multiple authoritative sources agree on immutability + metadata pattern.
**Expected improvement:** Full regression traceability; ability to identify which prompt change caused a behavior difference.
**Caveats:** The existing `trigger_template_history` table stores `old_template` and `new_template` but lacks `author` and `diff` columns. Migration needed.

### Recommendation 2: Variable Interpolation for Prompt Snippets via Delimiter Convention

**Recommendation:** Use `{{snippet_name}}` double-curly-brace syntax for snippet references (distinct from the existing `{placeholder}` single-brace syntax for runtime variables like `{paths}`, `{message}`, `{pr_url}`). Resolve snippets at render time in `PromptRenderer.render()` before runtime placeholder substitution.

**Evidence:**
- [Kinde: Prompt Patterns That Scale](https://www.kinde.com/learn/ai-for-software-engineering/prompting/prompt-patterns-that-scale-reusable-llm-prompts-for-dev-eams/) (2025) -- Documents the pattern of reusable prompt templates with named variable substitution using `{{variable}}` notation.
- [LangChain Prompt Templates](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langchain-setup-tools-agents-memory/langchain-prompt-templates-complete-guide-with-examples) (2025) -- Uses `{variable}` for runtime values; the convention of using double braces `{{...}}` for template-level references is well established in Jinja2/Mustache ecosystems.
- Codebase analysis: The existing `PromptRenderer._KNOWN_PLACEHOLDERS` uses single braces (`{paths}`, `{message}`, etc.). Using `{{...}}` avoids collision.

**Confidence:** HIGH -- The `{{...}}` convention is widely established across Jinja2, Mustache, Handlebars, and LangChain.
**Expected improvement:** Prompt DRY-ness; update a snippet once, all referencing bots pick up the change on next execution.
**Caveats:** Need to ensure `{{...}}` in prompt templates that are not snippet references (e.g., literal JSON examples) can be escaped. Use `\{\{` escape sequence.

### Recommendation 3: In-Database Curated Bot Templates (No External Repository)

**Recommendation:** Store bot templates as seed data in a `bot_templates` table rather than fetching from an external Git repository. Templates are curated JSON configurations that map 1:1 to `CreateTriggerRequest` fields. One-click deploy calls the existing `TriggerService.create_trigger()`.

**Evidence:**
- Codebase analysis: The existing plugin marketplace uses Git-based external repositories (`marketplaces.url`), which adds complexity (cloning, caching, network dependencies). For 5 curated bot templates that ship with the product, this overhead is unnecessary.
- [Engati Bot Marketplace](https://www.engati.ai/chatbot-templates) (2025) -- Demonstrates the curated template gallery pattern where templates are pre-built configurations ready for one-click deployment.
- [Workativ Chatbot Marketplace](https://workativ.com/conversational-ai-platform/chatbot-marketplace-templates) (2025) -- Confirms that marketplace templates work best as pre-configured, ready-to-use definitions.
- Codebase: `PREDEFINED_TRIGGERS` in `backend/app/db/triggers.py` already seeds two bot configurations at startup -- extending this pattern to a templates table is natural.

**Confidence:** HIGH -- The seed-data approach is simpler and the codebase already demonstrates it.
**Expected improvement:** Zero external dependencies, instant loading, offline-capable.
**Caveats:** Future phases could add user-contributed templates or external template sources. The table schema should include a `source` column to differentiate built-in vs. user-created templates.

### Recommendation 4: Extend BaseGenerationService for NL Bot Creator

**Recommendation:** Create `TriggerGenerationService(BaseGenerationService)` following the exact pattern of `PluginGenerationService`, `CommandGenerationService`, etc. The service accepts a natural language description, gathers context (existing triggers, available backends, available skills), builds a prompt that instructs Claude to generate a `CreateTriggerRequest`-compatible JSON, and returns the result via SSE streaming.

**Evidence:**
- Codebase: Five existing generation services (`PluginGenerationService`, `CommandGenerationService`, `HookGenerationService`, `RuleGenerationService`, `TeamGenerationService`) all extend `BaseGenerationService` with the same pattern: `_gather_context()` -> `_build_prompt()` -> `generate_streaming()` -> SSE response.
- Codebase: The `BaseGenerationService.generate_streaming()` method handles all subprocess management, stdout/stderr threading, JSON parsing, and SSE protocol -- no need to reimplement.
- [LaunchDarkly: Prompt Management](https://launchdarkly.com/blog/prompt-versioning-and-management/) (2025) -- Recommends treating AI-generated configurations as structured outputs that undergo validation before deployment.

**Confidence:** HIGH -- This is a direct extension of a proven codebase pattern with five prior implementations.
**Expected improvement:** Consistent UX with existing AI generation features; minimal new code required.
**Caveats:** Claude CLI must be installed for the generation to work. The generated config must be validated against `CreateTriggerRequest` Pydantic model constraints.

### Recommendation 5: Expand preview-prompt to Full CLI Command Preview

**Recommendation:** Extend the existing `TriggerService.preview_prompt()` (already at `POST /admin/triggers/{id}/preview-prompt`) to additionally return the full CLI command that would be executed, the backend type, and the model selection. For TPL-05, add a new "standalone" preview endpoint that accepts an arbitrary JSON payload (not just sample placeholder values) and renders the full execution plan.

**Evidence:**
- Codebase: `TriggerService.preview_prompt()` already performs placeholder substitution with sample data and returns `rendered_prompt`, `unresolved_placeholders`.
- Codebase: `ExecutionService.build_command()` already constructs the CLI command array from backend type, prompt, paths, and model.
- [Webhook.site](https://webhook.site/) and [TypedWebhook.tools](https://typedwebhook.tools/) -- Demonstrate the pattern of accepting arbitrary payloads and showing how they would be processed.
- [Hevo: Webhooks Testing](https://hevodata.com/learn/webhooks-testing/) (2025) -- Recommends testing with custom and recorded payloads to validate handling before production.

**Confidence:** HIGH -- The foundation already exists; this is an enhancement, not a new system.
**Expected improvement:** Users can validate trigger configuration without risking real subprocess execution.
**Caveats:** Must ensure the preview does NOT spawn any subprocess (the success criteria explicitly requires "no actual subprocess is spawned").

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask + flask-openapi3 | 2.x / 3.x | API routes for new endpoints | Existing framework; all routes use `APIBlueprint` |
| Pydantic v2 | 2.x | Request/response validation for new models | Existing validation layer; all models use BaseModel |
| SQLite (stdlib) | N/A | New tables for templates, snippets, enhanced history | Existing DB pattern; raw SQL with `get_connection()` |
| Vue 3 + TypeScript | 3.5 / 5.4 | Frontend views for marketplace, snippet library, etc. | Existing frontend stack |
| Python `difflib` | stdlib | Unified diff computation for template version diffs | Zero-dependency, built into Python |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `BaseGenerationService` | internal | NL bot creator SSE streaming | TPL-02 NL generation |
| `PromptRenderer` | internal | Snippet variable resolution at render time | TPL-03 snippet interpolation |
| `TriggerService` | internal | Create trigger from template, preview prompt | TPL-01 deploy, TPL-05 preview |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Evidence |
|------------|-----------|----------|----------|
| In-DB templates | Git-based marketplace (like plugins) | Adds network dependency, caching complexity; overkill for 5 curated templates | Plugin marketplace uses Git but adds `DeployService.discover_available_plugins_cached()` complexity |
| `{{snippet}}` syntax | Jinja2 template engine | Full Jinja2 is powerful but brings injection risks and complexity for simple variable substitution | Simple `.replace()` chain in `PromptRenderer` is safer and consistent with existing pattern |
| `difflib.unified_diff` | External diff library | No benefit; stdlib is sufficient for text diffs | `difflib` is standard Python, zero install |
| LiteLLM for NL generation | Claude CLI subprocess | LiteLLM adds API key dependency; CLI subprocess matches all 5 existing generation services | `BaseGenerationService` uses `claude -p` subprocess |

**Installation:**
```bash
# No new dependencies needed -- all features use existing stack
# Backend: Python stdlib (difflib, json, re, sqlite3)
# Frontend: No new npm packages
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
├── db/
│   ├── bot_templates.py       # Bot template CRUD (TPL-01)
│   ├── prompt_snippets.py     # Prompt snippet CRUD (TPL-03)
│   └── triggers.py            # Enhanced: version history additions (TPL-04)
├── models/
│   ├── bot_template.py        # Template request/response models (TPL-01)
│   └── prompt_snippet.py      # Snippet request/response models (TPL-03)
├── routes/
│   ├── bot_templates.py       # Template marketplace API (TPL-01)
│   ├── prompt_snippets.py     # Snippet library API (TPL-03)
│   └── triggers.py            # Enhanced: NL generate, history, preview (TPL-02/04/05)
├── services/
│   ├── trigger_generation_service.py  # NL bot creator (TPL-02)
│   ├── prompt_snippet_service.py      # Snippet resolution logic (TPL-03)
│   └── prompt_renderer.py             # Enhanced: snippet resolution before placeholders
└── ...

frontend/src/
├── views/
│   ├── BotTemplateMarketplace.vue     # Template gallery (TPL-01)
│   ├── PromptSnippetLibrary.vue       # Snippet management (TPL-03)
│   └── TriggerManagement.vue          # Enhanced: NL creator, history, preview tabs
├── components/
│   ├── templates/                     # Template card, deploy modal (TPL-01)
│   ├── snippets/                      # Snippet editor, reference list (TPL-03)
│   └── triggers/
│       ├── PromptVersionHistory.vue   # Version timeline with diff view (TPL-04)
│       └── WebhookTestConsole.vue     # Payload test panel (TPL-05)
├── services/api/
│   ├── bot-templates.ts               # Template marketplace API client
│   └── prompt-snippets.ts             # Snippet library API client
└── router/routes/
    └── triggers.ts                    # New routes for marketplace, snippets
```

### Pattern 1: Seed-Data Template Marketplace

**What:** Store curated bot templates as rows in a `bot_templates` table, seeded at startup via migrations. Each template is a JSON configuration blob matching `CreateTriggerRequest` fields. One-click deploy calls `TriggerService.create_trigger()` with the template's config.

**When to use:** When the template catalog is curated (not user-generated) and small (<50 items).

**Example:**
```python
# backend/app/db/bot_templates.py
CURATED_TEMPLATES = [
    {
        "slug": "pr-reviewer",
        "name": "PR Reviewer",
        "description": "Automatically review pull requests for code quality",
        "category": "code-review",
        "icon": "git-pull-request",
        "config": {
            "name": "PR Reviewer",
            "prompt_template": "Review this pull request: {pr_url}\n\nTitle: {pr_title}\nAuthor: {pr_author}\n\n...",
            "backend_type": "claude",
            "trigger_source": "github",
            "model": None,
        },
    },
    # ... 4 more templates
]

def get_all_templates() -> List[dict]:
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM bot_templates ORDER BY sort_order ASC")
        return [dict(row) for row in cursor.fetchall()]

def deploy_template(template_id: str) -> Optional[str]:
    """Deploy a template by creating a trigger from its config."""
    template = get_template(template_id)
    if not template:
        return None
    config = json.loads(template["config_json"])
    return add_trigger(**config)
```

### Pattern 2: Snippet Resolution Pipeline

**What:** `PromptRenderer.render()` gains a pre-processing step that resolves `{{snippet_name}}` references before performing standard `{placeholder}` substitution. Snippets are loaded from the `prompt_snippets` table. This is a two-phase render: (1) snippet expansion, (2) runtime placeholder substitution.

**When to use:** When prompt templates reference shared text fragments.

**Example:**
```python
# Enhanced PromptRenderer.render()
@staticmethod
def render(trigger, trigger_id, message_text, paths_str, event=None):
    prompt = trigger["prompt_template"]

    # Phase 1: Resolve snippet references ({{snippet_name}})
    prompt = SnippetService.resolve_snippets(prompt)

    # Phase 2: Standard placeholder substitution ({paths}, {message}, etc.)
    prompt = prompt.replace("{trigger_id}", trigger_id)
    prompt = prompt.replace("{paths}", paths_str)
    prompt = prompt.replace("{message}", message_text)
    # ... rest of existing logic
```

### Pattern 3: BaseGenerationService Extension for NL Bot Creator

**What:** `TriggerGenerationService` extends `BaseGenerationService` exactly like `PluginGenerationService` does. Accepts a natural language description ("I want a bot that reviews PRs every day at 9am"), generates a complete trigger configuration as JSON, returns it via SSE streaming.

**When to use:** TPL-02 natural language bot creation.

**Example:**
```python
# backend/app/services/trigger_generation_service.py
class TriggerGenerationService(BaseGenerationService):
    @classmethod
    def _gather_context(cls) -> dict:
        return {
            "triggers": get_all_triggers(),
            "backends": ["claude", "opencode", "gemini", "codex"],
        }

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        sections = [
            "You are a bot/trigger configuration generator for an AI agent platform.",
            "Generate a complete trigger configuration that matches the user's description.",
        ]
        # ... context injection and JSON schema
        sections.append(f"User's description: {description}")
        return "\n\n".join(sections)

    @classmethod
    def _validate(cls, config: dict) -> tuple:
        warnings = []
        if not config.get("name"):
            warnings.append("Missing trigger name")
        if not config.get("prompt_template"):
            warnings.append("Missing prompt template")
        # Validate trigger_source, backend_type, schedule fields...
        return config, warnings
```

### Anti-Patterns to Avoid

- **Over-engineering the template marketplace with Git integration:** For 5 curated templates, a Git-backed marketplace adds clone/cache/refresh complexity. Use in-DB seeds. Reserve Git integration for a future "community templates" feature.
- **Using Jinja2 for snippet resolution:** Jinja2 enables arbitrary code execution in templates (loops, conditionals, filters). This is an injection risk and unnecessary for simple named-variable substitution. Stick with `re.sub()` or `.replace()`.
- **Storing diffs as binary patches:** Unified text diffs via `difflib.unified_diff()` are human-readable and sufficient for prompt text. Binary patches add complexity with no benefit.
- **Creating a separate version table per trigger:** One `trigger_template_history` table with a `trigger_id` foreign key is correct (already implemented). Do not create per-entity version tables.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text diffing | Custom diff algorithm | Python `difflib.unified_diff()` | Handles edge cases (empty lines, encoding); stdlib, zero-install |
| SSE streaming for AI generation | Custom subprocess + threading | `BaseGenerationService.generate_streaming()` | Already handles stdout/stderr threading, JSON parsing, progress extraction, error handling |
| Trigger creation from template | Custom trigger insertion logic | `TriggerService.create_trigger(data)` | Already validates all fields, handles scheduling, audit logging, duplicate name check |
| Prompt placeholder substitution | Custom regex engine | Extend `PromptRenderer.render()` | Already handles all known placeholders, `skill_command` prepending, unresolved detection |
| CLI command building | Inline command array construction | `ExecutionService.build_command()` | Already handles backend-specific flags, model selection, path allowlisting |

**Key insight:** Every Phase 9 feature maps to an extension of an existing service, not a greenfield build. The risk of reimplementing existing logic (trigger creation validation, CLI command building, SSE streaming) far exceeds the cost of extending the existing services.

## Common Pitfalls

### Pitfall 1: Snippet Circular References

**What goes wrong:** Snippet A references snippet B which references snippet A, causing infinite recursion during resolution.
**Why it happens:** No depth limit or cycle detection in snippet expansion.
**How to avoid:** Implement a max recursion depth (e.g., 5 levels) and a visited-set to detect cycles. Return the unresolved `{{snippet_name}}` with a warning if a cycle is detected.
**Warning signs:** Stack overflow or timeout during `PromptRenderer.render()`.

### Pitfall 2: Template Deploy Creating Duplicate Names

**What goes wrong:** Deploying the same template twice creates a name conflict since `TriggerService.create_trigger()` rejects duplicate names.
**Why it happens:** Templates have fixed names; deploying twice hits the `get_trigger_by_name()` uniqueness check.
**How to avoid:** Append a numeric suffix to the trigger name if a duplicate exists (e.g., "PR Reviewer (2)"), or allow the user to customize the name during deploy.
**Warning signs:** 409 Conflict response on deploy.

### Pitfall 3: Snippet Content Update Not Visible Until Next Execution

**What goes wrong:** User updates a snippet and expects all bots to immediately reflect the change. But snippets are resolved at execution time, not at edit time.
**Why it happens:** This is actually correct behavior per the requirements ("propagates to all bots referencing it on next execution"), but users may not understand the delayed propagation.
**How to avoid:** Show a clear UX message: "Snippet changes take effect on the next bot execution." Provide a "Preview with current snippets" button that shows the rendered prompt with current snippet values.
**Warning signs:** User confusion about when changes take effect.

### Pitfall 4: Preview Endpoint Accidentally Spawning Processes

**What goes wrong:** The webhook test console inadvertently calls `ExecutionService.run_trigger()` instead of just rendering the prompt and building the command string.
**Why it happens:** Developer confusion between "preview" and "run" code paths.
**How to avoid:** The preview endpoint must ONLY call `PromptRenderer.render()` and `ExecutionService.build_command()`. It must NOT call `subprocess.Popen()` or `ExecutionService.run_trigger()`. Add an explicit "dry_run=True" flag that prevents process spawning.
**Warning signs:** Execution logs appearing during preview operations.

### Pitfall 5: Version History Growing Unbounded

**What goes wrong:** Every minor prompt edit creates a version record. Over time, the `trigger_template_history` table grows large for frequently-edited triggers.
**Why it happens:** No retention policy.
**How to avoid:** Add a configurable retention limit (e.g., keep last 100 versions per trigger). Optionally add a cleanup migration or scheduled task.
**Warning signs:** Slow queries on `get_prompt_template_history()` for triggers with hundreds of versions.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:** Template deploy method (one-click vs. manual config), NL description complexity (simple vs. complex), snippet nesting depth (0, 1, 3, 5 levels)

**Dependent variables:** Deploy success rate, NL generation accuracy (does generated bot run without manual editing?), snippet resolution time, version history query time

**Controlled variables:** Backend type (claude), database size, template count (5)

**Baseline comparison:**
- Method: Manual trigger creation via existing AddTriggerModal
- Expected performance: 100% success (user fills all fields manually)
- Our target: NL bot creator generates valid, runnable config >80% of the time without manual editing

**Ablation plan:**
1. NL creator with vs. without context injection (existing triggers list) -- tests whether context improves generation quality
2. Snippet resolution with vs. without cycle detection -- tests whether cycle detection adds measurable latency
3. Template deploy with vs. without name customization step -- tests user experience friction

**Statistical rigor:**
- Number of runs: 5 per NL description complexity level
- Confidence intervals: Standard deviation across runs
- Significance testing: Manual assessment (qualitative for NL generation quality)

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Template deploy success rate | Core TPL-01 metric | Deploys resulting in runnable trigger / total deploys | 100% (manual) |
| NL generation validity | Core TPL-02 metric | Generated configs passing `CreateTriggerRequest` validation / total generations | N/A (new feature) |
| Snippet resolution latency | Performance check for TPL-03 | Time for `resolve_snippets()` with 0-5 nested snippets | <10ms target |
| Version history load time | Performance check for TPL-04 | Time for `get_prompt_template_history()` with 100 versions | <50ms target |
| Preview render time | Performance check for TPL-05 | Time for `preview_prompt()` with all placeholders + snippets | <20ms target |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Bot template table seeds correctly at startup | Level 1 (Sanity) | Can check with a DB query in test |
| Template deploy creates a valid, enabled trigger | Level 1 (Sanity) | Can verify with `get_trigger()` after deploy |
| NL generation returns valid JSON matching schema | Level 2 (Proxy) | Requires Claude CLI; mock in unit tests, real in integration |
| Snippet resolution replaces `{{name}}` correctly | Level 1 (Sanity) | Pure function, easy to unit test |
| Snippet cycle detection prevents infinite loop | Level 1 (Sanity) | Unit test with circular references |
| Version history records author, timestamp, diff | Level 1 (Sanity) | DB insert + query test |
| Version rollback restores previous prompt | Level 1 (Sanity) | Update trigger with old version, verify |
| Preview endpoint returns rendered prompt + command | Level 1 (Sanity) | HTTP test with mock trigger |
| Preview endpoint does NOT spawn subprocess | Level 1 (Sanity) | Verify no `subprocess.Popen` call in preview path |
| Frontend template gallery renders 5 templates | Level 2 (Proxy) | Vitest + happy-dom component test |
| Frontend version history shows diff view | Level 2 (Proxy) | Component test with mock history data |
| Full E2E: deploy template, run bot, verify output | Level 3 (Deferred) | Needs running backend + Claude CLI |

**Level 1 checks to always include:**
- All 5 curated templates seed correctly in `bot_templates` table
- `deploy_template()` returns a valid trigger_id
- `resolve_snippets("Hello {{greeting}}")` returns "Hello [greeting content]" when snippet exists
- `resolve_snippets("Hello {{missing}}")` returns "Hello {{missing}}" with warning when snippet missing
- Circular snippet reference `A->B->A` terminates within 5 iterations
- `log_prompt_template_change()` stores diff in addition to old/new templates
- `get_prompt_template_history()` returns records with `changed_at`, `author`, `diff_text`
- Preview endpoint returns `rendered_prompt`, `cli_command`, `unresolved_placeholders`

**Level 2 proxy metrics:**
- NL bot creator generates valid trigger config for 3 test descriptions (mocked Claude response)
- Frontend build passes with new components (`vue-tsc` type check)
- All new API endpoints return correct HTTP status codes

**Level 3 deferred items:**
- NL bot creator with real Claude CLI generates runnable bot
- Deployed template bot executes successfully end-to-end
- Snippet propagation verified across multiple bot executions

## Production Considerations (from KNOWHOW.md)

Note: KNOWHOW.md is not yet populated. The following considerations are derived from codebase analysis.

### Known Failure Modes

- **Claude CLI not installed:** `BaseGenerationService` catches `FileNotFoundError` and returns an SSE error event. The NL bot creator must handle this gracefully.
  - Prevention: Check CLI availability before showing the NL creator UI (frontend already calls `utilityApi.checkBackend()`)
  - Detection: SSE error event with "Claude CLI not found" message

- **SQLite busy timeout on concurrent template deploys:** Multiple users deploying templates simultaneously could hit the 5-second busy timeout.
  - Prevention: The existing `get_connection()` sets `PRAGMA busy_timeout = 5000`; this is sufficient for low concurrency
  - Detection: `sqlite3.OperationalError: database is locked`

### Scaling Concerns

- **Version history table growth:** At current scale (single user, <50 triggers), unbounded history is fine. At production scale with frequent edits, add a retention policy.
  - At current scale: No action needed; default LIMIT 50 on queries
  - At production scale: Add `DELETE FROM trigger_template_history WHERE trigger_id = ? AND id NOT IN (SELECT id FROM trigger_template_history WHERE trigger_id = ? ORDER BY changed_at DESC LIMIT 100)`

- **Snippet resolution at execution time:** Adding a DB query to every trigger execution adds latency.
  - At current scale: <5ms per query; negligible
  - At production scale: Cache snippets in-memory with a 60-second TTL

### Common Implementation Traps

- **Modifying `PromptRenderer.render()` signature:** The `render()` method is called from `ExecutionService.run_trigger()`. Any signature change breaks the call site.
  - Correct approach: Add snippet resolution as internal logic within `render()`, fetching snippets inside the method. Do not change the external API.

- **Adding snippet resolution to `TriggerService.preview_prompt()`:** The preview method has its own placeholder substitution logic (duplicated from `PromptRenderer`). Adding snippet support to preview requires updating both places.
  - Correct approach: Refactor `preview_prompt()` to use `PromptRenderer.render()` internally, then snippet resolution works in both places automatically.

## Code Examples

Verified patterns from the existing codebase:

### Bot Template Seeding (following PREDEFINED_TRIGGERS pattern)
```python
# Source: backend/app/db/triggers.py lines 31-58 (PREDEFINED_TRIGGERS pattern)
CURATED_BOT_TEMPLATES = [
    {
        "slug": "pr-reviewer",
        "name": "PR Reviewer",
        "description": "Automatically review pull requests for code quality, security, and best practices",
        "category": "code-review",
        "config_json": json.dumps({
            "name": "PR Reviewer",
            "prompt_template": "Review this pull request thoroughly:\n\nURL: {pr_url}\nTitle: {pr_title}\nAuthor: {pr_author}\n\nProvide feedback on code quality, potential bugs, security issues, and adherence to best practices.",
            "backend_type": "claude",
            "trigger_source": "github",
        }),
    },
    # ... dependency-updater, security-scanner, changelog-generator, test-writer
]
```

### NL Generation Route (following commands.py pattern)
```python
# Source: backend/app/routes/commands.py lines 114-131
@triggers_bp.post("/generate/stream")
def generate_trigger_stream():
    """Generate a trigger config from a natural language description (streaming)."""
    from ..services.trigger_generation_service import TriggerGenerationService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    description = (data.get("description") or "").strip()
    if len(description) < 10:
        return {"error": "Description must be at least 10 characters"}, HTTPStatus.BAD_REQUEST

    return Response(
        TriggerGenerationService.generate_streaming(description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### Snippet Resolution (extending PromptRenderer pattern)
```python
# Source: backend/app/services/prompt_renderer.py (extension)
import re
from ..db.prompt_snippets import get_snippet_by_name

class SnippetService:
    MAX_DEPTH = 5

    @classmethod
    def resolve_snippets(cls, text: str, depth: int = 0, visited: set = None) -> str:
        if depth >= cls.MAX_DEPTH:
            return text
        if visited is None:
            visited = set()

        def replacer(match):
            name = match.group(1).strip()
            if name in visited:
                return match.group(0)  # Circular reference; leave unresolved
            snippet = get_snippet_by_name(name)
            if not snippet:
                return match.group(0)  # Unknown snippet; leave unresolved
            visited.add(name)
            # Recursively resolve nested snippets
            return cls.resolve_snippets(snippet["content"], depth + 1, visited)

        return re.sub(r"\{\{(\w[\w\-]*)\}\}", replacer, text)
```

### Enhanced Preview Endpoint (extending TriggerService pattern)
```python
# Source: backend/app/services/trigger_service.py lines 473-514 (extension)
@staticmethod
def preview_prompt_full(trigger_id: str, payload: dict) -> Tuple[dict, HTTPStatus]:
    """Full dry-run preview: render prompt with payload, show CLI command."""
    trigger = get_trigger(trigger_id)
    if not trigger:
        return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

    # Use PromptRenderer for consistent rendering (includes snippet resolution)
    prompt = PromptRenderer.render(
        trigger, trigger_id,
        message_text=payload.get("message", ""),
        paths_str=payload.get("paths", "/path/to/project"),
        event=payload.get("event"),
    )

    # Build CLI command without executing
    cmd = ExecutionService.build_command(
        backend=trigger["backend_type"],
        prompt=prompt,
        model=trigger.get("model"),
        allowed_tools=trigger.get("allowed_tools"),
    )

    return {
        "rendered_prompt": prompt,
        "cli_command": " ".join(cmd),
        "cli_command_parts": cmd,
        "backend_type": trigger["backend_type"],
        "model": trigger.get("model"),
        "trigger_name": trigger["name"],
        "unresolved_placeholders": re.findall(r"\{[^}]+\}", prompt),
        "unresolved_snippets": re.findall(r"\{\{[\w\-]+\}\}", prompt),
    }, HTTPStatus.OK
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Evidence |
|--------------|------------------|--------------|--------|---------|
| Hardcoded prompts in source code | Prompts as managed artifacts with versioning | 2024-2025 | Enables hot-fix without redeploy, audit trail | [LaunchDarkly](https://launchdarkly.com/blog/prompt-versioning-and-management/), [Maxim](https://www.getmaxim.ai/articles/prompt-versioning-and-its-best-practices-2025/) |
| Manual bot configuration | NL-to-config generation via LLM | 2024-2025 | Reduces configuration time from minutes to seconds | Codebase: 5 existing `*GenerationService` classes |
| Copy-paste prompt fragments | Shared snippet libraries with variable resolution | 2024-2025 | DRY prompts, centralized updates | [Kinde](https://www.kinde.com/learn/ai-for-software-engineering/prompting/prompt-patterns-that-scale-reusable-llm-prompts-for-dev-eams/) |

**Deprecated/outdated:**
- Static `{placeholder}` substitution without snippet support: Still valid for runtime variables but insufficient for shared prompt fragments. The codebase's `PromptRenderer` should be extended, not replaced.

## Open Questions

1. **User-contributed templates in future phases?**
   - What we know: TPL-01 requires only 5 curated templates. The `bot_templates` table should support future user contributions.
   - What's unclear: Whether user-contributed templates need review/approval workflow.
   - Recommendation: Add a `source` column (`built-in` vs `user`) and an `is_published` flag. Defer the review workflow.

2. **Snippet ownership and permissions?**
   - What we know: The requirements say "shared named snippets." Single-user context (no multi-tenancy).
   - What's unclear: Whether snippets should have per-trigger visibility or be globally shared.
   - Recommendation: All snippets are global. Add an `is_global` flag for future per-trigger scoping.

3. **How should the NL bot creator handle ambiguous descriptions?**
   - What we know: The existing `BaseGenerationService` pattern generates a single JSON config and validates it.
   - What's unclear: What happens when the description is too vague ("make a bot").
   - Recommendation: The validation step should return warnings for missing critical fields (trigger_source, prompt_template). The frontend should show these warnings and let the user edit before deploying.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `backend/app/db/triggers.py` -- trigger CRUD, `trigger_template_history` table, `PREDEFINED_TRIGGERS` seed pattern
- Codebase analysis: `backend/app/services/prompt_renderer.py` -- `PromptRenderer.render()`, `_KNOWN_PLACEHOLDERS`, placeholder substitution
- Codebase analysis: `backend/app/services/base_generation_service.py` -- `BaseGenerationService.generate_streaming()`, SSE protocol, subprocess management
- Codebase analysis: `backend/app/services/trigger_service.py` -- `TriggerService.preview_prompt()`, `TriggerService.create_trigger()`
- Codebase analysis: `backend/app/routes/marketplace.py` -- plugin marketplace pattern (`marketplaces` table, CRUD endpoints)
- Codebase analysis: `backend/app/db/schema.py` -- `trigger_template_history` table schema, `marketplaces` table schema
- Python stdlib documentation: `difflib.unified_diff()` -- text diff computation

### Secondary (MEDIUM confidence)
- [Prompt Versioning Best Practices (DEV.to)](https://dev.to/kuldeep_paul/mastering-prompt-versioning-best-practices-for-scalable-llm-development-2mgm) -- Immutable versioning principle
- [Braintrust: Best Prompt Versioning Tools 2025](https://www.braintrust.dev/articles/best-prompt-versioning-tools-2025) -- Continuous versioning audit trail
- [Maxim: Prompt Versioning Practices 2025](https://www.getmaxim.ai/articles/prompt-versioning-and-its-best-practices-2025/) -- Metadata tracking (who, when, why)
- [LaunchDarkly: Prompt Versioning & Management](https://launchdarkly.com/blog/prompt-versioning-and-management/) -- Prompts as managed artifacts
- [Kinde: Prompt Patterns That Scale](https://www.kinde.com/learn/ai-for-software-engineering/prompting/prompt-patterns-that-scale-reusable-llm-prompts-for-dev-eams/) -- Reusable prompt templates with variables
- [Engati Bot Marketplace](https://www.engati.ai/chatbot-templates) -- Curated template gallery pattern
- [Workativ Chatbot Marketplace](https://workativ.com/conversational-ai-platform/chatbot-marketplace-templates) -- Pre-built template deployment

### Tertiary (LOW confidence)
- [Hevo: Webhooks Testing](https://hevodata.com/learn/webhooks-testing/) -- Webhook test best practices (general; not specific to this codebase)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- No new dependencies; all features extend existing patterns
- Architecture: HIGH -- Every component maps to a proven codebase pattern with prior implementations
- Paper recommendations: MEDIUM -- Industry best practices (not academic papers; this is an engineering domain, not ML research)
- Pitfalls: HIGH -- Identified from codebase analysis and existing patterns; specific to this implementation

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable domain, no fast-moving dependencies)
