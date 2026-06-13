# Integrating SkillOpt's Text-Space Skill Optimization into Agented

> **Research report — scope:** the *text-space skill-optimization* engine (the
> "night loop" Rollout → Reflect → Aggregate → Select → Update → Gate) only.
> This is a cited analysis + phased plan for engineers about to implement, **not**
> code.
> **Method:** concept-map of SkillOpt's stages → Agented's actual surfaces →
> **one adversarial verifier per proposal checked against Agented's source at
> `file:line`.** Every citation below was confirmed by that pass unless flagged.
> **Verification result:** 3 proposals — **0 founded-clean, 2 needs-adjustment,
> 1 unfounded.** Corrections are folded into the needs-adjustment proposals; the
> unfounded one is recorded with its refutation so nobody rebuilds it.

---

## 1. What SkillOpt is, and the "night" loop

**SkillOpt** (Microsoft; arXiv:2605.23904, internally "ReflACT") treats a single
**skill document as the trainable external state of a frozen agent** — its
"prompt weights." The model is never fine-tuned; only the *text* of the skill
document is optimized, with weight-space discipline (a held-out gate, a bounded
"learning rate," a scheduler). The headline claim: *first systematic controllable
text-space optimizer for agent skills, with zero inference-time model calls at
deployment.*

The optimizer runs a **6-stage loop per step**, and a slow-update + meta-skill
pass at each epoch boundary:

1. **Rollout** — run the frozen agent on a fixed train/val task pool, collect
   trajectories.
2. **Reflect** — a *separate, strong* optimizer reads the **failed** trajectories
   and emits structured edit patches (`op`/`target`/`content`: add / replace /
   delete).
3. **Aggregate** — pool candidate edits across rollouts.
4. **Select** — `rank_and_select(max_edits=edit_budget)` keeps only the top
   edits, bounded by the **edit budget** (the *textual learning rate*; default
   `learning_rate=4`, `min=2`, cosine scheduler — the grad-clip analogue).
5. **Update** — apply the selected patches to the skill document (`apply_patch_with_report`) — the SGD step.
6. **Gate** — accept the candidate **only if it strictly beats the current best
   on a held-out selection split** (`if cand > current: accept; if > best:
   accept_new_best; else reject`, keep current). **The held-out split is never
   optimized against, and the optimizer never grades itself.**

The two load-bearing invariants for any port are (a) the **strict-improvement,
self-grading-forbidden gate on a held-out split**, and (b) the **bounded edit
budget**. Everything else (RL reward shaping, the labeled task pool, the
scheduler math) is convenience around those two.

---

## 2. The central mismatch — does-port / does-NOT-port

Agented is **not** a training system. It drives **opaque external harness CLIs**
(claude / codex / gemini) via `subprocess.Popen` and sees only their output; it
fine-tunes nothing and ships no held-out labeled dataset. SkillOpt's *frozen
agent + writable skill text* maps cleanly onto Agented's *opaque subprocess +
its `SKILL.md` on disk* — but three of SkillOpt's six stages have **no faithful
analogue** and must be either re-grounded or dropped.

| SkillOpt element | Ports? | Why / how |
|---|---|---|
| Skill doc = external "prompt weights" of a frozen agent | **Yes (clean)** | The frozen agent is the opaque claude/codex subprocess; `.claude/skills/<name>/SKILL.md` (rendered by `_render_skill_md`, written by `_create_skill`/`_update_skill`, `harness_evolver.py:1460/1517`) is its only writable text-space state. `WRITABLE_KINDS` already includes `"skill"` (`harness_evolver.py:67`). |
| Reflect → structured edit patches (`op`/`target`/`content`) | **Yes (strong)** | The codex-exec edit path already emits `PatchEntry(op,kind,name,payload)` where `op ∈ {create,update,delete}` (`harness_evolver.py:279`) = SkillOpt's add/replace/delete. Reuse verbatim, scoped to `kind=='skill'`. |
| Update → apply patch to skill doc (SGD step) | **Yes (strong)** | `_update_skill`/`_create_skill` already do the atomic, 04.H5-contained write; `WRITABLE_KINDS` and `_FIELD_MAP["skill"]` already wire it. The write side exists and is security-hardened. |
| Gate = strict improvement, optimizer never self-grades | **Partly** | The *shape* ports onto the AnswerEval blind judge + `_eval_gate` fail-closed wrapper. But the **held-out** property is only *approximated* (see §3, P1). |
| Edit budget (textual learning rate, bounded edits/step) | **Partly** | Nearest home is `AutonomyPolicy.max_ops_per_round` (default 5). But Agented's gate is an **all-or-nothing whole-round veto**, not a `rank_and_select` top-N (see P3). No first-class ranker exists. |
| Rollout on a fixed labeled train/val task pool | **No (re-ground)** | Agented has **no labeled task pool**. "Rollout" becomes *harvest already-recorded real trajectories* (`harness_evidence` ledger, execution logs/transcripts, evolver `gather_inputs`, age-decayed `harness_kg_signals`). This is the single biggest divergence — there is nothing to re-roll. |
| RL training / reward model / SFT | **No** | Agented trains no model. There is no policy to optimize, no reward to shape. Only the *text-space optimization architecture* transfers. |
| Held-out VAL split that is "never optimized against" | **No (build a proxy)** | `build_question_set` is `sorted(set(...))[:n]` over **all** telemetry (`answer_eval_service.py:103`); there is no seed/partition param and no disjoint split today. The honest port is a `corpus_health`-gated, run-disjoint, seed-partitioned question set — a *proxy*, not a frozen labeled VAL set. |
| Scheduler (cosine/linear lr), epoch boundary, meta-skill, slow-update | **No (defer)** | Convenience around a budget Agented doesn't yet need to anneal. Ship a constant edit budget first; revisit only if churn data justifies it. |
| Zero inference-time model calls at deploy | **N/A** | SkillOpt's deploy guarantee is irrelevant — Agented's skills are consumed by the opaque CLI at run time regardless. |

---

## 3. Concept map (SkillOpt → Agented)

| SkillOpt concept | Agented surface (verified) | Notes |
|---|---|---|
| Skill document = trainable external state ("prompt weights") of a frozen agent | `.claude/skills/<name>/SKILL.md` on disk + the `user_skills` row (`skill_path`, metadata) that points at it; rendered by `_render_skill_md`, written by `_create_skill`/`_update_skill` (`harness_evolver.py:1460/1517`). The `SKILL.md` body IS the externalized, optimizable text. | Clean port. The frozen agent is the opaque claude/codex subprocess; `SKILL.md` is its only writable text-space state. No weight access exists or is needed. |
| Rollout — run the frozen agent on tasks, collect trajectories | **Existing execution telemetry, NOT a fresh benchmark harness:** `harness_evidence.record_tool_use` ledger (`harness_evidence.py:16`), execution logs/transcripts, evolver `gather_inputs` (`harness_evolver.py` ~485–503), age-decayed Tesserae signals (`harness_kg_signals.py:104–168`). | **Partial.** SkillOpt re-rolls on a fixed task pool every step; Agented has **no labeled pool**, so "rollout" = harvest already-recorded real trajectories. Biggest divergence — call it out honestly. |
| Reflect — strong optimizer reads failed trajectories, emits structured edit patches | codex-exec edit path: `codex exec` (`harness_evolver.py:841–892`) over a scratch workspace, `parse_patch` (`:957`), `validate_patch`→`_validate_payload` (`:1049–1094`), producing `EvolutionPatch`/`PatchEntry(op,kind,name,payload)`. For skills: `_create_skill` (`:1460`) / `_update_skill` (`:1517`). | **Strong port.** `PatchEntry.op` already encodes create/update/delete = add/replace/delete. Reuse verbatim, scoped to `kind=='skill'`. |
| Aggregate + Select (`rank_and_select`, bounded by edit budget) | No first-class ranker today; nearest is `validate_patch` + `AutonomyPolicy.max_ops_per_round` cap (`autonomy_policy.py:11`, default 5) + `confidence_threshold` (0.85). Selection currently = "all valid entries that clear the gate." | Needs a small new ranker. `max_ops_per_round` is the natural home for the edit-budget cap (see P3). |
| Update — apply selected patches to the skill doc (SGD step) | `_update_skill`/`_create_skill` write the new `SKILL.md` via atomic write with 04.H5 containment (`_assert_within_skills:1472`, `_skill_write_allowed:1541`); `update_user_skill` keeps `skill_path`/`description` in sync. | **Strong port.** Write side already exists and is security-hardened. `WRITABLE_KINDS` already includes `"skill"` (`:67`) despite the stale docstring at `:16–18`. |
| Gate — accept only if candidate strictly beats current on held-out; optimizer never self-grades; else reject | Reuse the `AnswerEvalService` blind baseline-vs-pipeline judge (`answer_eval_service.py:191`, `_run_eval_body:251`): judge prompt **never names which arm is which** (enforced; `test_run_eval_blind_judge_prompt_contains_no_arm_names`). Gate logic wraps `_eval_gate` (`harness_evolver.py:1649`), which already **fails CLOSED** on infra error. | **Best-fit port.** SkillOpt's `cand>current` → `arm-B mean > arm-A mean` on groundedness/sufficiency/quality. The "never optimized against" property is *approximated* by `corpus_health`-gated, run-disjoint question sets (see P1 honest limits). |
| Held-out selection split / VAL set never optimized against | `build_question_set` (`answer_eval_service.py:103`) deterministically samples project questions from kg_signals / execution prompts / takeaways; `corpus_health` (`answer_pipeline_service.py:193`, gate `AGENTED_RAG_MIN_CORPUS` default 8). **No seed/partition param today** — `sorted(set(...))[:n]` over all telemetry. | **Proxy only.** Must *build* the disjoint partition; until then, questions overlap the telemetry the edit derived from — document this. |
| Edit budget = textual learning rate (max edits/step, grad-clip analogue) | `AutonomyPolicy.max_ops_per_round` (default 5, `autonomy_policy.py:11`). | Constant budget first; defer the cosine scheduler / epoch-boundary meta-skill. |

---

## 4. Integration proposals (verified & corrected)

Status legend: **✅ Adopt** (founded — implement as written) · **⚠ Adjust**
(idea sound, claims corrected — fold in the corrections) · **⛔ Refuted as
written** (recorded so it is not rebuilt).

### P1 · Skill-Sleep gate — reuse the AnswerEval blind judge to score current vs candidate `SKILL.md` — ⚠ Adjust → ✅ after re-anchoring

**SkillOpt origin:** Gate = strict improvement on held-out split; optimizer never
self-grades (`gate.py evaluate_gate`, `consolidate.py _gate_apply`).

**Idea:** Add a `SkillSleepGate` that runs the **same blind judge** as
`AnswerEvalService`, but binds **arm A = the agent answering with the CURRENT
skill body** and **arm B = the agent answering with the CANDIDATE skill body**,
over a `corpus_health`-gated, deterministic question set drawn from this
project's kg_signals / execution_logs / takeaways. Accept the candidate **only
if arm B's mean strictly beats arm A's** across the judge's three axes
(groundedness / sufficiency / quality) — mirroring SkillOpt `cand>current`. The
judge prompt continues to **never name which arm is which** (reuse the
blind-prompt construction verbatim). **Fail CLOSED** exactly like `_eval_gate`
(`harness_evolver.py:1649`): any judge/infra error → reject, keep current skill,
no auto-apply. **ABSTAIN (treat as reject)** when `corpus_health` is unhealthy
(< `AGENTED_RAG_MIN_CORPUS`), because without a real corpus the "held-out" proxy
is meaningless.

**Verification: every cited surface exists with the claimed shape.** The blind
judge (`run_eval`/`_run_eval_body` at `answer_eval_service.py:191/251`) genuinely
never names the arm and scores the three axes; `build_question_set`
(`:103–188`) draws deterministically from kg_signals/execution_logs/takeaways;
`corpus_health` + `AGENTED_RAG_MIN_CORPUS` (default 8) exist at
`answer_pipeline_service.py:193`; the fail-closed gate is exactly at
`harness_evolver.py:1649` (infra error → `EvalVerdict(passed=False)` → no
auto-apply); `evaluate_patch`/`_verdict` at `harness_evolution_eval.py:173/154`.
Skill bodies are **real, not placeholders** — materialized with asset content
(`forge_materialization_service.py:209`) and writable through evolution. The
opaque-subprocess blocker does **not** apply here: the eval runs **in-process**
via `llm_call`/`pipeline_llm_call`, never `subprocess.Popen`, so nothing needs
pausing.

**Corrections to fold in (load-bearing):**

1. **Do NOT claim `_run_eval_body`'s arms are reused as-is.** Its arms are
   hardcoded **A = plain-LLM, B = `gather_context` RAG-pipeline**
   (`answer_eval_service.py:268–345`), with **no seam to inject an arbitrary
   skill body** as the differentiator. The skill-body arm binding (A = current
   body, B = candidate body) is **net-new code** in a new `skill_sleep_service.py`
   that reuses **only** the judge prompt (`_build_judge_prompt`) + parser — not
   `run_eval`'s arm machinery.
2. **The disjoint train/eval partition must be built**, not described as
   existing. Add a `seed`/`partition` param to `build_question_set`. Until then,
   keep the honest-limit framing: questions overlap the telemetry the skill edit
   was derived from.
3. **Reconcile persistence:** prefer reusing `answer_eval_runs` /
   `answer_eval_results` (`schema/_answer_eval.py:14/37`; `db/answer_eval.py`) —
   **no new table**. If a dedicated `skill_sleep_verdicts` table is added
   instead, it MUST be registered in **both** `create_fresh_schema`
   (`schema/__init__.py:84` is where `create_answer_eval_tables` sits) **and**
   `V07_MIGRATIONS` (`v07_features.py:1219`).
4. **Minor:** reconcile the stale `harness_evolver.py:16–18` docstring (says
   skills are deferred/read-only) — it contradicts the writable skill paths the
   gate depends on.

**Files touched:** `backend/app/services/skill_sleep_service.py` (new),
`backend/app/services/answer_eval_service.py` (add `seed`/partition + a reusable
judge-arm builder), `backend/app/services/harness_evolver.py`,
`backend/tests/test_skill_sleep_gate.py`.

### P2 · Candidate isolation — render the candidate `SKILL.md` into a scratch workspace, never overwrite live before the gate passes — ⛔ Refuted as written

**SkillOpt origin:** Update stage is gated — apply patches only after the gate
accepts; the held-out skill file is never mutated speculatively.

**Idea (as proposed):** Make `_update_skill` render the candidate body to
`scratch/eval/skills/<name>/SKILL.md` and gate against the scratch copy while the
live file is untouched; reuse `evaluate_patch`'s materialize-into-workspace flow
so `_static_checks` validates frontmatter before any judge call; only on accept
call `_update_skill`/`_create_skill`.

**Refutation (multiple load-bearing assumptions fail against the codebase):**

1. **The primary file `skill_sleep_service.py` does not exist** and there are
   **zero `skill_sleep` references** anywhere in `backend/`. "Skill Sleep" is an
   invented surface; the only analogous service is `harness_evolver`.
2. **The goal is already the actual behavior, by a different design.**
   `_eval_gate` (`harness_evolver.py:1649`) materializes into a scratch eval
   workspace `scratch/eval` and runs `evaluate_patch` **there**; the live write
   (`_update_skill`/`_create_skill`) only fires inside `apply_patch` (called
   ~`:1831`) **after** the gate passes. `_update_skill` is **never called
   speculatively** — "stop writing speculatively" fixes a non-problem.
3. **The mechanism is structurally impossible as written.**
   `materialize_primitives` for `kind=="skill"`
   (`forge_materialization_service.py:365–369`) **deliberately does not write the
   SKILL.md body** to the workspace ("Body lives on disk… Don't rewrite from the
   DB"; only `rel_path` is recorded for the manifest). So `_static_checks`
   (`harness_evolution_eval.py:33–70`) **never finds a materialized candidate
   `SKILL.md`**, and the frontmatter open/close check the proposal hinges on
   never runs for skills.
4. **The round loop produces no skill candidate body to gate.** `parse_patch`
   (`:957`) states skills are "read-only in the workspace" and are **not diffed**
   for create/update — confirmed in its docstring.
5. **No held-out/labeled dataset exists.** `evaluate_patch` is a
   confidence-weighted blend of mechanical static checks + LLM-judge replay
   (`_verdict`, `harness_evolution_eval.py:154–170`) over incidents drawn from
   the **same input-window trajectories** that motivated the patch — no
   train/eval split, no labels, no held-out accuracy.

**If the real intent (structurally validate a candidate body before the judge
runs) is still wanted:** the actual blocker must be fixed first — either change
`materialize_primitives` / `parse_patch` to render the candidate body into
`scratch/eval/skills/<name>/SKILL.md` so `_static_checks` can see it, **or** have
P1's `skill_sleep_service` render the body itself before scoring. Otherwise this
proposal adds nothing: candidate isolation (scratch eval + post-gate apply) is
already met, so **record it as redundant and do not implement it as a separate
PR.** The structural-validation fix folds into P1's body-injection seam instead.

### P3 · Edit-budget ranker — `rank_and_select` bounded by `max_ops_per_round` — ⚠ Adjust (mechanism corrected)

**SkillOpt origin:** Textual learning rate = edit budget (max edits/step;
`rank_and_select(max_edits=edit_budget)`); the optimizer keeps only the top-N
edits per step.

**Idea:** Cap the number of skill edits applied per Skill-Sleep step using
`AutonomyPolicy.max_ops_per_round`, ranking candidate patches and keeping only
the top-N within budget — SkillOpt's `arr[:edit_budget]` (default 4).

**Verification — surfaces confirmed:** `AutonomyPolicy` exists with
`max_ops_per_round` (default 5) and `confidence_threshold` (default 0.85) at
`autonomy_policy.py:11/10`. `get_policy`/`upsert_policy` at
`project_autonomy_config.py:11/25`. The policy persists as a **single
`policy_json TEXT` blob** (`schema/_project_autonomy.py:12`) — so adding a
`skill_edit_budget` field needs **NO migration** (the dual-registration trap does
not apply). Skills **are** auto-evolvable: `WRITABLE_KINDS` includes `"skill"`
(`:67`), `validate_patch` accepts it. The header docstring (`:16–18`) calling
skills "deferred / unsupported" is **stale**.

**Corrections to fold in (load-bearing):**

1. **The current gate is NOT a rank-and-keep-top-N; it is an all-or-nothing
   whole-round veto.** `harness_autonomy.py:85` computes
   `blast_ok = len(entries) <= policy.max_ops_per_round` as one **boolean** gate,
   and `:138` sets `eligible = all(g.passed for g in gates)`. **Exceeding the cap
   rejects the entire round** — it does not trim to the top-N. To get SkillOpt's
   `arr[:edit_budget]` behavior you must add an actual ranker that *selects* a
   bounded subset **before** the veto runs, then re-evaluate the trimmed set —
   net-new code, not a config tweak.
2. The eval **cannot supply a per-edit ranking signal today**: `evaluate_patch`
   scores the **whole patch**, not individual entries. A ranker needs a per-entry
   score (e.g. per-entry replay confidence, or the judge run per single-edit
   candidate) — design this signal explicitly; it does not exist yet.
3. Add `skill_edit_budget` to the existing `policy_json` blob (no migration).
   Default to SkillOpt's `4`; keep the existing `max_ops_per_round` veto as the
   hard ceiling above the ranker.

**Files touched:** `backend/app/models/autonomy_policy.py` (add
`skill_edit_budget`), `backend/app/services/harness_autonomy.py` (insert ranker
before the veto), `backend/app/services/skill_sleep_service.py` (per-entry
scoring), `backend/tests/test_skill_edit_budget.py`.

---

## 5. What does **not** port

| Element | Why not |
|---|---|
| RL training inside the loop / reward model / reward shaping | Agented trains no models; there is no policy to optimize and no reward to shape. Only the text-space optimization architecture transfers. |
| Fixed labeled train/val **task pool** + re-rolling the agent each step | Agented has no labeled task pool. "Rollout" degrades to harvesting already-recorded real trajectories (`harness_evidence`, execution logs, kg_signals). |
| A frozen labeled **VAL split** never optimized against | No disjoint held-out dataset exists; `build_question_set` samples all telemetry. The port is a `corpus_health`-gated, seed-partitioned **proxy** — the guarantee is approximate. |
| lr scheduler (cosine/linear/constant), `num_epochs`, epoch-boundary slow-update + meta-skill | Convenience around annealing a budget Agented doesn't yet need. Ship a constant edit budget; revisit only if churn data justifies it. |
| "Zero inference-time model calls at deploy" guarantee | Irrelevant — Agented's skills are consumed by the opaque CLI at run time regardless. |
| `apply_patch_with_report` / SkillOpt-specific patch format | Agented already has `EvolutionPatch`/`PatchEntry` + `apply_patch`. Reuse Agented's, scoped to `kind=='skill'`. |

---

## 6. Phased plan (each phase = one PR)

| Phase | Goal | Proposals | Exit criteria |
|---|---|---|---|
| **1 — Held-out proxy + persistence** | Make a seed-partitioned, run-disjoint question set and decide the verdict store. | P1(partition) | `build_question_set` accepts a `seed`/`partition` param and returns disjoint train/eval halves deterministically; persistence target chosen — **reuse `answer_eval_runs`/`answer_eval_results`** (no new table) OR, if a `skill_sleep_verdicts` table is added, it is registered in **BOTH** `create_fresh_schema` (`schema/__init__.py`) **AND** `V07_MIGRATIONS` (`v07_features.py:1219`), with a `test_fresh_schema_has_*` test mirroring `test_answer_eval_repo.py`. Stale `harness_evolver.py:16–18` docstring corrected. |
| **2 — Skill-Sleep gate service** | The validation gate: blind judge scoring current vs candidate `SKILL.md`, reusing AnswerEval's judge prompt + `corpus_health`. | P1(gate) | New `skill_sleep_service.py` builds arm A = current body / arm B = candidate body by prepending each `SKILL.md` to the answer context, calls `_build_judge_prompt` **verbatim** (arm never named), accepts only if arm-B mean strictly beats arm-A across groundedness/sufficiency/quality. **Fails CLOSED** on judge/infra error and **ABSTAINS→reject** when `corpus_health` < `AGENTED_RAG_MIN_CORPUS`. Folds in P2's structural fix: render the candidate body to `scratch/eval/skills/<name>/SKILL.md` so `_static_checks` validates frontmatter before spending judge calls. Tests: blind-prompt has no arm names; infra error → reject; unhealthy corpus → abstain. |
| **3 — Edit-budget ranker** | Bound edits per step (SkillOpt's textual learning rate), ranking before the veto. | P3 | `skill_edit_budget` added to the `policy_json` blob (no migration), default 4; a ranker selects a bounded top-N **before** `harness_autonomy.py:85`'s `blast_ok` veto, using a per-entry score (not the whole-patch score); the existing `max_ops_per_round` veto remains the hard ceiling. Test: a 7-edit candidate is trimmed to budget and gated, not whole-round-rejected. |
| **4 — Staging / operator-adopt surface** | Surface gated candidates for operator review before any live write. | P1 + existing evolution UI | Accepted candidates land in `awaiting_approval` (reuse the evolution round status + `harness-evolution.ts` API), showing arm-A/arm-B judge scores and the diff; operator adopt triggers the existing `apply_patch` → `_update_skill`/`_create_skill` write (04.H5 containment intact). No live `SKILL.md` is overwritten before adopt. |
| **5 — Nightly / session-end trigger** | Run Skill-Sleep on a cadence, not interactively. | P1 + scheduler | A periodic job (mirroring the autonomy/evolution dispatchers in `lifecycle.py`) runs Skill-Sleep for projects with enabled autonomy at session-end or nightly, respecting `cooldown_seconds` / `rate_limit_per_day`. Skips projects whose `corpus_health` is unhealthy. |
| **6 — Outcome eval (does optimization actually help?)** | Measure whether optimized skills improve a *measured* outcome, not just the gate's self-score. | P1 + answer-eval harness | A before/after eval runs the existing AnswerEval baseline-vs-pipeline (or a task-success proxy) on a **held-out** question partition disjoint from the one the gate used, comparing pre-optimization vs post-optimization skill bodies. Report the delta (groundedness/sufficiency/quality). **If the delta is not positive on the disjoint split, the optimization is not shipped** — this is the honest check that the gate isn't gaming itself. |

---

## 7. Honest open risks

1. **The held-out split is a proxy, not a guarantee.** Questions are sampled from
   the same telemetry the skill edit derived from; even with seed-partitioning,
   the train and eval halves share a distribution. SkillOpt's "never optimized
   against" property is **approximated**, not achieved. Phase 6's disjoint-split
   outcome eval is the only real defense against the gate gaming itself.
2. **No labeled task pool means "rollout" is retrospective.** Agented cannot
   re-roll the agent on a fixed benchmark; it can only mine past real
   trajectories. Coverage is whatever the project happened to run — sparse,
   biased toward recent activity, and impossible to re-balance.
3. **The judge is itself an LLM.** Both arms are scored by an LLM judge with no
   ground truth. A systematically biased judge (e.g. preferring longer skill
   bodies) would pass bad edits. Blind-arm prompting mitigates *position* bias,
   not *content* bias.
4. **Per-edit ranking signal does not exist yet (P3).** `evaluate_patch` scores
   the whole patch; ranking individual edits requires a new per-entry score
   (per-entry replay or single-edit judge runs), which multiplies judge cost.
5. **Corpus-health abstain means most projects never optimize.**
   `AGENTED_RAG_MIN_CORPUS` (default 8) is a conservative floor; small/new
   projects will sit below it and Skill-Sleep will correctly abstain — so the
   feature only activates for mature projects, limiting its reach.
6. **Cost.** Each gate step is ≥ 2 arms × N questions × judge calls, on top of
   the codex-exec Reflect pass. A nightly cadence across many projects can be
   expensive; budget it like any other LLM job (the live budget killer covers
   subprocess runs, not in-process judge calls).
7. **Stale docstring is load-bearing for trust.** `harness_evolver.py:16–18`
   still says skills are deferred/read-only while the code writes them. Until
   corrected, a future reader may "fix" the writable paths to match the comment
   and silently break the gate's apply step.

---

## Appendix · Verification ledger

| Proposal | Verdict (as written) | Disposition | Core correction / refutation |
|---|---|---|---|
| **P1 — Skill-Sleep blind-judge gate** | needs-adjustment | **Adopted with corrections** | Surfaces real, but overstates reuse: `_run_eval_body` arms are hardcoded plain-LLM vs RAG-pipeline with no skill-body seam (net-new arm builder needed); no seed/held-out partition exists (must build it); reconcile persistence to `answer_eval_runs` or dual-register a new table; fix stale `:16–18` docstring. |
| **P2 — Candidate scratch isolation** | unfounded | **Recorded, not implemented** | Invented `skill_sleep_service.py`; candidate isolation is already met (`scratch/eval` + post-gate `apply_patch`); `materialize_primitives` deliberately skips the skill body (`:365–369`) and `parse_patch` doesn't diff skills, so `_static_checks` never sees a candidate body; no held-out dataset exists. The only salvageable piece (render candidate body to scratch for static validation) folds into P1. |
| **P3 — Edit-budget ranker** | needs-adjustment | **Adopted with corrections** | `AutonomyPolicy`/`policy_json` blob confirmed (no migration to add `skill_edit_budget`); but the gate is an **all-or-nothing veto** (`harness_autonomy.py:85/138`), not a top-N ranker — a real ranker selecting a bounded subset *before* the veto is net-new, and the eval supplies no per-entry score today. |

**Counts: 0 founded-clean · 2 needs-adjustment (adopted with corrections) · 1
unfounded (recorded, not implemented).**

*Synthesis claims are grounded in Agented source at the cited `file:line`,
confirmed by CodeGraph/Read against the working tree on the `main` branch. The
adversarial verification pass refuted or corrected every proposal before
inclusion. SkillOpt claims cite arXiv:2605.23904 and its engine spec
(`config.py`, `trainer.py`, `gate.py`/`consolidate.py`).*
