# Phase 8: Execution Intelligence & Replay - Research

**Researched:** 2026-03-04
**Domain:** Execution replay, diff-aware context engineering, smart chunking, conversation branching, real-time collaborative viewers
**Confidence:** MEDIUM-HIGH

## Summary

Phase 8 adds five distinct capabilities to the existing execution engine: (1) execution replay with side-by-side diff comparison, (2) diff-aware context injection for PR-triggered bots, (3) smart chunking for large code contexts, (4) conversation branching from any point in a transcript, and (5) live collaborative execution viewing with presence and inline comments.

The existing codebase provides a solid foundation. The `ExecutionLogService` already implements in-memory log buffering with SSE fan-out via `threading.Queue`, and the `execution_logs` table stores the full prompt, command, trigger config snapshot, stdout/stderr logs, and token usage. This means replay is primarily a matter of re-invoking `run_trigger` with stored inputs and building a comparison UI. Diff-aware context is achievable by parsing `git diff` output with the `unidiff` library before prompt rendering. Smart chunking requires a semantic-boundary splitter for code files. Conversation branching maps cleanly to the `agent_conversations` table with a tree structure (parent reference per message). The collaborative viewer extends the existing SSE subscriber pattern with presence tracking and a comment persistence layer.

**Primary recommendation:** Build each feature as an independent service module that extends the existing `ExecutionService`/`ExecutionLogService` pattern -- class-level state with `threading.Lock`, SSE broadcast via `Queue`, raw SQLite persistence. Use `unidiff` for diff parsing, Python `difflib` for output comparison, and extend the SSE protocol with presence/comment event types for collaboration.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists. All implementation choices are at researcher's discretion. No locked decisions, no deferred ideas.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Tree-Based Conversation Branching (ContextBranch Pattern)

**Recommendation:** Implement conversation branching using a tree data structure where each message is a node with a parent reference, and branches are created by forking from any node.

**Evidence:**
- Guo et al. "Context Branching for LLM Conversations: A Version Control Approach to Exploratory Programming" (arXiv:2512.13914, Dec 2025) -- Achieved 2.5% overall quality improvement (p=0.010, Cohen's d=0.73), 4.6% improvement in focus (d=0.80), and 58.1% reduction in context size. System uses four primitives: checkpoint, branch, switch, inject.
- Forky (github.com/ishandhanani/forky) -- Open-source implementation of git-style LLM chat branching using DAG structure. Demonstrates practical viability of tree-based message storage.
- The ContextBranch paper found benefits concentrated in complex scenarios with "conceptually distant explorations" (up to 13.2% improvement), validating that branching specifically addresses context pollution.

**Confidence:** HIGH -- Peer-reviewed paper with quantitative results plus working open-source implementation.
**Expected improvement:** 58% reduction in context size per branch; improved focus for A/B prompt exploration.
**Caveats:** Implementation in the paper is 900 lines of Python. Our scope is narrower (fork from message index, no merge/inject needed for v1).

### Recommendation 2: Diff-Aware Context Injection via Unified Diff Parsing

**Recommendation:** Use the `unidiff` Python library to parse `git diff` output from PRs, extract only changed files with configurable surrounding context lines (default N=10), and inject this focused context into bot prompts instead of full file contents.

**Evidence:**
- Redis engineering blog (2026) documents that context-aware tools reduce token usage from 198,000 tokens (full `git diff`) to ~50 tokens (summarized diff), demonstrating the magnitude of potential savings.
- LongLLMLingua (Jiang et al., 2023) -- Achieves up to 4x token reduction with 17.1% performance improvement for question-aware compression, establishing that focused context improves both cost and quality.
- K2View MCP strategies blog (2026) -- Documents that grounded prompts with only relevant context outperform full-context prompts in production LLM applications.

**Confidence:** HIGH -- Multiple sources confirm token reduction improves both cost and output quality. The `unidiff` library (v0.7.5) is mature and well-tested.
**Expected improvement:** At least 40% token reduction (success criterion target) is conservative; literature suggests 60-80% reduction for typical PRs.
**Caveats:** Very large diffs (1000+ changed files) may still need chunking. Binary file diffs are not meaningful for LLM context.

### Recommendation 3: Code-Aware Semantic Chunking for Large Contexts

**Recommendation:** Use a recursive character splitter with code-aware separators (function/class boundaries) at 400-512 token chunks with 10-20% overlap. Split on language-aware boundaries: class definitions, function definitions, blank line pairs, then single blank lines, then lines.

**Evidence:**
- Pinecone chunking strategies guide (2024-2026) -- Recommends RecursiveCharacterTextSplitter at 400-512 tokens with 10-20% overlap as the default starting point.
- NAACL 2025 Findings paper -- Found fixed 200-word chunks match or beat semantic chunking across retrieval and answer generation tasks, challenging the assumption that semantic chunking is always better. This supports our simpler code-boundary approach.
- MDPI Bioengineering (Nov 2025) -- Found adaptive chunking aligned to logical topic boundaries hit 87% accuracy versus 13% for fixed-size baselines in clinical decision support, supporting boundary-aware splitting for structured content like code.
- LangCopilot document chunking guide (2025) -- Tested 9 strategies; recursive character splitting with domain-appropriate separators was the best general-purpose approach.

**Confidence:** MEDIUM-HIGH -- Multiple sources agree on the approach, though the specific code-boundary separators are our design choice not directly validated in papers.
**Expected improvement:** Eliminates duplicate findings across chunks (success criterion); maintains semantic coherence within each chunk.
**Caveats:** Deduplication of results across chunks requires a merging step. Simple string-matching dedup may miss semantically equivalent but differently worded findings.

### Recommendation 4: SSE-Based Presence Protocol for Collaborative Viewing

**Recommendation:** Extend the existing SSE fan-out pattern with additional event types (`presence_join`, `presence_leave`, `presence_heartbeat`, `inline_comment`) rather than introducing WebSockets. Use the existing `threading.Queue` subscriber model with per-viewer identity.

**Evidence:**
- Existing codebase pattern: `ExecutionLogService._subscribers` already implements multi-client SSE fan-out with `Queue`-per-subscriber. This is proven to work in production for this application.
- Flask-SSE documentation (flask-sse.readthedocs.io) -- Confirms SSE is appropriate for server-to-client push patterns. Notes that bidirectional communication (for comments) requires a companion POST endpoint.
- Ajackus SSE implementation guide (2025) -- Documents the standard pattern: SSE for server push, regular HTTP POST for client-to-server messages.

**Confidence:** HIGH -- Extends proven existing pattern. No new infrastructure (Redis, WebSocket server) needed.
**Expected improvement:** Real-time presence with sub-100ms latency (same as current log streaming).
**Caveats:** Inline comments require a POST endpoint + broadcast pattern (SSE is unidirectional). Presence heartbeats add ~1 message/30s per viewer to server load. For >50 concurrent viewers, consider switching to a pub/sub broker.

### Recommendation 5: Line-Level Output Diffing with Python difflib

**Recommendation:** Use Python's stdlib `difflib.unified_diff` for backend output comparison and `difflib.HtmlDiff.make_table()` for generating side-by-side HTML diff views. Send raw diff data to the frontend and render with a Vue component for interactive highlighting.

**Evidence:**
- Python official docs (docs.python.org/3/library/difflib.html) -- `HtmlDiff` produces side-by-side HTML tables with inter-line and intra-line change highlights. Zero external dependencies.
- GNU diffutils documentation -- Establishes the standard side-by-side format that users expect from diff tools.
- Braintrust A/B testing guide (2025) -- Documents that "diff mode to highlight textual differences in outputs" is the standard UX pattern for LLM output comparison.

**Confidence:** HIGH -- Python stdlib, well-documented, widely used.
**Expected improvement:** Line-level highlighting of output differences as required by success criteria.
**Caveats:** Very large outputs (>10K lines) may produce slow HTML rendering. Consider pagination or virtual scrolling for the frontend diff viewer.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| unidiff | 0.7.5 | Parse unified diff output from `git diff` | Standard Python library for diff parsing; MIT license; mature (14 releases) |
| difflib (stdlib) | Python 3.10+ | Generate line-level output diffs for A/B comparison | Python standard library; zero dependencies; HtmlDiff produces ready-to-render HTML |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tiktoken | 0.7+ | Token counting for chunk size estimation | When implementing smart chunking to enforce token limits per chunk |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Evidence |
|------------|-----------|----------|----------|
| unidiff | whatthepatch (PyPI) | whatthepatch also applies patches; unidiff is focused on parsing/metadata extraction which is our use case | unidiff has clearer API for our read-only diff parsing needs |
| difflib | diff-match-patch (Google) | diff-match-patch is faster for character-level diffs but overkill for line-level comparison | difflib is stdlib; no dependency to manage |
| SSE presence | WebSockets | WebSockets enable true bidirectional; SSE requires POST endpoints for client-to-server | SSE matches existing architecture; avoids new infrastructure |
| tiktoken | manual char-count estimation | tiktoken is accurate but adds a dependency; 4 chars/token heuristic is a reasonable approximation | Use tiktoken if accurate token budgets matter for cost prediction |

**Installation:**
```bash
cd backend && uv add unidiff
# tiktoken is optional:
cd backend && uv add tiktoken
```

No new frontend dependencies needed -- `difflib` output is rendered as HTML on the backend or as structured data consumed by a Vue component.

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
  services/
    replay_service.py          # EXE-01: Execution replay logic
    diff_context_service.py    # EXE-02: Diff-aware context extraction
    chunk_service.py           # EXE-03: Smart chunking + result merging
    conversation_branch_service.py  # EXE-04: Conversation branching
    collaborative_viewer_service.py # EXE-05: Presence + inline comments
  routes/
    replay.py                  # Replay + comparison API endpoints
    collaborative.py           # Presence + comment endpoints
  db/
    replay.py                  # Replay comparison records
    conversation_branches.py   # Branch tree CRUD
    viewer_comments.py         # Inline comment persistence
  models/
    replay.py                  # Pydantic models for replay requests/responses
    collaborative.py           # Pydantic models for presence/comments

frontend/src/
  composables/
    useReplay.ts               # Replay comparison state
    useCollaborativeViewer.ts  # Presence + comments composable
    useConversationBranch.ts   # Branch navigation composable
  components/
    execution/
      DiffViewer.vue           # Side-by-side output diff component
      ReplayComparison.vue     # A/B comparison layout
      ChunkResults.vue         # Merged chunk results viewer
      PresenceIndicator.vue    # Who's watching indicator
      InlineComment.vue        # Comment on log line
      BranchNavigator.vue      # Conversation branch tree UI
  services/api/
    replay.ts                  # Replay API client
    collaborative.ts           # Collaborative viewer API client
```

### Pattern 1: Replay as Input Snapshot + Re-execution

**What:** Store all inputs needed for replay at execution time (already partially done via `prompt`, `command`, `trigger_config_snapshot` in `execution_logs`). Replay creates a new execution with the same inputs, producing a new `execution_id` that can be compared with the original.

**When to use:** Every execution replay operation.

**Example:**
```python
# Source: Derived from existing ExecutionService.run_trigger pattern
class ReplayService:
    @classmethod
    def replay_execution(cls, original_execution_id: str) -> str:
        """Replay an execution with identical inputs. Returns new execution_id."""
        original = get_execution_log(original_execution_id)
        if not original:
            raise ValueError(f"Execution {original_execution_id} not found")

        trigger = json.loads(original["trigger_config_snapshot"])
        # Re-run with same prompt (already rendered and stored)
        new_execution_id = ExecutionLogService.start_execution(
            trigger_id=original["trigger_id"],
            trigger_type=f"replay:{original['trigger_type']}",
            prompt=original["prompt"],
            backend_type=original["backend_type"],
            command=original["command"],
            trigger_config_snapshot=original["trigger_config_snapshot"],
        )

        # Store replay relationship
        create_replay_comparison(
            original_execution_id=original_execution_id,
            replay_execution_id=new_execution_id,
        )

        # Actually run the command (reuse existing subprocess machinery)
        # ...spawn process identical to run_trigger...

        return new_execution_id
```

### Pattern 2: Diff-Aware Context as Pre-Prompt Filter

**What:** Before calling `PromptRenderer.render()`, intercept the paths resolution for GitHub PRs and replace full file contents with diff-focused context.

**When to use:** When `event.type == "github_pr"` and the trigger is configured for diff-aware context.

**Example:**
```python
# Source: Extends existing prompt rendering pipeline
import subprocess
from unidiff import PatchSet

class DiffContextService:
    CONTEXT_LINES = 10  # Lines of surrounding context

    @classmethod
    def extract_pr_diff_context(cls, repo_path: str, base_branch: str = "main") -> str:
        """Extract only changed files + surrounding context from a PR."""
        result = subprocess.run(
            ["git", "diff", f"{base_branch}...HEAD", f"-U{cls.CONTEXT_LINES}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git diff failed: {result.stderr}")

        patch = PatchSet(result.stdout)
        context_parts = []
        for patched_file in patch:
            context_parts.append(f"## {patched_file.path}")
            context_parts.append(f"(+{patched_file.added}, -{patched_file.removed} lines)")
            for hunk in patched_file:
                context_parts.append(str(hunk))

        return "\n".join(context_parts)
```

### Pattern 3: Chunk-Process-Merge Pipeline

**What:** Split large context into chunks at semantic boundaries, process each chunk independently with the bot, then merge/deduplicate results.

**When to use:** When total context exceeds 100KB (success criterion threshold).

**Example:**
```python
# Source: Derived from Pinecone/LangCopilot chunking best practices
class ChunkService:
    # Code-aware separators in priority order
    CODE_SEPARATORS = [
        "\nclass ",       # Class boundaries
        "\ndef ",         # Function boundaries
        "\nasync def ",   # Async function boundaries
        "\n\n\n",         # Triple newlines (major sections)
        "\n\n",           # Double newlines (paragraph/block boundaries)
        "\n",             # Single newlines (line boundaries)
    ]
    MAX_CHUNK_CHARS = 2000  # ~500 tokens at 4 chars/token

    @classmethod
    def chunk_code(cls, content: str, file_path: str = "") -> list[str]:
        """Split code content into semantically meaningful chunks."""
        chunks = []
        current_chunk = []
        current_size = 0

        for separator in cls.CODE_SEPARATORS:
            if separator in content:
                parts = content.split(separator)
                for part in parts:
                    if current_size + len(part) > cls.MAX_CHUNK_CHARS and current_chunk:
                        chunks.append(separator.join(current_chunk))
                        current_chunk = [part]
                        current_size = len(part)
                    else:
                        current_chunk.append(part)
                        current_size += len(part)
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                return chunks

        # Fallback: split by character limit
        for i in range(0, len(content), cls.MAX_CHUNK_CHARS):
            chunks.append(content[i:i + cls.MAX_CHUNK_CHARS])
        return chunks
```

### Pattern 4: SSE Presence Protocol Extension

**What:** Add viewer identity to SSE subscriptions and broadcast join/leave/heartbeat events alongside log events.

**When to use:** Collaborative execution viewer (EXE-05).

**Example:**
```python
# Source: Extends existing ExecutionLogService._subscribers pattern
class CollaborativeViewerService:
    # Active viewers: {execution_id: {viewer_id: {"name": str, "last_seen": datetime}}}
    _viewers: Dict[str, Dict[str, dict]] = {}
    _lock = threading.Lock()

    @classmethod
    def join(cls, execution_id: str, viewer_id: str, viewer_name: str):
        """Register a viewer and broadcast presence."""
        with cls._lock:
            if execution_id not in cls._viewers:
                cls._viewers[execution_id] = {}
            cls._viewers[execution_id][viewer_id] = {
                "name": viewer_name,
                "last_seen": datetime.datetime.now(),
            }
        # Broadcast to existing SSE subscribers
        ExecutionLogService._broadcast(
            execution_id,
            "presence_join",
            {"viewer_id": viewer_id, "name": viewer_name,
             "viewers": cls.get_viewer_list(execution_id)},
        )
```

### Anti-Patterns to Avoid

- **Full file inclusion for PR context:** Never send entire file contents when a diff is available. This wastes tokens and dilutes the LLM's focus on what actually changed. Papers confirm focused context outperforms full context.
- **Mutable conversation history for branching:** Never modify the original conversation when creating a branch. The ContextBranch paper emphasizes immutable snapshots and deep-copy semantics for branch isolation.
- **Synchronous chunked execution:** Never process chunks sequentially in the request thread. Use background threads (matching existing `run_trigger` pattern) and stream results via SSE.
- **WebSocket introduction for presence:** The existing SSE infrastructure handles multi-client fan-out well. Adding WebSockets introduces operational complexity (new server, connection management) for marginal benefit.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unified diff parsing | Custom regex parser for git diff output | `unidiff` library | Unified diff format has edge cases (binary files, renames, symlinks, multi-byte encodings) that a mature library handles correctly |
| Text diff comparison | Custom line-matching algorithm | Python `difflib.unified_diff` / `difflib.HtmlDiff` | SequenceMatcher algorithm is well-optimized; HtmlDiff produces ready-to-use HTML with intra-line highlighting |
| Token counting | Character count / 4 estimation | `tiktoken` (if accuracy matters) | Token boundaries differ between models; tiktoken uses actual model tokenizers |
| SSE message formatting | Manual string concatenation of SSE events | Existing `ExecutionLogService._format_sse()` | Already handles JSON serialization and SSE protocol formatting correctly |

**Key insight:** The existing codebase already solves the hardest infrastructure problems (subprocess streaming, SSE fan-out, threaded execution). Phase 8 features are primarily about extending existing patterns with new data flows, not building new infrastructure.

## Common Pitfalls

### Pitfall 1: Replay Non-Determinism

**What goes wrong:** Replaying an execution with "identical inputs" produces wildly different output because external state changed (repo contents, API versions, model updates).
**Why it happens:** LLM outputs are inherently non-deterministic. The execution environment (file system, network) may have changed since the original run.
**How to avoid:** Clearly communicate in the UI that replay creates a new execution for comparison purposes, not an exact reproduction. Store the original prompt verbatim (already done in `execution_logs.prompt`). For GitHub triggers, the diff context at replay time may differ from the original.
**Warning signs:** Users expecting identical output from replayed executions.
**Paper reference:** Braintrust A/B testing guide documents this as a fundamental property of LLM evaluation.

### Pitfall 2: Chunking Destroys Cross-File Context

**What goes wrong:** Splitting context into chunks means the bot loses awareness of cross-file dependencies. A security issue in file A caused by an import from file B is missed when A and B are in different chunks.
**Why it happens:** Chunk boundaries don't respect semantic dependencies between files.
**How to avoid:** Include import statements and file headers in chunk preambles. Consider a two-pass approach: first pass identifies cross-file references, second pass ensures related files are co-chunked.
**Warning signs:** Findings that reference "unknown" functions or types that exist in other chunks.
**Paper reference:** MDPI Bioengineering (Nov 2025) found 87% accuracy for boundary-aware chunking vs. 13% for naive splitting, confirming that boundary placement is critical.

### Pitfall 3: SSE Subscriber Leak in Collaborative Viewer

**What goes wrong:** Viewers that disconnect without clean teardown leave orphaned Queue objects in `_subscribers`, consuming memory indefinitely.
**Why it happens:** Browser tab close, network interruption, or client crash don't send a disconnect signal to SSE endpoints.
**How to avoid:** Use heartbeat-based presence detection (existing pattern: 30s Queue.get timeout). Remove viewers that miss 2+ heartbeats. The existing `ExecutionLogService.cleanup_stale_executions()` pattern should be extended to clean viewer state.
**Warning signs:** Growing memory usage on long-running executions with many viewers.
**Paper reference:** Flask-SSE documentation notes this as a common production issue.

### Pitfall 4: Branch Isolation Violation

**What goes wrong:** Creating a branch from message index N accidentally includes messages from a different branch that was active at the time.
**Why it happens:** Storing messages as a flat JSON array (current `agent_conversations.messages` TEXT field) makes branching error-prone because there's no parent-child relationship between messages.
**How to avoid:** Model the conversation as a tree. Each message row has: `id`, `conversation_id`, `parent_message_id`, `branch_id`, `role`, `content`, `created_at`. A branch is defined by its root message (the fork point) and its unique `branch_id`.
**Warning signs:** Messages from one branch appearing in another branch's view.
**Paper reference:** ContextBranch (arXiv:2512.13914) formally proves branch isolation as a correctness property.

### Pitfall 5: Diff Context Too Small or Too Large

**What goes wrong:** Setting context lines (the `-U` flag) too low misses relevant surrounding code; too high includes too much noise and defeats the purpose of diff-aware injection.
**Why it happens:** The optimal context window depends on the code's structure and the bot's task.
**How to avoid:** Make context lines configurable per trigger (default 10, range 3-50). Include function/class headers even if they're outside the context window by detecting the enclosing scope.
**Warning signs:** Bot outputs that say "I need to see more context around this change" or bot outputs that include findings about unchanged code.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Context lines (N) for diff-aware injection: 3, 5, 10, 20, 50
- Chunk size for smart chunking: 200, 400, 800, 1600 tokens
- Deduplication strategy: exact string match, normalized string match, semantic similarity

**Dependent variables:**
- Token count reduction (%) compared to full-file inclusion
- Finding quality (precision/recall of bot outputs)
- Duplicate finding rate in merged chunk results
- Replay comparison usefulness (user perception)

**Controlled variables:**
- Same trigger/bot configuration across comparisons
- Same AI backend and model version
- Same test PR / code context for reproducibility

**Baseline comparison:**
- Method: Current full-file context inclusion (existing `run_trigger` behavior)
- Expected performance: ~100% of file tokens sent to LLM
- Our target: 40% token reduction (success criterion) with no quality loss

**Ablation plan:**
1. Diff-aware only (no chunking) vs. full context -- tests token reduction hypothesis
2. Chunked + no dedup vs. chunked + dedup -- tests deduplication necessity
3. Context lines N=5 vs. N=10 vs. N=20 -- tests optimal context window

**Statistical rigor:**
- Number of runs: 3 runs per configuration (LLM output variance)
- Compare token counts directly (deterministic metric)
- Manual quality assessment of bot outputs on 5 representative PRs

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Token count reduction (%) | Primary cost saving metric | `(full_tokens - diff_tokens) / full_tokens * 100` | 0% (full inclusion) |
| Unique findings ratio | Dedup effectiveness | `unique_findings / total_findings_across_chunks` | 1.0 (no chunks) |
| Context relevance score | Bot output quality | Manual assessment: 1-5 scale on finding relevance | Current trigger output quality |
| Replay diff coverage | A/B comparison utility | % of output lines that differ between original and replay | N/A (new feature) |
| Presence latency | Collaborative viewer responsiveness | Time from viewer join to presence indicator appearing for others | N/A (new feature) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Replay creates new execution with same prompt | Level 1 (Sanity) | Database query: compare prompts |
| Replay comparison stored with both execution IDs | Level 1 (Sanity) | Database query |
| Diff parser extracts correct files from test PR | Level 1 (Sanity) | Unit test with fixture diff |
| Token count reduced by 40%+ on test PR | Level 2 (Proxy) | Measure on representative test data |
| Chunks have no duplicate findings | Level 2 (Proxy) | Run chunked execution, check dedup |
| Branch preserves original conversation | Level 1 (Sanity) | Database query: original messages unchanged |
| Branch creates independent navigable thread | Level 2 (Proxy) | UI navigation test |
| Presence shows 2+ viewers | Level 2 (Proxy) | Open 2 browser tabs, verify indicators |
| Inline comments appear in real-time | Level 2 (Proxy) | Post comment, verify SSE broadcast |
| Side-by-side diff highlights line differences | Level 2 (Proxy) | Visual verification on replay output |
| Full end-to-end replay + compare workflow | Level 3 (Deferred) | Needs complete pipeline with real bot execution |

**Level 1 checks to always include:**
- Replay endpoint returns new execution_id
- Original execution data is not modified by replay
- Diff parser handles edge cases: empty diff, binary files, renamed files
- Branch creation doesn't mutate parent conversation messages
- Presence join/leave events have correct viewer list
- Comment POST returns created comment with timestamp

**Level 2 proxy metrics:**
- Token count comparison: measure actual tokens on a fixture PR diff vs. full file inclusion
- Run chunked execution on a >100KB test file, verify no duplicate findings in merged output
- Open 2 SSE connections to same execution, verify presence events received by both
- Create conversation branch, send message on branch, verify original thread unaffected

**Level 3 deferred items:**
- Full integration test: trigger PR webhook -> diff-aware context -> execute -> replay -> compare
- Performance under load: 10+ concurrent viewers on a single execution stream
- Cross-browser presence indicator synchronization

## Production Considerations

### Known Failure Modes

- **In-memory state loss on server restart:** `ExecutionLogService._log_buffers` and `_subscribers` are in-memory. If the server restarts during a collaborative viewing session, all presence state and live comment subscriptions are lost.
  - Prevention: Accept this limitation for v1. Document that presence is ephemeral. Comments are persisted to DB, so they survive restarts.
  - Detection: Monitor `get_buffer_stats()` for active execution count.

- **SQLite write contention under concurrent comments:** Multiple viewers posting inline comments simultaneously on the same execution may hit SQLite's single-writer lock.
  - Prevention: Use `PRAGMA busy_timeout = 5000` (already set in `get_connection()`). Comments are small writes, so contention should be brief.
  - Detection: Monitor for `sqlite3.OperationalError: database is locked` in logs.

### Scaling Concerns

- **Concurrent viewers per execution:**
  - At current scale (1-5 viewers): SSE Queue fan-out works fine. Each viewer adds one Queue and receives all broadcast events.
  - At production scale (50+ viewers): Consider Redis Pub/Sub as a broadcast backend to avoid N^2 message distribution in the server process.

- **Replay storage:**
  - At current scale: Replay comparisons are stored as references (two execution_ids). The actual outputs are in `execution_logs`.
  - At production scale: Old replay comparisons and execution logs need a retention policy. Consider adding `created_at` index and periodic cleanup.

- **Chunked execution parallelism:**
  - At current scale: Process chunks sequentially to avoid overwhelming the AI backend with parallel requests.
  - At production scale: Implement a concurrency limiter (semaphore) for parallel chunk processing.

### Common Implementation Traps

- **Forgetting to store replay metadata:** The replay relationship (original_id -> replay_id) must be persisted before starting the replay execution. If the replay crashes, the UI needs to know it was a replay attempt.
  - Correct approach: Insert replay_comparisons row first, then start execution.

- **Blocking the request thread on chunk processing:** Smart chunking may involve multiple bot invocations. Never process all chunks in a single HTTP request.
  - Correct approach: Return immediately with a job ID, process chunks in background threads, stream results via SSE.

- **Mutating trigger config between replay invocations:** If the trigger's prompt template changed since the original execution, replay should use the snapshot, not the current config.
  - Correct approach: Always use `trigger_config_snapshot` from the original `execution_logs` row.

## Code Examples

Verified patterns from official sources and the existing codebase:

### Parsing Git Diff with unidiff

```python
# Source: unidiff PyPI docs + GitHub README (github.com/matiasb/python-unidiff)
from unidiff import PatchSet

def parse_diff(diff_text: str) -> list[dict]:
    """Parse unified diff text and extract changed file info."""
    patch = PatchSet(diff_text)
    files = []
    for patched_file in patch:
        files.append({
            "path": patched_file.path,
            "is_added": patched_file.is_added_file,
            "is_removed": patched_file.is_removed_file,
            "is_modified": patched_file.is_modified_file,
            "added_lines": patched_file.added,
            "removed_lines": patched_file.removed,
            "hunks": [str(hunk) for hunk in patched_file],
        })
    return files
```

### Generating Side-by-Side Diff with difflib

```python
# Source: Python docs (docs.python.org/3/library/difflib.html)
import difflib

def generate_output_diff(original_output: str, replay_output: str) -> dict:
    """Generate a structured diff between two execution outputs."""
    original_lines = original_output.splitlines()
    replay_lines = replay_output.splitlines()

    # Unified diff for structured data (frontend rendering)
    unified = list(difflib.unified_diff(
        original_lines, replay_lines,
        fromfile="Original", tofile="Replay",
        lineterm=""
    ))

    # HTML diff for server-rendered view
    html_diff = difflib.HtmlDiff()
    html_table = html_diff.make_table(
        original_lines, replay_lines,
        fromdesc="Original", todesc="Replay",
        context=True, numlines=3
    )

    return {
        "unified_diff": unified,
        "html_diff": html_table,
        "original_line_count": len(original_lines),
        "replay_line_count": len(replay_lines),
    }
```

### SSE Presence Event Format

```python
# Source: Extends existing ExecutionLogService._format_sse pattern
# New SSE event types for collaborative viewer

# Presence join event
# event: presence_join
# data: {"viewer_id": "usr-abc123", "name": "Alice",
#         "viewers": [{"id": "usr-abc123", "name": "Alice"},
#                     {"id": "usr-def456", "name": "Bob"}]}

# Inline comment event
# event: inline_comment
# data: {"comment_id": "cmt-xyz789", "viewer_id": "usr-abc123",
#         "name": "Alice", "line_number": 42,
#         "content": "This looks suspicious", "timestamp": "2026-03-04T12:00:00"}
```

### Conversation Branch Data Model

```python
# Source: Derived from ContextBranch paper (arXiv:2512.13914)
# New table for conversation messages with tree structure

"""
CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,            -- msg-xxxxxx
    conversation_id TEXT NOT NULL,  -- conv-xxxxxx (parent conversation)
    branch_id TEXT NOT NULL,        -- branch-xxxxxx (which branch this message belongs to)
    parent_message_id TEXT,         -- msg-xxxxxx (null for root messages)
    message_index INTEGER NOT NULL, -- Position within the branch
    role TEXT NOT NULL,             -- 'user' | 'assistant' | 'system'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_branches (
    id TEXT PRIMARY KEY,            -- branch-xxxxxx
    conversation_id TEXT NOT NULL,  -- conv-xxxxxx
    parent_branch_id TEXT,          -- branch-xxxxxx (null for main branch)
    fork_message_id TEXT,           -- msg-xxxxxx (message this branch forks from)
    name TEXT,                      -- User-assigned branch name
    status TEXT DEFAULT 'active',   -- 'active' | 'archived'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE
);
"""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Paper |
|--------------|------------------|--------------|--------|-------|
| Full file context in prompts | Diff-aware context injection | 2024-2025 | 60-80% token reduction | LongLLMLingua (Jiang 2023), K2View MCP strategies (2026) |
| Linear chat history | Tree-structured conversation branching | 2025 | 58% context reduction, improved focus | ContextBranch (Guo 2025, arXiv:2512.13914) |
| Fixed-size chunking | Code-boundary-aware chunking | 2024-2025 | 87% accuracy vs 13% for naive | MDPI Bioengineering (Nov 2025), NAACL 2025 Findings |
| Polling for presence | SSE-based real-time presence | 2020+ | Sub-100ms latency | Industry standard (Flask-SSE, EventSource API) |

**Deprecated/outdated:**
- Full-file context injection for PR reviews: Sending entire files when only diffs matter. Wastes tokens and reduces output quality per LongLLMLingua findings.
- Flat JSON message arrays for conversations: The `agent_conversations.messages TEXT` column stores messages as a flat JSON array. This works for linear conversations but cannot represent branches. A normalized table with parent references is needed.

## Open Questions

1. **Replay with changed external state**
   - What we know: The prompt is stored verbatim, so the LLM input is identical. But the execution environment (cloned repo contents, API state) may differ.
   - What's unclear: Should replay re-clone the repo (getting latest code) or attempt to restore the original state (git checkout to the original commit)?
   - Paper leads: Braintrust A/B guide treats non-determinism as expected and focuses on statistical comparison across runs.
   - Recommendation: For v1, replay uses the stored prompt directly without re-cloning. Document that environmental differences may cause output variation. In v2, consider storing the git SHA and checking out the same commit.

2. **Deduplication strategy for chunked results**
   - What we know: Simple string matching catches exact duplicates. Semantic deduplication (embedding similarity) catches paraphrased duplicates but adds complexity.
   - What's unclear: What duplicate rate to expect in practice. Is exact-match dedup sufficient?
   - Paper leads: NAACL 2025 Findings paper suggests simpler approaches often match sophisticated ones.
   - Recommendation: Start with normalized string matching (lowercase, strip whitespace, remove line numbers). Add semantic dedup only if testing reveals significant paraphrased duplicates.

3. **Comment persistence model**
   - What we know: Comments must persist beyond the SSE session (so they're visible when replaying logs from DB).
   - What's unclear: Should comments reference line numbers in stdout or line numbers in the rendered output? Stdout line numbers are stable; rendered output line numbers depend on formatting.
   - Recommendation: Anchor comments to stdout line numbers (immutable once execution completes). Frontend maps these to rendered positions.

## Sources

### Primary (HIGH confidence)
- Guo et al. "Context Branching for LLM Conversations" (arXiv:2512.13914, Dec 2025) -- Established branching architecture with formal correctness proofs
- Python difflib documentation (docs.python.org/3/library/difflib.html) -- Verified HtmlDiff API and capabilities
- unidiff library (github.com/matiasb/python-unidiff, v0.7.5) -- Verified diff parsing API
- Existing Agented codebase -- ExecutionLogService, ExecutionService, ProcessManager patterns verified by code reading

### Secondary (MEDIUM confidence)
- Pinecone chunking strategies guide (pinecone.io/learn/chunking-strategies/) -- Recommended 400-512 token chunks with overlap
- Braintrust A/B testing guide (braintrust.dev/articles/ab-testing-llm-prompts) -- Established comparison UI patterns
- NAACL 2025 Findings paper on semantic chunking -- Fixed chunks competitive with semantic chunking
- MDPI Bioengineering (Nov 2025) -- Boundary-aware chunking benefits for structured content
- LangCopilot chunking guide (2025) -- Tested 9 strategies, recursive character splitting best general-purpose
- Redis LLM token optimization blog (2026) -- Context-aware tools reduce tokens by orders of magnitude

### Tertiary (LOW confidence)
- Flask-SSE documentation (flask-sse.readthedocs.io) -- SSE production patterns; verified against existing codebase
- Medium articles on Flask SSE implementation -- Confirmed SSE pattern but low authority source
- Forky GitHub repo (github.com/ishandhanani/forky) -- Working implementation of conversation branching; not peer-reviewed

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Uses Python stdlib (difflib) plus well-established library (unidiff v0.7.5)
- Architecture: HIGH - Extends proven existing patterns (ExecutionLogService, SSE fan-out, raw SQLite)
- Paper recommendations: MEDIUM-HIGH - Branching backed by peer-reviewed paper; chunking backed by multiple evaluation studies; diff-aware injection supported by industry consensus
- Pitfalls: HIGH - Derived from codebase analysis (known SSE subscriber leak patterns, SQLite contention) and published guides
- Experiment design: MEDIUM - Practical design but baselines for this specific codebase need to be established empirically

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable domain, no fast-moving dependencies)
