# Life-Harness Completion — Top-Level Design

**Date:** 2026-05-29
**Status:** Brainstorm output — awaiting operator review before plan-writing.
**Goal:** Take the self-improvement loop ("life-harness") from *scaffolded* to
*honestly complete* — all six stages at 100%: session capture → failure
annotation → takeaway extraction → eval'd evolution → autonomous, reversible
apply → forged, git-traceable, propagatable primitives, with the Tesserae KG
feeding back as evolution signal.

This document is the **spine**. Each phase has its own detailed design doc
(linked below). This file owns: the build order, the *unified* data-model
deltas, the cross-phase contract table, and the reconciliations that the
independent phase designs left mismatched.

---

## Phase map

| Phase | Title | Goal (done-when) | Detailed design |
|---|---|---|---|
| **A** | Complete the evidence | **(re-scoped — see Re-baseline below)** Fix the workflow emit/fetch id mismatch; *enrich* the existing `detect_h2/h3/h4` detectors with confidence/severity + typed shape; make the *already-working* LLM extractor provider-kind aware | [phaseA-evidence](2026-05-29-life-harness-phaseA-evidence-design.md) |
| **B** | Make the forge real | Applied rounds materialize primitives (incl. skills) to `.claude/` + a git commit referencing the round | [phaseB-forge](2026-05-29-life-harness-phaseB-forge-design.md) |
| **C** | Trust the changes | A patch is eval'd (static + replay) before apply; any applied round can be cleanly reverted | [phaseC-trust](2026-05-29-life-harness-phaseC-trust-design.md) |
| **D** | Close the loop | Confidence-gated autonomous apply; review-mode default, autonomy opt-in; global kill switch | [phaseD-autonomy](2026-05-29-life-harness-phaseD-autonomy-design.md) |
| **E** | Collective + self-feeding | Proven primitives propagate beyond their origin project; Tesserae KG feeds `gather_inputs()` | [phaseE-collective](2026-05-29-life-harness-phaseE-collective-design.md) |

## Re-baseline against source (2026-05-29)

The initial gap audit was a hand-wavy pass and **overstated Phase A**. Each
phase's claimed gaps were re-verified by reading the actual source. Trust this
table over the earlier audit narrative when writing plans.

| Phase | Verified verdict | Evidence (file:line) |
|---|---|---|
| **A** | 🟡 **Overstated.** Only the **workflow** scope is broken — `_fetch_workflow` queries `workflow_executions WHERE id = ?` (`harness_failure_annotator.py:220`) but the emit passes the **workflow-template** id `workflow_id` (`workflow_execution_service.py:666` → `execution_events.py:122`), whereas `workflow_executions.id` is the **execution-row** id — so both the `wf_row` and `nodes` lookups return empty (independently confirmed by Codex). The fix must pass/resolve the execution-row id, not the template id. `_fetch_team_session` is **correct** (`:244`). `detect_h2/detect_h3/detect_h4` **already exist and run** (`:408/:435/:463`, orchestrated by `_apply_priority_protocol:526`) — they are keyword-based and lack confidence/severity, so Gap 2 is *enrichment*, not from-scratch. The LLM extractor is **wired and ON by default** (`harness_takeaway_extractor.py:445`, `_extract_llm:535` → `_run_codex_for_extraction:483`) — it is **codex-only**, so Gap 3 is *provider-kind generalization*, not "wire the skeleton." |
| **B** | 🟢 **Accurate.** `apply_patch` performs **no** git commit and **no** `.claude` materialization (DB-only). `WRITABLE_KINDS = ("rule","hook","command","mcp_server")` excludes `skill` (`harness_evolver.py:64`); `validate_patch` flags skill ops unsupported. A read-only workspace projection already exists (`build_workspace:516`, `_run_codex_in_workspace:726`) and should be reused by `materialize_primitives`. |
| **C** | 🟢 **Accurate.** Only `validate_patch` (shape-check, `harness_evolver.py:858`) runs pre-apply — no eval/replay/regression. `harness_evolution.py` has `mark_running/applied/awaiting_approval/failed/aborted` but **no** `mark_reverted`/revert; routes have no revert endpoint. |
| **D** | 🟢 **Substantively accurate** (audit phrasing corrected). A live-apply path exists (`run_evolution_round(dry_run=False)` → `mark_applied:1146`, exposed at `/evolution/apply`), but it is operator-*initiated*. There is **no autonomous self-trigger** (nothing fires `dry_run=False` on session-complete/schedule) and **no autonomy config** (`AGENTED_AUTONOMY`/`autonomy_mode`/`auto_evolve` absent from the codebase). |
| **E** | 🟢 **Accurate.** `list_bindings(project_id, enabled_only)` is strictly per-project (`project_forge_bindings.py:40`); no promote/shared/global scope in the bindings layer. `gather_inputs` pulls **no** KG signal; Tesserae is used only to write a prose `tesserae_context.md` inside `build_workspace` (`harness_evolver.py:570-587`), not as structured evolution input. **Verified:** rules/hooks/commands already support a `project_id IS NULL` global scope (`rules.py:113`, `hooks.py:99`, `commands.py:109` — `WHERE project_id = ? OR project_id IS NULL`), so Phase E's shared-layer assumption holds for those three. **Nuance:** `mcp_servers` scopes via a `project_mcp_servers` junction table (`mcp_servers.py:208`), not a nullable `project_id` — Phase E propagation needs a separate path for mcp_servers. |

**Net effect on planning:** Phase A shrinks to roughly 40% of its billed size and changes character (fix + enrich + generalize, not build-from-scratch). Phases B–E are confirmed; their design docs are sound to plan against. The Codex-generated Phase A *plan* was discarded — it hallucinated file/function names (`execution_events.py::_fetch_workflow_execution`, `build_session_evidence`, `_merge_dedup`) that don't exist; plans will be authored directly against the verified symbols above.

## Build order & dependency DAG

```
A (evidence) ─────────────┐
                          ├──► C (eval + rollback) ──► D (autonomy) ──► E (collective + KG-feedback)
B (forge durability) ─────┘
```

- **A and B are independent** and can run in parallel (different services:
  annotator/extractor vs. evolver/forge materialization).
- **C depends on B** — the eval gate materializes the proposed primitives into a
  sandbox using B's `materialize_primitives`, and rollback reverts B's git commit.
- **C depends on A** in spirit — replay regression checks against classified
  incidents are only meaningful once classification (A·Gap2) produces typed
  incidents. C still functions without A, but with weaker signal.
- **D depends on C** — autonomy gates on C's eval verdict and is only safe given
  C's revert.
- **E depends on B + C** — promotion uses C's eval score as evidence and B's
  binding model as the runtime surface.

Recommended sequence: **A ∥ B → C → D → E**.

---

## Unified data-model deltas (coordination-critical)

Four phases ALTER `harness_evolution_rounds`. The columns are additive and
non-conflicting, but the **fresh-schema definition**
(`backend/app/db/schema/_harness_evolution.py`) must include all of them, and
migrations must be ordered B → C → D → E. Consolidated list:

| Column | Phase | Purpose |
|---|---|---|
| `materialization_result_json TEXT` | B | files written per apply |
| `git_commit_sha TEXT` | B | provenance + revert anchor |
| eval columns (`eval_verdict_json`, `eval_status`, `eval_score REAL`, …) | C | eval gate result |
| `apply_journal_json TEXT` (before/after images + binding snapshot) | C | enables transactional revert |
| `auto_applied INTEGER DEFAULT 0`, `auto_apply_reason TEXT`, `auto_apply_blocked_reason TEXT` | D | autonomy audit trail |
| `input_kg_signals_json TEXT` | E | KG-derived signal used this round |

New tables:

| Table | Phase | Purpose |
|---|---|---|
| `project_autonomy_config` | D | per-project autonomy policy (indexed `enabled`) |
| `shared_forge_bindings` | E | org-layer promoted-primitive catalogue |
| `project_shared_forge_adoptions` | E | which projects adopted which shared primitive |
| `forge_promotion_evidence` *(or reuse `harness_kg_signals` sibling)* | E | accumulating eval evidence toward promotion |
| `harness_kg_signals` | E | typed KG signal rows for audit/dedup |

New columns on existing tables: `project_forge_bindings.{source_scope,
source_shared_binding_id, conflict_policy, fingerprint}` (E);
`user_skills.content TEXT` (B, for skill body materialization).

**New round states** (C): `evaluating`, `eval_failed`, `reverted` — extend the
existing `pending/running/applied/awaiting_approval/failed/aborted` machine.

---

## Cross-phase contract table

| Contract | Produced by | Consumed by | Canonical shape |
|---|---|---|---|
| `materialize_primitives` | B | C | **see reconciliation #1** |
| `MaterializationResult` | B | C | `@dataclass` with per-file write results |
| `EvalVerdict` | C | D, E | Pydantic v2 in `backend/app/models/harness_evolution.py` — **see reconciliation #2** |
| `eval_score: float` | C | E (promotion evidence) | numeric on the round, surfaced from verdict |
| `revert_round(round_id)` | C | D (one-click revert UX) | `RevertResult` |
| typed incident `{layer, kind, event_index, evidence}` | A | C (replay targets) | from `harness_failure_annotator` |
| `project_forge_bindings` model | B | E (runtime surface) | unchanged binding repo |
| backend-agnostic LLM call `{backend_kind, model_override?}` | A, C | — | **see reconciliation #3** |

---

## Reconciliations — mismatches the independent phase designs left open

These were caught by reading the five docs together. **They must be resolved
before plan-writing**; otherwise the phases will not compose.

### #1 — `materialize_primitives` signature drift (B vs C)

- **Phase B** defines the low-level contract:
  `materialize_primitives(project, kinds, workspace_path) -> MaterializationResult`
  (resolves currently-bound primitives, writes `.claude/`, **no git**).
- **Phase C** *calls* it as `materialize_primitives(round_id, workspace_dir)`.

These don't match. **Resolution (recommended):** keep B's three-arg function as
the core, and add a thin **round-aware wrapper** in B:
`materialize_round(round_id, workspace_dir) -> MaterializationResult` that
resolves `project` + `kinds` from the round's `applied`/proposed entries, then
calls the core. Phase C consumes the wrapper; the apply-commit path and the
eval sandbox both go through it. One materialization code path, two entry points.

### #2 — `EvalVerdict` defined in two modules (C vs D)

- **Phase C** puts `EvalVerdict` (+ `CheckResult`, `ReplaySample`,
  `RevertResult`) in `backend/app/models/harness_evolution.py`.
- **Phase D** lists `EvalVerdict` again inside a new `autonomy_policy.py`.

**Resolution:** single source of truth — `EvalVerdict` lives in
`backend/app/models/harness_evolution.py` (C). Phase D's `autonomy_policy.py`
**imports** it and defines only `AutonomyPolicy` + decision/audit models.

### #3 — `backend_kind` taxonomy: provider vs harness — **DECIDED: provider-kind**

This is the one genuinely architectural call, and it surfaced because two phases
chose different vocabularies for the same project rule ("LLM features accept
`{backend_kind, model_override?}`, support all 4 backends, never claude-only"):

- **Phase A** keyed defaults by **harness kind** — `claude` / `codex` / `gemini`
  / `opencode` (reusing `goal_judge_service.py:_build_llm_command()`'s CLI-oriented
  routing).
- **Phase C** insists the *public* eval contract use **provider kind** —
  `anthropic` / `openai` / `gemini` / `ollama` — with a compatibility layer
  mapping to the CLI harness names internally.

Both satisfy "support 4 backends," but the loop will be inconsistent if A and C
disagree on what `backend_kind` *means*. We need one canonical taxonomy for all
LLM-calling features (annotator-adjacent, takeaway LLM, eval judge), plus a
single mapping layer to CLI/harness invocation.

> **DECIDED (operator-approved 2026-05-29):** canonical = **provider kind**
> (`anthropic/openai/gemini/ollama`), with one internal `provider→harness-CLI`
> map. Provider names are stable, match the existing per-kind-default-model
> memory rule, and don't conflate "which CLI binary" with "which model family."
> Phase A adopts provider keys and reuses C's mapping layer rather than the
> reverse. The mapping layer (`provider → CLI harness name`) is owned by Phase C
> (`harness_evolution_eval.py`) and imported by Phase A's takeaway-LLM path.

### #4 — coordinated migrations

All four `harness_evolution_rounds` migrations and the fresh-schema definition
must land in dependency order (B→C→D→E) with a single consolidated fresh-schema.
Not a conflict, but an execution-ordering constraint for plan-writing.

---

## Verification strategy (per phase, summary)

- **A:** unit tests for the two scope fetchers (correct WHERE/join), per-layer
  classification detector tests with fixture transcripts, LLM-path tests with a
  mocked provider asserting backend-agnostic routing + heuristic/LLM dedup merge.
- **B:** `materialize_primitives` temp-dir tests (incl. skill layout + delete
  manifest), git-commit-scope tests (only Agented-owned paths staged), non-git
  project fallback.
- **C:** eval-gate state-transition tests (`evaluating`/`eval_failed`), static
  + replay check tests, `revert_round` transactional reversal + git-revert +
  non-`applied`-state rejection + same-asset-later-round conflict detection.
- **D:** `AutonomyPolicy` bounds, decision-logic gating (eval-fail blocks,
  blast-radius blocks, cooldown), kill-switch (`AGENTED_AUTONOMY=0`), audit-field
  population, UX badges + after-the-fact revert.
- **E:** promotion-threshold scoring with decay, conflict resolution
  (local-wins + override), HarnessSync export block, KG-signal ingestion with
  stale-graph no-op + dedup-vs-forged + weight bounding.

All three project gates apply at each phase merge: `just build`,
`cd backend && uv run pytest`, `cd frontend && npm run test:run`.

---

## Out of scope (explicitly)

- Personal-life-admin / business-vertical product surface (the earlier
  misread) — not part of life-harness.
- Materializing **MCP servers** as runnable processes (only their config rows
  are forged today; runtime lifecycle is unchanged).
- Multi-tenant org model beyond the single shared/global scope E introduces.
