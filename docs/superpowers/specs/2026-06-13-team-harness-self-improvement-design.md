> 🌐 **Language:** English | [한국어](2026-06-13-team-harness-self-improvement-design.ko.md)

# v0.8.0 — Team Harness & Self-Improvement: Design Spec

**Date:** 2026-06-13
**Status:** Approved (design); pending milestone formalization via `/grd:new-milestone`
**Delivery:** GRD milestone, PR-driven (one or more PRs per phase), codex-review-until-green before merge.

## 1. Goal

Make every Agented project able to bootstrap, in one click, a team harness where:

1. Agents (and the sketch panel) can **create and improve harness primitives** — skill, rule, hook, command, subagent — through forge.
2. **GRD (GetResearchDone)** is the default execution driver for all superagent conversations, and all GRD features (autoresearch, life-harness/self-improvement, tesserae) are reachable from the frontend.
3. The system **self-improves**: repeated similar user requests are detected via the life-harness memory + tesserae and become skills automatically (confidence-gated).

### Locked product decisions

| Decision | Choice |
|---|---|
| Delivery | GRD milestone v0.8.0 (`.planning/milestones/v0.8.0/`), phase-by-phase PRs |
| GRD driver default | Default-on toggle: `driver: grd \| cli_agent \| cliproxy`, default `grd` |
| Auto-skill autonomy | Hybrid: high-confidence auto-create (≥3 near-identical + verified episode), lower confidence queued for approval |
| Harness targets | All four (claude/codex/gemini/opencode) via existing context-renderer/propagation layers |

## 2. Current state (recon summary)

Workflow recon (8 parallel agents, 2026-06-13) established:

- **Forge** has 6 primitive kinds (`rule, skill, hook, command, mcp_server, plugin`) bound to projects via `project_forge_bindings` (`backend/app/db/project_forge_bindings.py:24`; migration 121 explicitly allows new kinds without schema change). Primitives reach harnesses two ways: session-start `ContextCompilerService.compile` → per-backend renderers (claude/codex/gemini/opencode), and evolution-round apply → `forge_materialization_service.materialize_primitives` writing a persistent `.claude/` projection. Gaps: no `subagent` kind; create and bind are separate calls; `/generate/stream` endpoints emit drafts that are never persisted; `replace_for_project` drops provenance columns (`project_forge_bindings.py:177-191`); `skill_sets` is skills-only — no cross-kind bundle.
- **Sketch** pipeline: create → classify (`SketchRoutingService.classify`, keyword → trigram cache → LLM) → route (`route`, target_type `super_agent | team | none`) → `execute_sketch`. No primitive-creation routing target, no improve-primitive path, and the panel only renders SA-session SSE outcomes.
- **Superagents**: all chat paths funnel through `run_streaming_response` (`streaming_helper.py:263`) with a **boolean** routing rule `should_route_via_cli_agent` (`cli_agent_runner_service.py:530`). GRD is never invoked from chat. Chat turns are stateless one-shot `claude -p` runs; delegations and `grd_routes.project_chat` run with `cwd=None`. Precedents for bridging exist: `HANDLER_REGISTRY` (`execution_type_handler.py:686`), `GrdEvolveSessionHandler`, `GoalLoopSessionHandler`, `GrdPlanningService.invoke_command`, and the Ouroboros bridge (`super_agents_cluster.py:641`).
- **GRD wiring**: kanban/planning UI exposes 14/47 `/grd:` commands; life-harness rounds and takeaways partially wired; tesserae settings fully wired. **16 GRD-specific backend routes have zero frontend** (health, think, dead-ends, genome, verify-mechanical, reflections, verdict-counts, the evolve surface); round revert, autonomy policy, and shared-forge adoption have no UI; **autoresearch (`gd research` v2: threads, hypothesis ledger, portfolio) is entirely unwired**.
- **GRD package** `@jokerized/getresearchdone` 0.4.4 (`~/Developer/Projects/GetResearchDone`): ~95 deterministic `gd` tool commands, agent commands, autoresearch v2 (`gd research`), research KB (ingest/synthesize/retrieve), TesseraeClient KG sync, harness rounds with a 0.4.4 collective/upstream layer that already does **cross-project occurrence counting**, and `grd-mcp-server`.
- **One-click precedents**: ProjectDashboard actions row already hosts Load Harness (`HarnessLoaderService`), Deploy Harness, Run Setup (`InteractiveSetup.vue` SSE); project creation auto-runs GRD init with `grd_init_status` background+poll — the template for the new button.
- **Life-harness memory**: session-completion event bus (`execution_events.py:38`, five session kinds), takeaway extractor with `_apply_to_skill` (writes SKILL.md + `add_project_skill`, auto-apply ≥0.85 behind `AGENTED_TAKEAWAY_AUTOAPPLY`), Codex evolution rounds (eval-gated, journaled rollback), 10-gate autonomy, cross-project promotion. **No repeated-request detection exists**: kg_signals has no occurrence counter and its weight *decays* with age; no canonical store of raw user-request text; embeddings exist only for `memory_messages`; tesserae export skips `project_session`/`workflow`/`team_session`; the evolver prompt still claims skills are read-only although `_create_skill` is implemented.
- **Hermes research** (Nous Research Hermes agent + Voyager/ACE/Anthropic skill-creator prior art): episode-level LLM-judged creation triggers; staging gate (`write_approval` pending dir); progressive-disclosure skills index; patch-over-create dedup; origin-hash provenance; security scanning of self-written content; Voyager-style embedding-similarity retrieval; ACE-style delta updates; Anthropic-style trigger/non-trigger A/B eval.

## 3. Phase designs

### Phase 1 — Forge creation surface (backend foundation)

**New `subagent` kind.** New `subagents` table (id `subag-` prefix, name, description, content = full `.claude/agents/*.md` body incl. frontmatter, enabled, project_id, source_path, timestamps), CRUD routes mirroring `rules_plugins_hooks_commands.py`, `subagent` added to `VALID_KINDS`, materialization to `.claude/agents/<name>.md` in `forge_materialization_service`, and context-compiler support (claude renderer: overlay `agents/` dir; codex/gemini/opencode: nearest equivalent or prompt-prefix fallback, consistent with existing renderer behavior).

**Atomic create+bind+materialize.** `POST /admin/projects/{project_id}/forge/create` body `{kind, payload, bind: true, materialize: true}` → creates the asset row, adds the binding (idempotent upsert), and materializes the repo projection in one transaction-ish flow with compensating cleanup on failure. Fix `replace_for_project` to preserve `source_scope/source_shared_binding_id/fingerprint/conflict_policy`.

**Cross-kind bundles.** `forge_bundles` (+ `forge_bundle_items(kind, asset_id, position)`) with `POST /admin/projects/{id}/forge/bundles/{bundle_id}/bind` binding all items. `skill_sets` stays as-is (skills-only legacy).

**Forge-creator bundle (the "bundle skills").** Ship five creator skills as global-scope forge assets composed into a default bundle `forge-creator`: `skill-creator`, `rule-creator`, `hook-creator`, `command-creator`, `subagent-creator`. Each is agentskills.io-compatible SKILL.md (When to Use / Procedure / Pitfalls / Verification) instructing the in-session agent to scaffold the primitive **as files under the project's `.claude/` tree** (no in-session API auth surface). A new session-completion handler (`execution_events.register_session_handler`) diffs `.claude/` against the forge manifest and auto-imports new/changed primitives via `HarnessLoaderService` + the atomic create/bind API, recording provenance (origin content-hash, source session id).

**Testing:** repo-layer tests for new tables; route tests for atomic create (success + compensating cleanup); materialization golden-file tests incl. `.claude/agents/`; import-handler test against a fixture `.claude/` tree.

### Phase 2 — Sketch → primitive creation/improvement routing

**Classification.** Add an `action` dimension to `SketchRoutingService` (`sketch_routing_service.py:98/:132/:225-234`): `create_skill | create_rule | create_hook | create_command | create_subagent | improve_primitive | none`, in both the keyword stage (new keyword dict) and the LLM prompt/JSON schema. Confidence semantics unchanged.

**Routing.** In `route` (`:298`), when classification carries a primitive action with confidence ≥ 0.6, return new `target_type: "primitive_generator"` (target_id = primitive kind) before SA/team resolution. The route handler (`leaf_crud_g.py:165`) dispatches to a new `PrimitiveForgeService`:

- *Create:* drive the existing per-kind generation services to a complete draft, then persist+bind+materialize via Phase 1's atomic API. Skills reuse the conversational flow's preview-finalize internals.
- *Improve:* resolve the referenced primitive by fuzzy name match over the project's bound primitives; generate an ACE-style old→new delta patch; apply as update + re-materialize. Ambiguous reference → sketch status `collaborating` with a clarification question.

**Frontend.** `useSketchChat`/`SketchRouting.vue` get a third outcome branch: a "primitive created/updated" card (kind, name, description, diff view, bound-project list, one-click undo = unbind+delete or revert-update). Also fix the `SketchStatus` enum missing `collaborating`.

**Testing:** classifier unit tests (keyword + LLM-mocked) for each action; routing tests for `primitive_generator` precedence; PrimitiveForgeService create/improve tests; component tests for the outcome card. Dogfood: ≥3 real sketches through the live pipeline before declaring done.

### Phase 3 — GRD as default execution driver

**Driver abstraction.** Replace the boolean with `resolve_execution_driver(...) -> "cliproxy" | "cli_agent" | "grd"` in `cli_agent_runner_service.py`, honored at the single funnel `run_streaming_response` (`streaming_helper.py:263`). Resolution precedence: per-turn override → `SuperAgent.config_json.driver` → `project_sa_instances.driver` → project default (`projects.default_driver`) → global default **`grd`**. `grd` silently degrades to `cli_agent` when `grd_cli_service` reports the binary unavailable or the project has no workspace.

**GRD driver semantics.** A lightweight turn classifier (reuse the sketch keyword stage + cheap LLM fallback) splits turns into *task-shaped* vs *conversational*:

- Task-shaped → spawn a ProjectSessionManager session in the project workspace running `/grd:quick "<task>"` (research/planning-classified turns map to `/grd:research`, `/grd:plan-phase`, etc.), via a new `GrdChatSessionHandler` registered in `HANDLER_REGISTRY` (pattern: `GoalLoopSessionHandler`, which already supports `system_prompt_override` + forge bundle + `super_agent_id` linkage). PSM output events are bridged into the chat SSE `state_delta` protocol (content_delta/tool_use/finish/error) — a conversational evolution of the Ouroboros bridge.
- Conversational → unchanged cliproxy path.

**cwd fixes.** `execute_delegate`, `_scan_mentions_and_notify`, and `grd_routes.project_chat` resolve the project workspace instead of `cwd=None`, and `project_chat` stops hardcoding `backend='claude'`.

**Frontend.** Driver selector (default GRD) on superagent settings + project settings; chat transcript renders GRD session linkage (link to the project session / planning panel).

**Testing:** resolver precedence matrix tests; handler tests with fake PSM; SSE bridge tests (delta ordering, error propagation); regression tests that cliproxy conversational path is untouched; delegation cwd tests.

### Phase 4 — Full GRD feature wiring to the frontend

**Autoresearch.** New backend routes wrapping `gd research` (start/status/resume/report/portfolio + thread browser reading `.planning/research/threads/<id>/`) with a `grd_research` execution-type handler for long-running loops (PSM session + SSE, same as `grd_evolve`). New "Research" page: question intake, thread list with status/iteration, hypothesis ledger view, report viewer, portfolio runs.

**Life-harness completion.** UI for: autonomy policy editor (`GET/PUT /admin/projects/{id}/autonomy`), round revert, shared-forge browser + adopt (`GET /admin/shared-forge`, `POST .../adopt-shared/{id}`), and panels for the 16 unwired GRD routes (health, think, dead-ends, genome + snapshots, verify-mechanical, reflections, verdict-counts, evolve surface) on ActivityPage/GRD pages.

**Command surface.** PlanningCommandBar grows from 14 to the full supported `/grd:` command set, grouped (Plan / Execute / Verify / Research / Harness / Misc), driven from a declarative command manifest.

**i18n:** every new surface ships all four locales key-identical.

**Testing:** route tests for each new wrapper; component tests per panel; SSE tests for research streaming; no-new-failure frontend gate.

### Phase 5 — One-click team harness setup

**Entry point.** "Setup Team Harness" button in ProjectDashboard's actions row (`ProjectDashboard.vue:507-541`), following the `grd_init_status` pattern: new `projects.harness_setup_status` (`none/running/ready/failed`) + step-level progress via the InteractiveSetup SSE runner.

**Orchestration.** New `TeamHarnessSetupService.setup(project_id)` executes idempotent steps, each skippable when already satisfied:

1. Ensure clone + GRD init (`auto_init_project` if `grd_init_status != ready`).
2. Create default team topology + superagents (team-leader SA per team, `driver=grd`) from `team_topology_config` or a default template.
3. Bind the `forge-creator` bundle + baseline rules/hooks bundle, **tailored** by the project's map-codebase output (language/framework-conditional rule selection).
4. Enable tesserae for the project (existing `POST /admin/system/memory/tesserae/projects/{id}` path + MCP auto-bind).
5. Set default policies: evolution-round autonomy conservative (enabled=false, confidence 0.85, skill ∈ allowed_kinds, deletes blocked); takeaway auto-apply per-project policy on, scoped to skill-from-repetition (Phase 6).
6. Materialize the `.claude/` projection + verify per-backend renderer compilation for all four harnesses (compile `forge-context/preview` per backend as a smoke check).

Re-running reconciles instead of duplicating (manifest/fingerprint comparison). Failure leaves a step log and `failed` status; each step is independently retryable.

**Testing:** service step tests (fresh, partial, full re-run); route + SSE tests; dashboard component test; one live dogfood run against a real project.

### Phase 6 — Repeated-request detection → auto-skill

**Signal store.** `repeated_request_signals`: `signal_id` (PK), `project_id`, `canonical_text`, `embedding` (BLOB), `occurrence_count`, `example_session_ids` (JSON, capped), `first_seen_at`, `last_seen_at`, `verified_success_count`, `skill_created` flag. UPSERT preserves `first_seen_at` (pattern: `db/harness_kg_signals.record_signal`) but **increments count** — salience grows with repetition (inverse of kg_signals decay).

**Detection handler.** Registered on the session-completion bus alongside annotator/extractor/exporter (`lifecycle.py:454-485`), for all five session kinds:

1. Extract user-request turns via the `_FETCHERS` transcript layer (`harness_failure_annotator.py:304-315`) + `parse_claude_stream`.
2. Embed via `embedding_service`; match against existing signals by cosine ≥ 0.83; merge into the best match or insert new.
3. Record `verified_success` when the session has a passing verification record in the evidence ledger.
4. Cross-check tesserae (`ask_tesserae`) for historical occurrences predating the signal store.

**Skill synthesis gates** (per locked hybrid decision):

- **Auto path:** `occurrence_count ≥ 3` within 30 days **and** `verified_success_count ≥ 1` **and** security scan passes (prompt-injection/exfiltration patterns, invisible Unicode) → insert `session_takeaways` row (kind `discovered_procedure`, `suggested_target='skill'`, confidence 0.9, evidence = example sessions) → existing auto-apply machinery materializes SKILL.md (When to Use / Procedure / Pitfalls / Verification) + `add_project_skill`. The takeaway auto-apply gate is promoted from the global `AGENTED_TAKEAWAY_AUTOAPPLY` env flag to per-project policy, with skill-from-repetition **enabled by default** (this is distinct from evolution-round autonomy, which stays conservative — see Phase 5 step 5).
- **Propose path:** 2 occurrences, or unverified, or scan-flagged → same takeaway at confidence 0.65, queued in HarnessTakeawaysCard for operator approval.
- **Patch-over-create:** before creating, compare against the project's bound-skills index (name+description embedding match); a near-duplicate becomes an update proposal (delta patch) on the existing skill instead.
- **Provenance:** origin content-hash recorded at creation; refinement passes never overwrite operator-modified skills (hash mismatch → propose instead of apply).

**Consistency fixes folded in:** evolver `_DESIGN_GUIDE`/`_PROMPT_TEMPLATE` updated to reflect that skills are writable; `tesserae_integration._build_harness_session` extended to normalize `project_session`/`workflow`/`team_session` kinds so detection and KG signals see all sessions.

**Testing:** signal-store upsert/decay tests; detection handler tests over fixture transcripts; gate matrix tests (auto vs propose vs reject); security-scan tests; **live dogfood: replay ≥3 real session transcripts through the detector before declaring done** (house rule).

## 4. Cross-cutting

- **All-four-backends rule:** every LLM-calling addition accepts `{backend_kind, model_override?}`; renderer work covers claude/codex/gemini/opencode.
- **i18n:** all new UI strings in en/ko/ja/zh, key-identical; this spec ships with a `.ko.md` sibling.
- **Verification gates (house):** `just build`; backend pytest under the 12-minute watchdog procedure (disclose targeted substitution if the known hang hits); frontend `npm run test:run` no-new-failures.
- **Workflow:** PR per phase (or sub-phase), codex-review-until-green before merge.
- **Security:** auto-written skill/memory content is a system-prompt injection vector multiplied across four harnesses — scan before accept (Phase 6), staging gates default-on for autonomy (Phase 5 step 5).

## 5. Risks & mitigations

| Risk | Mitigation |
|---|---|
| GRD driver adds latency/weight to chat | Turn classifier keeps conversational turns on cliproxy; per-SA/project opt-out; silent degrade when GRD unavailable |
| Sketch misclassification creates unwanted primitives | Action confidence ≥ 0.6 gate; outcome card with one-click undo; improve-path asks on ambiguity |
| Junk-skill accumulation | Hybrid gates, patch-over-create dedup, provenance hashes, takeaway dismiss, skill disable |
| One-click setup mutates existing projects destructively | Idempotent reconcile per step; manifest comparison; step-level retry; no deletes in setup |
| Auto-import pulls malicious `.claude/` content from cloned repos | Import handler only auto-binds primitives created in Agented-driven sessions (session-id provenance); others queue for review |
| Backend test-suite hang masks regressions | Known-issue watchdog procedure, targeted suites disclosed per PR |

## 6. Dependency order

Phase 1 → Phase 2; Phases 1+3 → Phase 5; Phase 4 independent after 3 (shares driver plumbing); Phase 6 independent after 1 (uses skill creation path). Suggested execution: 1, 2, 3, 4, 5, 6.
