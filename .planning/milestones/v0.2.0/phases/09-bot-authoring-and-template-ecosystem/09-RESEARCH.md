# Phase 9: Bot Authoring & Template Ecosystem - Research

**Researched:** 2026-03-04
**Domain:** Bot configuration management, prompt engineering tooling, template ecosystems
**Confidence:** HIGH

## Summary

Phase 9 introduces five interconnected features that transform the trigger/bot system from manual configuration into an ecosystem with templates, AI generation, snippet reuse, version tracking, and dry-run testing. The codebase already has substantial infrastructure to build on: a `trigger_template_history` table (migration v50), a `preview_prompt` endpoint, a `BaseGenerationService` pattern for Claude CLI-based AI generation, an existing plugin marketplace system, and the `PromptRenderer` class for placeholder substitution.

The primary approach is to leverage existing patterns wholesale. The template marketplace follows the existing plugin marketplace pattern (curated JSON catalog + one-click deploy via `add_trigger`). The NL bot creator extends `BaseGenerationService` which already handles Claude CLI streaming, JSON parsing, and validation. Prompt snippets use a new `prompt_snippets` table with `{{snippet_name}}` syntax resolved at render time in `PromptRenderer`. Version control extends the existing `trigger_template_history` table with author metadata and a rollback endpoint. The webhook test console extends the existing `preview_prompt` with payload-driven rendering and `CommandBuilder.build()` for command preview.

**Primary recommendation:** Build all five features using existing codebase patterns -- no new libraries, no new architectural concepts. Each feature maps cleanly to an established pattern in the codebase.

## Standard Stack

### Core

No new libraries are required. All features build on the existing stack.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask / flask-openapi3 | 2.x / 3.x | API endpoints for all five features | Existing backend framework |
| Pydantic v2 | 2.x | Request/response models for new endpoints | Existing validation layer |
| SQLite (stdlib) | 3.x | New tables for snippets; extend template history | Existing database |
| Vue 3 + TypeScript | 3.5 / 5.4 | Frontend views for marketplace, creator, snippets, history, test console | Existing frontend framework |
| Claude CLI | latest | NL bot creator via `BaseGenerationService` subprocess pattern | Existing AI generation infrastructure |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `difflib` (Python stdlib) | 3.x | Compute unified diffs for template version comparison | TPL-04 version history diff view |
| `json` (Python stdlib) | 3.x | Parse/validate webhook test payloads | TPL-05 test console |
| `re` (Python stdlib) | 3.x | `{{snippet_name}}` resolution in PromptRenderer | TPL-03 snippet substitution |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| Claude CLI subprocess for NL generation | LiteLLM direct API call | LiteLLM already used in `conversation_streaming.py`; CLI gives richer streaming with thinking blocks | Use Claude CLI via `BaseGenerationService` -- it is the established pattern for generation services (TeamGenerationService, PluginGenerationService, etc.) |
| SQLite for template versions | Git-backed version control | Git would provide true branching/merging but adds massive complexity | SQLite -- existing `trigger_template_history` table already captures old/new pairs |
| Static JSON template catalog | Database-stored templates with admin CRUD | DB-stored templates need admin UI for management | Static JSON file in codebase -- simpler, version-controlled, no admin UI needed |

## Architecture Patterns

### Recommended Project Structure

**Backend additions:**
```
backend/app/
├── db/
│   ├── snippets.py              # prompt_snippets CRUD
│   └── bot_templates.py         # template catalog loader (reads JSON)
├── models/
│   └── bot_template.py          # Pydantic models for templates, snippets, version history
├── routes/
│   ├── bot_templates.py         # /admin/bot-templates/* endpoints
│   └── prompt_snippets.py       # /admin/prompt-snippets/* endpoints
├── services/
│   ├── bot_template_service.py  # Template catalog, deploy, NL generation
│   └── prompt_snippet_service.py # Snippet CRUD, resolution
└── data/
    └── bot_templates.json       # Curated template catalog (static)
```

**Frontend additions:**
```
frontend/src/
├── views/
│   ├── BotTemplatePage.vue      # Template marketplace gallery
│   └── BotCreatorPage.vue       # NL bot creator wizard
├── components/
│   ├── templates/
│   │   ├── TemplateCard.vue     # Individual template display card
│   │   └── TemplateDeployModal.vue # One-click deploy confirmation
│   ├── triggers/
│   │   ├── PromptSnippetPanel.vue   # Snippet library management
│   │   ├── PromptVersionHistory.vue # Version history with diff view
│   │   └── WebhookTestConsole.vue   # Payload test/preview panel
│   └── ...
├── services/api/
│   └── bot-templates.ts         # API client for templates and snippets
└── router/routes/
    └── (extend triggers.ts)     # Add template and creator routes
```

### Pattern 1: Static Template Catalog (TPL-01)

**What:** Bot templates defined as a static JSON file in the backend, loaded at request time. Each template is a complete trigger configuration (name, prompt_template, backend_type, trigger_source, model, etc.) with metadata (description, category, icon, required_placeholders).

**When to use:** When the catalog is curated by developers, not user-generated content.

**Rationale:** The existing plugin marketplace uses GitHub repos for discovery; bot templates are simpler -- a static JSON catalog avoids external dependencies and is version-controlled with the codebase. Templates are deployed by calling the existing `add_trigger()` function with the template's configuration.

**Example:**
```python
# backend/app/data/bot_templates.json
[
    {
        "slug": "pr-reviewer",
        "name": "PR Reviewer",
        "description": "Reviews pull requests for code quality, security issues, and best practices",
        "category": "code-review",
        "icon": "code-review",
        "config": {
            "prompt_template": "Review this pull request: {pr_url}\n\nTitle: {pr_title}\nAuthor: {pr_author}\n\nProvide feedback on code quality, potential bugs, security issues, and adherence to best practices.",
            "backend_type": "claude",
            "trigger_source": "github",
            "model": null
        },
        "required_paths": false,
        "placeholders": ["pr_url", "pr_title", "pr_author"]
    }
]
```

### Pattern 2: NL Bot Creator via BaseGenerationService (TPL-02)

**What:** Extend `BaseGenerationService` to create a `TriggerGenerationService` that accepts a natural language description and generates a complete trigger configuration JSON. Uses Claude CLI subprocess with streaming output (same pattern as `TeamGenerationService`, `PluginGenerationService`).

**When to use:** When the user provides a free-text description of what they want automated.

**Rationale:** Five existing generation services already follow this pattern. The prompt includes context about available backends, trigger sources, placeholder variables, and existing triggers to avoid name collisions.

**Example:**
```python
# backend/app/services/trigger_generation_service.py
class TriggerGenerationService(BaseGenerationService):
    @classmethod
    def _gather_context(cls) -> dict:
        return {"triggers": get_all_triggers()}

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        return f"""You are a trigger configuration generator for Agented.
Generate a JSON trigger config from this description: {description}

Available backends: claude, opencode, gemini, codex
Available trigger sources: webhook, github, manual, scheduled
Available placeholders: {{trigger_id}}, {{paths}}, {{message}}, {{pr_url}}, {{pr_number}}, {{pr_title}}, {{pr_author}}, {{repo_url}}, {{repo_full_name}}

Return ONLY valid JSON with these fields:
{{
  "name": "...",
  "prompt_template": "...",
  "backend_type": "claude",
  "trigger_source": "...",
  "model": null,
  ...
}}"""

    @classmethod
    def _validate(cls, config: dict) -> tuple:
        warnings = []
        if "name" not in config:
            config["name"] = "Generated Trigger"
            warnings.append("No name generated; using default")
        if "prompt_template" not in config:
            warnings.append("No prompt_template generated")
        return config, warnings
```

### Pattern 3: Snippet Variable Resolution in PromptRenderer (TPL-03)

**What:** Prompt snippets are named reusable text blocks stored in a `prompt_snippets` table. They are referenced in prompt templates using `{{snippet_name}}` syntax (double braces to distinguish from `{placeholder}` single-brace variables). Resolution happens in `PromptRenderer.render()` before standard placeholder substitution.

**When to use:** When multiple triggers share common prompt sections (e.g., security checklists, coding standards, output format instructions).

**Rationale:** The existing `PromptRenderer` already handles `{placeholder}` substitution. Adding `{{snippet}}` resolution as a pre-pass is a clean extension. The double-brace syntax avoids conflicts with existing single-brace placeholders.

**Example:**
```python
# Extension to PromptRenderer.render()
@staticmethod
def resolve_snippets(prompt: str) -> str:
    """Replace {{snippet_name}} references with snippet content."""
    from ..db.snippets import get_snippet_by_name

    def replacer(match):
        name = match.group(1).strip()
        snippet = get_snippet_by_name(name)
        return snippet["content"] if snippet else match.group(0)

    return re.sub(r"\{\{(\w[\w\s-]*)\}\}", replacer, prompt)
```

### Pattern 4: Extended Template Version History (TPL-04)

**What:** The existing `trigger_template_history` table already captures `(trigger_id, old_template, new_template, changed_at)`. Extend with an `author` column and add a rollback endpoint that reads a historical `new_template` and applies it as the current template via `update_trigger()`.

**When to use:** When users need to audit prompt changes and revert to a known-good state.

**Rationale:** The foundation already exists (migration v50). Extending it avoids creating a parallel versioning system. Rollback is simply reading a past entry's `old_template` value and writing it back via the existing `update_trigger` function, which in turn logs the change as a new history entry -- creating a full audit trail.

**Example:**
```python
# Rollback endpoint
@triggers_bp.post("/<trigger_id>/prompt-history/<version_id>/rollback")
def rollback_prompt(path: ...):
    history_entry = get_template_history_entry(version_id)
    old_template = history_entry["old_template"]
    # Use existing update_trigger which auto-logs the change
    TriggerService.update_trigger(trigger_id, {"prompt_template": old_template})
```

### Pattern 5: Webhook Test Console with CommandBuilder Preview (TPL-05)

**What:** Extend the existing `preview_prompt` endpoint to also accept a raw JSON webhook payload, extract text using the trigger's `text_field_path` and `match_field_path` configuration, render the prompt, and return the CLI command that would be built via `CommandBuilder.build()`. No subprocess is spawned.

**When to use:** Before deploying a new webhook trigger to production, to validate that payloads will render correctly.

**Rationale:** The `preview_prompt` endpoint already renders prompts with sample data. The test console extends this by: (1) accepting a full JSON payload instead of individual fields, (2) applying the trigger's payload extraction logic (same as `dispatch_webhook_event`), and (3) calling `CommandBuilder.build()` to show the exact CLI command.

**Example:**
```python
# Extended preview with payload simulation
@triggers_bp.post("/<trigger_id>/test-webhook")
def test_webhook_payload(path: TriggerPath):
    data = request.get_json()
    payload = data.get("payload", {})
    trigger = get_trigger(path.trigger_id)

    # Extract text using trigger's text_field_path
    text = get_nested_value(payload, trigger["text_field_path"]) or ""

    # Check match_field_path/match_field_value
    match_value = get_nested_value(payload, trigger["match_field_path"]) if trigger["match_field_path"] else None
    would_match = str(match_value) == trigger["match_field_value"] if trigger["match_field_value"] else True

    # Render prompt
    paths = get_symlink_paths_for_trigger(trigger["id"])
    prompt = PromptRenderer.render(trigger, trigger["id"], text, ", ".join(paths))

    # Build command preview
    command = CommandBuilder.build(trigger["backend_type"], prompt, paths, trigger.get("model"))

    return {
        "would_match": would_match,
        "extracted_text": text,
        "rendered_prompt": prompt,
        "cli_command": " ".join(command),
        "trigger_name": trigger["name"],
    }
```

### Anti-Patterns to Avoid

- **Over-engineering the template catalog:** Do not build a full marketplace with user submissions, ratings, and reviews. A static curated catalog is sufficient for v0.2.0. User-generated templates can be a v0.3.0+ feature.
- **Custom diff engine:** Do not hand-roll a text diff algorithm. Use Python's `difflib.unified_diff()` or `difflib.HtmlDiff()` for the version comparison view.
- **Snippet circular references:** Do not allow snippets to reference other snippets (no recursive resolution). A single-pass resolution is simpler, more predictable, and avoids infinite loops.
- **Spawning subprocesses in test console:** The webhook test console must NEVER run actual CLI commands. It only previews what would run.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text diffing for template versions | Custom diff algorithm | `difflib.unified_diff()` (Python stdlib) | Handles edge cases (whitespace, encoding), well-tested, standard output format |
| AI config generation | Custom LLM integration | `BaseGenerationService` (existing) | Handles CLI streaming, JSON extraction, error handling, timeout management |
| Trigger creation from template | New trigger creation logic | Existing `add_trigger()` DB function | All validation, ID generation, and constraint enforcement already handled |
| Prompt placeholder substitution | New renderer | Extend existing `PromptRenderer` class | Already handles all known placeholders, unresolved warnings |
| JSON path extraction from payload | Custom nested key walker | Existing `get_nested_value()` from `app/utils/json_path.py` | Already handles dot-notation paths like `event.group_id` |
| Webhook payload matching | New matching logic | Existing `dispatch_webhook_event` pattern | Match logic already validated in production |

**Key insight:** Every feature in this phase maps to an existing pattern in the codebase. The risk is not technical complexity but scope creep. Keep each feature minimal and focused.

## Common Pitfalls

### Pitfall 1: Template Deployment Creating Duplicate Names

**What goes wrong:** A user deploys a template that creates a trigger with a name that already exists, causing a database IntegrityError or confusing the user.
**Why it happens:** The template catalog uses fixed names, and users may deploy the same template twice.
**How to avoid:** The deploy endpoint should append a counter suffix to the trigger name if a trigger with that name already exists (e.g., "PR Reviewer (2)"). The existing `get_trigger_by_name()` function already supports this check.
**Warning signs:** IntegrityError in logs when deploying templates.

### Pitfall 2: Snippet Resolution Breaking Existing Prompts

**What goes wrong:** Introducing `{{snippet}}` resolution could accidentally transform existing prompt text that happens to contain double braces.
**Why it happens:** Some prompt templates might contain literal `{{` for other purposes (e.g., Jinja2-like syntax or documentation examples).
**How to avoid:** Only resolve snippets that match a pattern of `{{word_characters}}` AND exist in the snippets table. If a snippet name is not found, leave the `{{...}}` text unchanged. This is a "resolve-if-exists" pattern.
**Warning signs:** Existing prompts producing different output after snippet resolution is enabled.

### Pitfall 3: Version History Rollback Losing the "Current" State

**What goes wrong:** A user rolls back to version N, but the rollback action itself creates a new history entry (version N+1), making the version they just left from (the "current" before rollback) harder to find.
**Why it happens:** The existing `update_trigger` + `log_prompt_template_change` pipeline always logs changes, including rollback-induced changes.
**How to avoid:** This is actually correct behavior -- every state transition is logged. The UI should clearly label rollback-induced entries (e.g., "Rolled back to version #5") by adding a `change_type` field (`edit` vs `rollback`) to the history table.
**Warning signs:** Users confused about which version is "the original" vs "the rollback."

### Pitfall 4: NL Bot Creator Generating Invalid Configurations

**What goes wrong:** Claude generates a trigger config with an invalid `backend_type`, missing `prompt_template`, or incompatible field combinations (e.g., `trigger_source: scheduled` without `schedule_type`).
**Why it happens:** LLM outputs are non-deterministic and may not always conform to the schema.
**How to avoid:** The `_validate()` method in `TriggerGenerationService` must enforce all the same constraints as `TriggerService.create_trigger()`. Apply sensible defaults for missing fields. Present warnings to the user for any fields that were auto-corrected.
**Warning signs:** Generated triggers that fail on first execution.

### Pitfall 5: Test Console with Large Payloads

**What goes wrong:** A user pastes a very large JSON payload (e.g., a full GitHub webhook event with hundreds of KB of data) into the test console, causing slow rendering or timeouts.
**Why it happens:** GitHub webhook payloads can be 200KB+ with full diff content.
**How to avoid:** Enforce a payload size limit (e.g., 64KB) on the test console endpoint. Truncate the extracted text in the response if it exceeds a reasonable length. Add a loading indicator in the UI.
**Warning signs:** Frontend becoming unresponsive when pasting large payloads.

## Paper-Backed Recommendations

### Recommendation 1: Content-Addressable Version Tracking

**Recommendation:** Store template versions with content-based identification (hash of the template content) alongside sequential version numbers, following the content-addressable versioning pattern.

**Evidence:**
- Braintrust prompt versioning system (2025) uses content-addressable IDs where "the same prompt always produces the same ID, ensuring reproducibility." This prevents duplicate history entries when a template is changed and then changed back to the same content.
- Git's content-addressable storage (Torvalds, 2005) -- the foundational pattern for content-based deduplication.

**Confidence:** HIGH -- Well-established pattern used by multiple production systems.
**Expected improvement:** Eliminates duplicate history entries, enables efficient deduplication.
**Caveats:** Adds a computed column but minimal complexity for SQLite.

### Recommendation 2: Environment-Independent Rollback via Reassociation

**Recommendation:** Implement rollback as "set current template to the content of version X" rather than "delete versions after X." All versions remain immutable in the history table.

**Evidence:**
- Braintrust (2025): "All versions remain accessible indefinitely. Nothing gets deleted when you create new versions." Rollback operates through reassociation rather than deletion.
- LaunchDarkly prompt versioning (2025): Feature-flag-style rollback where the "active" version pointer moves without modifying history.

**Confidence:** HIGH -- Industry-standard approach for audit-critical versioning.
**Expected improvement:** Full audit trail preserved; no data loss during rollback.
**Caveats:** History table grows monotonically. Consider periodic archival for very active triggers (not needed at current scale).

### Recommendation 3: Structured Output via Prompt Engineering (not JSON Schema Constraints)

**Recommendation:** For the NL bot creator, use prompt engineering with examples and explicit JSON schema in the prompt (same as existing `BaseGenerationService` pattern), not structured output / constrained decoding.

**Evidence:**
- Gao et al. (2025) "Generating Structured Outputs from Language Models: Benchmark and Studies" (arXiv:2501.10868) found that grammar-constrained decoding can degrade quality compared to unconstrained generation with post-hoc parsing for simpler schemas.
- The existing `BaseGenerationService._parse_json()` handles mixed text + JSON output robustly with fallback extraction.
- Five existing generation services in the codebase use this same approach successfully.

**Confidence:** HIGH -- Pattern proven in production within this codebase.
**Expected improvement:** Consistent with existing codebase patterns; avoids adding new dependencies.
**Caveats:** Occasional malformed JSON from LLM; the existing `_parse_json` fallback handles this.

### Recommendation 4: Single-Pass Snippet Resolution

**Recommendation:** Resolve snippets in a single regex pass before placeholder substitution. Do not support nested snippets or recursive resolution.

**Evidence:**
- Fabric pattern system (danielmiessler/fabric, 2024): Uses flat file-based patterns with `{{variable}}` syntax. No nested pattern references. Simplicity is a deliberate design choice -- "patterns are reusable, structured prompt templates stored as files on disk."
- VS Code prompt files (2025): Supports `#file` references but explicitly does not support nested references to avoid complexity.

**Confidence:** HIGH -- Multiple production systems deliberately avoid recursive resolution.
**Expected improvement:** Predictable behavior, no circular reference risk, O(n) resolution time.
**Caveats:** Users wanting to compose snippets from other snippets must inline the content manually.

## Experiment Design

### Recommended Experimental Setup

This phase is feature development, not research. Experiments are validation-focused.

**Independent variables:** Template catalog size (5, 10, 15 templates), NL description complexity (simple/medium/complex), snippet library size (0, 5, 10 snippets).

**Dependent variables:**
- Template deploy success rate (should be 100%)
- NL bot creator valid config rate (target: >90%)
- Snippet resolution correctness (should be 100%)
- Version rollback accuracy (should be 100%)
- Test console response time (<200ms for payloads under 64KB)

**Baseline comparison:**
- Current state: Manual trigger creation via form, no templates, no NL generation, no snippets, basic template history exists but no UI, preview_prompt exists but no payload simulation.
- Target: All five features functional with success criteria met.

**Validation plan:**
1. Deploy all 5 curated templates -- verify each creates a runnable trigger
2. Generate 10 triggers via NL description -- verify >90% produce valid configs
3. Create 5 snippets, reference in 3 triggers -- verify resolution works
4. Edit a template 3 times -- verify history shows all versions, rollback works
5. Send 3 different webhook payloads to test console -- verify rendered prompt and command preview

### Recommended Metrics

| Metric | Why | How to Compute | Target |
|--------|-----|----------------|--------|
| Template deploy success rate | Core TPL-01 functionality | Deployed templates / total templates | 100% |
| NL config generation validity | Core TPL-02 functionality | Valid configs / total generations | >90% |
| Snippet resolution accuracy | Core TPL-03 functionality | Correctly resolved snippets / total references | 100% |
| Rollback restoration accuracy | Core TPL-04 functionality | Successful rollbacks / total rollback attempts | 100% |
| Test console response time | UX requirement for TPL-05 | API response time for preview endpoint | <200ms |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Template catalog loads and lists correctly | Level 1 (Sanity) | Static JSON parse, no external deps |
| Template deploy creates valid trigger | Level 1 (Sanity) | Uses existing `add_trigger`, can unit test |
| NL bot creator returns valid JSON config | Level 2 (Proxy) | Depends on Claude CLI availability |
| Snippet CRUD operations | Level 1 (Sanity) | Standard DB CRUD |
| Snippet resolution in PromptRenderer | Level 1 (Sanity) | Pure function, unit testable |
| Version history records changes | Level 1 (Sanity) | Already implemented, needs UI + API |
| Version rollback restores previous template | Level 1 (Sanity) | DB read + existing update_trigger |
| Test console renders prompt from payload | Level 1 (Sanity) | Pure function composition |
| Test console shows CLI command preview | Level 1 (Sanity) | Uses existing CommandBuilder |
| End-to-end: template deploy + execute | Level 2 (Proxy) | Needs running backend + CLI |
| End-to-end: NL create + execute | Level 3 (Deferred) | Needs Claude CLI + real execution |

**Level 1 checks to always include:**
- Template catalog JSON parses without errors
- Template deploy creates trigger with all expected fields
- Snippet CRUD: create, read, update, delete, list
- Snippet resolution: `{{known_snippet}}` replaced, `{{unknown}}` left unchanged
- Version history: 3 edits produce 3 history entries with correct old/new values
- Rollback: restoring version 1 after 3 edits produces the original template text
- Test console: payload extraction matches trigger's `text_field_path` / `match_field_path`

**Level 2 proxy metrics:**
- NL bot creator generates valid config for "create a bot that reviews PRs" description
- Generated trigger can be saved to database without validation errors
- Frontend build succeeds with all new components (vue-tsc type checking)

**Level 3 deferred items:**
- Generated bots actually execute successfully against real CLI
- Snippet-referenced prompts produce expected output from real CLI execution
- Template marketplace UX usability testing

## Production Considerations

### Known Failure Modes

- **Claude CLI unavailable for NL generation:** The NL bot creator depends on the Claude CLI being installed. If unavailable, the `BaseGenerationService` already returns an SSE error event: `"Claude CLI not found."` The UI should show a clear error message and suggest manual creation as fallback.
  - Prevention: Check CLI availability before showing the NL creator option
  - Detection: Frontend checks backend health/utility endpoint for CLI status

- **Template catalog schema drift:** If the `bot_templates.json` schema changes, old templates may fail to deploy.
  - Prevention: Version the catalog schema; validate on load
  - Detection: Startup validation of catalog JSON against Pydantic model

### Scaling Concerns

- **Version history table growth:** At current scale (tens of triggers, few edits per day), the `trigger_template_history` table will remain small. At scale (hundreds of triggers, frequent automated edits), consider:
  - At current scale: No concerns. Simple SELECT with LIMIT/OFFSET.
  - At production scale: Add pagination to history API (already planned via PaginationQuery pattern). Consider archiving entries older than 1 year.

- **Snippet resolution performance:** Each prompt render now requires N snippet lookups (where N = number of `{{...}}` references in the template).
  - At current scale: Negligible -- snippets are small, SQLite is fast for single-row lookups.
  - At production scale: Cache snippets in-memory with a 60-second TTL (similar to `ExecutionLogService._log_buffers` pattern).

### Common Implementation Traps

- **Forgetting to extend `PromptRenderer._KNOWN_PLACEHOLDERS`:** If new placeholders are added for templates, they must be added to `_KNOWN_PLACEHOLDERS` to avoid false "unresolved placeholder" warnings.
  - Correct approach: Keep `_KNOWN_PLACEHOLDERS` as the single source of truth; update when adding new built-in placeholders.

- **Not registering new blueprints:** New route files must be registered in `backend/app/routes/__init__.py` via `app.register_api(bp)`.
  - Correct approach: Add blueprint registration alongside existing registrations, before the SPA catch-all.

- **Frontend type drift:** All new API types must be added to `frontend/src/services/api/types.ts` and new API functions to domain-specific modules, re-exported from `index.ts`.
  - Correct approach: Follow the existing pattern in `triggers.ts` for new template/snippet API functions.

## Code Examples

### Template Catalog JSON Structure

```json
[
    {
        "slug": "pr-reviewer",
        "name": "PR Reviewer",
        "description": "Reviews pull requests for code quality, security, and best practices",
        "category": "code-review",
        "icon": "git-pull-request",
        "tags": ["github", "code-quality"],
        "config": {
            "prompt_template": "Review this pull request thoroughly:\n\nPR: {pr_url}\nTitle: {pr_title}\nAuthor: {pr_author}\n\nAnalyze for:\n1. Code quality and readability\n2. Potential bugs or edge cases\n3. Security vulnerabilities\n4. Performance implications\n5. Test coverage gaps\n\nProvide actionable, specific feedback.",
            "backend_type": "claude",
            "trigger_source": "github",
            "model": null,
            "allowed_tools": "Read,Glob,Grep,Bash"
        }
    },
    {
        "slug": "dependency-updater",
        "name": "Dependency Updater",
        "description": "Scans and updates outdated dependencies across project files",
        "category": "maintenance",
        "icon": "package",
        "tags": ["dependencies", "security"],
        "config": {
            "prompt_template": "Scan {paths} for outdated dependencies.\n\nFor each outdated package:\n1. Check the latest stable version\n2. Review the changelog for breaking changes\n3. Update the dependency if safe\n4. Run tests to verify compatibility\n\nReport all changes made.",
            "backend_type": "claude",
            "trigger_source": "manual",
            "model": null,
            "allowed_tools": "Read,Glob,Grep,Bash"
        }
    },
    {
        "slug": "security-scanner",
        "name": "Security Scanner",
        "description": "Performs comprehensive security audit of the codebase",
        "category": "security",
        "icon": "shield",
        "tags": ["security", "audit"],
        "config": {
            "prompt_template": "Perform a comprehensive security audit of {paths}.\n\nCheck for:\n1. Hardcoded secrets and credentials\n2. SQL injection vulnerabilities\n3. XSS attack vectors\n4. Insecure dependencies\n5. Authentication/authorization issues\n6. Sensitive data exposure\n\nFor each finding, rate severity (critical/high/medium/low) and provide a fix.",
            "backend_type": "claude",
            "trigger_source": "webhook",
            "model": null,
            "allowed_tools": "Read,Glob,Grep,Bash"
        }
    },
    {
        "slug": "changelog-generator",
        "name": "Changelog Generator",
        "description": "Generates a changelog from recent git commits",
        "category": "documentation",
        "icon": "file-text",
        "tags": ["documentation", "git"],
        "config": {
            "prompt_template": "Generate a changelog for {paths} from recent git commits.\n\n{message}\n\nGroup changes by:\n- Features (new functionality)\n- Fixes (bug fixes)\n- Improvements (enhancements)\n- Breaking Changes\n\nUse conventional commit format. Include commit hashes.",
            "backend_type": "claude",
            "trigger_source": "manual",
            "model": null,
            "allowed_tools": "Read,Glob,Grep,Bash"
        }
    },
    {
        "slug": "test-writer",
        "name": "Test Writer",
        "description": "Generates unit tests for untested or under-tested code",
        "category": "testing",
        "icon": "check-circle",
        "tags": ["testing", "code-quality"],
        "config": {
            "prompt_template": "Analyze {paths} and write unit tests for code that lacks test coverage.\n\n{message}\n\nRequirements:\n1. Identify files/functions without tests\n2. Write comprehensive test cases\n3. Cover edge cases and error paths\n4. Follow existing test conventions in the project\n5. Use the project's test framework",
            "backend_type": "claude",
            "trigger_source": "manual",
            "model": null,
            "allowed_tools": "Read,Glob,Grep,Bash"
        }
    }
]
```

### Prompt Snippet DB Schema

```sql
CREATE TABLE IF NOT EXISTS prompt_snippets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_prompt_snippets_name ON prompt_snippets(name);
```

### Version History Table Extension

```sql
-- Add author and change_type columns to existing trigger_template_history
ALTER TABLE trigger_template_history ADD COLUMN author TEXT DEFAULT 'user';
ALTER TABLE trigger_template_history ADD COLUMN change_type TEXT DEFAULT 'edit';
-- change_type: 'edit' | 'rollback' | 'deploy'
```

### Diff Computation (Python stdlib)

```python
import difflib

def compute_template_diff(old_template: str, new_template: str) -> str:
    """Compute a unified diff between two template versions."""
    old_lines = old_template.splitlines(keepends=True)
    new_lines = new_template.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="previous", tofile="current")
    return "".join(diff)
```

### Frontend Template Card Component Pattern

```vue
<!-- Source: follows existing card patterns in components/triggers/BackendStatusCard.vue -->
<script setup lang="ts">
defineProps<{
  template: {
    slug: string;
    name: string;
    description: string;
    category: string;
    icon: string;
    tags: string[];
  };
}>();

const emit = defineEmits<{
  deploy: [slug: string];
}>();
</script>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual trigger config via form | Template marketplace + NL creator | This phase | Reduces time-to-first-bot from minutes to seconds |
| Inline prompt text, copy-paste reuse | Named snippet library with variable references | This phase | Single source of truth for shared prompt sections |
| No prompt history (before migration v50) | Template version history with diff and rollback | This phase (extends v50) | Full audit trail, safe experimentation |
| preview_prompt with manual field entry | Webhook test console with payload simulation | This phase (extends preview) | Realistic dry-run testing before deployment |

**Building on existing foundations:**
- `trigger_template_history` table (migration v50) -- already captures old/new template pairs
- `preview_prompt` endpoint -- already renders templates with sample data
- `BaseGenerationService` -- already handles Claude CLI streaming for config generation
- `PromptRenderer` -- already handles placeholder substitution
- `CommandBuilder` -- already builds CLI commands from config
- `get_nested_value()` -- already extracts values from nested JSON by dot-path

## Open Questions

1. **Template catalog updates**
   - What we know: Static JSON in codebase works for curated templates. Five templates specified in requirements.
   - What's unclear: Should templates be hot-reloadable without backend restart? Current implementation would require restart.
   - Recommendation: Load JSON on each request (it's tiny). This avoids caching and restart issues.

2. **Snippet scope**
   - What we know: Snippets are global (available to all triggers). The `{{snippet_name}}` syntax is clear and unambiguous.
   - What's unclear: Should snippets support markdown/rich text, or plain text only?
   - Recommendation: Plain text only for v0.2.0. Snippets are inserted into CLI prompts where markdown formatting is handled by the LLM, not the snippet system.

3. **NL creator model selection**
   - What we know: The `BaseGenerationService` uses `claude -p` (default model). The NL creator prompt should be optimized for structured output.
   - What's unclear: Should users be able to choose which model generates the config?
   - Recommendation: Use default Claude model. The generation prompt is simple enough that model selection is unnecessary overhead for v0.2.0.

## Sources

### Primary (HIGH confidence)
- Agented codebase analysis: `backend/app/db/triggers.py` -- trigger CRUD, template history, preview_prompt
- Agented codebase analysis: `backend/app/services/prompt_renderer.py` -- placeholder substitution engine
- Agented codebase analysis: `backend/app/services/base_generation_service.py` -- Claude CLI generation pattern
- Agented codebase analysis: `backend/app/services/command_builder.py` -- CLI command construction
- Agented codebase analysis: `backend/app/services/trigger_service.py` -- trigger service with template change logging
- Agented codebase analysis: `backend/app/routes/triggers.py` -- existing trigger API with preview_prompt endpoint
- Agented codebase analysis: `backend/app/utils/json_path.py` -- nested JSON value extraction

### Secondary (MEDIUM confidence)
- Braintrust prompt versioning (2025) -- content-addressable versioning, immutable history, environment-based rollback
- Gao et al. "Generating Structured Outputs from Language Models" (arXiv:2501.10868, 2025) -- constrained vs unconstrained generation comparison
- Fabric pattern system (danielmiessler/fabric, GitHub) -- flat file-based reusable prompt patterns with variable syntax
- LaunchDarkly prompt versioning guide (2025) -- environment-based deployment, feature-flag rollback
- Workativ chatbot marketplace (2025) -- pre-built bot template gallery with one-click deployment

### Tertiary (LOW confidence)
- General webhook testing patterns from Zuplo, Paddle, Beeceptor documentation -- payload simulation and dry-run preview concepts

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- No new libraries needed; all features build on existing codebase patterns
- Architecture: HIGH -- Every feature maps to an established pattern in the codebase
- Paper recommendations: MEDIUM -- Versioning patterns well-established but not from academic papers; LLM generation patterns from recent pre-print
- Pitfalls: HIGH -- Identified from direct codebase analysis and existing production patterns

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable domain, no fast-moving dependencies)
