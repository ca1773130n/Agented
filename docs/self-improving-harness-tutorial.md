# Tutorial: Watch the Harness Improve Itself (with Wiki-Style Memory)

**Languages:** English (canonical) · [한국어](ko/self-improving-harness-tutorial.md)

*A hands-on walkthrough. In about 30 minutes you will run a few agent
sessions, watch Agented turn them into typed memory, compile that memory
into a browsable **LLM-wiki**, and then watch the harness propose, grade,
apply, and (if you want) roll back a change to **its own rules** — with a
provenance chain from the new rule all the way back to the session that
motivated it.*

> This is the *show-me* companion to two reference docs. Read them when you
> want the "why" and the "what":
> - **[The Self-Improving Harness: Architecture](self-improving-harness-architecture.md)** — the closed loop, stage by stage, mapped to real symbols.
> - **[Blog: Your Agent Doesn't Have a Memory Problem. It Has a Provenance Problem.](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md)** — the argument this system falls out of.

---

## What you'll build a feel for

Two distinct layers, and how they feed each other:

1. **Wiki-style memory** — every completed session is compiled into a typed
   knowledge graph (Tesserae) and projected as a **browsable wiki / Obsidian
   vault**. You read it like a wiki; agents query it like a graph.
2. **The self-improvement loop** — the harness reads that memory plus a
   failure/success evidence stream, **proposes a diff to its own primitives**
   (rules, hooks, commands, skills, MCP bindings), **grades** it, **applies**
   it as one git commit, and can **revert** or **propagate** it.

The punchline you'll see at the end: the graph the loop *produces* is the
substrate the loop *consumes*. That edge is what makes it a loop, not a
pipeline.

---

## 0. Prerequisites

```bash
# from the repo root
just deploy            # builds + starts backend (:20000), sidecar (:20001), frontend (:3000)
# …or, for iteration:
just dev-backend &     # :20000
just dev-frontend      # :3000
```

Open the operator console at `http://localhost:3000`.

You also need the **Tesserae** CLI + MCP available (the agent memory system).
Confirm with:

```bash
tesserae --version
```

Pick (or create) a **project** in the console — Projects → New. Everything
below is scoped to one project.

> **Under the hood:** projects, products, teams, and agents are prefixed-ID
> rows (`proj-…`, `agent-…`). The backend drives every harness via
> `subprocess.Popen` and SSE-streams output to the console.

---

## 1. Turn on wiki-style memory for the project

In the console: **Settings → Memory System →** enable Tesserae for this
project and point it at a workspace path. (Equivalent SQL, if you prefer:
`UPDATE projects SET tesserae_project_root = '/abs/path' WHERE id = 'proj-…';`)

Once enabled, **every completed session is auto-imported** into this project's
Tesserae workspace — you don't wire anything per session.

> **Under the hood:** `app/services/tesserae_integration.py`
> (`on_session_complete → export_sessions_to_tesserae`). This is stage **(10)**
> of the loop.

---

## 2. Generate some evidence (run a few sessions)

The loop has nothing to learn from until agents have *done* things. Run 3–5
real tasks so there's signal — a mix of wins and stumbles is ideal (the system
captures **both**, asymmetrically; see step 4).

From the console, kick off any normal work: a trigger execution, a super-agent
run, a team execution, or a workflow. For example, point an agent at a small
bug and let it fix it; then ask another to do something it will get *wrong* the
first time (a stale path, a missing env var). Both are useful.

> **Under the hood:** on **every** completed session — not just "bots" — a
> snapshot of the resolved harness bundle is persisted alongside the raw event
> stream (`harness_snapshot_service.py`, `session_events.py`). This is stage
> **(1) Capture** — the input layer of the provenance ledger.

---

## 3. Watch memory form: two asymmetric streams

Open the project's **Activity** dashboard lane. You'll see, accumulating from
the sessions you just ran:

- **Takeaways** (positive signal) — user preferences, discovered procedures,
  tool patterns, constraints, domain facts, root causes, success patterns.
  Each has a stable `tk-…` ID and back-points to the session it came from.
- **Failure incidents** (negative signal) — typed by a four-layer taxonomy
  (interface → environment-contract → trajectory → general).

The **asymmetry is the point**: failures want *rules and hooks*; successes
want *skills and commands*. Most memory systems capture one direction and lose
half the signal.

> **Under the hood:** `harness_takeaway_extractor.py` → `harness_takeaways`
> (stage 2, positive) and `harness_failure_annotator.py`
> (`detect_h2/h3/h4`) → `harness_annotations` (stage 2, negative). Both fan out
> from the same `session_complete` channel.

---

## 4. Compile the wiki — and read your project's memory like a wiki

This is the **LLM-wiki** moment. Compile the accumulated sessions, docs, and
code into a typed graph, then project it as a browsable site:

```bash
tesserae status                 # sanity: node/edge/session counts, last compile
tesserae project compile        # extract typed graph + write vault + site artifacts
tesserae build-site             # render the static wiki
tesserae serve                  # browse it locally
```

Open the served site. You're now reading a **wiki of your project's memory** —
pages for code files, sessions, decisions, takeaways, and concepts, cross-linked
by typed edges. Click from a session to the decisions it produced to the code
it touched.

Ask it questions in natural language (CLI or the bundled MCP tool):

```bash
tesserae ask "what did we decide about retry/backoff?"
tesserae ask "which sessions touched the cost dashboard, and what broke?"
```

Want it in your editor? Sync the vault into Obsidian:

```bash
tesserae obsidian-sync
```

> **Under the hood:** the graph types are `CodeFile`, `Session`,
> `SessionTakeaway`, `SessionDecision`, … The MCP surface (`tesserae_ask`,
> `search_facts`, `graph_ppr`, `wiki_page`, `find_session_findings`) is how
> *agents* read this same memory mid-task — see the Tesserae section of
> `CLAUDE.md`. Refresh after big changes with `tesserae refresh`.

---

## 5. Run an evolution round (dry-run): propose → grade

Now the loop. In the console, open the project's **Harness Evolution** card
(Activity lane) and start a **dry-run** round. (API equivalent:
`POST /projects/{project_id}/evolution/dry-run`.)

Three things happen, in order, and the round's state machine walks
`pending → running → evaluating → awaiting_approval`:

1. **Gather** — the round assembles its inputs: currently-bound primitives,
   recent trajectories + their incidents, recent takeaways, **and KG signals
   queried back from the wiki you just compiled** (≤3 bounded discovery
   questions). The memory feeds the proposer.
2. **Propose** — the inputs are written to an ephemeral workspace and **Codex
   runs in a sandbox** against it. It emits a **diff**; it never edits a live
   primitive in-process.
3. **Eval-gate** — before anything can apply, the patch is graded into an
   **`EvalVerdict`** (`passed`, `score ∈ [0,1]`, per-check results): static
   checks (schema/frontmatter/no-op/anchors) **plus** a regression-replay judge
   that replays representative sessions against the *patched* primitives.

The card shows you the **proposed diff** and the **verdict**. A failed gate
short-circuits — nothing lands.

> **Under the hood:** `harness_evolver.py` (`gather_inputs`, `build_workspace`,
> `_run_codex_in_workspace`, `parse_patch`, `validate_patch`),
> `harness_kg_signals.py::gather_kg_signals`, and
> `harness_evolution_eval.py` (`evaluate_patch`, `_static_checks`, `_run_judge`,
> `_verdict`). Gate *errors* fail closed with a recorded bypass verdict at
> score 0.0 — a bypass is never indistinguishable from a real pass.

---

## 6. Apply, and watch it become a git commit

Happy with the diff? **Approve** it (the round sits at `awaiting_approval`;
approving is `POST /evolution/rounds/{id}/apply`).

On apply, the primitives are **materialized** into the project's real
`.claude/` layout (commands/rules/hooks + `settings.json`/`mcp.json`/skills),
idempotently and operator-preservingly, and committed as **one git commit per
round**. Confirm it:

```bash
git -C <project_root> log --oneline -1     # the round's materialization commit
git -C <project_root> status               # see which .claude/ primitives changed
```

The harness's evolution is now literally `git log`.

> **Under the hood:** `forge_materialization_service.py`. The round transitions
> to `applied`.

---

## 7. Trace the provenance (the part no memory benchmark measures)

Pick the rule that just landed and walk it backwards. Every hop is a row with a
timestamp and a back-pointer:

```
a behavior
  → the RULE that produced it
    → the ROUND that forged it           (harness_evolution_rounds)
      → the EVAL VERDICT that graded it  (EvalVerdict)
        → the TAKEAWAYS / INCIDENTS      (tk-… / harness_annotations)
          → the SESSIONS they came from  (durable transcripts)
```

Nothing in this chain is a similarity score over an embedding blob. You can
answer "*why does the harness believe this, and what graded it?*" with IDs, not
guesses. That's the property the blog's hypothetical *AuditEval* would test.

---

## 8. Roll it back

Changed your mind? Revert the round (`POST /evolution/rounds/{id}/revert`):

```bash
# from the console's Harness Evolution card, or the API
```

The rollback captures a **before-image journal**, refuses unless the round is
`applied` with a journal, detects conflicts (a later round touching the same
`{kind, asset_id}`), reverses the DB ops idempotently, then **git-reverts** the
materialization commit. If git or a partial step fails, the round stays
`applied` with a `revert_error` — it never *claims* a `reverted` it didn't
achieve.

> **Under the hood:** `harness_evolution_rollback.py` (`revert_round`,
> `reverse_apply_journal`, `_git_revert`).

---

## 9. (Optional) Let it apply autonomously — behind nine gates

Operator approval is the default. To let proven changes apply themselves, opt a
project into autonomy (**Settings → … → Autonomy**, or
`PUT /projects/{id}/autonomy`). A 5-minute scheduler job auto-applies **only**
when `autonomous_apply_eligible` clears **nine hard gates**:

1. kill switch off (`AGENTED_AUTONOMY` ≠ `0`)
2. per-project policy enabled
3. eval `passed`
4. `score ≥ confidence_threshold` (default **0.85**)
5. blast radius ≤ `max_ops_per_round`
6. `allowed_kinds`
7. `block_deletes`
8. `cooldown_seconds`
9. `rate_limit_per_day`

It's off by default and is a *bounded escalation of the operator path*, not a
separate unaudited code path. The global kill switch:

```bash
export AGENTED_AUTONOMY=0      # hard-stop all autonomous applies
```

> **Under the hood:** `harness_autonomy.py`
> (`autonomous_apply_eligible`, `process_project_autonomy`),
> `autonomous_apply_job` in `lifecycle.py`, `project_autonomy_config`.

---

## 10. (Optional) Watch a proven primitive propagate across projects

Run the loop in a second project. Once a primitive's content **fingerprint**
accumulates enough decayed, **eval-passed** promotion evidence
(`score ≥ PROMOTION_THRESHOLD = 3.0`), a global-scope copy is promoted and
other projects can **adopt** it (`POST /projects/{id}/adopt-shared/{sbid}`;
local-wins conflict policy). Only `rule`, `hook`, `command` propagate, and only
eval-passed rounds contribute — no force-apply can poison the shared layer.

> **Under the hood:** `harness_propagation.py`, `forge_fingerprint.py`,
> `shared_forge_bindings`; `GET /shared-forge`.

---

## The loop closed

Re-run `tesserae project compile`. The sessions from *this very walkthrough* —
including the evolution rounds — are now nodes in the wiki. The next dry-run's
**Gather** step (5.1) will query them. The graph the loop produced now seeds the
loop.

```
 sessions ──► takeaways + incidents ──► gather (KG-seeded) ──► propose (Codex)
     ▲                                                              │
     │                                                              ▼
  KG feedback ◄── git commit ◄── materialize ◄── apply ◄── eval-gate (scored)
 (Tesserae wiki)                                  │
                                                  └─ revert / propagate
```

---

## Troubleshooting & where things live

| Symptom | Look here |
|---|---|
| No takeaways/incidents after sessions | Confirm sessions *completed*; check the Activity lane; `harness_takeaways` / `harness_annotations` rows |
| Wiki is empty / stale | `tesserae status`, then `tesserae project compile` (or `tesserae refresh`) |
| Dry-run proposes nothing | Needs recent evidence; run more sessions. A no-op is caught by `_static_checks` |
| Round stuck at `awaiting_approval` | That's the gate — approve it, or enable autonomy (§9) |
| Round won't revert | Only `applied` rounds with a journal revert; check for a conflicting later round |
| Autonomy never fires | Walk the nine gates (§9); confirm `AGENTED_AUTONOMY` ≠ `0` and `score ≥ 0.85` |

Full symbol map: the **Source map** table in
[the architecture doc](self-improving-harness-architecture.md#source-map-every-claim-above-is-a-symbol-in-the-tree).

---

## Next steps

- Read the **[architecture](self-improving-harness-architecture.md)** for the
  honest comparison with Letta/MemGPT, Hermes Agent, Mastra, Zep/Graphiti,
  Mem0, Cognee.
- Wire the Tesserae MCP tools into your agents so they *query* the wiki
  mid-task instead of re-deriving — `tesserae_ask`, `find_session_findings`,
  `graph_ppr`, `wiki_page`.
- Turn on autonomy for one low-risk project and watch a week of `git log`
  write itself — every commit revertible, every belief traceable to a session.
