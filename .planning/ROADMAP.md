# Roadmap: v0.8.0 — Team Harness & Self-Improvement

> **Active milestone.** First GRD-planned milestone since v0.5.0. Derived
> from the approved design spec
> `docs/superpowers/specs/2026-06-13-team-harness-self-improvement-design.md`
> (+ `.ko.md`). Delivery is PR-per-phase with codex-review-until-green
> before merge. The historical v0.5.0 roadmap lives at
> `.planning/milestones/v0.5.0/ROADMAP.md`.

## Overview

Make every Agented project able to one-click bootstrap a **team harness**.
The journey runs backend-first: lay the forge creation surface (new
`subagent` primitive, atomic create+bind+materialize, cross-kind bundles,
the `forge-creator` skill bundle, session-completion auto-import), then route
the sketch panel into primitive create/improve, make GRD the default
execution driver for all superagent chat, wire GRD's full feature set
(autoresearch, life-harness completion, full `/grd:` command surface) to the
frontend, assemble the one-click `TeamHarnessSetupService`, and finally close
the self-improvement loop with repeated-request detection that converts
recurring user requests into skills behind hybrid confidence gates. Every
LLM-calling addition covers all four harnesses (claude/codex/gemini/opencode),
every new UI surface ships en/ko/ja/zh, and every phase passes the house
gates (`just build`, backend pytest watchdog, frontend no-new-failures).

## Phases

**Phase Numbering:**
- Integer phases: Planned milestone work. This milestone continues the
  project's phase sequence — the highest archived phase is 16, so v0.8.0
  runs phases **17–22** (spec Phase 1→6 = roadmap Phase 17→22).
- Decimal phases (17.1, 17.2): Urgent insertions (marked with INSERTED).

**Phase Types:** survey | implement | evaluate | integrate

- [x] **Phase 17: Forge creation surface** - `subagent` kind, atomic create+bind+materialize, cross-kind bundles, `forge-creator` bundle, session-completion auto-import `implement` ✓ 2026-06-13
- [ ] **Phase 18: Sketch → primitive routing** - classification `action` dimension, `primitive_generator` target, PrimitiveForgeService create + ACE-style improve, outcome card with undo `implement`
- [ ] **Phase 19: GRD default driver** - `resolve_execution_driver()` 3-way (default grd), GrdChatSessionHandler PSM→chat-SSE bridge, cwd/backend fixes, driver selector UI `implement`
- [ ] **Phase 20: GRD frontend wiring** - autoresearch page, life-harness completion UI (16 unwired routes), full `/grd:` command bar, 4-locale i18n `implement`
- [ ] **Phase 21: One-click team harness setup** - ProjectDashboard button + idempotent TeamHarnessSetupService (GRD init, topology, bundles, tesserae, policies, 4-harness materialization) `integrate`
- [ ] **Phase 22: Repeated-request auto-skill** - `repeated_request_signals` store, embedding detection over 5 session kinds, hybrid gates, patch-over-create, provenance, security scan `implement`

## Phase Details

### Phase 17: Forge creation surface
**Goal**: Forge can create and persist a fifth-and-sixth-class of primitive — `subagent` — and any primitive can be created, bound, and materialized to the repo `.claude/` projection in one atomic call; cross-kind bundles bind as a unit; a default `forge-creator` skill bundle exists; and primitives an agent scaffolds during an Agented-driven session are auto-imported with provenance.
**Type**: implement
**Depends on**: Nothing (first phase of milestone)
**Requirements**: REQ-01, REQ-02, REQ-03, REQ-04, REQ-05
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. `subagent` is a valid forge kind: `subagents` table (`subag-` ID prefix) with CRUD routes, `VALID_KINDS` entry, materialization to `.claude/agents/<name>.md`, and context-compiler/renderer support across claude/codex/gemini/opencode (golden-file tests pass, including `.claude/agents/`).
  2. `POST /admin/projects/{id}/forge/create` with `{kind, payload, bind, materialize}` creates+binds+materializes in one flow; on injected mid-flow failure, compensating cleanup leaves no orphaned row, binding, or repo file (route test for success + cleanup).
  3. `replace_for_project` preserves `source_scope`, `source_shared_binding_id`, `fingerprint`, and `conflict_policy` (regression test asserting columns survive a replace).
  4. `forge_bundles` + `forge_bundle_items` exist and the bundle-bind endpoint binds every item cross-kind in one call; `skill_sets` is unchanged.
  5. The `forge-creator` bundle ships five global-scope creator skills (skill/rule/hook/command/subagent-creator) in agentskills.io-compatible SKILL.md format; the session-completion import handler diffs `.claude/` against the forge manifest and auto-imports only Agented-driven-session artifacts, recording origin content-hash + source session id (import-handler test against a fixture `.claude/` tree).
  6. House gates pass: `just build`; backend pytest (watchdog procedure, targeted substitution disclosed if the known hang hits); frontend no-new-failures.
**Plans**: TBD

Plans:
- [ ] 17-NN: TBD (set by /grd:plan-phase 17)

### Phase 18: Sketch → primitive routing
**Goal**: The sketch panel can turn a free-text request into a created or improved forge primitive — classification gains an `action` dimension, a `primitive_generator` routing target drives `PrimitiveForgeService` (create via per-kind generators, improve via ACE-style delta over fuzzy-resolved bound primitives), and the panel renders a primitive outcome card with one-click undo.
**Type**: implement
**Depends on**: Phase 17 (uses the atomic create/bind/materialize API and the per-kind primitives)
**Requirements**: REQ-06, REQ-07, REQ-08, REQ-09
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. `SketchRoutingService` classification emits an `action` ∈ {create_skill, create_rule, create_hook, create_command, create_subagent, improve_primitive, none} from both the keyword stage and the LLM prompt/schema (unit tests, keyword + LLM-mocked, per action).
  2. `route` returns `target_type: "primitive_generator"` (target_id = kind) when a primitive action carries confidence ≥ 0.6, ahead of SA/team resolution (routing-precedence test).
  3. `PrimitiveForgeService` create path drives per-kind generation to a complete draft then persists+binds+materializes via Phase 17's atomic API (create test).
  4. Improve path fuzzy-resolves the referenced primitive over bound primitives, applies an ACE-style old→new delta patch, and re-materializes; an ambiguous reference yields sketch status `collaborating` with a clarification question (improve + ambiguity tests; `SketchStatus` enum includes `collaborating`).
  5. The sketch panel renders a "primitive created/updated" outcome card (kind, name, diff, bound-project list, one-click undo = unbind+delete or revert-update) (component test).
  6. Dogfood: ≥3 real sketches routed through the live pipeline before sign-off. House gates pass.
**Plans**: TBD

Plans:
- [ ] 18-NN: TBD (set by /grd:plan-phase 18)

### Phase 19: GRD default driver
**Goal**: GRD is the default execution driver for superagent chat — a 3-way `resolve_execution_driver()` (cliproxy | cli_agent | grd, default grd) is honored at the single streaming funnel, task-shaped turns spawn GRD PSM sessions bridged into the chat SSE protocol while conversational turns stay on cliproxy, delegation/project_chat cwd-and-backend bugs are fixed, and the driver is operator-selectable.
**Type**: implement
**Depends on**: Phase 17 (driver/forge plumbing; GRD sessions consume forge bundles)
**Requirements**: REQ-10, REQ-11, REQ-12, REQ-13
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. `resolve_execution_driver()` returns one of cliproxy/cli_agent/grd with precedence turn-override → SA `config_json.driver` → instance → project default → global default `grd`, and silently degrades to `cli_agent` when GRD binary/workspace is unavailable (precedence-matrix test incl. degrade path).
  2. `GrdChatSessionHandler` is registered in `HANDLER_REGISTRY`: task-shaped turns spawn a PSM session in the project cwd running `/grd:quick` (or the mapped `/grd:` command), with output bridged to chat SSE `state_delta` (content_delta/tool_use/finish/error); conversational turns stay on cliproxy via the turn classifier (handler test with fake PSM; SSE delta-ordering + error-propagation tests).
  3. The cliproxy conversational path is provably unchanged (regression test).
  4. `execute_delegate`, `_scan_mentions_and_notify`, and `grd_routes.project_chat` resolve the project workspace instead of `cwd=None`, and `project_chat` no longer hardcodes `backend='claude'` (delegation cwd tests).
  5. A driver selector (default GRD) appears on superagent and project settings, and the chat transcript shows GRD session linkage (component test).
  6. House gates pass.
**Plans**: 6 plans

Plans:
- [ ] 19-01-PLAN.md — Driver resolver + migration 158 (projects.default_driver, project_sa_instances.driver) + degrade injection (Wave 1)
- [ ] 19-02-PLAN.md — Turn classifier classify_turn + /grd: command mapping (Wave 1)
- [ ] 19-03-PLAN.md — cwd/backend bug fixes (execute_delegate, _scan_mentions_and_notify, project_chat) (Wave 1)
- [ ] 19-04-PLAN.md — GrdChatSessionHandler + HANDLER_REGISTRY entry + PSM→chat-SSE bridge (Wave 2)
- [ ] 19-05-PLAN.md — Funnel integration: 3-way branch in run_streaming_response + 2 call-site migrations + cliproxy regression (Wave 3)
- [ ] 19-06-PLAN.md — Frontend driver selectors (default GRD) + transcript GRD-session linkage + 4-locale i18n (Wave 3)

### Phase 20: GRD frontend wiring
**Goal**: GRD's full feature set is reachable from the frontend — autoresearch (`gd research`) has backend routes and a Research page, the life-harness completion surfaces (autonomy editor, round revert, shared-forge adopt, the 16 previously-unwired GRD routes) have UI, the PlanningCommandBar exposes the full supported `/grd:` command set from a manifest, and every new surface is fully localized.
**Type**: implement
**Depends on**: Phase 19 (shares the driver/GRD-session plumbing; the `grd_research` handler follows the GRD session pattern)
**Requirements**: REQ-14, REQ-15, REQ-16, REQ-17, REQ-18
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Autoresearch backend routes wrap `gd research` (start/status/resume/report/portfolio + thread browser over `.planning/research/threads/<id>/`) with a `grd_research` execution-type handler (PSM + SSE) (route + SSE-streaming tests).
  2. A Research page provides question intake, thread list with status/iteration, hypothesis ledger view, report viewer, and portfolio runs (component tests).
  3. Life-harness completion UI ships: autonomy policy editor, round revert, shared-forge browse/adopt, and panels for the 16 unwired GRD routes (health/think/dead-ends/genome/verify-mechanical/reflections/verdict-counts/evolve) (per-panel component tests).
  4. PlanningCommandBar exposes the full supported `/grd:` command set, grouped (Plan/Execute/Verify/Research/Harness/Misc), driven from a declarative manifest.
  5. Every new UI surface ships en/ko/ja/zh key-identical catalogs.
  6. House gates pass (frontend no-new-failures explicitly).
**Plans**: TBD

Plans:
- [ ] 20-NN: TBD (set by /grd:plan-phase 20)

### Phase 21: One-click team harness setup
**Goal**: A single ProjectDashboard button bootstraps a complete team harness — an idempotent `TeamHarnessSetupService` runs GRD init, team topology + GRD-driven superagents, project-tailored bundle binding, tesserae enablement, default policies, and 4-harness materialization with a per-backend compile smoke check; re-running reconciles rather than duplicates, and each step is independently retryable with step-level SSE progress.
**Type**: integrate
**Depends on**: Phase 17, Phase 19 (assembles the forge surface + GRD-driven SAs; this is the milestone's integration point for those two)
**Requirements**: REQ-19, REQ-20, REQ-21
**Verification Level**: full
**Success Criteria** (what must be TRUE):
  1. `projects.harness_setup_status` (none/running/ready/failed) backs a "Setup Team Harness" button on ProjectDashboard that streams step-level progress over SSE (grd_init pattern) (route + SSE + dashboard component tests).
  2. `TeamHarnessSetupService.setup(project_id)` runs the six idempotent steps — GRD init, team topology + SAs (`driver=grd`), bundle binding, tesserae enable, default policies (evolution autonomy conservative; takeaway auto-apply per-project on, scoped to skill-from-repetition), 4-harness materialization + per-backend compile smoke check (service step tests: fresh, partial, full re-run).
  3. Bundle selection is tailored by map-codebase output (language/framework-conditional rule selection).
  4. Re-running reconciles via manifest/fingerprint comparison without duplicating; a failed run leaves a step log + `failed` status and every step is independently retryable; setup performs no destructive deletes.
  5. One live dogfood run completes against a real project end-to-end, with all four backends compiling the materialized projection.
  6. House gates pass.
**Plans**: TBD

Plans:
- [ ] 21-NN: TBD (set by /grd:plan-phase 21)

### Phase 22: Repeated-request auto-skill
**Goal**: The harness self-improves — a `repeated_request_signals` store and a session-completion detection handler (over all five session kinds) embed and match recurring user requests, and hybrid confidence gates convert them into skills automatically (≥3 occurrences + verified + scan-pass) or queue them for approval, with patch-over-create dedup, origin-hash provenance protecting operator-modified skills, and prompt-injection/exfiltration/invisible-Unicode scanning.
**Type**: implement
**Depends on**: Phase 17 (uses the skill creation/bind/materialize path; closes the self-improvement loop)
**Verification Level**: proxy
**Requirements**: REQ-22, REQ-23, REQ-24, REQ-25, REQ-26
**Success Criteria** (what must be TRUE):
  1. `repeated_request_signals` UPSERT preserves `first_seen_at`, increments `occurrence_count`, stores `embedding`, caps `example_session_ids`, and tracks `verified_success_count` + `skill_created` (signal-store upsert tests; salience grows with repetition, not decays).
  2. The detection handler runs on the session-completion bus for all five session kinds: extracts user-request turns via `_FETCHERS`, embeds and matches by cosine ≥ 0.83, cross-checks tesserae, and is verification-record aware (handler tests over fixture transcripts).
  3. Hybrid gates: auto path (≥3 occurrences/30d + ≥1 verified + scan pass → `discovered_procedure` takeaway conf 0.9 → auto-apply skill) vs propose path (conf 0.65, operator queue); takeaway auto-apply is promoted from the env flag to per-project policy (gate-matrix tests: auto vs propose vs reject).
  4. Quality/safety: patch-over-create dedup against the bound-skills index turns near-duplicates into update proposals; origin-hash provenance never overwrites operator-modified skills; prompt-injection/exfiltration + invisible-Unicode scan rejects unsafe content (security-scan tests).
  5. Consistency fixes land: evolver `_DESIGN_GUIDE`/`_PROMPT_TEMPLATE` reflect writable skills; `tesserae_integration._build_harness_session` normalizes `project_session`/`workflow`/`team_session`.
  6. Live dogfood: replay ≥3 real session transcripts through the detector before sign-off. House gates pass.
**Plans**: TBD

Plans:
- [ ] 22-NN: TBD (set by /grd:plan-phase 22)

## Dependencies

```
17 ──► 18
17 ──┐
     ├──► 21
19 ──┘
19 ──► 20
17 ──► 22
```

- 17 → 18 (sketch routing consumes the atomic forge API)
- 17 + 19 → 21 (one-click setup assembles forge surface + GRD-driven SAs)
- 19 → 20 (frontend wiring shares GRD-session plumbing)
- 17 → 22 (auto-skill uses the skill creation path)

**Execution order:** 17, 18, 19, 20, 21, 22.

## Progress

| Phase | Name | Requirements | Depends on | Verification | Status |
|-------|------|--------------|------------|--------------|--------|
| 17 | Forge creation surface | Complete    | 2026-06-12 | proxy | Complete (6/6 ✓ 2026-06-13) |
| 18 | Sketch → primitive routing | REQ-06..09 | 17 | proxy | Not started |
| 19 | GRD default driver | REQ-10..13 | 17 | proxy | Not started |
| 20 | GRD frontend wiring | REQ-14..18 | 19 | proxy | Not started |
| 21 | One-click team harness setup | REQ-19..21 | 17, 19 | full | Not started |
| 22 | Repeated-request auto-skill | REQ-22..26 | 17 | proxy | Not started |

**Coverage:** 26/26 requirements mapped (REQ-01 … REQ-26), each to exactly one phase. No orphans, no duplicates.

**Integration phase:** Phase 21 (One-click team harness setup) is the milestone's integration point — it assembles the forge surface (17) and GRD-driven superagents (19) into a single idempotent bootstrap, validated by a live end-to-end dogfood run with all four backends compiling.
