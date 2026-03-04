# Phase 8: Execution Intelligence & Replay - Research

**Researched:** 2026-03-04
**Domain:** Execution lifecycle management, diff comparison, context optimization, collaborative real-time streaming
**Confidence:** MEDIUM

## Summary

Phase 8 adds five capabilities to the existing execution engine: replay with A/B diff comparison (EXE-01), diff-aware context injection for PRs (EXE-02), smart context chunking for large inputs (EXE-03), conversation branching (EXE-04), and live collaborative execution viewing (EXE-05). These requirements span backend execution pipeline modifications, new database tables, and significant frontend UI work.

The existing codebase provides a solid foundation. The `ExecutionLogService` already implements in-memory log buffering with SSE fan-out via `threading.Queue`, the `execution_logs` table stores prompt/command/stdout/stderr per execution, and the `AuthenticatedEventSource` on the frontend handles reconnection with backpressure. The primary challenge is that the current execution model is fire-and-forget with no concept of replaying from stored inputs, no diff extraction from PRs, no chunking pipeline, no branching of conversation state, and no multi-user awareness on SSE streams.

**Primary recommendation:** Build incrementally on the existing `ExecutionLogService` + `ExecutionService` architecture, adding replay as a thin orchestration layer over `run_trigger`, diff-aware injection via `gh` CLI + `unidiff` parsing, AST-aware chunking via Python's `ast` module, conversation branching via a tree-structured message table, and collaborative viewing by extending the existing SSE subscriber model with presence/comment broadcasting.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Use Python difflib for Output Diff Comparison (EXE-01)

**Recommendation:** Use Python's stdlib `difflib.unified_diff()` for generating line-level diffs between execution outputs, and `diff2html` on the frontend for rendering side-by-side views.

**Evidence:**
- Python `difflib` documentation (Python Standard Library) -- implements the Ratcliff-Obershelp "gestalt pattern matching" algorithm, finding the longest contiguous matching subsequences. The `unified_diff()` function produces standard unified diff format with configurable context lines.
- diff2html (GitHub, 4.2k stars) -- generates GitHub-style HTML diff views from unified diff input, supporting both "line-by-line" and "side-by-side" output formats with syntax highlighting via highlight.js.
- Braintrust A/B Testing Guide (2025) -- recommends deterministic decoding (temperature=0) and fixed max output length for reproducible A/B comparisons of LLM prompt variants. Version prompt templates, model versions, and generation parameters together.

**Confidence:** HIGH -- `difflib` is Python stdlib (no new dependency), `diff2html` is widely used (4.2k GitHub stars).
**Expected improvement:** Side-by-side diff view enables visual regression detection and prompt optimization feedback loops.
**Caveats:** LLM outputs are inherently non-deterministic. Even with temperature=0, outputs may differ between runs. The diff view surfaces differences; it does not guarantee identical outputs for identical inputs.

### Recommendation 2: Use `gh` CLI + `unidiff` for PR Diff Extraction (EXE-02)

**Recommendation:** Extract PR diffs using `gh pr diff <number> --repo <owner/repo>` (already available -- `gh` CLI is a documented dependency), parse with the `unidiff` Python library to extract changed files and surrounding context lines, then inject only the relevant hunks into the bot prompt.

**Evidence:**
- GitHub REST API documentation -- PR diffs can be fetched via `Accept: application/vnd.github.v3.diff` header on the pull request endpoint, or via `gh pr diff`.
- python-unidiff (PyPI, GitHub 570+ stars) -- parses unified diff output into structured `PatchSet` > `PatchedFile` > `Hunk` objects, providing per-file stats (added/removed lines), hunk boundaries, and line-level access.
- The existing codebase already uses `gh` CLI extensively (`GitHubService.clone_repo`, `GitHubService.validate_repo_url`, `GitHubService.create_pull_request`). Adding `gh pr diff` is consistent with established patterns.

**Confidence:** HIGH -- `gh` CLI is already a project dependency, `unidiff` is stable (v0.7.5, 12 years of development).
**Expected improvement:** The success criteria requires 40% token reduction. A typical PR changes 5-15 files out of potentially hundreds. Sending only changed files + N context lines (configurable, default 10) vs. full file contents will achieve well beyond 40% reduction for most PRs.
**Caveats:** Binary file diffs, renamed files, and very large diffs (1000+ changed files) need special handling. The `unidiff` library handles these edge cases gracefully (binary files have `is_binary_file` flag).

### Recommendation 3: Use AST-Aware Chunking for Code Context (EXE-03)

**Recommendation:** For code files, use Python's built-in `ast` module (for Python files) and a regex-based function/class boundary detector (for other languages) to split large contexts at semantic boundaries. For non-code content, use recursive text splitting with configurable chunk size (default 512 tokens) and 10% overlap.

**Evidence:**
- cAST: Enhancing Code Retrieval-Augmented Generation with Structural Chunking via AST (CMU, 2025) -- demonstrates that AST-based code chunking significantly outperforms fixed-size splitting for code understanding tasks. The "split-then-merge" recursive algorithm generates chunks aligned with syntax boundaries.
- ASTChunk (GitHub, yilinjz/astchunk) -- Python toolkit implementing AST-aware code chunking, dividing source code into meaningful chunks while respecting AST structure.
- Weaviate Chunking Strategies for RAG (2025) -- benchmarks show recursive 512-token splitting achieves 69% accuracy vs. fixed-size baselines, while semantic chunking achieves 54%. For code specifically, AST-aware chunking outperforms both.
- LangChain/LangFuse documentation (2025) -- recommends 256-512 token chunks with 10-20% overlap as practical defaults.

**Confidence:** MEDIUM -- AST chunking is well-established for Python via `ast` module, but multi-language support adds complexity. For non-Python code, a simpler regex-based approach (splitting at function/class boundaries using language-specific patterns) is pragmatic.
**Expected improvement:** Semantically coherent chunks produce non-overlapping findings, enabling effective deduplication of results from independent chunk runs.
**Caveats:** The "merged/deduplicated result that contains no duplicate findings" criterion requires a deduplication strategy. Line-number-based deduplication (same file + overlapping line ranges = duplicate) is the simplest and most reliable approach for code findings. Semantic deduplication (using embeddings) is overkill for this use case.

### Recommendation 4: Tree-Structured Message Storage for Conversation Branching (EXE-04)

**Recommendation:** Implement conversation branching using a tree-structured message table where each message has a `parent_message_id` column. Forking from message N creates a new branch by inserting a new message with `parent_message_id` pointing to message N. Both the original continuation and the fork are independently traversable by walking the parent chain.

**Evidence:**
- Forky (GitHub, ishandhanani/forky) -- implements git-style branching for LLM conversations using a DAG structure. Key primitives: fork (create new path from any point), branch (explore alternatives), merge (combine insights). Demonstrates that tree-structured message storage is the natural data model.
- ContextBranch (arXiv 2512.13914, Dec 2025) -- "Context Branching for LLM Conversations: A Version Control Approach to Exploratory Programming." Proposes four core primitives: checkpoint, branch, switch, inject. Analysis of 200,000+ conversations reveals 39% average performance drop in extended conversations, motivating branching as a mitigation strategy.
- GitChat (GitHub, DrustZ/GitChat) -- treats messages as interconnected nodes in a flowchart structure, allowing branch creation, merge, and rewiring of chat histories.

**Confidence:** MEDIUM -- the tree-structured approach is well-established in multiple implementations. The complexity lies in the UI for navigating branches (tree visualization) and in replaying the correct message chain when sending a branch continuation to the LLM.
**Expected improvement:** Enables exploring alternative approaches from any point in an execution transcript without losing the original context.
**Caveats:** The existing `super_agent_sessions.conversation_log` stores messages as a JSON text blob. Branching requires migrating to a relational message table with `parent_message_id` foreign keys, or extending the execution_logs table with a branch/parent concept.

### Recommendation 5: Extend SSE Subscriber Model for Collaborative Viewing (EXE-05)

**Recommendation:** Extend the existing `ExecutionLogService._subscribers` dictionary to track viewer metadata (user identifier, connected_at timestamp) alongside each Queue. Add a separate `_presence` dict for tracking connected viewers per execution. Use the same SSE channel to broadcast presence updates and inline comments as named events alongside log events.

**Evidence:**
- Flask SSE patterns (Max Halford, 2025; Noë Flatreaud, 2025) -- the EventBouncer/MessageAnnouncer pattern for multi-subscriber broadcasting is exactly what Agented already implements in `ExecutionLogService._broadcast()`. Extending it with presence metadata is a natural evolution.
- SSE vs. WebSocket analysis (DEV Community, 2025) -- SSE is recommended for "simple, one-way real-time updates like notifications or live data." Collaborative viewing (presence + comments) is primarily one-way broadcast from server to viewers, with occasional POST requests for submitting comments. This fits SSE better than WebSocket.
- Existing `AuthenticatedEventSource` in `frontend/src/services/api/client.ts` already supports named event types via `addEventListener(type, handler)`. Adding "presence" and "comment" event types requires no changes to the SSE client infrastructure.

**Confidence:** HIGH -- this is a direct extension of the existing architecture with no new dependencies.
**Expected improvement:** Multiple viewers can watch the same execution stream with real-time presence indicators and comment broadcasting.
**Caveats:** The existing `ExecutionLogService` uses class-level in-memory state. This is a known concern (CONCERNS.md 7.2 -- "In-Memory State Incompatible with Horizontal Scaling"). For single-process deployment (the current reality), this works. For future multi-process deployment, Redis pub/sub would be needed.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `difflib` | stdlib | Line-level text diff generation | Python standard library, no dependency. Implements Ratcliff-Obershelp algorithm |
| `unidiff` | 0.7.5 | Parse unified diff output from `gh pr diff` | Stable library (12 years), 570+ GitHub stars, handles binary files and edge cases |
| `diff2html` | 3.x | Frontend side-by-side diff rendering | 4.2k GitHub stars, supports unified diff input, syntax highlighting |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jsdiff` | 7.x | Generate unified diff in browser for frontend-only comparisons | When backend diff is unavailable or for real-time preview |
| `ast` | stdlib | Python AST parsing for semantic code chunking | When chunking Python source files at function/class boundaries |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| `difflib` | `deepdiff` | deepdiff handles structured data (JSON, dicts); difflib handles text lines | Use difflib -- execution output is text, not structured data |
| `unidiff` | `whatthepatch` | whatthepatch is newer but less mature; unidiff is battle-tested | Use unidiff -- stability matters for production PR processing |
| `diff2html` | Custom Vue diff component | Custom gives more control but months of work | Use diff2html -- feature-complete, widely used |
| Python `ast` | `tree-sitter` | tree-sitter supports all languages; `ast` is Python-only | Use `ast` for Python, regex fallback for others -- tree-sitter adds a native dependency |

**Installation:**
```bash
# Backend
cd backend && uv add unidiff

# Frontend
cd frontend && npm install diff2html jsdiff
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
├── services/
│   ├── replay_service.py          # EXE-01: Execution replay orchestration
│   ├── diff_context_service.py    # EXE-02: PR diff extraction and context injection
│   ├── context_chunking_service.py # EXE-03: Smart context splitting and merge
│   ├── conversation_branch_service.py # EXE-04: Branching operations
│   └── collaborative_viewer_service.py # EXE-05: Presence + comment management
├── db/
│   ├── replays.py                 # Replay and comparison CRUD
│   ├── conversation_branches.py   # Branch message tree CRUD
│   └── viewer_comments.py         # Inline comment CRUD
├── models/
│   ├── replay.py                  # Pydantic models for replay/diff APIs
│   ├── branch.py                  # Pydantic models for branching APIs
│   └── collaborative.py           # Pydantic models for viewer/comment APIs
└── routes/
    ├── replays.py                 # /admin/replays/* endpoints
    ├── context.py                 # /admin/context/* endpoints (diff-aware, chunking)
    ├── branches.py                # /admin/branches/* endpoints
    └── collaborative.py           # /admin/collaborative/* endpoints

frontend/src/
├── components/
│   ├── execution/
│   │   ├── ExecutionDiffViewer.vue     # Side-by-side diff component
│   │   ├── ExecutionReplayPanel.vue    # Replay controls and comparison
│   │   ├── ContextPreview.vue          # Shows diff-aware context before execution
│   │   ├── ChunkViewer.vue             # Shows chunk boundaries and merged results
│   │   ├── BranchTree.vue             # Conversation branch visualization
│   │   └── CollaborativeOverlay.vue   # Presence indicators + inline comments
│   └── ...
├── composables/
│   ├── useExecutionReplay.ts          # Replay state management
│   ├── useCollaborativeViewer.ts      # Presence + comment SSE composable
│   └── useBranchNavigation.ts         # Branch tree navigation
└── views/
    ├── ExecutionCompare.vue            # A/B comparison page
    └── ConversationBranch.vue          # Branch exploration page
```

### Pattern 1: Replay as Re-execution with Stored Inputs

**What:** Replay creates a new execution using the exact same inputs (prompt, backend_type, model, paths, trigger config snapshot) stored in the original `execution_logs` record.
**When to use:** For EXE-01 -- all the necessary input data already exists in `execution_logs.prompt`, `execution_logs.backend_type`, `execution_logs.command`, and `execution_logs.trigger_config_snapshot`.
**Example:**
```python
# Source: Agented codebase pattern — extending ExecutionService
class ReplayService:
    @classmethod
    def replay_execution(cls, original_execution_id: str) -> str:
        """Replay an execution using stored inputs. Returns new execution_id."""
        original = get_execution_log(original_execution_id)
        if not original:
            raise ValueError(f"Execution {original_execution_id} not found")

        # Reconstruct trigger config from snapshot
        trigger = json.loads(original["trigger_config_snapshot"])
        prompt = original["prompt"]
        backend = original["backend_type"]

        # Create new execution with replay metadata
        new_execution_id = ExecutionLogService.start_execution(
            trigger_id=original["trigger_id"],
            trigger_type="replay",
            prompt=prompt,
            backend_type=backend,
            command=original["command"],
            trigger_config_snapshot=original["trigger_config_snapshot"],
            account_id=original.get("account_id"),
        )

        # Store replay link in new table
        create_replay_link(new_execution_id, original_execution_id)

        # Run the actual command (same as original)
        cmd = CommandBuilder.build(backend, prompt)
        # ... subprocess execution via existing ExecutionService pattern

        return new_execution_id
```

### Pattern 2: Diff-Aware Context as a Prompt Preprocessor

**What:** A service that sits between PR event receipt and prompt rendering, extracting only changed files and surrounding context lines from the PR diff, and injecting them as structured context into the prompt template.
**When to use:** For EXE-02 -- intercepts the GitHub PR flow before `PromptRenderer.render()`.
**Example:**
```python
# Source: Agented codebase pattern — new service
import subprocess
from unidiff import PatchSet

class DiffContextService:
    DEFAULT_CONTEXT_LINES = 10

    @classmethod
    def extract_pr_context(cls, repo_full_name: str, pr_number: int,
                           context_lines: int = None) -> str:
        """Extract diff-aware context from a PR."""
        n = context_lines or cls.DEFAULT_CONTEXT_LINES

        # Use gh CLI (already a project dependency)
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number), "--repo", repo_full_name],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr diff failed: {result.stderr}")

        patch = PatchSet(result.stdout)
        context_parts = []
        for patched_file in patch:
            if patched_file.is_binary_file:
                context_parts.append(f"## {patched_file.path} (binary file changed)")
                continue
            context_parts.append(f"## {patched_file.path}")
            context_parts.append(f"  +{patched_file.added} -{patched_file.removed} lines")
            for hunk in patched_file:
                context_parts.append(str(hunk))

        return "\n".join(context_parts)
```

### Pattern 3: Multi-Subscriber SSE with Named Event Types

**What:** Extend `ExecutionLogService._broadcast()` to emit additional named SSE events ("presence", "comment") alongside existing "log", "status", "complete" events. The frontend `AuthenticatedEventSource.addEventListener(type, handler)` already supports this.
**When to use:** For EXE-05 -- adding presence and comment events to the existing SSE stream.
**Example:**
```python
# Source: Extending existing ExecutionLogService pattern
class CollaborativeViewerService:
    _presence: Dict[str, Dict[str, dict]] = {}  # {exec_id: {viewer_id: metadata}}
    _lock = threading.Lock()

    @classmethod
    def join(cls, execution_id: str, viewer_id: str, display_name: str):
        with cls._lock:
            if execution_id not in cls._presence:
                cls._presence[execution_id] = {}
            cls._presence[execution_id][viewer_id] = {
                "viewer_id": viewer_id,
                "display_name": display_name,
                "joined_at": datetime.datetime.now().isoformat(),
            }
        # Broadcast presence update via existing SSE channel
        ExecutionLogService._broadcast(execution_id, "presence", {
            "viewers": list(cls._presence.get(execution_id, {}).values())
        })
```

### Anti-Patterns to Avoid

- **Storing diffs in the database as pre-computed HTML:** Store raw unified diff text; render to HTML on the frontend with diff2html. This keeps the backend output-format-agnostic and allows the frontend to control rendering (line-by-line vs. side-by-side toggle).
- **Running all chunks sequentially in one thread:** Each chunk should be executed independently (potentially in parallel threads) with separate execution IDs, then results merged. Sequential execution negates the token-cost benefit.
- **Using WebSocket for collaborative viewing:** The existing SSE infrastructure works well for the broadcast-heavy, low-bidirectional pattern. Adding WebSocket would introduce a parallel communication layer with its own connection management, authentication, and reconnection logic.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unified diff parsing | Custom diff parser | `unidiff` library | Handles binary files, renamed files, Git-specific headers, encoding issues |
| Side-by-side diff rendering | Custom diff HTML component | `diff2html` library | Handles syntax highlighting, line matching, word-level diffs |
| Text diff generation | Custom text comparison | `difflib.unified_diff()` | Python stdlib, well-tested, handles edge cases |
| Token counting for chunks | Character counting / naive splitting | `tiktoken` or model-specific tokenizer | Character count does not correlate with token count; overestimation wastes context, underestimation exceeds limits |

**Key insight:** The diff/comparison domain is deceptively complex. Edge cases (binary files, renamed files, moved code blocks, encoding differences, empty files) make custom implementations fragile. Using established libraries avoids months of edge-case debugging.

## Common Pitfalls

### Pitfall 1: Non-Deterministic LLM Output Confuses A/B Comparison

**What goes wrong:** Users expect replay to produce identical output for identical inputs. LLM outputs vary even with temperature=0 due to non-deterministic GPU operations and model version updates.
**Why it happens:** LLM inference is inherently stochastic. Even "deterministic" mode has variance.
**How to avoid:** Frame the feature as "comparison" not "regression test." The UI should explicitly label executions as "Run A" and "Run B" rather than "Expected" and "Actual." Document that differences are expected and the value is in seeing what changed.
**Warning signs:** User complaints about "the same prompt giving different results."
**Reference:** Braintrust A/B Testing Guide (2025) -- "Reduce variance with temperature=0 and fixed max length, but expect differences."

### Pitfall 2: Unbounded Chunk Count Creates Too Many Executions

**What goes wrong:** A 1MB code file chunked at 512 tokens produces 200+ chunks, each spawning a separate execution. This overwhelms the execution system, creates hundreds of DB records, and exhausts API rate limits.
**Why it happens:** No upper bound on chunk count.
**How to avoid:** Set a maximum chunk count (e.g., 20). If a context exceeds this limit, increase chunk size to fit within the limit rather than producing more chunks. Also implement chunk execution concurrency limits (e.g., 3 concurrent).
**Warning signs:** Execution count per trigger suddenly spikes by 100x.

### Pitfall 3: Memory Leak in Presence Tracking

**What goes wrong:** The `_presence` dict accumulates entries for viewers who disconnect without properly leaving (browser tab close, network drop).
**Why it happens:** SSE disconnections are detected via the subscriber queue (when `_broadcast` fails to put), but presence entries are not cleaned up automatically.
**How to avoid:** Tie presence cleanup to SSE subscriber removal. When `subscribe()` unregisters a queue in its `finally` block, also remove the viewer from `_presence`. Additionally, add a periodic heartbeat presence sweep (every 60 seconds) that removes viewers whose last heartbeat is older than 120 seconds.
**Warning signs:** Presence indicator shows "3 viewers" when only 1 is actually connected.

### Pitfall 4: Branch Tree Depth Causes Performance Degradation

**What goes wrong:** Deep branch chains (branching from a branch from a branch) require walking the full parent chain to reconstruct the message history for LLM context. At depth 50+, this becomes slow.
**Why it happens:** Tree traversal with no depth limit.
**How to avoid:** Limit branch depth to a reasonable maximum (e.g., 10 levels). Cache the reconstructed message chain for each branch point. Consider materializing the full chain as a JSON snapshot when creating a branch, avoiding recursive parent-chain walks.
**Warning signs:** Branch creation latency increasing with depth.

### Pitfall 5: PR Diff Exceeds Token Limits Even After Extraction

**What goes wrong:** A massive PR (500+ files changed) produces a diff-aware context that still exceeds the LLM context window.
**Why it happens:** Diff-aware injection reduces context but does not guarantee it fits within token limits.
**How to avoid:** Chain EXE-02 and EXE-03: first extract the diff-aware context, then if it exceeds a configurable threshold (e.g., 50k tokens), chunk it via the smart chunking pipeline. This composable architecture is essential for handling large PRs.
**Warning signs:** Execution failures with "context too long" errors from the CLI backend.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- For EXE-02: Number of context lines around changed hunks (5, 10, 20, 50)
- For EXE-03: Chunk size (256, 512, 1024 tokens), overlap percentage (0%, 10%, 20%)
- For EXE-01: Same prompt executed twice with temperature=0

**Dependent variables:**
- Token count reduction percentage (EXE-02)
- Duplicate finding count in merged results (EXE-03)
- Output similarity score between original and replay (EXE-01)
- Presence update latency (EXE-05)
- Branch creation time vs. depth (EXE-04)

**Controlled variables:**
- Same PR/repository for context injection tests
- Same LLM model and version
- Same backend type (claude)

**Baseline comparison:**
- EXE-02 baseline: Full file content inclusion (current behavior)
- EXE-03 baseline: No chunking (single prompt with full context)
- EXE-05 baseline: Single viewer SSE (current behavior)

**Ablation plan:**
1. Diff-aware injection with N=0 context lines vs. N=10 vs. full file -- tests whether surrounding context matters for output quality
2. AST-aware chunking vs. fixed-size chunking vs. no chunking -- tests whether semantic boundaries improve deduplication
3. Collaborative viewing with 1, 2, 5, 10 simultaneous viewers -- tests SSE fan-out scalability

**Statistical rigor:**
- Number of runs: 3-5 per configuration for LLM output comparison
- For EXE-02: Token count is deterministic given same diff; 1 run per configuration sufficient
- For EXE-05: Measure P95 latency over 100 events per viewer count

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Token reduction % | Validates EXE-02 40% target | `(full_tokens - diff_tokens) / full_tokens * 100` | 0% (full file inclusion) |
| Duplicate findings | Validates EXE-03 dedup | Count findings with overlapping file+line ranges | N/A (no chunking) |
| Diff line count | EXE-01 comparison quality | `len(difflib.unified_diff(output_a, output_b))` | N/A |
| Presence broadcast latency | EXE-05 real-time requirement | Time from join event to all viewers receiving update | N/A |
| Branch creation latency | EXE-04 performance | Time from fork request to branch ready | N/A |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Replay creates new execution with same inputs | Level 1 (Sanity) | Can verify by comparing stored fields |
| Diff view renders side-by-side in browser | Level 1 (Sanity) | Visual inspection |
| `gh pr diff` extracts changed files correctly | Level 1 (Sanity) | Unit test with known PR |
| Token reduction >= 40% on test PR | Level 2 (Proxy) | Measurable on representative PR |
| Chunk deduplication produces zero duplicates | Level 2 (Proxy) | Testable with synthetic overlapping chunks |
| Branch fork preserves original thread | Level 1 (Sanity) | DB query to verify both branches exist |
| Branch navigation works in UI | Level 2 (Proxy) | E2E test with branching scenario |
| Presence shows 2+ viewers | Level 2 (Proxy) | Open two browser tabs, verify indicators |
| Inline comments appear cross-viewer | Level 2 (Proxy) | Post comment in tab A, verify in tab B |
| Large context (>100KB) chunks correctly | Level 2 (Proxy) | Unit test with known large file |
| Full end-to-end replay + diff workflow | Level 3 (Deferred) | Needs complete pipeline with real LLM execution |

**Level 1 checks to always include:**
- Replay endpoint returns valid execution_id and stores replay link in DB
- Diff extraction produces non-empty output for a PR with changes
- Chunk boundaries fall on function/class boundaries (for Python files)
- Branch creation inserts new message with correct parent_message_id
- Presence join/leave events are broadcast to all subscribers

**Level 2 proxy metrics:**
- Token count comparison between full-file and diff-aware contexts (target: 40%+ reduction)
- Deduplication test: chunk a known file, produce findings, verify zero duplicates after merge
- Concurrent viewer test: 2-5 SSE connections to same execution, verify all receive events
- Branch tree with 3+ levels, verify each is independently navigable

**Level 3 deferred items:**
- Full LLM execution replay with actual Claude CLI (requires API credits)
- Performance under 10+ concurrent viewers (load testing)
- Cross-browser collaborative viewing test

## Production Considerations

### Known Failure Modes

- **In-memory state loss on restart:** All SSE subscribers, presence tracking, and active replay state is in-memory. Server restart during a collaborative viewing session drops all viewers without notification.
  - Prevention: Accept this limitation for v0.2.0. Document that collaborative features require persistent server uptime.
  - Detection: Health endpoint already reports active execution count and subscriber count via `ExecutionLogService.get_buffer_stats()`.

- **SQLite write contention during chunk execution:** Running 10-20 chunk executions in parallel generates concurrent DB writes for execution_logs. SQLite's single-writer constraint with 5s busy_timeout may cause write failures.
  - Prevention: Limit concurrent chunk executions to 3 (configurable). Queue additional chunks.
  - Detection: Monitor for "database is locked" errors in logs.

### Scaling Concerns

- **SSE fan-out with many viewers:** The existing `_broadcast()` iterates over all subscriber queues and puts messages. With 10+ viewers per execution, the broadcast lock hold time increases linearly.
  - At current scale (1-3 viewers): No issue.
  - At production scale (10+ viewers): Consider batching broadcasts or moving to asyncio-based fan-out.

- **Chunk execution cost:** Smart chunking multiplies execution count. A 20-chunk context means 20x the API calls and cost.
  - Prevention: Show estimated chunk count and projected cost before execution. Require user confirmation for >5 chunks.

### Common Implementation Traps

- **Storing replay diffs in memory:** Diff computation for large outputs can produce substantial data. Always stream diffs to the client rather than buffering the entire diff in memory.
  - Correct approach: Generate diff lazily via Python generator, stream as SSE or chunked HTTP response.

- **Blocking on chunk merge:** Waiting for all chunks to complete before starting merge blocks the UI.
  - Correct approach: Stream individual chunk results as they complete, show incremental merge progress.

## Code Examples

Verified patterns from official sources and the existing codebase:

### Generating Line-Level Diff (EXE-01)
```python
# Source: Python stdlib difflib documentation
import difflib

def generate_execution_diff(stdout_a: str, stdout_b: str,
                            label_a: str = "Run A", label_b: str = "Run B") -> str:
    """Generate unified diff between two execution outputs."""
    lines_a = stdout_a.splitlines(keepends=True)
    lines_b = stdout_b.splitlines(keepends=True)
    diff = difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, n=3)
    return "".join(diff)
```

### Extracting PR Diff Context (EXE-02)
```python
# Source: unidiff library documentation + Agented GitHubService pattern
import subprocess
from unidiff import PatchSet

def extract_diff_context(repo_full_name: str, pr_number: int,
                         context_lines: int = 10) -> tuple[str, dict]:
    """Extract diff-aware context from PR. Returns (context_text, stats)."""
    result = subprocess.run(
        ["gh", "pr", "diff", str(pr_number), "--repo", repo_full_name],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get PR diff: {result.stderr}")

    patch = PatchSet(result.stdout)
    total_original_lines = 0
    context_parts = []

    for pf in patch:
        if pf.is_binary_file:
            context_parts.append(f"# Binary file changed: {pf.path}")
            continue
        context_parts.append(f"# File: {pf.path} (+{pf.added} -{pf.removed})")
        for hunk in pf:
            context_parts.append(str(hunk))

    stats = {
        "files_changed": len(patch),
        "total_additions": sum(pf.added for pf in patch),
        "total_deletions": sum(pf.removed for pf in patch),
        "diff_token_estimate": len(" ".join(context_parts).split()),
    }
    return "\n".join(context_parts), stats
```

### AST-Aware Code Chunking (EXE-03)
```python
# Source: Python ast module documentation + cAST paper pattern
import ast

def chunk_python_code(source: str, max_chunk_tokens: int = 512) -> list[dict]:
    """Split Python source into semantically meaningful chunks."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback to line-based chunking for non-parseable files
        return _chunk_by_lines(source, max_chunk_tokens)

    chunks = []
    lines = source.splitlines()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno - 1
            end = node.end_lineno or start + 1
            chunk_text = "\n".join(lines[start:end])
            token_estimate = len(chunk_text.split())

            if token_estimate <= max_chunk_tokens:
                chunks.append({
                    "type": type(node).__name__,
                    "name": node.name,
                    "start_line": start + 1,
                    "end_line": end,
                    "content": chunk_text,
                    "token_estimate": token_estimate,
                })
            else:
                # Large function/class: split into sub-chunks
                for sub in _split_large_node(chunk_text, max_chunk_tokens):
                    chunks.append(sub)

    return chunks
```

### Conversation Branch DB Schema (EXE-04)
```sql
-- Source: Tree-structured message storage pattern (Forky, GitChat)
CREATE TABLE IF NOT EXISTS execution_branches (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    parent_branch_id TEXT,
    branch_point_index INTEGER NOT NULL DEFAULT 0,
    label TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_branch_id) REFERENCES execution_branches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS branch_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id TEXT NOT NULL,
    message_index INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (branch_id) REFERENCES execution_branches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_branch_messages_branch ON branch_messages(branch_id, message_index);
CREATE INDEX IF NOT EXISTS idx_execution_branches_exec ON execution_branches(execution_id);
```

### Collaborative Viewer SSE Events (EXE-05)
```python
# Source: Extending existing ExecutionLogService._broadcast pattern
# New SSE event types alongside existing "log", "status", "complete"

def broadcast_presence(execution_id: str, viewers: list[dict]):
    """Broadcast presence update to all subscribers."""
    ExecutionLogService._broadcast(execution_id, "presence", {
        "viewers": viewers,
        "count": len(viewers),
    })

def broadcast_comment(execution_id: str, comment: dict):
    """Broadcast inline comment to all subscribers."""
    ExecutionLogService._broadcast(execution_id, "comment", {
        "id": comment["id"],
        "viewer_id": comment["viewer_id"],
        "display_name": comment["display_name"],
        "line_number": comment["line_number"],
        "content": comment["content"],
        "created_at": comment["created_at"],
    })
```

```typescript
// Source: Extending existing AuthenticatedEventSource pattern in frontend
// frontend/src/composables/useCollaborativeViewer.ts

function setupCollaborativeEvents(eventSource: AuthenticatedEventSource) {
  eventSource.addEventListener('presence', (event: MessageEvent) => {
    const data = JSON.parse(event.data);
    viewers.value = data.viewers;
  });

  eventSource.addEventListener('comment', (event: MessageEvent) => {
    const data = JSON.parse(event.data);
    comments.value.push(data);
  });
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Reference |
|--------------|------------------|--------------|--------|-----------|
| Fixed-size text chunking | AST-aware semantic chunking | 2024-2025 | 15-30% better retrieval accuracy for code | cAST (CMU, 2025) |
| Linear chat history | Tree-structured branching | 2024-2025 | Enables exploratory LLM interaction patterns | ContextBranch (arXiv, Dec 2025) |
| Full file inclusion in prompts | Diff-aware context injection | 2024-2025 | 40-90% token reduction for PR reviews | Industry practice (Braintrust, Langfuse) |
| WebSocket for all real-time | SSE for broadcast-heavy patterns | 2024-2025 | Simpler implementation, better proxy compatibility | Industry consensus (2025) |

**Deprecated/outdated:**
- Fixed-size character splitting for code: Outperformed by AST-aware approaches in all benchmarks. Still acceptable as a fallback for unparseable files.
- Embedding-based semantic deduplication for code findings: Overkill for this use case. Line-number overlap detection is faster, simpler, and more reliable for code findings.

## Open Questions

1. **How to handle prompt modifications in replay?**
   - What we know: EXE-01 says "identical inputs" but the success criteria mentions "A/B testing prompt revisions." These are contradictory -- replaying with identical inputs is trivial, but A/B comparison of modified prompts requires a way to edit the prompt before replay.
   - What's unclear: Should the replay API accept an optional `prompt_override` parameter?
   - Recommendation: Support both modes -- "exact replay" (same prompt) and "modified replay" (user provides modified prompt). The diff view is useful in both cases.

2. **What counts as a "finding" for deduplication in EXE-03?**
   - What we know: The success criteria says "no duplicate findings" in merged results.
   - What's unclear: The system runs CLI tools (claude, opencode) that produce free-form text output. There is no structured "finding" format.
   - Recommendation: Define a simple finding structure (file path + line range + description). Parse structured output (JSON) from CLI tools when available. For unstructured text output, use line-number overlap within the same file as the deduplication key.

3. **How to persist inline comments after execution completes?**
   - What we know: Inline comments are broadcast via SSE during live viewing. But what happens to comments after the execution finishes and SSE streams close?
   - What's unclear: Should comments be stored in the database and shown on the execution detail page?
   - Recommendation: Store comments in a `viewer_comments` table with `execution_id` and `line_number` foreign keys. Display them alongside the execution log on the detail view.

4. **What is the "execution transcript" for branching (EXE-04)?**
   - What we know: The existing system stores execution output as `stdout_log` and `stderr_log` text blobs. This is output, not a conversation transcript.
   - What's unclear: EXE-04 references "any message index in an existing transcript" -- this implies structured message-by-message storage, which only exists for `super_agent_sessions.conversation_log`, not for trigger executions.
   - Recommendation: Implement branching for super agent sessions (which have structured conversation logs) rather than for trigger executions (which have unstructured output logs). Alternatively, if branching trigger executions is required, parse the JSON output from `--output-format json` CLI flag to extract individual message turns.

## Sources

### Primary (HIGH confidence)
- Python `difflib` standard library documentation -- text comparison algorithms, unified diff generation
- Python `ast` standard library documentation -- AST parsing for code chunking
- GitHub REST API documentation -- PR diff endpoints, changed files API
- Agented codebase analysis -- ExecutionService, ExecutionLogService, ProcessManager, AuthenticatedEventSource patterns

### Secondary (MEDIUM confidence)
- cAST: Enhancing Code RAG with Structural Chunking via AST (CMU, 2025) -- AST-based code chunking methodology
- ContextBranch: A Version Control Approach (arXiv 2512.13914, Dec 2025) -- conversation branching primitives
- Forky (GitHub, ishandhanani/forky) -- git-style LLM conversation branching implementation
- Braintrust A/B Testing Guide (2025) -- LLM prompt A/B testing methodology
- diff2html (GitHub, rtfpessoa/diff2html, 4.2k stars) -- unified diff to HTML rendering
- python-unidiff (GitHub, matiasb/python-unidiff, 570+ stars) -- unified diff parsing

### Tertiary (LOW confidence)
- Weaviate/Pinecone chunking strategy benchmarks (2025) -- chunking size recommendations (blog posts, not peer-reviewed)
- Flask SSE patterns (blog posts) -- multi-subscriber broadcasting patterns
- Velt collaboration API documentation -- presence and commenting architecture patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- uses Python stdlib (`difflib`, `ast`) plus well-established libraries (`unidiff`, `diff2html`)
- Architecture: HIGH -- extends existing proven patterns (ExecutionLogService, SSE broadcasting, Pydantic models)
- Paper recommendations: MEDIUM -- AST chunking and conversation branching are well-researched but specific to our use case (CLI tool output, not interactive LLM chat)
- Pitfalls: MEDIUM -- based on analysis of existing codebase concerns and general real-time system experience
- Experiment design: MEDIUM -- metrics are straightforward but LLM output variance makes A/B comparison inherently noisy

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable domain, no fast-moving dependencies)
