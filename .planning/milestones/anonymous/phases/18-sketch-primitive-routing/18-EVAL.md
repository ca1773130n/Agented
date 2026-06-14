# Evaluation Plan: Phase 18 — Sketch → Primitive Routing

**Designed:** 2026-06-13
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** action-dimension sketch classification, `primitive_generator` routing target, `PrimitiveForgeService` (create/improve/undo), primitive outcome card
**Reference:** No paper — behavioral/feature phase. Targets anchored to the 6 phase success criteria (REQ-06..09).

## Evaluation Overview

This is a **behavioral/feature phase**, not a metric-optimization phase, so there are no PSNR-style numeric targets. "Proxy" (Tier 2) here means **automated behavioral tests with explicit pass/fail thresholds** — coverage-of-behavior and green/red test counts that stand in for the real proof (a human routing real sketches through the live pipeline, which is Tier 3 / deferred).

The honest limitation: passing every Tier-2 test confirms the wiring is correct on mocked LLM + in-process services, but it does NOT confirm that real free-text sketches classify correctly or that materialized primitives are useful. That confidence only arrives at the dogfood gate (DEFER-18-01..03).

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 5 | Build, lint, type, i18n parity, enum importability, no-new-frontend-failures |
| Proxy (L2) | 7 | Mocked behavioral tests for classification, routing, create, improve, undo, frontend card, 4-backend |
| Deferred (L3) | 3 | Live-pipeline dogfood, full backend suite, real-LLM quality spot-check |

### Criteria → Tier Map

| Criterion | Sanity | Proxy | Deferred |
|-----------|--------|-------|----------|
| 1. `action` from keyword + LLM | — | P1 | D3 |
| 2. `primitive_generator` ≥0.6 ahead of SA/team | — | P2 | — |
| 3. create → persist+bind+materialize | — | P3 | D1 |
| 4. improve fuzzy+delta; ambiguity→collaborating; enum | S5 | P4 | D1 |
| 5. outcome card (kind/name/diff/bound/undo) | S2 | P6 | D1 |
| 6. dogfood ≥3 + house gates | S1,S2,S3,S4,S6 | P5,P7 | D1,D2 |

## Level 1: Sanity Checks

**Gate:** ALL must pass before proceeding. Seconds to run.

### S1: Ruff clean on touched backend files — covers crit 6
- **Command:** `cd backend && uv run ruff format --check app/models/sketch.py app/services/sketch_routing_service.py app/services/primitive_forge_service.py app_litestar/routes/leaf_crud_g.py && uv run ruff check app/services/primitive_forge_service.py app/services/sketch_routing_service.py`
- **Expected:** exit 0, no reformatting, no lint errors.
- **Failure means:** style/lint regression — blocks.

### S2: `just build` passes (vue-tsc + vite) — covers crit 5, 6
- **Command:** `just build`
- **Expected:** exit 0; vue-tsc resolves new `SketchPrimitiveOutcome` type and `SketchRouting.vue` card; vite build succeeds.
- **Failure means:** type error in new frontend type or component — blocks.

### S3: i18n 4-locale key-parity for `sketchPrimitiveOutcome.*` — covers crit 6
- **Command:** `cd frontend && node -e "const en=require('./src/locales/en.json').sketchPrimitiveOutcome||{},ko=require('./src/locales/ko.json').sketchPrimitiveOutcome||{},ja=require('./src/locales/ja.json').sketchPrimitiveOutcome||{},zh=require('./src/locales/zh.json').sketchPrimitiveOutcome||{};const k=o=>Object.keys(o).sort().join(',');const base=k(en);if(![ko,ja,zh].every(l=>k(l)===base)||base==='')throw new Error('locale key mismatch or empty');console.log('PARITY OK',base.split(',').length,'keys')"`
- **Expected:** prints `PARITY OK N keys`; all four locales key-identical and non-empty.
- **Failure means:** missing/extra key in a locale (violates 4-locale parity rule) — blocks.

### S4: `SketchStatus.COLLABORATING` importable — covers crit 4, 6
- **Command:** `cd backend && uv run python -c "from app.models.sketch import SketchStatus; assert SketchStatus.COLLABORATING.value=='collaborating'; print('OK', SketchStatus.COLLABORATING.value)"`
- **Expected:** prints `OK collaborating`.
- **Failure means:** enum member missing/misnamed — blocks 18-03 improve path.

### S5: Enum surface check — covers crit 4
- **Command:** `cd backend && uv run python -c "from app.models.sketch import SketchStatus; vals={s.value for s in SketchStatus}; assert 'collaborating' in vals; print(sorted(vals))"`
- **Expected:** `collaborating` present in status value set.
- **Failure means:** status not wired into enum — blocks.

### S6: No NEW frontend test failures vs 7-known baseline — covers crit 6
- **Command:** `cd frontend && npm run test:run`
- **Expected:** total failures ≤ 7, and the failing set ⊆ {RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine}. ANY failure outside that set = NEW failure = FAIL.
- **Failure means:** regression introduced by 18-04 — blocks.

**Sanity gate:** S1–S6 all pass.

## Level 2: Proxy Metrics

**IMPORTANT:** These are mocked/in-process behavioral tests. Green here ≠ validated end-to-end. All `validated: false` until DEFER-18-01 dogfood confirms. Each has an explicit pass/fail threshold.

### P1: Action classification from BOTH stages — covers crit 1
- **What:** All 7 action values `{create_skill, create_rule, create_hook, create_command, create_subagent, improve_primitive, none}` emitted from keyword stage AND from LLM-mocked stage.
- **Command:** `cd backend && uv run pytest tests/test_sketch_routing_service.py -k "action" -v`
- **Target:** keyword stage 7/7 distinct action values reachable; LLM-mocked stage 7/7. Both parametrized sets fully green.
- **Evidence:** Plan 18-01 defines `ACTION_KEYWORDS` + LLM prompt/schema for the same 7-value space.
- **Blind spots:** Keyword fixtures and mocked LLM responses are author-chosen; says nothing about real free-text accuracy (→ DEFER-18-03).
- **Validated:** false (awaits DEFER-18-01).

### P2: Routing precedence ≥0.6 ahead of SA/team — covers crit 2
- **What:** primitive action at confidence ≥ 0.6 → `target_type == 'primitive_generator'`, `target_id == kind`, ahead of SA/team; < 0.6 falls through to SA/team resolution.
- **Command:** `cd backend && uv run pytest tests/test_sketch_routing_service.py -k "route and (primitive or precedence or confidence)" -v`
- **Target:** BOTH assertions pass — (a) ≥0.6 returns primitive_generator before SA/team; (b) <0.6 falls through.
- **Evidence:** Plan 18-02 — precedence branch at top of `route()`, gated 0.6.
- **Blind spots:** Threshold tuning not validated against real distribution (→ DEFER-18-03).
- **Validated:** false.

### P3: Create path persist+bind+materialize — covers crit 3
- **What:** Per-kind create for ≥5 reachable kinds (rule/hook/command/subagent/skill) → complete draft → Phase 17 atomic `create_and_bind_and_materialize`; `create_skill` via `add_user_skill`+bind+materialize.
- **Command:** `cd backend && uv run pytest tests/test_primitive_forge_service.py -k "create" -v`
- **Target:** all reachable kinds green; each asserts persist + bind + materialize occurred (Phase 17 atomic API called); create_skill asserts `add_user_skill` path.
- **Evidence:** Plan 18-03 create path.
- **Blind spots:** Materialization correctness on disk validated in DEFER-18-01.
- **Validated:** false.

### P4: Improve path delta + ambiguity → collaborating — covers crit 4
- **What:** fuzzy-resolve hit → old→new delta patch + re-materialize; ambiguous match → status `collaborating` + clarification question returned.
- **Command:** `cd backend && uv run pytest tests/test_primitive_forge_service.py -k "improve or ambiguous or collaborating" -v`
- **Target:** BOTH green — (a) single fuzzy hit applies delta + re-materializes; (b) ambiguous returns COLLABORATING + non-empty clarification.
- **Evidence:** Plan 18-03 improve path (difflib fuzzy-resolve, ACE-style delta).
- **Blind spots:** difflib cutoff quality on real names (→ DEFER-18-03).
- **Validated:** false.

### P5: Undo restores prior state — covers crit 6 (and 3, 4)
- **What:** create-undo (unbind+delete+re-materialize) and improve-undo (revert prior content from routing_json) both restore prior state.
- **Command:** `cd backend && uv run pytest tests/test_primitive_forge_service.py -k "undo" -v`
- **Target:** BOTH green — post-undo state equals pre-action state for create and improve.
- **Evidence:** Plan 18-03 undo.
- **Validated:** false.

### P6: Frontend outcome card renders + undo button — covers crit 5
- **What:** `SketchRouting.vue` primitive outcome card renders kind, name, diff, bound-project list, and a working one-click undo button.
- **Command:** `cd frontend && npm run test:run -- SketchRouting`
- **Target:** component test green; asserts kind/name/diff/bound-projects present and undo emits `sketchApi.undoPrimitive`. No new failures (consistent with S6).
- **Evidence:** Plan 18-04.
- **Validated:** false.

### P7: 4-backend LLM model-string resolution — covers crit 6 (4-backend rule)
- **What:** classification LLM call resolves litellm model string from `provider_kind` via `_LLM_MODELS` map; `model_override` takes precedence; no claude hard-code.
- **Command:** `cd backend && uv run pytest tests/test_sketch_routing_service.py -k "model or backend or override" -v`
- **Target:** test asserts (a) each of 4 provider_kinds maps to its per-kind default; (b) `model_override` wins when set; (c) no unconditional claude default.
- **Evidence:** Plan 18-01 `_LLM_MODELS` map (4-backend rule from CLAUDE.md).
- **Validated:** false.

**Combined targeted backend run (disclose substitution for the hanging full suite):**
```
cd backend && uv run pytest \
  tests/test_sketch_routing_service.py \
  tests/test_primitive_forge_service.py \
  tests/test_leaf_crud_g.py \
  tests/test_execution_service.py tests/test_streaming.py tests/test_harness.py -v
```
**Target:** all selected green; regression suites (execution/streaming/harness) unchanged. Substitution for the full serial suite (hangs ~40-48%) MUST be disclosed in the PR.

## Level 3: Deferred Validations

### D1: Live-pipeline dogfood ≥3 sketches — DEFER-18-01 — covers crit 6 (and 1–5 end-to-end)
- **What:** ≥3 real free-text sketches through the LIVE pipeline: ≥1 create + ≥1 improve, each producing a correct outcome card with working undo.
- **How:** With backend+frontend running (`just deploy`), submit 3 real sketches via the sketch panel; verify each routes to `primitive_generator`, materializes on disk, renders the card (kind/name/diff/bound-projects), and undo restores prior state.
- **Why deferred:** Requires live backend + frontend + real LLM + disk materialization — not available in unit context.
- **Validates at:** phase-18 completion gate (human sign-off before phase marked complete).
- **Depends on:** all Tier-1 + Tier-2 green; Phase 17 atomic API live.
- **Target:** 3/3 sketches produce correct card + working undo; ≥1 create and ≥1 improve covered.
- **Risk if unmet:** classification/threshold/materialization bug invisible to mocks → budget 1 iteration phase.
- **Fallback:** capture failing sketch as a regression fixture, feed back into P1/P2.

### D2: Full (non-targeted) backend suite — DEFER-18-02 — covers crit 6
- **What:** `cd backend && uv run pytest` entire serial suite green.
- **Why deferred:** Known full-suite hang at ~40-48% (pre-existing, repo-wide).
- **Validates at:** whenever the hang is resolved repo-wide; not a Phase 18 blocker.
- **Target:** 0 new failures vs targeted set.
- **Risk if unmet:** low — targeted set covers all changed + regression suites.
- **Fallback:** targeted run (above) is the accepted substitute, disclosed in PR.

### D3: Real-LLM classification quality spot-check — DEFER-18-03 — covers crit 1, 2, 4
- **What:** With a real LLM backend (not mocked), spot-check that varied free-text sketches classify to the right `action` and confidence lands sensibly around the 0.6 gate; difflib fuzzy-resolve picks the right primitive on real names.
- **Why deferred:** Requires real LLM call + human judgment; non-deterministic, unsuitable for CI.
- **Validates at:** phase-18 completion gate, alongside D1.
- **Target:** qualitative — no systematic misclassification on the dogfood set; no obviously-wrong fuzzy resolutions.
- **Risk if unmet:** keyword/prompt or 0.6 threshold needs tuning → cheap config iteration.
- **Fallback:** adjust `ACTION_KEYWORDS` / prompt / threshold; add fixtures to P1/P2.

## Results Template

*To be filled by grd-eval-reporter after execution.*

### Sanity Results
| Check | Status | Notes |
|-------|--------|-------|
| S1 ruff | | |
| S2 just build | | |
| S3 i18n parity | | |
| S4 enum import | | |
| S5 enum surface | | |
| S6 no-new-frontend-fail | | |

### Proxy Results
| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| P1 action 7/7 ×2 | 7/7 keyword + 7/7 LLM | | |
| P2 routing precedence | both assertions | | |
| P3 create all kinds | all reachable green | | |
| P4 improve+ambiguity | both green | | |
| P5 undo | both green | | |
| P6 frontend card | green | | |
| P7 4-backend | map+override+no-hardcode | | |

### Deferred Status
| ID | Metric | Status | Validates At |
|----|--------|--------|--------------|
| DEFER-18-01 | dogfood ≥3 live | PENDING | phase-18 completion |
| DEFER-18-02 | full backend suite | PENDING | hang resolved (non-blocking) |
| DEFER-18-03 | real-LLM quality | PENDING | phase-18 completion |

## Evaluation Confidence

**Overall:** MEDIUM — appropriate for a proxy-level feature phase.

- **Sanity:** adequate — house gates + parity + enum cover the structural surface.
- **Proxy:** well-evidenced — every behavioral criterion (1–5) has a targeted test with an explicit threshold traced to a plan.
- **Deferred coverage:** the irreducible gap (real free-text classification + on-disk materialization usefulness) is honestly deferred to a gated human dogfood (D1/D3), not faked with a proxy.

**CAN tell us now:** wiring is correct on mocked LLM/in-process services — classification space, routing precedence, create/improve/undo state transitions, card rendering, 4-backend resolution.

**CANNOT tell us until D1/D3:** whether real sketches classify correctly, whether the 0.6 gate is well-tuned, whether materialized primitives are actually correct/useful on disk.

---

*Evaluation plan by: Claude (grd-eval-planner) — 2026-06-13*
