# Agentic-RAG Dependable Answers for Leader Chat (Design)

**Date:** 2026-06-11
**Status:** Approved (autonomous directive — no user gates)
**Source approach:** Google Research, "Unlocking dependable responses with Gemini
Enterprise Agent Platform's Agentic RAG" (research.google/blog, June 5 2026) —
planner → query rewrite/fanout → **Sufficient Context Agent** (gap-naming
feedback) → iterate → grounded answer. Their results: up to +34% factuality;
90.1% cross-corpus accuracy on FramesQA via LLM-as-judge.
**Grounding:** 5-agent Understand workflow over Agented (ARAG-1); all anchors
below verified at file:line this session.

## Operator requirements (verbatim intent)
1. Integrate the agentic-RAG approach into Agented's answer path.
2. **Extract facts** (via Tesserae and the other knowledge stores) so answers
   are grounded in provenance-keyed claims, persisted.
3. **Measure usefulness** — an eval proving the pipeline measurably improves
   product answers (baseline vs pipeline, judged, persisted, surfaced) — "an
   achievement that affects the product," not just shipped code.

## The mapping

Google's "islands of data" are real in Agented: a leader answering "what broke
in last week's security runs and did we fix it?" needs execution logs (FTS),
findings, verification records, takeaways, and the Tesserae KG — today it gets
one LLM call with whatever happens to be in the conversation log. The pipeline
closes that gap server-side.

**Why server-side fanout is forced, not chosen:** the leader-chat path applies
no forge bundle and no MCP config overlay (`_build_env`,
`cli_agent_runner_service.py:316-337`); the `tesserae-<project_id>` MCP binding
is consumed only on the project-SESSION path (`project_session_manager.py:943-949`).
In-harness `tesserae_ask` in chat is effectively absent. The pipeline must call
the corpora itself, before the answer LLM is invoked. (Also: one operator turn
is ONE opaque LLM invocation — the loop must run before it, not inside it.)

---

## Unit A — `AnswerPipelineService` (the loop)

New `backend/app/services/answer_pipeline_service.py`. Hook: inside
`run_streaming_response` (`streaming_helper.py`), after `llm_messages` assembly
(:146-150) and before the routing branch (~:174) — gated on a new
`rag_enabled: bool = False` kwarg threaded from the leader-chat call site
(which resolves session_type; `streaming_helper` stays generic). Both the
CLIProxy and CLI-agent dispatch paths see the same enriched `llm_messages`.

Loop (max **2** iterations, hard wall-clock budget ~20s excluding Tesserae,
all caps config-constants):

1. **Plan** — one cheap LLM call (haiku-class; defaults mirror
   `GoalJudgeService` per-backend judge models at `goal_judge_service.py:49`)
   decomposes the operator turn into ≤4 sub-queries, each tagged with target
   corpora. Call pattern: `stream_llm_response(...)` (`conversation_streaming.py:291`)
   collected with **isinstance(str) filtering** (ToolUseEvent/ThinkingEvent
   interleave on CLI paths — crash risk verified). Forgiving JSON parse mirrors
   `_parse_judge_json` (`goal_judge_service.py:478`): regex the first `{...}`
   blob; unparseable → single sub-query = the raw turn.
2. **Fanout** — `ThreadPoolExecutor` over per-corpus retrievers, each returning
   `RetrievedChunk{text, source, provenance_key, score}`:
   - `harness_kg_signals` cache FIRST (`list_signals`, `app/db/harness_kg_signals.py:76`) — free, question-keyed Tesserae answers.
   - `ExecutionSearchService.search` (`app/services/execution_search_service.py:16-95`) — BM25 over execution logs; provenance `execution_id`.
   - `session_takeaways` (`list_for_project`, `app/db/harness_takeaways.py:75`) — provenance takeaway id + session.
   - `findings` (`list_findings`, `app/db/findings.py:47`) — provenance execution_id + file_ref.
   - `verification_records` (`list_verifications`, `app/db/verification_records.py:30`) — provenance execution_id.
   - `ask_tesserae` (`tesserae_integration.py:948-975`) — **budgeted: at most 1 call per turn, only on cache miss, only if the project has a tesserae root**; 60s CLI shell-out is the latency hazard. Provenance is coarse: (project_id, question).
3. **Sufficiency check** — one judge call: given the operator turn + retrieved
   chunks, return `{sufficient: bool, gap: str, feedback: str}` (the Google
   "missing pieces analysis"). On insufficient and iterations remaining, the
   `feedback` string goes back to step 1 as the re-plan hint. On final
   insufficiency: proceed anyway but mark the context block as partial (the
   honest "answer with what we have, flagged" behavior).
4. **Inject** — one system-role context message appended to `llm_messages`:
   numbered fact lines, each with its provenance key, plus instructions to cite
   `[F1]`-style markers and say so when context is insufficient.
5. **Stream progress** — `ChatStateService.push_delta` types `planning` /
   `retrieval` (stringly-typed wire, `chat_state_service.py:64-90`; replay +
   reconnect free; unknown types fall through harmlessly in every consumer).
6. **Post-answer** — after `finish`: extract facts (Unit B) and push a
   `citations` delta with the structured chunks actually cited.

**Fail-open invariant:** any pipeline exception → log + proceed with the plain
baseline messages. The operator's turn must never block on RAG infra (mirror
the `_eval_gate` discipline, inverted: answers fail open, evals fail closed).

## Unit B — extracted facts (persistence + citations)

- New table `extracted_facts` (schema module `_extracted_facts.py`, mirror
  `session_takeaways`): id PK, `session_id`, `super_agent_id`, `project_id`,
  `claim TEXT`, `evidence_json` (corpus + provenance key + quote span),
  `confidence REAL`, `dedup_hash` (sha256 of project+claim, mirroring
  `harness_kg_signals`' signal-id discipline; UNIQUE), `created_at`.
  Registered in **both** `create_fresh_schema` and **migration 153**
  (current max verified: 152). Accessor `app/db/extracted_facts.py`:
  `insert_facts` (dedup-tolerant), `list_for_session`, `list_for_project`,
  `count_for_project`.
- Fact extraction = one cheap LLM call over (answer text + injected context):
  claims actually asserted in the answer, each linked to the chunk(s) that
  ground it; confidence from the extractor. Runs post-finish, best-effort,
  never blocks the stream.
- **Citations delta**: backend-pushed structured `citations` replacing the
  frontend's regex extraction as the primary source
  (`ProjectTeamLeaderChat.vue` `extractCitations` ~:276-300 stays as fallback
  for non-RAG turns). The existing "Cited" chip row (:469-478) renders it; the
  "Queried" row (:438-447) keeps riding `harness_evidence` (the existing
  `_record_tool_use_evidence` tap stays untouched).

## Unit C — usefulness eval (the achievement)

- New tables (migration **154**): `answer_eval_runs` (id, project_id,
  question_count, baseline/pipeline aggregate scores per axis, delta,
  judge_backend, created_at) and `answer_eval_results` (run FK, question,
  arm (`baseline`|`pipeline`), answer_text, groundedness REAL, sufficiency
  REAL, quality REAL, judge_reason, tokens, cost — shape mirrors
  `goal_loop_iterations`, `app/db/goal_loop.py:55/76`).
- `AnswerEvalService`:
  1. **Question set from the product's own data**: sample from
     `harness_kg_signals` questions, recent `execution_logs` prompts, and
     `session_takeaways` content (N configurable, default 8).
  2. For each question run both arms: baseline = plain single LLM call;
     pipeline = Unit A's gather+inject then the same LLM call.
  3. **LLM-as-judge** per answer on three axes (groundedness: claims traceable
     to provided sources; sufficiency: addressed all parts; quality), 0..1
     each, via the `GoalJudgeService`-style CLIProxy/judge cascade with the
     forgiving parse. Judge never sees which arm produced the answer
     (blind: answers presented as "Answer A").
  4. Persist per-question rows + run aggregate with per-axis
     `delta = pipeline − baseline`.
- Entry points: `scripts/run_answer_eval.py` (modeled on
  `scripts/run_harness_evolution.py`) + admin routes
  `POST /admin/answer-eval/run` (async, returns run id) and
  `GET /admin/answer-eval/runs` / `/runs/{id}`.
- **The deliverable includes one real run** against this repo's own project
  data with the resulting numbers reported in the PR (small N; real LLM calls;
  judged blind). If the delta is not positive, that is reported too — the
  measurement is the deliverable, not the cheerleading.

## Unit D — frontend (minimal)

- `ProjectTeamLeaderChat.vue`: handle `planning`/`retrieval` deltas as progress
  folds beside the existing thinking fold (:145); handle `citations` delta
  feeding the existing cite-chip renderer; prefer backend citations over the
  regex when present.
- Dashboards: one "Answer groundedness" card on the Quality page riding the
  existing stats shape (`AgentQualityScoringPage.vue:28-63` pattern), backed by
  `GET /admin/answer-eval/runs` aggregates.
- i18n for new strings in all four catalogs.

## Verification gates
Targeted backend pytest (LLM calls mocked everywhere in tests; the judge/
planner parse functions get pure-function tests); frontend `npm run test:run`
at baseline + new delta-handling tests; `just build`; ruff no-new-errors vs
main. The eval's REAL run is a manual post-merge-gate step executed once by the
orchestrator (not in CI). Codex xhigh plan review iterated to green; opus final
review; codex PR review — per the standing pipeline. No user gates (directive).

## Out of scope
Embedding/vector index over execution logs (FTS only); a docs corpus; Tesserae
node-level provenance (its CLI returns opaque markdown — coarse provenance
tolerated and recorded as such); multi-turn pipeline memory; cross-project
fanout; replacing the Queried/tool_use ledger; any RL/training.

## File manifest (high level)
**New:** `app/services/answer_pipeline_service.py`,
`app/services/answer_eval_service.py`, `app/db/schema/_extracted_facts.py`,
`app/db/schema/_answer_eval.py`, `app/db/extracted_facts.py`,
`app/db/answer_eval.py`, `app_litestar/routes/answer_eval.py`,
`scripts/run_answer_eval.py`, tests for each.
**Modified:** `streaming_helper.py` (hook + rag_enabled), the leader-chat call
site (thread the flag), `v07_features.py` (153, 154), `schema/__init__.py`,
`ProjectTeamLeaderChat.vue`, one dashboard card, locales ×4, `main.py` (router).
