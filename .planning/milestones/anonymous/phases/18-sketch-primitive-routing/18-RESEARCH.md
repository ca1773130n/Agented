# Phase 18: Sketch → primitive routing - Research

**Researched:** 2026-06-13
**Domain:** Sketch classification/routing pipeline (Litestar backend) + sketch panel (Vue 3); reuse of Phase 17 forge atomic API
**Confidence:** HIGH — every symbol/path/signature below was read directly from the live tree this session.

## Summary

Phase 18 extends the existing `SketchRoutingService` (a classmethod-only service in `backend/app/services/sketch_routing_service.py`) with an `action` classification dimension and a new `primitive_generator` routing target, wires a brand-new `PrimitiveForgeService` to Phase 17's atomic `create_and_bind_and_materialize(...)` (create path) and to per-kind `update_*`/`get_*`/`materialize_primitives` (improve path), adds the missing `SketchStatus.COLLABORATING` enum member on the **backend** (the frontend type already has it), and renders a "primitive created/updated" outcome card in the sketch panel (`SketchRouting.vue` + `useSketchChat.ts`) with one-click undo. There is **no existing `PrimitiveForgeService`** and **no existing "ACE" delta helper** — both are net-new. The repo has **no `rapidfuzz`**; the established fuzzy/diff tool is the stdlib `difflib` (used in `replay_service.py`, `mcp_sync_service.py`, `db/triggers.py`), so fuzzy resolution = `difflib.get_close_matches`/`SequenceMatcher.ratio` and the ACE-style old→new patch = a literal old→new string replacement against materialized content with a `difflib.unified_diff` for display.

**Primary recommendation:** Build in strict dependency order — (1) backend `SketchStatus.COLLABORATING` + the `action` classification dimension (keyword + LLM), (2) the `route()` `primitive_generator` precedence branch, (3) the net-new `PrimitiveForgeService` (create reuses `create_and_bind_and_materialize`; improve uses `difflib` fuzzy-resolve + literal patch + `update_*` + `materialize_primitives`), (4) the `/route` handler dispatch to it + outcome card + undo endpoints + i18n. The whole feature is plain-Python/Vue glue over already-shipped Phase 17 machinery; the only genuinely new logic is the `action` classifier, the fuzzy-resolve, and the literal patch.

## User Constraints (from CONTEXT.md)

No `*-CONTEXT.md` exists in the phase dir — `/grd:discuss-phase` was not run. Constraints are taken from the ROADMAP goal/success-criteria and the milestone-wide CLAUDE.md house rules:

### Locked Decisions (from ROADMAP + house rules)
- `action` ∈ `{create_skill, create_rule, create_hook, create_command, create_subagent, improve_primitive, none}` — emitted from **both** keyword and LLM stages.
- `primitive_generator` target wins at confidence **≥ 0.6**, **ahead of** SA/team resolution.
- Create path MUST reuse Phase 17's atomic `create_and_bind_and_materialize` — do not re-implement persist/bind/materialize.
- Improve path: fuzzy-resolve over **bound** primitives → ACE-style old→new delta → re-materialize; ambiguous reference → `SketchStatus.collaborating` + clarification question.
- **House rule (CLAUDE.md):** any new LLM-calling feature accepts `{backend_kind, model_override?}`, per-kind default models, never claude-only. The `action` LLM classifier and any "generation" LLM call MUST follow `resolve_llm_cmd(provider_kind, model_override)` (see `provider_cli_map.py`).
- **House rule:** i18n — all four locales (`en/ko/ja/zh`) stay key-identical; add a `sketchPrimitiveOutcome.*` (or extend `sketchRouting.*`) namespace in all four.
- **House rule:** Dogfood — run ≥3 real sketches through the live pipeline before sign-off.

### Claude's Discretion
- Exact `PrimitiveForgeService` API shape; the JSON shape of the `primitive_generator` routing/outcome result; fuzzy threshold value; whether the outcome card is a new component or a branch in `SketchRouting.vue`.

### Deferred Ideas (OUT OF SCOPE)
- Phase 22's `repeated_request_signals` auto-skill detection (separate phase).
- Skill-kind *create* via the atomic API (Phase 17 excluded `skill` from `_CREATE_FNS` — there is no `create_skill` db fn; see Open Question 1).

## Architecture Patterns (grounded in actual code)

### The classification pipeline (what `action` must thread through)
`SketchRoutingService` (`backend/app/services/sketch_routing_service.py:90`) is **classmethod-only**, no instance state.
- `classify(cls, sketch) -> dict` (`:98`) — pipeline: `_keyword_classify` → `_check_cache` → `_llm_classify` → keyword fallback. Returns `{phase, domains, complexity, confidence, source}`.
- `_keyword_classify(cls, text) -> dict` (`:132`) — scores `PHASE_KEYWORDS`/`DOMAIN_KEYWORDS`/`COMPLEXITY_SIGNALS` module dicts (`:18-82`). **Add an `ACTION_KEYWORDS` dict** here (e.g. `improve_primitive`: ["improve","update the skill","fix the rule","enhance the hook"], `create_skill`: ["create a skill","new skill"], …) and emit `action` + an action-confidence; surface both in the returned dict.
- `_llm_classify(cls, text) -> Optional[dict]` (`:217`) — builds `system_prompt` (`:225-234`) and validates `required = {"phase","domains","complexity","confidence"}` (`:277`). **Add `action` to the prompt schema and to `required`.** NOTE: current code uses `litellm.completion` directly with `DEFAULT_LLM_MODEL = "openai/claude-sonnet-4-20250514"` (`:95`) — this is the **claude-only** anti-pattern the house rule forbids. Phase 18 should add `provider_kind`/`model_override` params to `_llm_classify` (default-preserving) per the `resolve_llm_cmd` convention; minimally, thread them through and keep litellm but stop hard-coding claude. Flag in plan as a discretionary cleanup tied to REQ-06.
- `classify` returns early at `:110` when keyword confidence ≥ `KEYWORD_CONFIDENCE_THRESHOLD = 0.6` (`:93`) — the `action` must be present on that early-return path too.

### The routing precedence (where `primitive_generator` slots in)
`route(cls, classification, project_id=None) -> dict` (`:298`) returns `{target_type, target_id, reason}`. Current order: research/planning→SA (`:360`), execution→team (`:373`), review→SA (`:387`), psa-instance fallback (`:406`), else `none` (`:419`). **Insert the `primitive_generator` branch at the very top of `route` (immediately after the `phase`/`domains` extraction at `:314-315`), before any DB load**: if `action` is a primitive action and `confidence >= 0.6`, return `{"target_type": "primitive_generator", "target_id": <kind>, "reason": ..., "action": <action>}` where `target_id = kind` (e.g. `"skill"`/`"rule"`/… for create, or the resolved kind for improve). This guarantees precedence ahead of SA/team. Map `create_<kind>` → `<kind>`; `improve_primitive` → resolve kind during the forge step (target_id can be `"improve"` or left for the service).

### The Phase 17 atomic create API (REUSE — do not re-build)
`backend/app/services/forge_create_service.py`:
- `create_and_bind_and_materialize(project_id: str, kind: str, payload: dict, bind: bool = True, materialize: bool = True) -> dict` returns `{"kind","asset","binding","written"}`. LIFO-compensated; leaves no orphan on failure.
- Supported create kinds via `_CREATE_FNS`: `{subagent, rule, command, hook, mcp_server}` — **`skill` is excluded** (no `create_skill` db fn). `VALID_FORGE_BINDING_KINDS = {"rule","skill","hook","command","mcp_server","plugin","subagent"}` (`db/project_forge_bindings.py:24`).
- `payload.pop("role")` is handled internally (role belongs to binding). rule/command/hook return int ids; subagent/mcp_server return full dict (see `_coerce_asset_id`).
- **There is NO Python "per-kind generator" that drafts content from free text.** Phase 17's "generators" are the five `forge-creator` **SKILL.md prompt files** (`backend/app/forge_seeds/forge-creator/*/SKILL.md`) used by a live agent — not callable code. So "drives per-kind generation to a complete draft" means: `PrimitiveForgeService` produces the `payload` dict (name/content/etc.) — via an LLM call (following `resolve_llm_cmd`) or a deterministic template — then hands it to `create_and_bind_and_materialize`. See Open Question 2.

### The improve path building blocks (REUSE)
- Bound primitives for a project: `list_bindings(project_id, *, enabled_only=False) -> List[dict]` (`db/project_forge_bindings.py`) → rows of `{kind, asset_id, role, enabled, position, ...}`.
- Per-kind fetch for fuzzy-match text + current content: `get_rule(rule_id:int)`, `get_command(command_id:int)`, `get_hook(hook_id:int)` (`db/{rules,commands,hooks}.py`), `get_subagent(subagent_id:str)` / `get_subagent_by_name(name)` (`db/subagents.py:56,64`).
- Per-kind update: `update_rule(...)` (`rules.py:48`), `update_command(...)` (`commands.py:46`), `update_hook(...)` (`hooks.py:38`), `update_subagent(subagent_id, **fields) -> bool` (`subagents.py:85`).
- Re-materialize after update: `materialize_primitives(project, [kind], workspace_path)` (`forge_materialization_service.py:183`); resolve workspace via `ProjectWorkspaceService.resolve_working_directory(project_id)` (pattern in `forge_create_service.py` step 3).
- Fuzzy resolution: **use `difflib`** (no rapidfuzz in repo). `difflib.get_close_matches(query, names, n=, cutoff=0.6)` over the bound-primitive name list; if 0 matches or ≥2 near-ties → ambiguous → return `collaborating`. ACE-style old→new patch: do a literal `content.replace(old, new)` (or regenerate full new content) and produce a `difflib.unified_diff(old.splitlines(), new.splitlines())` for the card's `diff` field (exact pattern in `services/replay_service.py:228`, `services/mcp_sync_service.py:107`).

### The route handler dispatch (where the service is called)
`route_sketch(sketch_id, data=None)` in `backend/app_litestar/routes/leaf_crud_g.py:166`. Today it branches `target_type == "super_agent"` / `"team"` and else writes `status="routed"`. **Add a `target_type == "primitive_generator"` branch** that calls `PrimitiveForgeService`, writes `routing_json` with the primitive outcome (kind, name, asset_id, binding_id, diff, bound_projects, undo handle), sets `status` to `completed` (success) or `collaborating` (ambiguous), and returns the outcome dict. Router registration is the `sketches_router` list at the bottom of the same file — add any new undo endpoint there.

### The frontend panel (where the card renders)
- `frontend/src/components/sketches/SketchRouting.vue` — `defineProps<{ routing: SketchRoutingData | null }>()`; template branches `routing.target_type === 'none'` vs the SA/team `routing-details` block. **Add a `v-else-if="routing.target_type === 'primitive_generator'"` block** (or a child `SketchPrimitiveOutcome.vue`) rendering kind/name/diff/bound-projects + an undo button. `getTargetIcon`/`handleTargetClick` switch statements also need a `primitive_generator` case.
- `frontend/src/composables/useSketchChat.ts` — parses `routeResult.routing` (`:182-189`), already special-cases `sketch.status === 'collaborating'` (`:278`) and `target_type === 'none'` (`:299`). Add a `primitive_generator` branch to push the outcome message and wire undo.
- `frontend/src/views/SketchChatPage.vue` hosts the panel.

### Frontend types + API client
- `frontend/src/services/api/types/sketches.ts` — `SketchStatus` type **already includes `'collaborating'`** (good; only the *backend* enum is missing it). Add a `SketchPrimitiveOutcome` interface (`{ kind; name; asset_id; binding_id?; diff?; bound_projects: string[]; undo: {...} }`) and a `routing` shape extension.
- `frontend/src/services/api/sketches.ts` — `sketchApi` object; `route()` returns `{ routing, session_id?, super_agent_id? }`. Add an `undoPrimitive(sketchId)` (or `forge.undo`) method calling the new undo endpoint.

## Per-Plan Implementation Guidance & Dependency Order

Recommended decomposition (4 plans; strict order — each depends on the previous):

**18-01 — Backend classification `action` dimension + `SketchStatus.COLLABORATING`** (REQ-06; foundation, no deps)
- `backend/app/models/sketch.py:9` — add `COLLABORATING = "collaborating"` to `SketchStatus` enum (between `IN_PROGRESS` and `COMPLETED` to mirror the FE order). Sweep consumers: `db/sketches.py` status writes, `routes/leaf_crud_g.py` status strings (they pass plain strings, so low risk; the enum is for validation in `UpdateSketchRequest`).
- `sketch_routing_service.py` — add `ACTION_KEYWORDS` dict; emit `action`+confidence from `_keyword_classify` and `classify` (all return paths); add `action` to `_llm_classify` prompt + `required` set; thread `provider_kind`/`model_override` (house rule).
- Files: `backend/app/models/sketch.py`, `backend/app/services/sketch_routing_service.py`, new `backend/tests/test_sketch_action_classification.py`.

**18-02 — `route()` `primitive_generator` precedence** (REQ-07; depends on 18-01's `action`)
- `sketch_routing_service.py::route` — insert primitive branch at top, target_id=kind, confidence ≥ 0.6 gate, ahead of SA/team.
- Files: `backend/app/services/sketch_routing_service.py`, `backend/tests/test_sketch_routing_scoped.py` (extend) or new `test_sketch_primitive_routing.py`.

**18-03 — `PrimitiveForgeService` (create + improve)** (REQ-07/REQ-08; depends on 18-02 + Phase 17 API)
- NEW `backend/app/services/primitive_forge_service.py`. Create path → builds payload (template or LLM via `resolve_llm_cmd`) → `create_and_bind_and_materialize`. Improve path → `list_bindings` → per-kind `get_*` → `difflib` fuzzy-resolve → literal old→new patch + `unified_diff` → `update_*` → `materialize_primitives`; ambiguous → `{status:"collaborating", question:...}`.
- Wire into `routes/leaf_crud_g.py::route_sketch` `primitive_generator` branch; add undo endpoint(s) (`remove_project_forge_binding` + `delete_<kind>` for create-undo; re-apply stored prior content via `update_*`+re-materialize for improve-undo).
- Files: new `backend/app/services/primitive_forge_service.py`, `backend/app_litestar/routes/leaf_crud_g.py`, new `backend/tests/test_primitive_forge_service.py`, `backend/tests/routes/test_sketch_primitive_routes.py`.

**18-04 — Frontend outcome card + undo + i18n** (REQ-09; depends on 18-03's response shape)
- `SketchRouting.vue` (or new `SketchPrimitiveOutcome.vue`), `useSketchChat.ts`, `types/sketches.ts`, `services/api/sketches.ts`, `locales/{en,ko,ja,zh}.json` (`sketchPrimitiveOutcome.*` — key-identical), new component test + `useSketchChat` test extension.

**Dependency chain:** `SketchStatus.COLLABORATING` + `action` enum (18-01) → routing precedence (18-02) → `PrimitiveForgeService` + handler + undo (18-03) → panel card + i18n (18-04). Phase 17 reuse: `create_and_bind_and_materialize`, `list_bindings`, `materialize_primitives`, `update_*`/`get_*`, `remove_project_forge_binding`, `delete_*`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Persist+bind+materialize | New transaction/saga | `create_and_bind_and_materialize` (`forge_create_service.py`) | Phase 17 already implements LIFO compensation; re-rolling risks orphans |
| Fuzzy primitive name match | Custom Levenshtein / new dep | stdlib `difflib.get_close_matches` | Repo has **no** rapidfuzz; difflib is the established tool |
| old→new diff for the card | Custom diff | `difflib.unified_diff` | Exact pattern already in `replay_service.py` / `mcp_sync_service.py` |
| Re-materialize after update | Hand-write `.claude/` files | `materialize_primitives(project,[kind],ws)` | Handles all 4 backends + manifest |
| LLM model selection | Hard-code claude | `resolve_llm_cmd(provider_kind, model_override)` (`provider_cli_map.py:33`, `_DEFAULT_MODELS` `:28`) | House rule: support 4 backends, per-kind defaults |

## Common Pitfalls

- **Backend enum lag:** FE `SketchStatus` already has `collaborating`; the BACKEND enum (`models/sketch.py:9`) does NOT. Forgetting this is the #1 trap — `UpdateSketchRequest.status: Optional[SketchStatus]` will reject `"collaborating"` until added.
- **`skill` cannot be created** via the atomic API (`_CREATE_FNS` excludes it). `create_skill` is in the success-criteria action set but has no db create fn. Resolution: route `create_skill` to `user_skills`/`add_user_skill` separately, OR scope the create path to `{rule,hook,command,subagent}` for Phase 18 and treat `create_skill` as improve-or-collaborate. **Recommend:** check `db/__init__.py` for `add_user_skill`; if create-by-payload is feasible, add a `skill` create branch in the service (not in `create_and_bind_and_materialize`). See Open Question 1.
- **`route_sketch` returns plain dict, status as string** — keep that contract; don't break the SA/team branches.
- **classmethod service** — `PrimitiveForgeService` should mirror the classmethod style of `SketchRoutingService`, and import db/forge fns into its own module namespace so tests can monkeypatch `app.services.primitive_forge_service.<name>` (the Phase-17 pattern: "Service imports … into its own namespace so tests monkeypatch").
- **i18n parity** — adding a key to `en.json` only will silently miss ko/ja/zh; the gate is key-identical across all four.

## Experiment Design

- **Variables:** sketch free-text → (action, confidence) → (target_type, kind) → (created/updated primitive, diff). 
- **Baseline:** current pipeline routes only to SA/team/none; primitive actions are unreachable (0% today).
- **Target / Dogfood (success criterion #6):** ≥3 real sketches routed through the live pipeline producing ≥1 create and ≥1 improve, with a visible outcome card and a working undo. Per CLAUDE.md "dogfood new pipelines against live data" — hand-crafted unit inputs miss format-mismatch; run real rows.
- **Per-action unit coverage (criterion #1):** one keyword test + one LLM-mocked test per `action` member (7 actions).

## Verification Strategy

| Item | Tier | Rationale |
|---|---|---|
| `action` emitted by keyword + LLM stages, per action | L1 Sanity | Pure-function assertions, no DB |
| `route` returns `primitive_generator` at conf ≥ 0.6 ahead of SA/team | L1 Sanity | Dict-shape assertion with seeded classification |
| create path → atomic API → row+binding+file | L2 Proxy | Needs `isolated_db` + temp workspace; assert asset+binding+`.claude/` file |
| improve fuzzy-resolve + patch + re-materialize; ambiguity→collaborating | L2 Proxy | Seed ≥2 bound primitives; assert diff + status |
| outcome card render + undo | L2 Proxy | Vitest + happy-dom component test |
| ≥3 live sketches + house gates | L3 Deferred | Dogfood + `just build` / pytest watchdog / FE no-new-failures |

**Test conventions:**
- Backend: `isolated_db` fixture (patches `DB_PATH` to temp). For Litestar route tests, the TestClient logger doesn't propagate to `caplog` — spy on `module.logger.warning` via `monkeypatch`. Existing sketch tests live at `backend/tests/test_sketch_routing_scoped.py`, `test_sketch_instance_routing.py`, `test_sketch_execution.py`, `test_sketch_crud.py` (no `test_sketch_classification.py` exists — create one for `action`). NOTE: I could not locate a test that currently mocks `litellm` for `_llm_classify`; the LLM path appears exercised only via fallback. For 18-01 LLM-mocked tests, monkeypatch `litellm.completion` (or the new `resolve_llm_cmd`/`_run_llm` path) to return a canned JSON string — mirror the takeaway-extractor tests' approach.
- Frontend: Vitest + happy-dom + @vue/test-utils; tests under `__tests__/`. Baseline carries 7 known pre-existing FE failures — gate is **no NEW failures**.

## Production Considerations (no KNOWHOW.md present for this milestone)

- **LLM 4-backend support** (CLAUDE.md memory `feedback_llm_features_support_all_backends`): the `action` classifier and any draft-generation LLM call MUST accept `{backend_kind, model_override?}` and use per-kind defaults — never default claude-only. The existing `_llm_classify` hard-codes `openai/claude-sonnet-4` and is the canonical violation to fix.
- **Bug-class sweep** (memory `feedback_bug_class_sweep`): when adding `SketchStatus.COLLABORATING`, grep every `SketchStatus` consumer and every status-string literal; fix in the shared model, one PR.
- **Undo correctness:** create-undo = `remove_project_forge_binding(binding_id)` + `delete_<kind>(asset_id)` + re-materialize (mirror `_compensate` in `forge_create_service.py`). improve-undo needs the **prior content stored** in `routing_json` before the patch so `update_*` can revert — there is no version table. Persist `old_content` in the outcome so undo is self-contained.
- **Security gate** (memory `feedback_session_not_bot_scope`, Phase 17 §Security Gate): primitive creation writes executable `.claude/` artifacts; keep the Phase 17 provenance/gating posture — only operator-driven sketch routes should create, and improve should not silently overwrite unrelated primitives (the fuzzy ambiguity→collaborating gate is the safety valve).

## Code Examples (verified patterns from this repo)

### Atomic create (reuse)
```python
# Source: backend/app/services/forge_create_service.py
result = create_and_bind_and_materialize(
    project_id, kind="rule", payload={"name": ..., "content": ...},
    bind=True, materialize=True,
)  # -> {"kind","asset","binding","written"}
```

### Fuzzy resolve + diff (improve path)
```python
import difflib  # repo's established tool (replay_service.py, mcp_sync_service.py)
names = [b["asset_id"] for b in list_bindings(project_id, enabled_only=True) if b["kind"] == kind]
matches = difflib.get_close_matches(query_name, names, n=3, cutoff=0.6)
if len(matches) != 1:   # 0 or ambiguous → collaborate
    return {"status": "collaborating", "question": "Which primitive did you mean?", "candidates": matches}
diff = "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm=""))
```

### LLM convention (house rule)
```python
# Source: backend/app/services/harness_takeaway_extractor.py + provider_cli_map.py:33
cmd_template = resolve_llm_cmd(provider_kind, model_override)  # per-kind default model
```

## State of the Art / Notes

- "ACE-style old→new delta patch" — no "ACE" helper exists in the repo (grep found none). Interpret as: capture `old_content`, compute `new_content` (literal replacement or full regeneration), persist both, render a `difflib.unified_diff`. This satisfies "old→new delta" and gives undo its revert source. **Recommendation: literal old→new replacement against materialized content + unified_diff for display + stored old_content for undo.** (MEDIUM confidence on intent; HIGH on the mechanism.)

## Open Questions

1. **`create_skill` has no db create fn.** `_CREATE_FNS` excludes `skill`. What backs `create_skill`?
   - Known: `add_user_skill`/`user_skills` exist (referenced in Phase 17 seed). 
   - Recommendation: in `PrimitiveForgeService`, branch `create_skill` to the user-skill create path (not the atomic forge API), or — if a per-project skill row + binding is desired — add a thin `skill` create that writes a `user_skills` row then binds/materializes. Confirm `add_user_skill` signature in `db/__init__.py` during 18-03. Do NOT try to push `skill` through `create_and_bind_and_materialize` (it raises `ValueError`).
2. **"per-kind generation to a complete draft"** — Phase 17 generators are SKILL.md prompts, not callable code. Recommendation: `PrimitiveForgeService` builds the `payload` either deterministically (name from sketch title, content from sketch body) for a v1, or via an LLM draft call using `resolve_llm_cmd`. For dogfood/test stability, make the draft source injectable (param/monkeypatch) so tests don't require a live LLM.
3. **`improve_primitive` target_id at route time** — kind may be unknown until the bound primitive is resolved. Recommendation: set `target_id="improve"` (or omit) in `route()`; let `PrimitiveForgeService` resolve kind from the fuzzy match.

## Sources

### Primary (HIGH — code read this session)
- `backend/app/services/sketch_routing_service.py` — classify/keyword/llm/route, lines cited above
- `backend/app/models/sketch.py:9` — `SketchStatus` (missing `collaborating`)
- `backend/app/services/forge_create_service.py` — `create_and_bind_and_materialize`, `_CREATE_FNS`/`_DELETE_FNS`, `_compensate`
- `backend/app/db/project_forge_bindings.py` — `VALID_KINDS`, `list_bindings`, `add_binding`, `remove_binding`, `upsert_binding`
- `backend/app/db/{rules,commands,hooks,subagents}.py` — `get_*`/`update_*`/`list_subagents`
- `backend/app/services/forge_materialization_service.py:183` — `materialize_primitives`
- `backend/app/services/provider_cli_map.py:28,33` — `_DEFAULT_MODELS`, `resolve_llm_cmd`; `harness_takeaway_extractor.py:543-565` — `_extract_llm` convention
- `backend/app_litestar/routes/leaf_crud_g.py:166` — `route_sketch` + `sketches_router`
- `frontend/src/components/sketches/SketchRouting.vue`, `composables/useSketchChat.ts`, `services/api/sketches.ts`, `services/api/types/sketches.ts` (`collaborating` already present)
- Phase 17 SUMMARYs (`17-04`, `17-05`, `17-06`) + `17-RESEARCH.md`

### Secondary (MEDIUM)
- `services/replay_service.py:228`, `services/mcp_sync_service.py:107`, `db/triggers.py:533` — `difflib.unified_diff` usage establishing the diff pattern

## Citation Recovery

| Component | Source | Status | Priority |
|---|---|---|---|
| atomic create API | Phase 17 `forge_create_service.py` | Resolved | Critical |
| fuzzy lib | stdlib `difflib` (no rapidfuzz) | Resolved | Critical |
| ACE delta helper | none found in repo | Unresolved (build minimal) | Normal |
| LLM 4-backend convention | `provider_cli_map.resolve_llm_cmd` | Resolved | Critical |

**Unresolved critical dependencies:** 0 (the only "unresolved" item — ACE helper — is intentionally net-new and has a recommended minimal mechanism).

## Metadata

**Confidence breakdown:**
- Symbols/paths/signatures: HIGH — read from live tree
- Routing precedence insertion point: HIGH
- ACE-delta interpretation: MEDIUM (intent inferred; mechanism HIGH)
- `create_skill` backing: MEDIUM (needs `add_user_skill` sig confirmation in 18-03)

**Research date:** 2026-06-13
**Valid until:** ~2026-07-13 (stable internal code; revalidate if Phase 17 forge API changes)
