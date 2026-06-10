# Integrating Harness‑1's State‑Externalizing Harness into Agented

> **Research report — scope:** the *state‑externalizing harness* architecture pattern only. Decided with the user: this is a cited analysis + phased plan, **not** code.
> **Method:** parallel deep‑reads of (the paper, the repo's `harness/` code, Agented's orchestration/persistence layer) → synthesis into concrete proposals → **one adversarial verifier per proposal checked against Agented's actual source.** Every `file:line` below was confirmed by that pass unless explicitly flagged.
> **Verification result:** 8 proposals — **0 confirmed clean, 5 adjusted, 3 refuted as written.** The corrections are folded in; the refuted ones are reframed as conditional/deferred.

---

## Source

**Harness‑1: Reinforcement Learning for Search Agents with State‑Externalizing Harnesses** — Jiang, Shi, Hong, Xu, Sun, Sun, Bashir, Han. arXiv:2606.02373 (2026). Repo: `github.com/pat-jj/harness-1`. Checkpoint: `huggingface.co/pat-jj/harness-1`.

A 20B search agent trained with RL **inside a stateful retrieval harness**. The harness maintains *recoverable* search state — candidate documents, curated evidence, evidence links, verification records, budget‑aware context. The policy (the LLM) keeps only the **semantic decisions**: what to search, which documents to inspect/curate, what claims to verify, and when evidence is sufficient.

---

## 1. The transferable idea

Split a long‑running agent into two halves:

- **Policy** (the LLM) — owns *semantic* decisions only.
- **Harness** (the environment) — owns *all recoverable bookkeeping* as durable, environment‑side state the model never has to re‑derive: a candidate/evidence ledger, evidence links, verification records, budget accounting, and budget‑aware context compaction.

The payoff is **long‑horizon robustness**: a serialized trajectory (ordered action/observation log + step cursor) makes a run crash‑recoverable; a typed evidence ledger makes artifacts auditable instead of grepped out of stdout; persisted verification records let review gates attest claims; and budget‑aware assembly enforces token discipline *live* rather than recording cost after the fact.

**The RL/SFT half does not port. The architecture does.** (See §6.)

---

## 2. How Agented runs a harness today

Agented treats a harness run as **fire‑and‑forget**. It drives an *external* harness CLI (Claude Code, Codex, Gemini) as a **one‑shot `subprocess.Popen`**, streams stdout/stderr line‑by‑line, and flushes to SQLite once at the end.

| Aspect | Reality (verified) |
|---|---|
| In‑flight state | **Ephemeral.** `ExecutionLogService` keeps `_log_buffers`/`_subscribers`/`_start_times` in class‑level memory (`execution_log_service.py:41‑65`, guarded by `cls._lock`), single‑process (`workers=1`). `append_log:113` only appends to memory + broadcasts SSE — it **never persists**. |
| Durability point | **Once, at the end.** `finish_execution:127` (flush at `:144‑165`) writes `stdout_log`/`stderr_log` via `update_execution_log` (`execution_logs.py:58`). |
| On crash | A stale `status='running'` row with NULL output. `create_execution_log` (`execution_logs.py:17`) hardcodes `status='running'`; `cleanup_stale_executions:377‑406` **pops the in‑memory buffer without touching the DB row**. |
| Continuation | Retry‑**from scratch** only, via `pending_retries` (`execution_retry.py` `schedule_retry:63`, `restore_pending_retries:225`, wired at `lifecycle.py:361`). `mark_stale_executions_interrupted` (`execution_logs.py:107`) is a restart *tombstone*, not a resume handle. |
| Record table | `execution_logs` (`schema/_core.py:60‑85`): `id` PK, `execution_id TEXT UNIQUE`, status, `stdout_log`/`stderr_log`, `input_tokens`/`output_tokens`/`total_cost_usd` (`:78‑80`), `session_id`. **No cursor / checkpoint / turn‑ledger column.** |

**What Agented already has** (and Harness‑1‑style proposals must not re‑invent):

- **A live budget killer.** `budget_monitor` (`execution_runner.py:111‑216`, wired via `execution_service._budget_monitor:283`) polls every 30 s while `process.poll() is None`, calls `BudgetService.check_budget` (`budget_service.py:307`) + `check_execution_time_limit:377`, and `os.killpg(SIGKILL)`s an over‑budget process group. Live hard‑stop is **not** missing.
- **A `/resume` endpoint** — `resume_execution` (`routes/executions.py:353`, wired `:562‑573`) → `ProcessManager.resume` (`process_manager.py:224`). But it's an **in‑memory `SIGCONT`** on `cls._processes`; it resumes a `paused`→`running` process *still tracked in this worker* and returns `False` after any restart. Not durable resume.
- **`traces` / `trace_spans`** (`schema/_monitoring.py:147`, `:170`; writers in `db/tracing.py` `create_trace:37`/`create_span:158`/`end_span:209`) with `input`/`output`/`metadata`/`status`/parent links — the **closest existing analogue to evidence links + verification records.** Build on these, don't parallel them.
- **Post‑hoc verification** — predefined `bot-pr-review` / `bot-security` (`db/triggers.py:32`, `_runner.py:85`), `db/pr_reviews.py`, `quality_ratings` + `execution_quality_ratings` (`schema/_monitoring.py:73`).
- **The `_harness_*` schema family** — `_harness_annotations/_evolution/_kg_signals/_snapshots/_takeaways`, each a `create_<domain>_tables(conn)` registered in `schema/__init__.py:36‑73`. Proves the project already has a slot for harness‑state scaffolding.

---

## 3. The central mismatch (the most important finding)

Harness‑1's contract is **"the environment owns the policy's working state."** In Agented that **inverts**: the policy *and* most of its bookkeeping live **inside an opaque child process**. Agented sees only a line stream and holds exactly one mid‑run lever — **`SIGKILL`** (`budget_monitor` / `ProcessManager.cancel_graceful`). It does not orchestrate the agent turn‑by‑turn.

Three consequences shape every proposal below:

1. **Faithful "harness owns policy state" is impossible for subprocess runs.** It ports as *capture/checkpoint the harness's reported state*, not *own it*. It ports more faithfully only for Agented's **in‑process conversation services**.
2. **In‑loop verification gates (pause → consult → resume) are impossible.** Verification is inherently post‑hoc; the realistic lever is gating **downstream side effects** (e.g. PR creation in `auto_resolve_and_pr`, `execution_runner.py:301`), or a binary `SIGKILL`‑on‑critical‑failure.
3. **True mid‑run resume requires the harness CLI's native `--resume <session_id>`** — a per‑backend capability `build_command` does not pass today. Without it, "resume" can only mean *smart restart from re‑hydrated context as a new prompt*.

---

## 4. Concept map (Harness‑1 → Agented)

| Harness‑1 concept | Agented surface | Fit | Note |
|---|---|---|---|
| Externalized run state (serializable trajectory: action/obs log + step cursor) | `ExecutionLogService` in‑memory dicts; `execution_logs` row | **partial** | Container exists but is process‑only memory flushed once. No serialized ledger, no cursor. Needs a new incrementally‑written table. |
| Candidate / evidence ledger (seen vs curated/kept) | `stdout_log`/`stderr_log` + FTS5 mirror; `db/findings.py`; PR URLs | **weak** | Only flattened text + findings/PR URLs. **No typed per‑step ledger.** Largest gap, highest‑value net‑new structure. *(Harness‑1's `returned_chunk_ids`/`output_chunk_ids` is retrieval‑RAG vocabulary with **no Agented analogue** — drop it.)* |
| Evidence links (typed refs to source spans) | `tool_use` events → SSE → `stdout_log`; `trace_spans` input/output/metadata | **partial** | `trace_spans` already carry the right shape. Reuse it; don't duplicate. |
| Verification records (claim → checked status + evidence) | `bot-pr-review`/`bot-security`; `db/pr_reviews.py`; `quality_ratings` | **partial** | Machinery exists but is **post‑hoc**, not in‑loop attestation. |
| Budget‑aware context assembly (live per‑turn render under budget) | `BudgetService.check_budget`; token cols on `execution_logs`; `db/budgets.py` | **partial** | Agented gates **once pre‑launch** + a live *kill* monitor, but records tokens **post‑run** and does no per‑turn *context* assembly (context lives in the child). |
| Harness/policy contract (env owns bookkeeping) | `ExecutionService.run_trigger` → `Popen`; `OrchestrationService` | **weak** | **Inverted today** — policy + bookkeeping live in the opaque child. Ports cleanly only for in‑process conversation services. |
| Trajectory checkpoint / recovery | `ExecutionRetryManager` + `pending_retries`; `session_id` col | **partial** | Durable retry‑from‑scratch + a `session_id` column exist, but **no mid‑run checkpoint/resume**. |

---

## 5. Integration proposals (verified & corrected)

Status legend: **✅ Adopt** (sound after adjustment) · **⚠ Adjust** (idea good, claims corrected) · **⛔ Deferred** (refuted as written — depends on foundation and/or per‑backend support).

### Foundation — durable run state

**P1 · Durable harness‑state store** — ✅ Adopt *(was: needs‑adjustment)*
Add `schema/_harness_state.py` (`create_harness_state_tables(conn)`) defining `harness_runs` (status, step_cursor, budget_used, updated_at) and `harness_checkpoints` (step, serialized turn ledger JSON, created_at), plus a `db/harness_state.py` repo module — mirroring the verified `_harness_snapshots` pattern (`db/connection.py:33‑66` convention).
**Corrections from verification (high confidence):**
- **FK was wrong.** There is no `executions` table and no bare `execution_id` PK. Use `FOREIGN KEY (execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE` — the established pattern at `_misc.py:206/335‑336/390` and `_monitoring.py:80`.
- **Registration was incomplete.** Adding to `schema/__init__.py:create_fresh_schema` only builds on a *fresh* DB. Existing DBs need a **`V07_MIGRATIONS` entry** (`v07_features.py:1024`, idempotent `CREATE TABLE IF NOT EXISTS` — cf. `harness_layers v07:914`) **as well**.
- The hedge "maybe extend `harness_snapshots`" is **unfounded** — that table is a polymorphic `(session_kind, session_id)` Forge‑binding snapshot keyed by `bundle_hash`, not a run‑state ledger. A new table is correct.

**P2 · Incremental `checkpoint()` on `ExecutionLogService`** — ⚠ Adjust → ✅ after re‑anchoring
Add a throttled `checkpoint()` (every N appends / T seconds) so run state persists *before* `finish_execution`. The attach point is right — `ExecutionLogService` is the single run‑lifecycle chokepoint, and the threaded (`threading.Thread:552‑566`, **not** async) runner makes a synchronous `@classmethod` checkpoint compatible.
**Corrections (high confidence):**
- "Write the step cursor + serialized turn ledger" assumes structures that **do not exist** — the runner only has raw per‑line `List[LogLine]` buffers; there is no turn/step model. Either (a) snapshot `_log_buffers` → `stdout_log`/`stderr_log` mid‑run (mirroring `finish_execution:144‑165`) **without** setting terminal `status`/`finished_at`, or (b) land the real ledger via P1 first and write to it.
- **Also fix the crash tombstone:** extend `cleanup_stale_executions:377‑406` to mark abandoned rows `failed` — today it never touches the DB row.
- Keep checkpoint writes off the `_lock` hot path; `workers=1` is load‑bearing, so the store must be the durability bridge across restarts.

### Evidence & verification

**P3 · Typed, persisted evidence ledger** — ⚠ Adjust (re‑target)
Turn transient `tool_use` events into queryable ledger rows. **Feasible, but the named targets were wrong:**
- `_run_claude_response` (`agent_conversation_service.py:254`) and `_process_with_claude` (`base_conversation_service.py:604`) call `stream_llm_response` (`conversation_streaming.py:291`), which is `Generator[str]` — **text only.** Tap the typed stream at its real source instead: `_extract_tool_uses_from_event:1092` / the `ToolUseEvent` yield (`conversation_streaming.py:62/874`), or instrument `run_streaming_response` (`streaming_helper.py`) where `ChatChunk`/`ToolUseEvent` already dispatch.
- **Drop** the `returned_chunk_ids`/`output_chunk_ids` kept/seen flag — no such mechanism exists in Agented.
- `tool_result` parsing is **absent** — add it if results are needed.
- Reusing `trace_spans` is sound, but conversations create **no parent trace today** — `create_trace` per turn must come first.

**P5 · Persisted verification records + gate** — ⚠ Adjust (split in two)
*Persistence half is sound and idiomatic:* add a `verification_records` table (FK to `execution_logs(execution_id)`, claim id, status, evidence ref, `checked_at`) via a numbered migration, with a `db/verification_records.py` CRUD module + a Litestar router (cf. `quality_ratings_router`). **Reconcile with the existing `traces`/`trace_spans`** rather than building a parallel store.
*Gate half must be reframed:* "block the run mid‑flight to consult a check" is **incompatible** — Agented cannot pause an opaque subprocess. Realistic options: **(a)** post‑hoc — run `bot-security`/`bot-pr-review` after the subprocess exits, write records, and gate the **downstream action** (whether `auto_resolve_and_pr` proceeds); or **(b)** a hard‑fail monitor that `SIGKILL`s on a critical failed claim (binary, not a handshake).

### Budget

**P6 · Per‑run incremental token accounting + soft wrap‑up** — ⚠ Adjust (premise corrected)
The original premise — "convert the pre‑launch gate into live enforcement" — is **false**: live enforcement already exists (`budget_monitor`, §2). Reframe to the **genuine residual gaps**:
- Usage is parsed **only post‑run** (`extract_token_usage` + `record_usage`, `execution_service.py:684‑698`). Incremental parsing is feasible for **codex** (`_extract_codex_usage` reads JSONL `turn.completed`) but **not uniform** — `_extract_claude_usage`/`_extract_gemini_usage` parse a single terminal result object. Per‑backend parsers needed.
- Add a **per‑run** ceiling distinct from period‑aggregate spend (today a single run only trips the kill when the *period* total crosses `hard_limit_usd`).
- Add a **soft "wrap up" signal** (the soft‑limit path currently only logs — `budget_service.py:341`).
- Persist deltas into `harness_runs.budget_used` once P1 lands; until then, into `execution_logs.total_cost_usd`.
- *Citation fixes:* token cols at `_core.py:78‑80`; `check_budget` at `budget_service.py:307` (not `orchestration_service.py:51`, which is the thin `_check_budget` wrapper).

### Deferred — require the foundation + per‑backend resume support

**P4 · Resumable status + re‑hydrate path** — ⛔ Refuted as written
Depends on `harness_runs`/cursor/ledger that **don't exist yet** (self‑admits "Depends on P1/P2"), and the one‑shot `Popen` model holds no resumable handle to the harness's internal state. `ExecutionStatus` (`orchestration_service.py:20`, dispatch‑outcome enum) is also distinct from `ExecutionState` (`execution_service.py:94`, where `interrupted` lives). **Realistic reframe:** **(A) restart recovery** — on startup, scan `interrupted` `execution_logs` rows (set by `mark_stale_executions_interrupted`) and **re‑dispatch from scratch** (`restore_pending_retries:225` is the model); or **(B) true resume** — only after P1/P2 *and* threading the harness's native `--resume <session_id>` through `build_command` and capturing that id during streaming. A `resumable` concept belongs to `ExecutionState`, not `ExecutionStatus`.

**P7 · `GET /state` + `POST /resume` operator surface** — ⛔ Refuted as written
`harness_runs`/ledger/verification records don't exist, so as written it's unbuildable; **`POST /resume` already exists** (`executions.py:353`, in‑memory `SIGCONT` only). **Realistic reframe:** `GET /state` surfaces what exists today — `ExecutionLogService.get_execution` + replayable ring‑buffer lines; do **not** re‑add `/resume`; put any new endpoint on `executions_router` (not `triggers.py`); the SSE reuse via `ExecutionLogService.subscribe:221`/`_broadcast:291` is sound. Build *after* P1–P5 are real.

**P8 · Checkpoint PTY‑backed `ralph_loop`/`team_spawn` sessions** — ⛔ Refuted as written
Rests on a non‑existent "P2 checkpoint cadence," and a step cursor **cannot make a PTY session resumable**: these are forked subprocesses bound to a live master fd in the in‑memory `_sessions` dict; restart behavior (`cleanup_dead_sessions:1969‑2008`) marks them **`failed`**, with no reattach path. (Also: `create_session:820`, `_reader_loop:1147` — not the cited `:819`/`:1792`; `project_sessions` schema `_orgs.py:259` has no cursor column, and `update_project_session` `db/grd.py:518` has a fixed allowlist.) **Realistic reframe:** externalized resumability for these belongs at the **orchestration layer** (e.g. a `GoalLoopRunner` spawning a fresh session from durable plan/turn state at ralph iteration boundaries), not in `_reader_loop`. A persisted per‑step **counter** in `_reader_loop` is feasible but is **observability, not resumability**, and still needs a new column.

---

## 6. What does **not** port

| Element | Why not |
|---|---|
| RL training inside the harness | Agented trains no models; there is no policy to optimize. Only the state‑externalization architecture transfers. |
| SFT training + SFT data generation (`generate_search_sft.py`) | No model fitting; the curated‑trajectory pipeline has no consumer. |
| Tinker cookbook / vLLM / Modal / Baseten serving | Agented drives external CLIs via `Popen`; it neither hosts nor serves weights. |
| Chroma corpus + `text-embedding-3-small` (BM25+dense RRF) | Harness‑1 retrieves over a fixed corpus; Agented's runs are code/PR/product workflows with no corpus. The candidate pool ports as an **artifact ledger**, not a vector store. |
| Rerankers (`rerank.py`, Baseten/Contextual/Jina) | No corpus → nothing to rerank. Budget truncation ports conceptually (P6); the reranker components do not. |
| Reward model / RL reward shaping | Only meaningful inside the (non‑ported) RL loop. |
| BrowseComp+ & the eight retrieval benchmarks (the 0.730 headline) | Measure *retrieval quality*. Agented would instead measure **crash/resume success, budget adherence, audit completeness**. |
| Concrete tool surface (`search_corpus`/`read_document`/`grep_corpus`/`prune_chunks`) | Retrieval‑corpus tools. The harness/policy *contract* ports; these signatures do not. |

---

## 7. Phased plan

| Phase | Goal | Proposals | Exit criteria |
|---|---|---|---|
| **1 — Durable state foundation** | Persist run state incrementally; no change to how runs are driven. | P1, P2 | A killed mid‑run execution leaves a `harness_runs` row with a non‑NULL cursor + a deserializable checkpoint; `cleanup_stale_executions` marks abandoned rows `failed`; `finish_execution` still does the final flush; existing tests green + a new "survives simulated crash" test. |
| **2 — Structured evidence + verification** | Typed, auditable ledger; persisted verification records (record‑only first). | P3, P5(persist) | In‑process conversation runs emit typed ledger rows with evidence refs (reusing `trace_spans`); `verification_records` written during a run and queryable without grepping `stdout_log`. |
| **3 — Budget discipline + operator surface** | Incremental accounting, soft wrap‑up, console visibility. | P6, P7(`GET /state`) | `budget_used` updates mid‑run for codex (claude/gemini documented as terminal‑only); a per‑run ceiling + soft signal exist; `GET /state` renders live via SSE. |
| **4 — Resume & long‑horizon** *(gated on §8 answers)* | Restart recovery → true resume where the backend supports it; PTY runs. | P4(restart→resume), P8(orchestration‑layer) | Interrupted runs re‑dispatch from scratch; *if* a backend exposes `--resume`, one run resumes via re‑hydrated session id with proven idempotency; ralph/team‑spawn resumability designed at the orchestration boundary. |

---

## 8. Open decisions for the maintainer

1. **Subprocess transparency per backend.** Can each CLI emit a structured `tool_use`/step stream, or only flattened stdout? Gates P3/P6 fidelity; differs per backend (codex JSONL is incremental; claude/gemini are terminal).
2. **Native resume per backend.** Does each CLI accept `--resume`/`--session` to continue a partial run (P4), or must "resume" mean smart restart?
3. **Idempotency of replayed steps.** If a checkpointed step already opened a PR / pushed a commit (`auto_resolve_and_pr`, `execution_runner.py:301`), how does resume avoid double‑acting? Need a per‑step `applied` marker before P4 ships.
4. **Verification authority.** Advisory (record‑only) or blocking? Blocking needs a timeout + bypass policy and, given §3, can only be a post‑run side‑effect gate or a `SIGKILL`.
5. **`workers=1` boundary.** If the deployment ever moves to `workers>1`, the class‑level in‑memory dicts break — should the harness‑state store become the **single source of truth** rather than a backup?
6. **Checkpoint cadence vs SQLite write load.** Per‑append / per‑N / per‑T? Tied to expected run length on raw SQLite (WAL).
7. **First‑class `Run` entity?** Agented deliberately has **no** `Run` object today; `harness_runs` is close to introducing one. Decide whether it becomes a product‑hierarchy entity or stays a row+ledger keyed by `execution_id`.

---

## Appendix · Verification ledger

| Proposal | Verdict (as written) | Confidence | Core defect corrected |
|---|---|---|---|
| P1 | needs‑adjustment | high | FK target (`executions` table doesn't exist); missing versioned‑migration registration. |
| P2 | needs‑adjustment | high | Depends on non‑existent cursor/turn‑ledger; re‑anchor on `stdout_log`/`status`; fix crash tombstone. |
| P3 | needs‑adjustment | high | Named services see text‑only; tap typed stream at source; drop `chunk_ids`; no parent trace today. |
| P4 | **unfounded** | high | No `harness_runs`/cursor; one‑shot `Popen` has no resumable handle; wrong enum. |
| P5 | needs‑adjustment | high | In‑loop gate impossible; gate side effects post‑hoc; reconcile with `trace_spans`. |
| P6 | needs‑adjustment | high | Live enforcement already exists; reframe to incremental accounting + soft signal. |
| P7 | **unfounded** | high | Prereqs absent; `/resume` already exists (in‑memory); wrong router. |
| P8 | **unfounded** | high | No checkpoint subsystem; PTY child unrecoverable after restart; wrong line numbers. |

*Generated by a custom research workflow (12 agents, 3 ingest → synthesis → 8 adversarial verifiers). Synthesis claims are grounded in Agented source at the cited lines; the verification pass refuted or corrected every proposal before inclusion. Paper claims cite arXiv:2606.02373.*
