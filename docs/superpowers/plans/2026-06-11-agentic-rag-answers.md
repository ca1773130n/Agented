# Agentic-RAG Dependable Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Google-style agentic RAG for leader chat — planner → multi-source fanout → sufficient-context check with gap feedback → iterate (≤2) → grounded answer; extracted facts persisted with provenance; a baseline-vs-pipeline usefulness eval with LLM-as-judge, persisted and surfaced.

**Architecture:** A server-side `AnswerPipelineService` hooks into `run_streaming_response` (`streaming_helper.py`, after `llm_messages` assembly at :146-150, before the routing branch ~:174) behind a `rag_enabled` kwarg threaded from the ONE leader-chat call site (`app_litestar/routes/leaf_crud_i.py:582`; leader-ness from `_resolve_chat_session`'s `session.get("session_type") == "leader"` at :514, project id from the session row). Fanout composes EXISTING query helpers (kg-signals cache, execution FTS, takeaways, findings, verifications, budgeted `ask_tesserae`); planner/sufficiency/judge LLM calls reuse `stream_llm_response` (collected, isinstance-filtered) with `_parse_judge_json`-style forgiving parsing. Facts → new `extracted_facts` (migration **153**); eval → `answer_eval_runs`/`answer_eval_results` (migration **154**). Fail-open: any pipeline error → plain baseline turn.

**Tech Stack:** Python/raw SQLite/Litestar/pytest (LLM calls mocked in ALL tests); Vue 3 + Vitest; ruff 100.

**Verified anchors (do not re-derive):** hook region `streaming_helper.py:134-198` (status push :134, system prompt :136-141, llm_messages :146-150, routing :174-181, isinstance filter :189-198); `ChatStateService.push_delta(session_id, delta_type, data)` `chat_state_service.py:64` (stringly-typed; unknown types harmless downstream); `stream_llm_response(messages, model=, account_email=, backend=, cwd=, chat_mode=)` `conversation_streaming.py:291` yields `Union[str, ToolUseEvent, ThinkingEvent, RateLimitEvent]`; judge parse + cascade `goal_judge_service.py:478/:145-227/:49`; corpora: `ExecutionSearchService.search` `execution_search_service.py:16-95`, `harness_kg_signals.list_signals` :76, `harness_takeaways.list_for_project` :75, `findings.list_findings` :47, `verification_records.list_verifications` :30, `ask_tesserae(project_id, question, top_k=5)` `tesserae_integration.py:948-975` (60s subprocess; may return None); migrations max = **152**; script template `scripts/run_harness_evolution.py`; frontend `ProjectTeamLeaderChat.vue` delta dispatch ~:138-228, regex citations ~:276-300, cite chips :469-478.

**Conventions:** TDD fail-then-pass per task; targeted pytest only (full serial suite hangs — disclose substitution in PR); migrations registered in BOTH `create_fresh_schema` AND `V07_MIGRATIONS`; fresh-DDL tests call `create_fresh_schema` directly; i18n keys in all four catalogs; stage explicit files only; no new ruff errors vs origin/main.

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
    status TEXT NOT NULL DEFAULT 'running',
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
- `extracted_facts.py`: `insert_facts(session_id, *, super_agent_id, project_id, facts: list[dict]) -> int` (each fact `{claim, evidence: list, confidence}`; `dedup_hash = sha256(f"{project_id or ''}|{claim}")`; `INSERT OR IGNORE`; returns inserted count), `list_for_session(session_id)`, `list_for_project(project_id, limit=50)`, `count_for_project(project_id)` — `evidence_json` deserialized to `evidence` (mirror `_row_to_dict` in `harness_takeaways.py:154`).
- `answer_eval.py`: `create_run(project_id, judge_backend) -> int`, `record_result(run_id, question, arm, answer_text, scores: dict, judge_reason, tokens, cost_usd) -> int`, `finalize_run(run_id, aggregates: dict) -> bool` (sets per-arm means + deltas + status='complete' + finished_at), `get_run(run_id)`, `list_runs(project_id=None, limit=20)`, `list_results(run_id)`.

Registration: `_migrate_153_extracted_facts` + `_migrate_154_answer_eval` (import+call schema fns) appended to `V07_MIGRATIONS` after `(152, ...)`; both schema fns called in `create_fresh_schema` (any position after core).

Tests (TDD; fixtures use the autouse `isolated_db`):
- migrations 153+154 registered (versions + names in `VERSIONED_MIGRATIONS`).
- fresh DDL has all three tables — direct `create_fresh_schema(conn)` on in-memory sqlite (Phase-3 lesson).
- `insert_facts` dedups (same project+claim twice → 1 row; returns 1 then 0); evidence round-trips.
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
- `gather_context(project_id, turn, *, llm_call, max_iterations=2, tesserae_budget=1, deadline_seconds=20) -> dict` returning `{chunks: list[RetrievedChunk], context_message: dict|None, iterations: int, sufficient: bool, gap: str|None}`:
  1. plan via `llm_call` (prompt asks for ≤4 sub-queries JSON, each with `sources` subset).
  2. fanout via `ThreadPoolExecutor`: per-source retriever fns `_search_kg_signals`, `_search_execution_logs`, `_search_takeaways`, `_search_findings`, `_search_verifications`, `_ask_tesserae_budgeted` — each thin over the verified helpers, returning ≤K chunks with provenance keys; every retriever wrapped try/except → empty list (fail-open per source). Tesserae: only if a kg-signal cache pass produced nothing relevant AND budget remains AND the project has a tesserae root (the helper returns None gracefully otherwise).
  3. sufficiency via `llm_call` (prompt: question + numbered chunks → JSON `{sufficient, gap, feedback}`); if insufficient and iterations remain → re-plan with `feedback` appended; else proceed.
  4. dedupe chunks by provenance_key; build `context_message = {"role": "system", "content": ...}` with numbered `[F1] (source, key) text` lines + cite-marker instructions + an explicit "context may be partial: <gap>" line when `not sufficient`.
- `extract_facts_from_answer(answer_text, chunks, *, llm_call) -> list[dict]` — prompt yields JSON list of `{claim, fact_ids: [F1...], confidence}`; map fact_ids back to chunk provenance into `evidence` lists; forgiving parse → `[]` on failure.

Tests — pure-core (`test_answer_pipeline_core.py`, no DB):
- `_parse_plan`: valid JSON array; JSON embedded in prose; garbage → raw-turn fallback; >4 queries truncated.
- `_parse_sufficiency`: valid; garbage → sufficient=True fail-open.
- `gather_context` with stubbed `llm_call` + monkeypatched retrievers: (a) sufficient on round 1 → 1 iteration, context_message contains `[F1]` + provenance; (b) insufficient → feedback string reaches the round-2 plan prompt, iterations==2; (c) all retrievers raise → empty chunks, context_message is None, no exception; (d) deadline exceeded → stops early.
- `extract_facts_from_answer`: maps fact_ids→evidence; garbage → [].

Tests — fanout (`test_answer_pipeline_fanout.py`, real `isolated_db`):
- seed a kg signal + an execution_logs row (FTS) + a takeaway + a finding + a verification record; each `_search_*` returns chunks with the right provenance prefix.
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
                        llm_messages.append(rag["context_message"])
                    _rag_chunks = rag["chunks"]
                except Exception:
                    logger.warning("answer pipeline failed — falling back to baseline", exc_info=True)
                    _rag_chunks = []
            else:
                _rag_chunks = []
```

   (Derive `content_of_last_user_turn` from the last user entry in `llm_messages`/conversation log — inspect the local shape at :146-150 and use the real variable. Lazy-import the service inside the function, matching the module's deferred-import style.)
3. Post-finish (where `_finalize` runs, :151-170 region): if `_rag_chunks`, best-effort `extract_facts_from_answer` + `extracted_facts.insert_facts` + `push_delta("citations", {"facts": [...]})`, all inside try/except. Citations payload: `[{claim, evidence:[{source, provenance_key}], confidence}]`.
4. `leaf_crud_i.py` (:555-595): `_resolve_chat_session`'s resolved dict exposes the session row (leader-ness at :514: `session.get("session_type") == "leader"`). Compute `rag_enabled = session_type == "leader" and bool(project_id)`; pass `rag_enabled=rag_enabled, rag_project_id=project_id` to the `run_streaming_response(` call at :582. Confirm the locals' names in the route — `resolved` carries what's needed; adapt minimally.

Tests (mock `AnswerPipelineService.gather_context` + the LLM stream; mirror the existing streaming-helper test conventions — find them via `grep -rln "run_streaming_response" backend/tests/`):
- rag_enabled+project → gather called; context message appended (assert via captured llm_messages on the mocked `stream_llm_response`); `planning` + `retrieval` deltas pushed.
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
- `build_question_set(project_id, n=8) -> list[str]`: sample from `harness_kg_signals.list_signals` questions + recent `execution_logs` prompts (`get_execution_logs_filtered(limit=...)`, first line, deduped) + `session_takeaways.list_for_project` content-derived questions; deterministic order (sorted + sliced), pad with generic project questions if short.
- `run_eval(project_id, *, n=8, judge_backend="claude", llm_call=None, pipeline_llm_call=None) -> int`: `create_run` → per question: arm A baseline = `llm_call([system, user])`; arm B pipeline = `gather_context(...)` then same call with the context message; judge each answer **blind** (prompt contains question + answer + the sources list for groundedness checking; never names the arm) → forgiving-parse `{groundedness, sufficiency, quality, reason}` each 0..1 → `record_result`; `finalize_run` with per-arm means + deltas. Every LLM call injected (`llm_call` seam) so tests are pure; the default wraps `stream_llm_response` exactly like Task 2's `_default_llm_call`.
- Fail-closed per question (exception → record zeros + reason='error'), run always finalizes.

Routes (mirror `quality_ratings.py` style, `Router(path="/")`, absolute paths):
- `POST /admin/answer-eval/run` body `{project_id, n?}` → spawns a daemon thread running `run_eval`, returns `{run_id}` immediately (preallocate via `create_run`, thread takes it — mirror the Phase-4 async-dispatch idiom: nothing blocking the request).
- `GET /admin/answer-eval/runs?project_id=` → `list_runs`; `GET /admin/answer-eval/runs/{run_id:int}` → run + results.

Script `scripts/run_answer_eval.py` (model on `run_harness_evolution.py`): argparse `--project-id --n --judge-backend`, calls `run_eval` synchronously, prints the aggregate table.

Tests: question-set sampling (seeded db rows → deterministic set, padding); `run_eval` with stubbed llm_calls + judge (two questions → 4 result rows, aggregates + deltas correct, blind prompt contains no arm names — assert on captured judge prompts); per-question failure → zeros + run completes; route POST returns run_id without blocking (mock service), GETs return rows; router registered.

Commit: `feat(arag): answer eval — question set, blind LLM-as-judge, baseline-vs-pipeline deltas`

---

## Task 5: Frontend — deltas, citations, dashboard card

**Files:**
- Modify: `frontend/src/components/projects/ProjectTeamLeaderChat.vue`
- Create: `frontend/src/components/dashboards/cards/AnswerGroundednessCard.vue` (place beside existing cards — confirm dir via `ls frontend/src/views/dashboards/cards frontend/src/components/dashboards 2>/dev/null`)
- Modify: the Quality dashboard view that hosts cards (locate via `grep -rln "QualityPage\|qualityApi" frontend/src/views`)
- Modify: `frontend/src/services/api/` (new `answerEvalApi` in the idiomatic module + types + barrel export)
- Modify: `frontend/src/locales/{en,ko,ja,zh}.json`
- Test: extend/create colocated tests mirroring `HarnessStatePanel.test.ts` conventions

1. `ProjectTeamLeaderChat.vue` delta dispatch (~:138-228): add `planning` branch (progress line beside the thinking fold ~:145), `retrieval` branch (chunk/iteration count line), `citations` branch — store payload; at finish, when backend citations exist use them for the Cited row (:469-478) and skip the regex (`extractCitations` ~:276-300 stays as fallback when absent).
2. `answerEvalApi`: `listRuns(projectId?)`, `getRun(id)`, `startRun(projectId, n?)` via `apiFetch` (mirror `executionApi` style in `services/api/triggers.ts`; new module `services/api/answer-eval.ts` + types + barrel export).
3. Card: latest finished run for the page's project — three delta stats (groundedness/sufficiency/quality, pipeline−baseline) with up/down styling; empty-state when no runs. Mount on the quality dashboard.
4. i18n: `answerEval.*` + chat progress strings, four catalogs, key-identical.

Tests (TDD): chat — `citations` delta replaces regex citations (mount with mocked api, feed deltas, assert chips); `planning`/`retrieval` render progress and unknown-type safety holds; card — renders deltas from mocked api, empty state. Run the full frontend suite (baseline 7 known failures, no new) + `npx vue-tsc --noEmit`.

Commit: `feat(arag): chat progress + backend citations + answer-groundedness card`

---

## Task 6: Verification sweep

1. Backend: `uv run pytest` on ALL new test files + regressions: `tests/test_execution_service.py tests/test_litestar_streams.py tests/test_harness_state_repo.py tests/test_goal_loop_reentry.py tests/test_redispatch_service.py` (full-suite substitution disclosed in PR — known serial hang).
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
