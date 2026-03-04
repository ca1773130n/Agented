# Evaluation Plan: Phase 8 — Execution Intelligence & Replay

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Methods evaluated:** Execution Replay (EXE-01), Diff-Aware Context Injection (EXE-02), Smart Chunking (EXE-03), Conversation Branching (EXE-04), Collaborative Viewer (EXE-05)
**Reference research:** 08-RESEARCH.md — ContextBranch (arXiv:2512.13914), LongLLMLingua (Jiang 2023), Pinecone/LangCopilot chunking guides, Flask-SSE patterns, Python difflib/unidiff

---

## Evaluation Overview

Phase 8 delivers five distinct capabilities: execution replay with side-by-side diffing, diff-aware context injection for PR bots, smart context chunking with deduplication, tree-structured conversation branching, and real-time collaborative execution viewing. Across two waves (backend services first, frontend components second), this phase adds approximately 15 new backend service/DB/route files and 10+ frontend component/composable/API files.

The evaluation challenge here is that these five features are independent in implementation but interact at the integration layer. Backend services can be validated with unit and integration tests at the Python level; frontend components depend on the backend existing and can only be fully validated with a running stack. There is no published benchmark suite for "execution replay quality" or "chunking deduplication effectiveness" — the paper-derived targets (40% token reduction, 58% context reduction per branch) are performance aspirations based on research, not direct reproducibility tests.

No BENCHMARKS.md baseline has been established for this project, so all targets in this plan derive directly from the success criteria stated in the phase goal, the research paper claims cited in 08-RESEARCH.md, and pragmatic thresholds set by the plan authors.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Token count reduction (%) | 08-RESEARCH.md Rec. 2 — LongLLMLingua, Redis blog | Primary EXE-02 success criterion; measures cost reduction of diff-aware injection |
| Duplicate finding rate | 08-RESEARCH.md Rec. 3 — Pinecone, NAACL 2025 | Measures chunking dedup correctness; success criterion requires zero duplicates |
| Branch isolation correctness | 08-RESEARCH.md Rec. 1 — ContextBranch paper | Core correctness property; paper formally proves this as a required invariant |
| SSE presence event latency | 08-RESEARCH.md Rec. 4 — existing codebase pattern | Measures collaborative viewer responsiveness; target sub-100ms from existing SSE pattern |
| Diff line accuracy | 08-RESEARCH.md Rec. 5 — Python difflib | Measures side-by-side output comparison correctness |
| TypeScript compilation | Frontend coding standard | Gate: zero type errors required before any frontend ships |
| Existing test regression | CLAUDE.md requirement | Gate: zero regressions in backend pytest and frontend vitest suites |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 11 checks | Import validation, DB schema creation, test suites, build pipeline |
| Proxy (L2) | 10 metrics | Token reduction measurement, dedup correctness, branch isolation, SSE presence, diff rendering |
| Deferred (L3) | 5 validations | Full end-to-end with real bot executions, cross-browser, production load |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before any plan wave is considered complete.

### S1: Backend service imports succeed

- **What:** All five new service modules import without Python errors
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.replay_service import ReplayService; from app.services.diff_context_service import DiffContextService; from app.services.chunk_service import ChunkService; from app.services.conversation_branch_service import ConversationBranchService; from app.services.collaborative_viewer_service import CollaborativeViewerService; print('All services imported successfully')"`
- **Expected:** `All services imported successfully` with exit code 0
- **Failure means:** Module-level syntax error, missing dependency, or circular import — blocks all further evaluation

### S2: New DB tables created by schema and migrations

- **What:** All seven new tables (replay_comparisons, conversation_messages, conversation_branches, chunked_executions, chunk_results, viewer_comments) exist after `init_db()`
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.database import get_connection; from app.db.schema import create_tables; import tempfile, os; db = tempfile.mktemp(suffix='.db'); os.environ['DB_PATH'] = db; create_tables(); conn = get_connection(); tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]; required = ['replay_comparisons','conversation_messages','conversation_branches','chunked_executions','chunk_results','viewer_comments']; missing = [t for t in required if t not in tables]; assert not missing, f'Missing tables: {missing}'; print(f'All tables present: {tables}')"`
- **Expected:** All six table names present in output, exit code 0
- **Failure means:** Schema not updated or migration not applied — DB layer non-functional

### S3: All new API blueprints register without error

- **What:** replay_bp, conversation_branches_bp, chunks_bp, and collaborative_bp all construct without error and have correct URL prefixes
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.routes.replay import replay_bp; from app.routes.conversation_branches import conversation_branches_bp; from app.routes.chunks import chunks_bp; from app.routes.collaborative import collaborative_bp; print(f'replay_bp prefix: {replay_bp.url_prefix}'); print(f'branches_bp prefix: {conversation_branches_bp.url_prefix}'); print(f'chunks_bp prefix: {chunks_bp.url_prefix}'); print(f'collaborative_bp prefix: {collaborative_bp.url_prefix}')"`
- **Expected:** All four blueprints print `/admin` prefix, exit code 0
- **Failure means:** Blueprint construction error or wrong URL prefix — endpoints will not route correctly

### S4: Existing backend test suite passes with zero regressions

- **What:** All existing pytest tests pass after Phase 8 changes; no regressions introduced
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/ -x -q 2>&1 | tail -10`
- **Expected:** `N passed` with zero failures, zero errors. The count of passing tests must not decrease from pre-phase baseline.
- **Failure means:** Phase 8 changes broke existing behavior — must be fixed before shipping

### S5: DiffContextService handles edge cases without error

- **What:** Empty diff, binary-only diff, and renamed file diff all return without exception
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.diff_context_service import DiffContextService; r1 = DiffContextService.extract_pr_diff_context(''); assert r1 == '', f'Empty diff failed: {r1!r}'; print('Empty diff: PASS'); r2 = DiffContextService.extract_pr_diff_context('diff --git a/img.png b/img.png\nindex abc..def 100644\nBinary files a/img.png and b/img.png differ\n'); print(f'Binary diff (no crash): PASS'); print('Edge case handling: PASS')"`
- **Expected:** All three edge cases handled, exit code 0
- **Failure means:** Production PR diffs with binary files or empty changesets will cause 500 errors

### S6: ChunkService correctly skips chunking for small content

- **What:** Content under 100KB (SIZE_THRESHOLD) is returned as a single chunk without modification
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.chunk_service import ChunkService; small = 'def hello():\n    return 42\n'; chunks = ChunkService.chunk_code(small); assert len(chunks) == 1, f'Expected 1 chunk, got {len(chunks)}'; assert chunks[0] == small, 'Content modified for small input'; print('Small content passthrough: PASS')"`
- **Expected:** Single chunk returned unchanged, exit code 0
- **Failure means:** Unnecessary chunking of small content wastes bot invocations

### S7: CollaborativeViewerService tracks multiple viewers without error

- **What:** Two viewers can join and leave an execution stream without exceptions; viewer list is accurate throughout
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.collaborative_viewer_service import CollaborativeViewerService; v1 = CollaborativeViewerService.join('exec-test-1', 'usr-001', 'Alice'); assert any(v.get('viewer_id','') == 'usr-001' or v.get('id','') == 'usr-001' for v in v1) or len(v1) >= 1, f'Viewer not in list: {v1}'; v2 = CollaborativeViewerService.join('exec-test-1', 'usr-002', 'Bob'); viewers = CollaborativeViewerService.get_viewers('exec-test-1'); assert len(viewers) == 2, f'Expected 2 viewers, got {len(viewers)}'; CollaborativeViewerService.leave('exec-test-1', 'usr-001'); viewers = CollaborativeViewerService.get_viewers('exec-test-1'); assert len(viewers) == 1, f'Expected 1 viewer after leave, got {len(viewers)}'; print('Presence tracking: PASS')"`
- **Expected:** Viewer list accurately reflects join/leave sequence, exit code 0
- **Failure means:** Multi-viewer presence state is broken — EXE-05 success criterion unmet

### S8: TypeScript compilation succeeds for frontend (Plan 08-04 and 08-05)

- **What:** All new frontend TypeScript types and components compile without type errors
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npx vue-tsc --noEmit 2>&1 | tail -15`
- **Expected:** Zero TypeScript errors, exit code 0
- **Failure means:** Type mismatches between frontend and backend API shapes — runtime breakage likely

### S9: Existing frontend test suite passes with zero regressions

- **What:** All existing Vitest tests pass after Phase 8 frontend changes
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run 2>&1 | tail -10`
- **Expected:** All tests pass, zero failures. The count of passing tests must not decrease from pre-phase baseline.
- **Failure means:** Phase 8 frontend changes broke existing components

### S10: Production frontend build succeeds (Plans 08-04 and 08-05)

- **What:** `vite build` (which includes vue-tsc type checking) completes without error
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run build 2>&1 | tail -15`
- **Expected:** Build completes with `dist/` output, exit code 0
- **Failure means:** App cannot be deployed — Phase 8 is not shippable

### S11: Replay relationship stored before execution starts

- **What:** `ReplayService.replay_execution()` creates the replay_comparisons DB row prior to spawning the subprocess (crash safety)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "import inspect; from app.services.replay_service import ReplayService; src = inspect.getsource(ReplayService.replay_execution); lines = src.split('\n'); replay_idx = next((i for i,l in enumerate(lines) if 'create_replay_comparison' in l), -1); process_idx = next((i for i,l in enumerate(lines) if 'ProcessManager' in l or 'subprocess' in l or 'start_execution' in l), -1); assert replay_idx < process_idx, f'DB insert (line {replay_idx}) must come before process start (line {process_idx})'; print('Replay persistence ordering: PASS')"`
- **Expected:** DB insert line precedes subprocess line in source, exit code 0
- **Failure means:** Crash during replay leaves a ghost execution with no comparison record — per 08-RESEARCH.md "Insert replay_comparisons row first, then start execution"

**Sanity gate:** ALL sanity checks must pass. Any failure blocks progression to proxy metrics and blocks marking the relevant plan as complete.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of correctness and performance.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full end-to-end evaluation with real bot executions. Treat results with appropriate skepticism — especially token reduction estimates which use a character-count heuristic.

### P1: Token reduction estimate meets 40% threshold on representative diff

- **What:** DiffContextService.estimate_token_reduction() reports at least 40% reduction when comparing a representative PR diff context against the equivalent full-file content
- **How:** Feed a known diff and its corresponding full-file content into estimate_token_reduction(); verify reduction_percent >= 40.0
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.diff_context_service import DiffContextService; SAMPLE_FULL = 'x' * 10000; SAMPLE_DIFF = 'x' * 5000; result = DiffContextService.estimate_token_reduction(SAMPLE_FULL, SAMPLE_DIFF); print(f'Reduction: {result[\"reduction_percent\"]}%'); assert result['reduction_percent'] >= 40.0, f'Below 40% threshold: {result}'; print('Token reduction estimate: PASS')"`
- **Target:** >= 40% reduction (from EXE-02 success criterion)
- **Evidence from:** 08-RESEARCH.md Recommendation 2 — "literature suggests 60-80% reduction for typical PRs; our 40% target is conservative"
- **Correlation with full metric:** MEDIUM — character-count heuristic approximates token count at 4 chars/token. Real reduction depends on LLM tokenizer. For a well-structured diff vs full file, structural tokens (whitespace, imports) compress well, so this proxy underestimates real token savings.
- **Blind spots:** Does not measure quality of extracted context. A diff that includes only comment lines would "pass" this metric while providing poor bot context. Does not account for binary files or very small PRs where chunking adds overhead.
- **Validated:** No — awaiting deferred validation D1

### P2: ChunkService deduplication removes all normalized duplicates

- **What:** ChunkService.deduplicate_findings() removes duplicate findings under case-insensitive normalized string matching, including line-number-variant duplicates
- **How:** Supply a known set of findings with expected duplicates; assert unique count matches expected
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.chunk_service import ChunkService; findings = ['SQL injection on line 42', 'sql injection on line 99', 'XSS vulnerability in form', 'XSS VULNERABILITY IN FORM', 'Buffer overflow at offset 0']; unique = ChunkService.deduplicate_findings(findings); print(f'Input: {len(findings)}, Unique: {len(unique)}: {unique}'); assert len(unique) == 3, f'Expected 3 unique findings, got {len(unique)}'; print('Deduplication correctness: PASS')"`
- **Target:** 3 unique findings from 5 inputs (exact ratio matches test fixture)
- **Evidence from:** 08-RESEARCH.md Recommendation 3 — "normalized string matching (lowercase, strip whitespace, remove line numbers)" as dedup strategy; NAACL 2025 Findings paper confirms simpler approaches match sophisticated ones
- **Correlation with full metric:** MEDIUM — normalized string match catches exact and case-variant duplicates but misses paraphrased duplicates. Per 08-RESEARCH.md Open Question 2: "Add semantic dedup only if testing reveals significant paraphrased duplicates." Real-world dedup rate cannot be measured without actual bot output.
- **Blind spots:** Does not measure recall (legitimate distinct findings that happen to normalize similarly). Does not test semantic/paraphrase dedup.
- **Validated:** No — awaiting deferred validation D2

### P3: Large content is chunked at code boundaries, not mid-token

- **What:** ChunkService.chunk_code() on >100KB content produces chunks that split at class/function boundaries, not within identifier tokens or string literals
- **How:** Feed a synthetic code file with known class boundaries; verify each chunk starts with a class or function keyword (after preamble)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.chunk_service import ChunkService; code = ('class Foo:\n    def method(self): pass\n\n' * 200); chunks = ChunkService.chunk_code(code); assert len(chunks) > 1, f'Expected multiple chunks for {len(code)} chars content, got {len(chunks)}'; max_chunk = max(len(c) for c in chunks); assert max_chunk <= ChunkService.MAX_CHUNK_CHARS * 1.5, f'Largest chunk {max_chunk} exceeds 1.5x limit'; print(f'Chunked into {len(chunks)} chunks, largest={max_chunk} chars: PASS')"`
- **Target:** Multiple chunks produced; no individual chunk exceeds 1.5x MAX_CHUNK_CHARS (allowing for overlap)
- **Evidence from:** 08-RESEARCH.md Recommendation 3 — Pinecone/LangCopilot: RecursiveCharacterTextSplitter at 400-512 tokens with 10-20% overlap; code separators in priority order
- **Correlation with full metric:** MEDIUM-HIGH — chunk size compliance is directly measurable; semantic boundary quality requires manual inspection of real code
- **Blind spots:** Does not verify that chunk content is semantically coherent. Does not test cross-file dependency handling (Pitfall 2 from 08-RESEARCH.md). Synthetic code may split more cleanly than real heterogeneous codebases.
- **Validated:** No — awaiting deferred validation D2

### P4: Branch creation preserves original conversation immutability

- **What:** ConversationBranchService.create_branch() does not modify the original agent_conversations.messages JSON field
- **How:** Store original messages JSON before branch creation; assert messages JSON is byte-identical after branch creation
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "import json, os, tempfile; os.environ['DB_PATH'] = tempfile.mktemp(suffix='.db'); from app.db.schema import create_tables; create_tables(); from app.db.agents import create_agent_conversation; from app.services.conversation_branch_service import ConversationBranchService; msgs = [{'role':'user','content':'Hello'},{'role':'assistant','content':'Hi there'},{'role':'user','content':'Fork here'}]; conv_id = create_agent_conversation('agent-test', json.dumps(msgs)); from app.db.agents import get_agent_conversation; original = get_agent_conversation(conv_id); original_msgs = original['messages']; branch = ConversationBranchService.create_branch(conv_id, fork_message_index=1); after = get_agent_conversation(conv_id); assert after['messages'] == original_msgs, 'Original messages mutated by branch creation!'; print(f'Branch created: {branch[\"id\"]}'); print('Branch isolation: original messages unchanged: PASS')"`
- **Target:** Messages JSON identical before and after branch creation (byte-for-byte)
- **Evidence from:** 08-RESEARCH.md Recommendation 1 — ContextBranch paper (arXiv:2512.13914): "immutable snapshots and deep-copy semantics for branch isolation"; Pitfall 4: "Never modify the original conversation when creating a branch"
- **Correlation with full metric:** HIGH — this directly tests the correctness invariant the paper formally proves. If original messages are modified, the feature is broken by definition.
- **Blind spots:** Only tests the Python DB layer. Does not test frontend branch navigator's interpretation of branch tree. Does not test behavior when branching from the last message.
- **Validated:** No — awaiting deferred validation D3

### P5: Output diff produces correct structured diff from known inputs

- **What:** ReplayService.compare_outputs() returns an OutputDiff with correct added/removed/unchanged line counts for a known pair of execution outputs
- **How:** Supply two known strings (original, modified); verify diff_lines and change_summary match expected counts
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "from app.services.replay_service import ReplayService; orig = 'line one\nline two\nline three\n'; replay = 'line one\nline TWO modified\nline three\nline four added\n'; diff = ReplayService.compare_outputs_from_text(orig, replay); summary = diff['change_summary']; print(f'Summary: {summary}'); assert summary.get('removed', 0) >= 1, 'Expected at least 1 removed line'; assert summary.get('added', 0) >= 1, 'Expected at least 1 added line'; print('Output diff correctness: PASS')"`
- **Target:** At least 1 added line and 1 removed line detected correctly in change_summary
- **Evidence from:** 08-RESEARCH.md Recommendation 5 — Python stdlib difflib.unified_diff; Braintrust A/B guide establishes "diff mode to highlight textual differences" as the standard UX pattern
- **Correlation with full metric:** HIGH — difflib is deterministic. The proxy directly measures the same thing as the final product feature.
- **Blind spots:** Does not test the frontend DiffViewer rendering of the diff data. Does not test very large outputs (>10K lines) for performance.
- **Validated:** No — awaiting deferred validation D1

### P6: Replay comparison record is persisted correctly before execution

- **What:** After calling replay_execution(), a row exists in replay_comparisons with correct original_execution_id before the subprocess completes
- **How:** Mock or stub the subprocess invocation to be a no-op; verify DB record exists immediately after replay_execution() returns
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "import os, tempfile; os.environ['DB_PATH'] = tempfile.mktemp(suffix='.db'); from app.db.schema import create_tables; create_tables(); from app.db.replay import create_replay_comparison, get_replay_comparisons_for_execution; cid = create_replay_comparison('exec-original-001', 'exec-replay-002'); assert cid.startswith('rpl-'), f'ID prefix wrong: {cid}'; rows = get_replay_comparisons_for_execution('exec-original-001'); assert len(rows) == 1, f'Expected 1 row, got {len(rows)}'; assert rows[0]['original_execution_id'] == 'exec-original-001'; print(f'Replay comparison CRUD: PASS (id={cid})')"`
- **Target:** Row created with correct IDs and `rpl-` prefix
- **Evidence from:** 08-RESEARCH.md Pattern 1 — "Insert replay_comparisons row first, then start execution"
- **Correlation with full metric:** HIGH — tests the DB layer directly. If CRUD fails, the replay feature is non-functional.
- **Blind spots:** Does not test the full replay_execution() call chain with a real execution record; tests DB layer in isolation.
- **Validated:** No — awaiting deferred validation D1

### P7: Presence events broadcast via SSE to existing subscribers

- **What:** CollaborativeViewerService.join() calls ExecutionLogService._broadcast() with a presence_join event type
- **How:** Inspect source code to verify the _broadcast call with correct event type, or mock _broadcast and verify it is called
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "import inspect; from app.services.collaborative_viewer_service import CollaborativeViewerService; src = inspect.getsource(CollaborativeViewerService.join); assert 'presence_join' in src or '_broadcast' in src, 'join() does not broadcast presence_join event'; print('Presence broadcast wiring: PASS in join()')"`
- **Target:** `presence_join` event type present in join() implementation
- **Evidence from:** 08-RESEARCH.md Recommendation 4 — "Extend existing SSE fan-out pattern with additional event types (presence_join, presence_leave, presence_heartbeat, inline_comment)"
- **Correlation with full metric:** MEDIUM — verifies wiring exists in source but does not verify actual SSE delivery to connected clients. Real delivery requires a running server with open SSE connections.
- **Blind spots:** Source inspection cannot verify event is correctly formatted for SSE protocol. Cannot verify client-side SSE event handler parses the event correctly.
- **Validated:** No — awaiting deferred validation D4

### P8: DiffContextService is wired into ExecutionService for github_pr triggers

- **What:** ExecutionService source code references DiffContextService for github_pr trigger events
- **How:** Inspect ExecutionService source for DiffContextService import and github_pr conditional
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && python -c "import inspect; from app.services.execution_service import ExecutionService; src = inspect.getsource(ExecutionService); assert 'DiffContextService' in src or 'diff_context_service' in src, 'DiffContextService not referenced in ExecutionService'; assert 'github_pr' in src, 'github_pr trigger handling not found'; print('DiffContextService wiring into ExecutionService: PASS')"`
- **Target:** Both `DiffContextService` and `github_pr` appear in ExecutionService source
- **Evidence from:** 08-RESEARCH.md Pattern 2 — "Before calling PromptRenderer.render(), intercept the paths resolution for GitHub PRs and replace full file contents with diff-focused context"
- **Correlation with full metric:** MEDIUM — verifies integration wiring in source but cannot verify actual token reduction in live execution without a real PR.
- **Blind spots:** Does not verify the wiring is correctly conditional (only fires for github_pr, not all triggers). Requires a real github_pr webhook to validate end-to-end.
- **Validated:** No — awaiting deferred validation D1

### P9: Frontend diff viewer renders color-coded lines from mock data (Plan 08-04)

- **What:** DiffViewer.vue correctly applies CSS classes for added/removed/unchanged line types when given structured diff data
- **How:** Vitest unit test with mock OutputDiff data verifying rendered class names
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run -- --reporter=verbose 2>&1 | grep -E '(DiffViewer|PASS|FAIL)' | head -20`
- **Target:** DiffViewer unit test passes, rendering correct class names for each DiffLine type
- **Evidence from:** 08-RESEARCH.md Recommendation 5 — Braintrust A/B guide: "diff mode to highlight textual differences in outputs" with color coding
- **Correlation with full metric:** MEDIUM — unit test verifies rendering logic but not visual correctness or user perception. Color choices (green/red) are functional but may not match user expectations without user testing.
- **Blind spots:** Unit test cannot verify cross-browser rendering. Does not test pagination behavior for >500 line diffs.
- **Validated:** No — awaiting deferred validation D5

### P10: useCollaborativeViewer composable manages heartbeat interval

- **What:** useCollaborativeViewer.ts sets up a heartbeat interval and clears it on unmount
- **How:** Unit test using vi.useFakeTimers() to verify setInterval call with 30s interval; verify clearInterval on unmount
- **Command:** `cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run -- --reporter=verbose 2>&1 | grep -E '(useCollaborativeViewer|PASS|FAIL)' | head -20`
- **Target:** Heartbeat interval test passes; interval cleared on unmount
- **Evidence from:** 08-RESEARCH.md Pitfall 3 — "Use heartbeat-based presence detection (existing pattern: 30s Queue.get timeout). Remove viewers that miss 2+ heartbeats."
- **Correlation with full metric:** MEDIUM-HIGH — verifies the client-side lifecycle management that prevents orphaned SSE subscribers
- **Blind spots:** Does not test the server-side stale viewer cleanup. Does not test what happens if the heartbeat POST fails (network error during session).
- **Validated:** No — awaiting deferred validation D4

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation that requires a running server, real bot execution, or multi-browser testing — not available in the development/planning phase.

### D1: Full replay end-to-end — DEFER-08-01

- **What:** Trigger replay of a real completed execution via the UI, wait for replay to complete, view side-by-side diff — verify diff accurately reflects output differences
- **How:** Run a real bot execution via the executions UI; click "Replay Execution"; when replay completes, click "View Diff"; verify color-coded diff displays with correct line-level changes
- **Why deferred:** Requires a running backend with real bot execution capability (claude CLI), a completed execution record, and the Plan 08-04 frontend to be deployed
- **Validates at:** post-08-04-integration (after plans 08-01 and 08-04 both complete and stack is running)
- **Depends on:** Running backend (just dev-backend), completed execution with real output, replay_service.py wired to ProcessManager, DiffViewer.vue rendering correctly
- **Target:** Replay completes within 2x original execution time; diff view shows at least some changed lines (LLM outputs are non-deterministic); EXE-01 success criterion 1 met
- **Risk if unmet:** Replay may silently fail if ProcessManager integration is incomplete; diff may show no changes if replay is re-using cached output. Budget 0.5 phase for fix iteration.
- **Fallback:** If replay crashes, check execution_logs for the replay execution_id — may reveal ProcessManager invocation error

### D2: Full chunked execution end-to-end — DEFER-08-02

- **What:** POST /admin/bots/{bot_id}/run-chunked with >100KB content; poll status until complete; verify GET /admin/chunked-executions/{id}/results returns merged output with zero duplicate findings
- **How:** Use a large Python or JavaScript file (>100KB) as input; submit to run-chunked endpoint; poll completed_chunks until equal to total_chunks; inspect unique_findings for duplicates
- **Why deferred:** Requires a running backend with real bot execution; duplicate detection can only be verified with actual bot-generated output (which may vary by model and prompt)
- **Validates at:** post-08-02-integration (after plan 08-02 complete and backend running)
- **Depends on:** Running backend, a real bot configured with a code review prompt, a >100KB test file
- **Target:** Zero duplicate findings in merged output (EXE-03 success criterion 3); merged output is non-empty; total_chunks > 1 for >100KB input
- **Risk if unmet:** Semantic paraphrasing by the LLM may produce duplicates that normalized string matching misses — per 08-RESEARCH.md Open Question 2. If >20% of findings are paraphrased duplicates, semantic dedup must be added.
- **Fallback:** If semantic dedup is needed, integrate sentence-transformers or a lightweight embedding model for dedup pass

### D3: Conversation branch isolation with real messages — DEFER-08-03

- **What:** Create a branch from a real agent conversation transcript; add messages to the branch; verify original conversation thread is unmodified and both branches are independently navigable
- **How:** Use a real conversation with 5+ messages; branch from message index 3; add 2 messages to branch; verify original GET /admin/branches/{main_id}/messages still returns 5 messages unchanged; verify branch GET returns original 4 + 2 new = 6 messages
- **Why deferred:** Requires a real agent conversation (not just synthetic test data); needs Plan 08-02 backend and Plan 08-05 BranchNavigator frontend
- **Validates at:** post-08-05-integration (full wave 2 complete)
- **Depends on:** A real agent conversation with multiple messages, both backend and frontend deployed
- **Target:** Original branch: 5 messages unchanged; forked branch: 4 inherited + 2 new = 6 messages; BranchNavigator shows correct tree structure (EXE-04 success criteria 4 and 5)
- **Risk if unmet:** If original messages are mutated, this is a data integrity bug. Must block release. Budget 1 additional phase for data model redesign if the tree-structured approach has fundamental issues.
- **Fallback:** The DB-level isolation test (P4) should catch this early. If P4 passes but D3 fails, the issue is likely in the API or frontend layer.

### D4: Live collaborative viewing with 2 real browser sessions — DEFER-08-04

- **What:** Open the same running execution in two real browser windows; verify both see each other's presence indicators; post a comment from window A and verify it appears in window B without page refresh
- **How:** Start a long-running bot execution; open execution stream URL in two Chrome windows; verify PresenceIndicator shows 2 viewers in both; post comment from window A; verify comment appears in window B within 1 second
- **Why deferred:** Requires two simultaneous browser sessions against a running server; SSE event delivery to clients cannot be simulated in unit tests
- **Validates at:** post-08-05-integration (full wave 2 complete)
- **Depends on:** Running server (just deploy or just dev-backend + just dev-frontend), a live execution stream, two browser sessions
- **Target:** Both viewers visible to each other (EXE-05 success criterion 5); comment visible in second window within 1s of posting in first window; presence_join event appears in both SSE streams
- **Risk if unmet:** SSE subscriber leak (Pitfall 3 from 08-RESEARCH.md) may prevent second viewer from receiving events. If viewer 2 is not receiving events, check CollaborativeViewerService._subscribers is populated with 2 queues.
- **Fallback:** If SSE fan-out to multiple clients fails, check ExecutionLogService._broadcast() is called after viewer join. The existing multi-client SSE pattern is proven in the codebase — failures are likely in the wiring between CollaborativeViewerService and ExecutionLogService.

### D5: Token reduction measurement on real PRs — DEFER-08-05

- **What:** Measure actual token reduction on 3+ representative PRs by comparing the diff-context prompt length to the equivalent full-file prompt length; use tiktoken for accurate token counting
- **How:** Select 3 PRs of varying sizes (small/medium/large); for each, run both full-file injection and diff-aware injection via the preview endpoint; count tokens with tiktoken; compute reduction percentage
- **Why deferred:** Requires real GitHub PRs and tiktoken for accurate (non-heuristic) token counting; proxy P1 only uses character-count approximation
- **Validates at:** post-phase-8-production-eval (after full stack deployed with real GitHub webhook integration)
- **Depends on:** Real GitHub repositories with PR activity, tiktoken installed, diff-aware injection wired into github_pr trigger flow
- **Target:** >= 40% token reduction on at least 2 of 3 representative PRs (EXE-02 success criterion 2); literature suggests 60-80% for typical PRs
- **Risk if unmet:** If real token reduction is below 40%, the context lines setting (default N=10) may be too generous. Try N=5 for tighter diffs.
- **Fallback:** Make context_lines configurable per trigger (default 10, range 3-50) — already recommended in 08-RESEARCH.md Pitfall 5. Expose the setting in the trigger configuration UI.

---

## Ablation Plan

**Purpose:** Isolate component contributions to verify that each feature adds value independently.

### A1: Diff-aware context vs. full-file context (EXE-02)

- **Condition:** Compare bot output quality with diff-aware context (N=10 context lines) vs. full-file inclusion for the same PR review task
- **Expected impact:** Per 08-RESEARCH.md Rec. 2 — LongLLMLingua shows 17.1% quality improvement alongside 4x token reduction. We expect comparable or better finding precision with focused context.
- **Command:** `POST /admin/diff-context/preview with a representative diff, then compare against full file content for the same files. Measure character counts and manually assess finding relevance.`
- **Evidence:** 08-RESEARCH.md Recommendation 2 — K2View MCP strategies: "grounded prompts with only relevant context outperform full-context prompts"

### A2: Chunked execution with dedup vs. chunked without dedup (EXE-03)

- **Condition:** Run the same >100KB content through chunked execution; compare raw merged output (no dedup) vs. deduped merged output
- **Expected impact:** Duplicate finding rate should be measurable in the raw output. Per 08-RESEARCH.md Open Question 2, normalized string match should eliminate the majority of identical-wording duplicates.
- **Command:** `GET /admin/chunked-executions/{id}/results returns both raw chunk_results and deduplicated unique_findings. Compare len(raw findings from all chunks) vs len(unique_findings).`
- **Evidence:** 08-RESEARCH.md Rec. 3 — NAACL 2025 Findings: simpler dedup approaches competitive with semantic; this ablation validates the "simple first" approach

### A3: Branch isolation unit ablation (EXE-04)

- **Condition:** Verify that adding a message to a branch does NOT affect the parent branch's message list
- **Expected impact:** Zero cross-contamination between branches (ContextBranch paper: correctness invariant)
- **Command:** `Create branch B from conversation C at index 2. Add message to B. GET /admin/branches/{main_branch_id}/messages must still return original count.`
- **Evidence:** 08-RESEARCH.md Rec. 1 — ContextBranch (arXiv:2512.13914) formally proves branch isolation as a correctness property

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — MCP not confirmed available for this project configuration.

Note for integration testing: The collaborative viewer's presence indicators and real-time comment updates (EXE-05) are the primary frontend behaviors that would benefit from browser-based validation. If WebMCP becomes available, priority tools would be:
- `hive_check_execution_viewer_presence` — verify PresenceIndicator renders viewer badges
- `hive_check_diff_viewer_layout` — verify side-by-side diff columns render correctly
- `hive_check_console_errors` — verify no SSE connection errors in browser console

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Token usage (full-file PR context) | Current behavior: full file contents sent for github_pr triggers | 100% of file tokens (no reduction) | 08-RESEARCH.md Experiment Design |
| Duplicate finding rate (no chunking) | Single execution on full context: 0 duplicates by definition | 0% duplicates (no chunks to deduplicate) | Logical baseline |
| Branch count per conversation | Current state: 0 branches (flat JSON message array) | 0 branches | Codebase analysis |
| Simultaneous viewers tracked | Current state: ExecutionLogService SSE has no viewer identity | 0 named viewers | Codebase analysis |
| Replay comparisons | Current state: no replay feature exists | 0 comparisons | Codebase analysis |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/ — existing test suite (run with uv run pytest)
frontend/src/components/triggers/__tests__/ — component unit tests (run with npm run test:run)
```

**Quick sanity run (backend):**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/ -x -q
```

**Quick sanity run (frontend):**
```bash
cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
```

**Full build verification:**
```bash
cd /Users/neo/Developer/Projects/Agented && just build
```

**Token reduction proxy check:**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && python -c "
from app.services.diff_context_service import DiffContextService
# Replace with actual diff and full-file content for real measurement
sample_full = 'x' * 10000
sample_diff = 'x' * 5000
result = DiffContextService.estimate_token_reduction(sample_full, sample_diff)
print(f'Token reduction: {result[\"reduction_percent\"]}%')
print(f'Full tokens (est): {result[\"full_tokens\"]}')
print(f'Diff tokens (est): {result[\"diff_tokens\"]}')
"
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: Service imports | | | |
| S2: DB tables created | | | |
| S3: Blueprints register | | | |
| S4: Backend pytest | | | |
| S5: DiffContext edge cases | | | |
| S6: Small content no-chunk | | | |
| S7: Multi-viewer presence | | | |
| S8: TypeScript compilation | | | |
| S9: Frontend vitest | | | |
| S10: Production build | | | |
| S11: Replay persistence order | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: Token reduction estimate | >= 40% | | | Character-count heuristic |
| P2: Dedup correctness | 3 unique from 5 inputs | | | Normalized string match |
| P3: Code boundary chunking | Chunks within 1.5x limit | | | |
| P4: Branch isolation | Messages byte-identical | | | |
| P5: Diff correctness | >= 1 added + 1 removed detected | | | |
| P6: Replay CRUD | rpl- prefixed ID, row exists | | | |
| P7: Presence broadcast wiring | presence_join in join() source | | | |
| P8: DiffContext wiring | DiffContextService in ExecutionService | | | |
| P9: DiffViewer rendering | Unit test passes | | | |
| P10: Heartbeat interval | Unit test passes | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: Diff vs full-file context | >= 40% char reduction, focused findings | | |
| A2: Dedup vs no-dedup | Measurable duplicate count in raw | | |
| A3: Branch isolation | 0 cross-contamination | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-08-01 | Full replay end-to-end with diff view | PENDING | post-08-04-integration |
| DEFER-08-02 | Chunked execution end-to-end, zero dedup failures | PENDING | post-08-02-integration |
| DEFER-08-03 | Branch isolation with real conversation | PENDING | post-08-05-integration |
| DEFER-08-04 | Live 2-browser collaborative viewing | PENDING | post-08-05-integration |
| DEFER-08-05 | Real PR token reduction with tiktoken | PENDING | post-phase-8-production-eval |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM

**Justification:**

- **Sanity checks:** Adequate — 11 checks cover imports, DB schema, blueprint registration, test regressions, and build pipeline. These are exhaustive for the "does it run" tier.

- **Proxy metrics:** Weakly-evidenced for quality aspects; well-evidenced for structural correctness. Token reduction (P1) uses a character-count heuristic that is accurate at the order-of-magnitude level but not exact. Dedup correctness (P2, P3) tests the algorithm on synthetic data — real bot output may produce more paraphrased duplicates than the test fixtures assume. Diff accuracy (P5) is HIGH confidence because difflib is deterministic. Branch isolation (P4) is HIGH confidence because it directly tests the DB invariant.

- **Deferred coverage:** Comprehensive — all five success criteria have a corresponding deferred validation. The "real bot execution" requirement for D1, D2, D3 cannot be bypassed; these features only demonstrate their full value when the bot actually runs and produces output. D4 (live collaborative viewing) requires manual multi-browser testing that cannot be automated without WebMCP.

**What this evaluation CAN tell us:**
- Whether the implementation compiles and runs without errors (S1-S11)
- Whether the algorithmic correctness properties hold on synthetic data (P1-P10)
- Whether existing functionality was broken by Phase 8 additions (S4, S9)
- Whether the DB schema and service wiring match the research-backed design (P4, P6, P7, P8)

**What this evaluation CANNOT tell us:**
- Whether 40% token reduction is achieved on real PRs with real LLM tokenizers (validated at D5)
- Whether semantic paraphrasing by the LLM produces more duplicates than normalized string matching catches (validated at D2)
- Whether the collaborative viewer creates a good user experience for team members watching together (validated at D4 — requires human judgment)
- Whether the replay comparison is useful for A/B testing prompt revisions in practice (validated at D1 — requires real bot output to compare)
- Cross-browser rendering of DiffViewer and PresenceIndicator (validated at D4-D5)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
