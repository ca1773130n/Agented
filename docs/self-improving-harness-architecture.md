# The Self-Improving Harness: Architecture

**Languages:** English (canonical) · [한국어](/ko/self-improving-harness-architecture)

*A companion to [BLOG-self-improving-harness.md](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md).
The blog argues that the agent-memory field is optimizing the wrong axis
(recall accuracy) and missing the one that matters in production
(provenance + auditability). This document explains the system that
falls out of taking that seriously — not a memory store, but a closed
**self-improvement loop** — and compares it, honestly, with the memory
architectures the blog references.*

---

## 1. Memory is not the problem we solved

Every system the blog names — Mastra, Letta/MemGPT, Zep/Graphiti, Mem0,
Cognee, Hermes Agent — is a **memory architecture**. Its job is: given a
stream of conversation, *retain* facts and *recall* them later under
pressure. The benchmark is LongMemEval; the axis is retrieval accuracy.

Agented's self-improving harness sits one layer up. Memory is the
substrate, not the product. The product is a loop that asks a different
question:

> Given everything the agent did across its sessions, **how should the
> harness itself change** — its rules, hooks, commands, skills, MCP
> bindings — and can that change be graded, approved, reversed, and
> propagated *without a human editing a primitive by hand and without
> losing the audit chain?*

This is a **self-improvement** problem (mutate your own operating
context), not a **memory** problem (recall what you were told). The two
are routinely conflated. They are different, and the second is the
harder one. A memory system that recalls "the deploy script moved" still
needs a human to turn that into a rule. A self-improving harness closes
that gap — and the moment it does, it inherits a security and audit
burden that pure-recall systems never face: it is now *writing
executable instructions to disk based on its own inference.*

Our entire architecture is shaped by refusing to let that write happen
without a graded gate, an approval (operator or policy-bounded
autonomous), a rollback journal, and end-to-end provenance.

---

## 2. The closed loop

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                                                                            │
 │   (1) CAPTURE            (2) ANNOTATE / EXTRACT        (3) GATHER          │
 │   every session   ──►    two asymmetric evidence  ──►  + KG-seeded        │
 │   → snapshot+events      streams (failures|wins)       evolution inputs    │
 │                                                            │               │
 │                                                            ▼               │
 │   (10) KG FEEDBACK                                    (4) PROPOSE          │
 │   sessions compiled  ◄────────────────────────        Codex in sandboxed  │
 │   into typed graph                                     scratch → patch     │
 │        ▲                                                   │               │
 │        │                                                   ▼               │
 │   (9) PROPAGATE                                       (5) EVAL-GATE        │
 │   proven primitives   ◄───────┐                       static checks +     │
 │   promote cross-project        │                      replay LLM judge     │
 │        ▲                       │                       → EvalVerdict       │
 │        │                       │                           │               │
 │   (8) ROLLBACK            (7) MATERIALIZE             (6) APPLY            │
 │   reverse journal     ◄──  .claude/ + one git    ◄──  operator-approved   │
 │   + git revert            commit per round            OR policy-autonomous │
 │                                                                            │
 └──────────────────────────────────────────────────────────────────────────┘
```

Each numbered stage is a real, auditable artifact in the codebase. The
loop is **gated**, not free-running: nothing mutates a primitive, lands
on disk, or propagates without crossing an explicit boundary that
records provenance.

### (1) Capture — `harness_snapshot_service.py`, `session_events.py`
On every completed session (across *all* session kinds — trigger
executions, super-agent runs, team executions, workflows; never just
"bots"), a **snapshot** of the resolved harness bundle is persisted
alongside the raw session event stream. This is the provenance ledger's
input layer. The blog's "12 silent failures" interlude is exactly about
making sure this layer does not lie downstream — every fetcher/parser is
dogfooded against ≥3 real production rows before it is trusted.

### (2) Annotate + Extract — two asymmetric evidence streams
Both fan out from the same `session_complete` channel:

- **Failure annotator** (`harness_failure_annotator.py`) runs the
  **Life-Harness four-layer taxonomy** — `detect_h2` (interface) →
  `detect_h3` (environment contract) → `detect_h4` (trajectory
  regulation) → general — ordered by `_apply_priority_protocol`, writing
  typed incidents to `harness_annotations`.
- **Takeaway extractor** (`harness_takeaway_extractor.py`, heuristic +
  provider-kind LLM) surfaces *positive* signal — user preferences,
  discovered procedures, tool patterns, constraints, domain facts, root
  causes, success patterns — to `harness_takeaways` (stable `tk-*` IDs,
  `session_kind`/`session_id` back-pointers, extractor version,
  confidence).

The **asymmetry is the point**: failures want rules and hooks; successes
want skills and commands. Most memory systems capture one direction
(usually positive) and silently lose half the signal.

### (3) Gather — `harness_evolver.gather_inputs`
Assembles the evolution round's inputs: the project's currently-bound
Forge primitives, recent trajectories (snapshots + their annotations +
incidents), recent takeaways, **and** — the final loop edge — **KG
signals** from the compiled Tesserae graph (`gather_kg_signals`, ≤3
bounded `ask_tesserae` discovery questions, weighted/deduped, gated so a
Tesserae-disabled project pays nothing). The graph the loop *produces*
(stage 10) now *seeds* the loop (stage 3). That is what makes it a loop
and not a pipeline.

### (4) Propose — Codex in a sandboxed scratch workspace
`build_workspace` writes the inputs to an ephemeral dir
(`forge/`, `trajectories/`, `takeaways/`, `KG_SIGNALS.md`,
`tesserae_context.md`); `codex exec --sandbox workspace-write` runs
against it; the resulting patch is parsed and schema-validated. **The
model proposes a diff; it never edits a live primitive in-process.**

### (5) Eval-gate — `harness_evolution_eval.py`
Before any apply, the patch is graded into an **`EvalVerdict`**
(`passed: bool`, `score: float ∈ [0,1]`, `per_check: [CheckResult]`):

- **Static checks** (`_static_checks`) — mechanical: schema validity,
  frontmatter sanity, no-op detection, line-anchored guards.
- **Regression-replay judge** (`_run_judge`, provider-kind via
  `resolve_llm_cmd`) — replays representative session samples against the
  *patched* primitive set and asks a judge whether behavior regressed.

`_verdict` caps the score below a trust floor when the patch doesn't pass.
A failed gate (`eval_failed`) short-circuits the apply. Gate *errors*
fail-open but record a **bypass verdict at score 0.0**, so a bypass is
never silently indistinguishable from a real pass. This is the grading
layer every "self-editing memory" system lacks.

### (6) Apply — operator-approved **or** policy-autonomous
The round's state machine
(`pending → running → evaluating → awaiting_approval → applied`, with
`eval_failed`/`failed`/`aborted`/`reverted` exits) supports two apply
paths against the **same** machinery:

- **Operator**: the dry-run round sits at `awaiting_approval`; the
  operator reviews the diff and `POST /evolution/rounds/{id}/apply`.
- **Autonomous** (`harness_autonomy.py`): a 5-minute scheduler job
  (`autonomous_apply_job` → `process_project_autonomy`) auto-applies
  *only* when `autonomous_apply_eligible` clears **nine hard gates** —
  kill switch (`AGENTED_AUTONOMY=0`), per-project policy enabled, eval
  `passed` **and** `score ≥ confidence_threshold` (default 0.85), blast
  radius ≤ `max_ops_per_round`, `allowed_kinds`, `block_deletes`,
  `cooldown_seconds`, `rate_limit_per_day`. Off by default; opt-in
  per project (`project_autonomy_config`).

Autonomy is a *bounded* escalation of the operator path, not a separate
unaudited code path.

### (7) Materialize — `forge_materialization_service.py`
Applied primitives are projected into the project's real `.claude/`
layout (commands/rules/hooks + `settings.json`/`mcp.json`/skills),
idempotently and operator-preservingly, and committed as **one git
commit per round**. The harness's evolution is now `git log`.

### (8) Rollback — `harness_evolution_rollback.py`
`apply_patch` captures a **before-image apply-journal**. `revert_round`
refuses unless the round is `applied` with a journal, detects conflicts
(later rounds touching the same `{kind, asset_id}`), reverses the DB ops
idempotently, then git-reverts the materialization commit. Partial or
git failure leaves the round `applied` with a `revert_error` — it never
*claims* `reverted` it didn't achieve. This is the blog's
"AuditEval Rollback axis," implemented.

### (9) Propagate — `harness_propagation.py`
A content **fingerprint** (`forge_fingerprint.py`, sha256 of content
fields) gives a primitive a cross-project identity. Each applied,
**eval-PASSED** round records decayed promotion evidence; once a
fingerprint's time-decayed score crosses `PROMOTION_THRESHOLD = 3.0`, a
**global-scope copy** is promoted (`shared_forge_bindings`) and other
projects adopt it (`adopt_shared_binding`, local-wins conflict policy).
`_PROPAGATABLE = (rule, hook, command)`. Only eval-passed rounds
contribute — no force-apply can poison the shared layer.

### (10) KG feedback — `tesserae_integration.py`
Every completed session is auto-imported into the project's Tesserae
workspace (`on_session_complete` → `export_sessions_to_tesserae`); the
operator compiles a typed knowledge graph (`CodeFile`, `Session`,
`SessionTakeaway`, `SessionDecision`, …). That graph is the substrate
stage (3) queries — closing the loop.

---

## 3. What makes it auditable (the through-line)

Every stage emits a row with a timestamp and a back-pointer:

- a behavior → the **rule** that produced it → the **round** that forged
  it → the **eval verdict** that graded it → the **takeaways/incidents**
  that motivated it → the **sessions** they were extracted from → durable
  transcripts.
- a learned heuristic can be **reverted** by ID, with the sessions and
  takeaways it came from still queryable.
- a promoted primitive carries its **fingerprint** and the evidence that
  crossed the threshold.

Nothing in the chain is similarity-scored over an embedding blob. This
is the property no memory benchmark measures and the blog's
hypothetical *AuditEval* would.

---

## 4. Comparison with the architectures the blog references

The honest framing: **these are mostly not competitors — they operate on
a different axis.** Mastra/Zep/Mem0/Cognee are memory/retrieval tiers;
Agented could *use* one as its capture substrate. The two systems with a
genuine self-modification story — **Letta** (self-editing memory via
tools) and **Hermes Agent** (`skill_manage`, autonomous skill creation)
— are the real points of comparison, and the contrast is the *gate*.

| Axis | **Agented self-improving harness** | Letta / MemGPT | Hermes Agent | Mastra | Zep / Graphiti | Mem0 | Cognee |
|---|---|---|---|---|---|---|---|
| Primary problem | Self-improvement loop | Memory (LLM-as-OS) | File-based harness state + skill gen | Memory tiers | Bi-temporal KG memory | Hybrid memory | RAG-to-graph |
| Evidence streams | **Two, asymmetric** (failure taxonomy + positive takeaways) | One (positive) | One (positive) | One | One | One | One |
| Self-modification | **Proposed diff** (Codex in sandbox) | In-line, agent edits memory via tools | Agent writes new skill to disk | n/a (store) | n/a | n/a | n/a |
| Grading before apply | **Eval gate** (static + replay judge → scored verdict) | None | None | n/a | n/a | n/a | n/a |
| Approval model | **Operator-approved, or policy-bounded autonomous (9 gates)** | Autonomous | Autonomous | n/a | n/a | n/a | n/a |
| Lands on disk as | **One git commit / round** (`.claude/`) | Memory rows | Files | Store rows | Graph | Store | Graph |
| Rollback | **Before-image journal + git revert, conflict-aware** | — | — | — | bi-temporal (historical view) | — | — |
| Cross-project propagation | **Fingerprint → decayed evidence → global promote → adopt** | — | — | — | — | — | — |
| Provenance of a belief | **Row-chain to source session, no embedding guess** | tool-edit history | file history | store metadata | bi-temporal edges | extraction log | graph lineage |
| Threat-model posture | "Propose → approve" by default; deletes blocked; bypass = score 0 | inline edit = inline risk | **`skill_manage` = downloaded dependency** | store-only | store-only | store-only | store-only |

### Stated plainly

- **vs. Letta / MemGPT** — Letta pioneered self-editing memory; the agent
  rewrites its own core/archival memory through tool calls, in-process,
  unreviewed. We deliberately took the **proposal-review** variant: the
  model emits a *diff*, an eval gate *scores* it, and an operator (or a
  bounded policy) approves it. In a world where 36.8% of public skills
  have security flaws (Snyk ToxicSkills), a diff-before-landing is not a
  nicety. We are not claiming inline-edit is wrong — we are claiming any
  regulated deployment will add this gate, and architecting around it
  from day one is cheaper than retrofitting.
- **vs. Hermes Agent** — Hermes's `skill_manage` lets the agent author
  skills autonomously to disk. Structurally, *an agent that learns by
  writing a skill has downloaded a dependency.* Our skill path is
  operator-approved by default (`AGENTED_TAKEAWAY_AUTOAPPLY` opt-in),
  written to a **separate gitignored `.agented-takeaways/` directory** so
  the diff against operator-curated skills is one `git status` away, and
  every applied skill back-points to its takeaway + session + confidence.
- **vs. Mastra / Mem0 / Cognee** — pure memory/retrieval tiers. They win
  LongMemEval; that is genuinely good engineering on the recall axis.
  They have no proposal/grade/apply/rollback/propagate loop because that
  is not their problem. Agented can sit *above* any of them.
- **vs. Zep / Graphiti** — the closest in spirit on *one* axis:
  Graphiti's bi-temporal graph tracks both event-time and ingestion-time,
  which is real provenance infrastructure for the **memory** layer. We
  use Tesserae (typed, compiled-offline, queried-online) for the analogous
  job, but our bi-temporal-equivalent lives at the *harness-evolution*
  layer: a round's apply-journal + git history records exactly what the
  harness believed and when, and lets you revert it.
- **vs. the Life-Harness paper** ([arXiv 2605.22166](https://arxiv.org/abs/2605.22166))
  — we adopt its four-layer failure taxonomy (H2/H3/H4/general) as the
  *failure* evidence stream, and generalize it: the paper classifies what
  went wrong; we wire that classification into a forge-and-grade loop that
  acts on it, pairs it with a positive-evidence stream, and makes every
  resulting change revertible and propagatable.

---

## 5. The one-sentence version

The memory field is racing to recall facts accurately; we built the
layer that **decides what the harness should become** from those facts —
and made that decision *graded, approved, reversible, propagatable, and
auditable end-to-end*, because the moment an agent improves itself by
writing instructions to disk, every one of those properties stops being
optional.

---

## Source map (every claim above is a symbol in the tree)

| Stage | Code |
|---|---|
| Capture | `app/services/harness_snapshot_service.py`, `app/db/session_events.py`, `harness_snapshots` |
| Annotate | `app/services/harness_failure_annotator.py` (`detect_h2/h3/h4`, `_apply_priority_protocol`), `harness_annotations` |
| Extract | `app/services/harness_takeaway_extractor.py`, `harness_takeaways` (`tk-*`) |
| Gather | `app/services/harness_evolver.py::gather_inputs`, `app/services/harness_kg_signals.py::gather_kg_signals` |
| Propose | `harness_evolver.py` (`build_workspace`, `_run_codex_in_workspace`, `parse_patch`, `validate_patch`) |
| Eval-gate | `app/services/harness_evolution_eval.py` (`evaluate_patch`, `_static_checks`, `_run_judge`, `_verdict`), `EvalVerdict` in `app/models/harness_evolution.py` |
| Apply | `harness_evolver.py::apply_patch`; routes in `app_litestar/routes/harness_evolution.py` |
| Autonomy | `app/services/harness_autonomy.py` (`autonomous_apply_eligible`, `process_project_autonomy`), `autonomous_apply_job` in `app_litestar/lifecycle.py`, `app/models/autonomy_policy.py`, `project_autonomy_config` |
| Materialize | `app/services/forge_materialization_service.py` |
| Rollback | `app/services/harness_evolution_rollback.py` (`revert_round`, `reverse_apply_journal`, `_git_revert`); `POST /evolution/rounds/{id}/revert` |
| Propagate | `app/services/harness_propagation.py`, `app/services/forge_fingerprint.py`, `forge_promotion` repo, `shared_forge_bindings`; `GET /shared-forge`, `POST /projects/{id}/adopt-shared/{sbid}` |
| KG feedback | `app/services/tesserae_integration.py` (`on_session_complete`, `export_sessions_to_tesserae`, `ask_tesserae`) |
| Round state | `harness_evolution_rounds` CHECK: `pending·running·evaluating·awaiting_approval·applied·eval_failed·failed·aborted·reverted` |

*Architecture delivered across 5 phases (A evidence · B forge · C
eval+rollback · D autonomy · E propagation+KG-source), merged to `main`
2026-05-31.*
