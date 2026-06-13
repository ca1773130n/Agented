# Requirements — v0.8.0 Team Harness & Self-Improvement

Derived from the approved design spec
`docs/superpowers/specs/2026-06-13-team-harness-self-improvement-design.md`.
Prior milestones shipped without formal REQ-IDs (PR-driven era); numbering
starts at REQ-01 for this milestone.

**Traceability:** phase mapping is filled by the roadmapper (every REQ maps
to exactly one phase).

## Forge creation surface (FRG)

- [ ] **REQ-01** — `subagent` forge primitive kind: `subagents` table (`subag-` ID prefix), CRUD routes, `VALID_KINDS` entry, `.claude/agents/<name>.md` materialization, context-compiler/renderer support across claude/codex/gemini/opencode. (Phase: 17)
- [ ] **REQ-02** — Atomic create+bind+materialize: `POST /admin/projects/{id}/forge/create` with compensating cleanup; fix `replace_for_project` dropping `source_scope/source_shared_binding_id/fingerprint/conflict_policy`. (Phase: 17)
- [ ] **REQ-03** — Cross-kind bundles: `forge_bundles` + `forge_bundle_items`, bundle bind endpoint; `skill_sets` untouched. (Phase: 17)
- [ ] **REQ-04** — `forge-creator` default bundle: five global-scope creator skills (skill/rule/hook/command/subagent-creator), agentskills.io-compatible SKILL.md format. (Phase: 17)
- [ ] **REQ-05** — Session-completion auto-import: handler diffs `.claude/` against forge manifest, imports session-scaffolded primitives via `HarnessLoaderService` + atomic API, records origin content-hash + source session id; only Agented-driven-session artifacts auto-bind. (Phase: 17)

## Sketch → primitive routing (SKC)

- [ ] **REQ-06** — Classification `action` dimension (`create_skill|create_rule|create_hook|create_command|create_subagent|improve_primitive|none`) in keyword stage + LLM prompt/schema. (Phase: 18)
- [ ] **REQ-07** — `primitive_generator` routing target (confidence ≥ 0.6) + `PrimitiveForgeService` create path reusing per-kind generation services → atomic persist+bind+materialize. (Phase: 18)
- [ ] **REQ-08** — Improve path: fuzzy resolve over bound primitives, ACE-style old→new delta patch, re-materialize; ambiguity → `collaborating` clarification. (Phase: 18)
- [ ] **REQ-09** — Sketch panel "primitive created/updated" outcome card (kind, name, diff, bound projects, one-click undo); fix `SketchStatus` missing `collaborating`. (Phase: 18)

## GRD default driver (DRV)

- [ ] **REQ-10** — `resolve_execution_driver()` → `cliproxy|cli_agent|grd`; precedence: turn override → SA `config_json.driver` → instance → project default → global default `grd`; silent degrade to `cli_agent` when GRD/workspace unavailable. (Phase: 19)
- [ ] **REQ-11** — `GrdChatSessionHandler` in `HANDLER_REGISTRY`: task-shaped turns spawn PSM sessions in project cwd running `/grd:quick` (or mapped `/grd:` command), output bridged to chat SSE `state_delta`; conversational turns stay on cliproxy via lightweight turn classifier. (Phase: 19)
- [ ] **REQ-12** — cwd/backend fixes: `execute_delegate`, `_scan_mentions_and_notify`, `grd_routes.project_chat` resolve project workspace; drop `backend='claude'` hardcode. (Phase: 19)
- [ ] **REQ-13** — Driver selector UI on superagent + project settings (default GRD); chat transcript shows GRD session linkage. (Phase: 19)

## GRD frontend wiring (GWR)

- [ ] **REQ-14** — Autoresearch backend: routes wrapping `gd research` (start/status/resume/report/portfolio + thread browser) + `grd_research` execution-type handler (PSM + SSE). (Phase: 20)
- [ ] **REQ-15** — Research page: question intake, thread list, hypothesis ledger, report viewer, portfolio runs. (Phase: 20)
- [ ] **REQ-16** — Life-harness completion UI: autonomy policy editor, round revert, shared-forge browse/adopt, panels for the 16 unwired GRD routes (health/think/dead-ends/genome/verify-mechanical/reflections/verdict-counts/evolve). (Phase: 20)
- [ ] **REQ-17** — PlanningCommandBar exposes the full supported `/grd:` command set, grouped, from a declarative manifest. (Phase: 20)
- [ ] **REQ-18** — All new UI surfaces ship en/ko/ja/zh key-identical catalogs. (Phase: 20)

## One-click team harness setup (OCS)

- [ ] **REQ-19** — `projects.harness_setup_status` + "Setup Team Harness" button on ProjectDashboard with step-level SSE progress (grd_init pattern). (Phase: 21)
- [ ] **REQ-20** — `TeamHarnessSetupService`: idempotent steps — GRD init, team topology + SAs (`driver=grd`), bundle binding, tesserae enable, default policies (evolution autonomy conservative; takeaway auto-apply per-project on, scoped to skill-from-repetition), 4-harness materialization + per-backend compile smoke check; re-run reconciles, steps independently retryable. (Phase: 21)
- [ ] **REQ-21** — Project-tailored bundle selection driven by map-codebase output (language/framework-conditional rules). (Phase: 21)

## Repeated-request auto-skill (ASK)

- [x] **REQ-22** — `repeated_request_signals` store: UPSERT preserving `first_seen_at`, incrementing `occurrence_count`, embedding, capped `example_session_ids`, `verified_success_count`, `skill_created`. (Phase: 22)
- [x] **REQ-23** — Detection handler on the session-completion bus for all five session kinds: user-turn extraction via `_FETCHERS`, embedding match (cosine ≥ 0.83), tesserae cross-check, verification-record awareness. (Phase: 22)
- [x] **REQ-24** — Hybrid gates: auto path (≥3 occurrences/30d + ≥1 verified + scan pass → `discovered_procedure` takeaway conf 0.9 → auto-apply skill); propose path (conf 0.65, operator queue); takeaway auto-apply promoted from env flag to per-project policy. (Phase: 22)
- [x] **REQ-25** — Quality/safety: patch-over-create dedup against bound-skills index, origin-hash provenance (never overwrite operator-modified), prompt-injection/exfiltration + invisible-Unicode scan. (Phase: 22)
- [x] **REQ-26** — Consistency fixes: evolver `_DESIGN_GUIDE`/`_PROMPT_TEMPLATE` reflect writable skills; `tesserae_integration._build_harness_session` normalizes `project_session`/`workflow`/`team_session`. (Phase: 22)

## Out of scope (this milestone)

- Skill/mcp_server cross-project promotion (`_PROPAGATABLE` extension) — deferred
- Persistent `.codex/`/`.gemini/` repo projections (session overlays remain the non-claude channel)
- Replacing the in-memory wizard conversation store
- Multi-tenant/RBAC changes
