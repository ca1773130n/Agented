# Agentic-RAG Dependable Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Google-style agentic RAG for leader chat — planner → multi-source fanout → sufficient-context check with gap feedback → iterate (≤2) → grounded answer; extracted facts persisted with provenance; a baseline-vs-pipeline usefulness eval with LLM-as-judge, persisted and surfaced.

**Architecture:** A server-side `AnswerPipelineService` hooks into `run_streaming_response` (`streaming_helper.py`, after `llm_messages` assembly at :146-150, before the routing branch ~:174) behind a `rag_enabled` kwarg threaded from the ONE leader-chat call site (`app_litestar/routes/leaf_crud_i.py:582`; leader-ness from `_resolve_chat_session`'s `session.get("session_type") == "leader"` at :514, project id from the session row). Fanout composes EXISTING query helpers (kg-signals cache, execution FTS, takeaways, findings, verifications, budgeted `ask_tesserae`); planner/sufficiency/judge LLM calls reuse `stream_llm_response` (collected, isinstance-filtered) with `_parse_judge_json`-style forgiving parsing. Facts → new `extracted_facts` (migration **153**); eval → `answer_eval_runs`/`answer_eval_results` (migration **154**). Fail-open: any pipeline error → plain baseline turn.

**Tech Stack:** Python/raw SQLite/Litestar/pytest (LLM calls mocked in ALL tests); Vue 3 + Vitest; ruff 100.

**Verified anchors (do not re-derive):** hook region `streaming_helper.py:134-198` (status push :134, system prompt :136-141, llm_messages :146-150, routing :174-181, isinstance filter :189-198); `ChatStateService.push_delta(session_id, delta_type, data)` `chat_state_service.py:64` (stringly-typed; unknown types harmless downstream); `stream_llm_response(messages, model=, account_email=, backend=, cwd=, chat_mode=)` `conversation_streaming.py:291` yields `Union[str, ToolUseEvent, ThinkingEvent, RateLimitEvent]`; judge parse + cascade `goal_judge_service.py:478/:145-227/:49`; corpora: `ExecutionSearchService.search` `execution_search_service.py:16-95`, `harness_kg_signals.list_signals` :76, `harness_takeaways.list_for_project` :75, `findings.list_findings` :47, `verification_records.list_verifications` :30, `ask_tesserae(project_id, question, top_k=5)` `tesserae_integration.py:948-975` (60s subprocess; may return None); migrations max = **152**; script template `scripts/run_harness_evolution.py`; frontend `ProjectTeamLeaderChat.vue` delta dispatch ~:138-228, regex citations ~:276-300, cite chips :469-478.

**Conventions:** TDD fail-then-pass per task; targeted pytest while developing each task; the FINAL gate is Task 6's full-suite-first watchdog procedure (the repo rule; targeted fallback only on the documented hang, disclosed in the PR); migrations registered in BOTH `create_fresh_schema` AND `V07_MIGRATIONS`; fresh-DDL tests call `create_fresh_schema` directly; i18n keys in all four catalogs; stage explicit files only; no new ruff errors vs origin/main.

---

## Task 1: Migrations 153+154 — `extracted_facts` + answer-eval tables

**Files:**
- Create: `backend/app/db/schema/_extracted_facts.py`, `backend/app/db/schema/_answer_eval.py`
- Create: `backend/app/db/extracted_facts.py`, `backend/app/db/answer_eval.py`
- Modify: `backend/app/db/schema/__init__.py`, `backend/app/db/migrations/v07_features.py`
- Test: `backend/tests/test_extracted_facts_repo.py`, `backend/tests/test_answer_eval_repo.py`

DDL (mirror `_harness_state.py` style; idempotent `CREATE TABLE IF NOT EXISTS`):

```sql
CREATE TABLE IF NOT EXISTS extracted_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    super_agent_id TEXT,
    project_id TEXT,
    claim TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    dedup_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_extracted_facts_session ON extracted_facts(session_id);
CREATE INDEX IF NOT EXISTS idx_extracted_facts_project ON extracted_facts(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS answer_eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    question_count INTEGER NOT NULL DEFAULT 0,
    judge_backend TEXT,
    baseline_groundedness REAL, baseline_sufficiency REAL, baseline_quality REAL,
    pipeline_groundedness REAL, pipeline_sufficiency REAL, pipeline_quality REAL,
    delta_groundedness REAL, delta_sufficiency REAL, delta_quality REAL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','complete','failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS answer_eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    arm TEXT NOT NULL CHECK (arm IN ('baseline','pipeline')),
    answer_text TEXT,
    groundedness REAL, sufficiency REAL, quality REAL,
    judge_reason TEXT, tokens INTEGER, cost_usd REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES answer_eval_runs(id) ON DELETE CASCADE
);
```

Accessors:
- `extracted_facts.py`: `insert_facts(session_id, *, super_agent_id, project_id, facts: list[dict]) -> int` (each fact `{claim, evidence: list, confidence}`; `dedup_hash = sha256(f"{project_id or ''}|{session_id}|{claim}")` — session-scoped so a later session re-asserting the same claim still records it and `list_for_session` stays correct (cross-session dedup intentionally NOT attempted); `INSERT OR IGNORE`; returns inserted count), `list_for_session(session_id)`, `list_for_project(project_id, limit=50)`, `count_for_project(project_id)` — `evidence_json` deserialized to `evidence` (mirror `_row_to_dict` in `harness_takeaways.py:154`).
- `answer_eval.py`: `create_run(project_id, judge_backend) -> int`, `record_result(run_id, question, arm, answer_text, scores: dict, judge_reason, tokens, cost_usd) -> int`, `finalize_run(run_id, aggregates: dict) -> bool` (sets per-arm means + deltas + status='complete' + finished_at), `get_run(run_id)`, `list_runs(project_id=None, limit=20)`, `list_results(run_id)`.

Registration: `_migrate_153_extracted_facts` + `_migrate_154_answer_eval` (import+call schema fns) appended to `V07_MIGRATIONS` after `(152, ...)`; both schema fns called in `create_fresh_schema` (any position after core).

Tests (TDD; fixtures use the autouse `isolated_db`):
- migrations 153+154 registered (versions + names in `VERSIONED_MIGRATIONS`).
- fresh DDL has all three tables — direct `create_fresh_schema(conn)` on in-memory sqlite (Phase-3 lesson).
- `insert_facts` dedups within a session (same session+project+claim twice → 1 row; returns 1 then 0) and does NOT dedup across sessions (same claim, different session_id → 2 rows); evidence round-trips.
- `list_for_project` ordered desc; `count_for_project`.
- eval: `create_run` → `record_result` ×2 arms → `finalize_run` sets deltas; `list_results`; CHECK rejects bad arm (`pytest.raises(sqlite3.IntegrityError)`); FK cascade on run delete.

Commit: `feat(arag): extracted_facts + answer_eval stores (migrations 153, 154)`

---

## Task 2: `AnswerPipelineService` — pure core + fanout retrievers

**Files:**
- Create: `backend/app/services/answer_pipeline_service.py`
- Test: `backend/tests/test_answer_pipeline_core.py`, `backend/tests/test_answer_pipeline_fanout.py`

Design (one module, dependency-injected LLM):

```python
@dataclass
class RetrievedChunk:
    text: str
    source: str          # 'kg_signal'|'execution_log'|'takeaway'|'finding'|'verification'|'tesserae'
    provenance_key: str  # e.g. 'execution:exec-...' | 'signal:<id>' | 'takeaway:<id>' | 'tesserae:(project,question)'
    score: float = 0.0

LLMCall = Callable[[list[dict]], str]  # messages -> collected text (injection seam for tests)
```

- `_default_llm_call(backend, account_email, ...)` wraps `stream_llm_response(...)` with the **isinstance(str) filter** (crash risk verified) and `"".join`.
- `_parse_plan(text) -> list[dict]` and `_parse_sufficiency(text) -> dict` — forgiving: regex first `{...}`/`[...]` blob (mirror `goal_judge_service._parse_judge_json:478`); on failure, plan falls back to `[{"query": <raw turn>, "sources": ["all"]}]` and sufficiency to `{"sufficient": True, ...}` (fail-open).
- `gather_context(project_id, turn, *, backend="claude", account_email=None, llm_call=None, max_iterations=2, tesserae_budget=1, deadline_seconds=20) -> dict` — `llm_call` is the test seam; when None it is built internally from backend/account_email via `_default_llm_call` (so the hook passes `backend=`/`account_email=` and tests pass `llm_call=`). Returns `{chunks: list[RetrievedChunk], context_message: dict|None, iterations: int, sufficient: bool, gap: str|None}`:
  1. plan via `llm_call` (prompt asks for ≤4 sub-queries JSON, each with `sources` subset).
  2. fanout via `ThreadPoolExecutor` with REAL deadline mechanics: submit all retriever futures, `concurrent.futures.wait(futures, timeout=remaining_budget)`, then `executor.shutdown(wait=False, cancel_futures=True)` — unfinished sources contribute nothing. Retriever fns `_search_kg_signals`, `_search_execution_logs`, `_search_takeaways`, `_search_findings`, `_search_verifications`, `_ask_tesserae_budgeted` — each returning ≤K chunks with provenance keys; every retriever wrapped try/except → empty list (fail-open per source). **Project scoping is mandatory — the raw helpers are global (cross-project leak):** a memoized `_project_execution_ids(project_id) -> set[str]` derives allowed ids via `SELECT e.execution_id FROM execution_logs e JOIN project_paths p ON p.trigger_id = e.trigger_id WHERE p.project_id = ?` (`project_paths.project_id` verified at `schema/_core.py:51`); `_search_execution_logs` post-filters `ExecutionSearchService.search` hits by that set; `_search_findings` filters `list_findings` by it; `_search_verifications` queries `list_verifications(execution_id)` per allowed id (capped to the most recent ~10). `_search_takeaways`/`_search_kg_signals` are already project-keyed. Tesserae: submitted ONLY when `remaining_budget > 25s` AND the kg-signal cache pass produced nothing relevant AND the project has a tesserae root (60s subprocess — the latency hazard). **Intentional consequence, stated:** with the chat default `deadline_seconds=20`, live `ask_tesserae` NEVER runs in a leader turn — chat relies on the cached `harness_kg_signals` answers (which Tesserae populated offline). Live Tesserae fires only for callers that pass a larger deadline: the EVAL pipeline arm uses `deadline_seconds=90`. This is the latency-honest design, not an accident.
  3. sufficiency via `llm_call` (prompt: question + numbered chunks → JSON `{sufficient, gap, feedback}`); if insufficient and iterations remain → re-plan with `feedback` appended; else proceed.
  4. dedupe chunks by provenance_key; build `context_message = {"role": "system", "content": ...}` — INSERTED before the final user message (`llm_messages.insert(-1, ctx)`; proxy/chat APIs behave better with system context ahead of the final user prompt) — with numbered `[F1] (source, key) text` lines + cite-marker instructions + an explicit "context may be partial: <gap>" line when `not sufficient`.
- `extract_facts_from_answer(answer_text, chunks, *, llm_call) -> list[dict]` — prompt yields JSON list of `{claim, fact_ids: [F1...], confidence}`; map fact_ids back to chunk provenance into `evidence` lists; forgiving parse → `[]` on failure.

Tests — pure-core (`test_answer_pipeline_core.py`, no DB):
- `_parse_plan`: valid JSON array; JSON embedded in prose; garbage → raw-turn fallback; >4 queries truncated.
- `_parse_sufficiency`: valid; garbage → sufficient=True fail-open.
- `gather_context` with stubbed `llm_call` + monkeypatched retrievers: (a) sufficient on round 1 → 1 iteration, context_message contains `[F1]` + provenance; (b) insufficient → feedback string reaches the round-2 plan prompt, iterations==2; (c) all retrievers raise → empty chunks, context_message is None, no exception; (d) deadline exceeded → stops early.
- `extract_facts_from_answer`: maps fact_ids→evidence; garbage → [].

Tests — fanout (`test_answer_pipeline_fanout.py`, real `isolated_db`):
- seed a kg signal + an execution_logs row (FTS) + a takeaway + a finding + a verification record; each `_search_*` returns chunks with the right provenance prefix.
- **two-project leak test:** seed TWO projects with their own triggers/project_paths/executions/findings; fanout for project A returns ZERO chunks whose provenance keys belong to project B (assert on every source).
- `_ask_tesserae_budgeted`: monkeypatch `ask_tesserae` → returns chunk once, second call within same gather returns nothing (budget); when patched to return None → empty.

Commit: `feat(arag): AnswerPipelineService — planner, fanout, sufficiency loop, fact extraction`

---

## Task 3: Hook into the leader turn

**Files:**
- Modify: `backend/app/services/streaming_helper.py` (kwargs + hook + deltas)
- Modify: `backend/app_litestar/routes/leaf_crud_i.py` (thread the flag from :555-595)
- Test: `backend/tests/test_answer_pipeline_hook.py`

1. `run_streaming_response(..., rag_enabled: bool = False, rag_project_id: Optional[str] = None)` — defaults keep every other caller unchanged.
2. In the thread body, after `llm_messages` is built (:146-150) and before the routing branch (~:174):

```python
            if rag_enabled and rag_project_id:
                try:
                    ChatStateService.push_delta(_session_id, "planning", {"status": "started"})
                    rag = AnswerPipelineService.gather_context(
                        rag_project_id, content_of_last_user_turn, backend=backend,
                        account_email=account_id,
                    )
                    ChatStateService.push_delta(_session_id, "retrieval", {
                        "chunks": len(rag["chunks"]), "iterations": rag["iterations"],
                        "sufficient": rag["sufficient"],
                    })
                    if rag.get("context_message"):
                        # BEFORE the final user message (which is already in
                        # llm_messages — it was persisted pre-stream).
                        llm_messages.insert(-1, rag["context_message"])
                    _rag_chunks = rag["chunks"]
                except Exception:
                    logger.warning("answer pipeline failed — falling back to baseline", exc_info=True)
                    _rag_chunks = []
            else:
                _rag_chunks = []
```

   (Derive `content_of_last_user_turn` from the last user entry in `llm_messages`/conversation log — inspect the local shape at :146-150 and use the real variable. Lazy-import the service inside the function, matching the module's deferred-import style.)
3. Post-finish (where `_finalize` runs, :151-170 region): if `_rag_chunks`, best-effort `extract_facts_from_answer` + `extracted_facts.insert_facts` + `push_delta("citations", ...)`, all inside try/except. The delta arrives AFTER `finish` by design (extraction is an LLM call; the visible turn must not wait) — the FRONTEND attaches late citations to the LAST assistant message (Task 5), since `finish` clears `activeAssistant` (`ProjectTeamLeaderChat.vue:220`). Payload pre-mapped to the chip shape `{kind, value}` the chips expect (:468): `{"message_scope": "last_assistant", "citations": [{"kind": <source>, "value": <provenance_key>}...], "facts": [{claim, evidence, confidence}...]}`.
4. **Retry-queue preservation:** `run_streaming_response` parks rate-limited turns in `chat_retry_queue` (:347) and `chat_retry_service._dispatch` re-calls it (:137) with only the legacy fields — so a retried leader turn would silently lose RAG. Fix inside `chat_retry_service._dispatch`: recompute `rag_enabled`/`rag_project_id` from `get_super_agent_session(session_id)` (`session_type == "leader"` + project_id) and pass them through. One test: a parked leader-session retry re-dispatches with `rag_enabled=True` (mock the session row + run_streaming_response).
5. `leaf_crud_i.py` (:555-595): `_resolve_chat_session`'s resolved dict exposes the session row (leader-ness at :514: `session.get("session_type") == "leader"`). Compute `rag_enabled = session_type == "leader" and bool(project_id)`; pass `rag_enabled=rag_enabled, rag_project_id=project_id` to the `run_streaming_response(` call at :582. Confirm the locals' names in the route — `resolved` carries what's needed; adapt minimally.

Tests (mock `AnswerPipelineService.gather_context` + the LLM stream; mirror `tests/test_streaming_helper_rotation.py:51`'s sync-thread/Event patterns; **force the CLIProxy path** with `use_cli_agent=False` or monkeypatched `should_route_via_cli_agent` — YOLO defaults can route to the CLI-agent path (`cli_agent_runner_service.py:426`) and the captured `stream_llm_response` would never fire):
- rag_enabled+project → gather called; context message inserted BEFORE the final user message (assert ordering via captured llm_messages on the mocked `stream_llm_response`: `messages[-1]` is the user turn, `messages[-2]` is the RAG system context); `planning` + `retrieval` deltas pushed.
- gather raises → turn proceeds, no context appended, no exception escapes (fail-open).
- rag_enabled=False (default) → gather NOT called (every existing caller unaffected).
- facts persisted + `citations` delta after finish (mock extractor returning one fact).

Commit: `feat(arag): leader-chat hook — sufficiency loop before the answer, citations after`

---

## Task 4: `AnswerEvalService` + routes + script

**Files:**
- Create: `backend/app/services/answer_eval_service.py`, `backend/app_litestar/routes/answer_eval.py`, `backend/scripts/run_answer_eval.py`
- Modify: `backend/app_litestar/main.py` (register router — mirror how `quality_ratings_router` is imported/registered)
- Test: `backend/tests/test_answer_eval_service.py`, `backend/tests/test_answer_eval_routes.py`

`AnswerEvalService`:
- `build_question_set(project_id, n=8) -> list[str]`: sample from `harness_kg_signals.list_signals(project_id)` questions + recent execution prompts **project-scoped via the same `_project_execution_ids` JOIN as the fanout** (`get_execution_logs_filtered` is global — verified no project filter at `execution_logs.py:158`; filter rows to the allowed id set, take first prompt lines, dedupe) + `session_takeaways.list_for_project` content-derived questions; deterministic order (sorted + sliced), pad with generic project questions if short.
- `run_eval(project_id, *, n=8, judge_backend="claude", llm_call=None, pipeline_llm_call=None, run_id: int | None = None) -> int`: uses the provided `run_id` when given (the async route preallocates), else `create_run` — ONE owner per run, no orphans → per question: arm A baseline = `llm_call([system, user])`; arm B pipeline = `gather_context(...)` then same call with the context message; judge each answer **blind** (prompt contains question + answer + the sources list for groundedness checking; never names the arm) → forgiving-parse `{groundedness, sufficiency, quality, reason}` each 0..1 → `record_result`; `finalize_run` with per-arm means + deltas. Every LLM call injected (`llm_call` seam) so tests are pure; the default wraps `stream_llm_response` exactly like Task 2's `_default_llm_call`.
- Fail-closed per question (exception → record zeros + reason='error'), run always finalizes.

Routes (mirror `quality_ratings.py` style, `Router(path="/")`, absolute paths):
- `POST /admin/answer-eval/run` body `{project_id, n?}` → `run_id = create_run(...)`, daemon thread runs `run_eval(..., run_id=run_id)`, returns `{run_id}` immediately (Phase-4 async idiom; the thread NEVER creates a second run).
- `GET /admin/answer-eval/runs?project_id=` → `list_runs`; `GET /admin/answer-eval/runs/{run_id:int}` → run + results.

Script `scripts/run_answer_eval.py` (model on `run_harness_evolution.py`): argparse `--project-id --n --judge-backend`, calls `run_eval` synchronously, prints the aggregate table.

Tests: question-set sampling (seeded db rows → deterministic set, padding); **two-project question-set leak test** (project B's prompts never sampled for project A); `run_eval` with stubbed llm_calls + judge (two questions → 4 result rows, aggregates + deltas correct, blind prompt contains no arm names — assert on captured judge prompts); per-question failure → zeros + run completes; route POST returns run_id without blocking (mock service), GETs return rows; router registered.

Commit: `feat(arag): answer eval — question set, blind LLM-as-judge, baseline-vs-pipeline deltas`

---

## Task 5: Frontend — deltas, citations, dashboard card

**Files:**
- Modify: `frontend/src/components/projects/ProjectTeamLeaderChat.vue`
- Create: `frontend/src/views/dashboards/cards/AnswerGroundednessCard.vue` (the REAL cards directory — verified)
- Modify: `frontend/src/views/dashboards/QualityPage.vue` (:37 region) — NOTE: the page has NO project context; the card is therefore GLOBAL: it shows the latest finished run across all projects with the project name displayed (no selector in v1)
- Modify: `frontend/src/services/api/` (new `answerEvalApi` in the idiomatic module + types + barrel export)
- Modify: `frontend/src/locales/{en,ko,ja,zh}.json`
- Test: extend/create colocated tests mirroring `HarnessStatePanel.test.ts` conventions

1. `ProjectTeamLeaderChat.vue` delta dispatch (~:138-228): add `planning` branch (progress line beside the thinking fold ~:145), `retrieval` branch (chunk/iteration count line), and a `citations` branch that — because it arrives AFTER `finish` has cleared `activeAssistant` (:220) — attaches the payload's pre-mapped `{kind, value}` citations to the LAST assistant message in the list, replacing that message's regex-derived citations (`extractCitations` ~:276-300 stays as the fallback for non-RAG turns).
2. `answerEvalApi`: `listRuns(projectId?)`, `getRun(id)`, `startRun(projectId, n?)` via `apiFetch` (mirror `executionApi` style in `services/api/triggers.ts`; new module `services/api/answer-eval.ts` + types + barrel export).
3. Card: latest finished run across ALL projects (QualityPage has no project context — verified) — project name + three delta stats (groundedness/sufficiency/quality, pipeline−baseline) with up/down styling; empty-state when no runs. Mount on QualityPage.
4. i18n: `answerEval.*` + chat progress strings, four catalogs, key-identical.

Tests (TDD): chat — `citations` delta replaces regex citations (mount with mocked api, feed deltas, assert chips); `planning`/`retrieval` render progress and unknown-type safety holds; card — renders deltas from mocked api, empty state. Run the full frontend suite (baseline 7 known failures, no new) + `npx vue-tsc --noEmit`.

Commit: `feat(arag): chat progress + backend citations + answer-groundedness card`

---

## Task 6: Verification sweep

1. Backend — honor the repo's full-suite gate with a watchdog: FIRST attempt the full `cd backend && uv run pytest -q` in a background shell with a 12-minute watchdog loop; if it completes, that IS the gate. If it hangs (the documented ~40-46% serial hang — project memory; all four Harness-1 phases hit it), kill it and run the comprehensive targeted substitute: ALL new test files + regressions `tests/test_execution_service.py tests/test_litestar_streams.py tests/test_harness_state_repo.py tests/test_goal_loop_reentry.py tests/test_redispatch_service.py tests/test_execution_log_checkpoint.py tests/test_budget_monitor_per_run.py`. DISCLOSE in the PR which path ran and why — never present targeted runs as the full suite.
2. `ruff format` + `ruff check` on every touched backend file — no new errors vs origin/main.
3. Frontend: `npm run test:run` (baseline) + `just build`.
4. Stage explicit files only (per-task Files lists), never `git add -A`.

Commit (if needed): `chore(arag): format/lint pass`

---

## Task 7: The real eval run (orchestrator-executed, post-implementation)

NOT a subagent task. The orchestrator runs `uv run python scripts/run_answer_eval.py --project-id <the dev DB's main project> --n 6` against the development database (real data, real LLM calls, blind judge), captures the aggregate deltas, and reports the numbers in the PR description — positive or not. If no project has enough corpus rows, seed the question set from whatever exists and report the limitation honestly.

---

## Self-Review notes (author)
- Spec coverage: stores (T1), loop core+fanout (T2), hook+facts+citations (T3), eval+routes+script (T4), frontend (T5), gates (T6), real measurement (T7). All spec units covered.
- Type consistency: `RetrievedChunk{text,source,provenance_key,score}`; `gather_context(...) -> {chunks, context_message, iterations, sufficient, gap}`; `insert_facts(session_id, *, super_agent_id, project_id, facts)`; `run_eval(project_id, *, n, judge_backend, llm_call, pipeline_llm_call) -> run_id`; deltas `planning`/`retrieval`/`citations` — consistent across tasks.
- Confirm-at-execution points (flagged in-task): the last-user-turn local at the hook site; `_resolve_chat_session`'s resolved dict shape at the route; streaming-helper test conventions; frontend cards directory + quality view; `answerEvalApi` module placement.
