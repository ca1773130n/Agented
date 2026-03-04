# Phase 12: Specialized Automation Bots - Research

**Researched:** 2026-03-04
**Domain:** Engineering automation bots (vulnerability triage, code tours, test coverage, incident postmortems, changelog, PR summaries, NL log search)
**Confidence:** MEDIUM-HIGH

## Summary

Phase 12 adds seven specialized pre-built bots to the Agented platform, each implemented as a predefined trigger with a tailored prompt template and supporting backend service. The platform already has a mature bot execution infrastructure: predefined triggers (`bot-security`, `bot-pr-review`), prompt template rendering via `PromptRenderer`, CLI subprocess execution via `ExecutionService.run_trigger()`, scheduled execution via `SchedulerService`, GitHub webhook dispatch via `dispatch_github_event()`, and execution log persistence in SQLite.

The primary implementation pattern for all seven bots is: (1) define a new predefined trigger with an appropriate `trigger_source`, `prompt_template`, and `skill_command`; (2) create or extend a Claude skill (markdown instruction file) that guides the AI through the specific task; (3) add a supporting service for any data pre-processing (e.g., parsing package manifests, querying CVE databases, aggregating merged PRs); (4) add an API endpoint for bot-specific results; (5) add a frontend view for displaying results. The natural language log search (BOT-07) is the most architecturally distinct requirement, needing SQLite FTS5 for efficient full-text search across execution logs.

**Primary recommendation:** Implement each bot as a predefined trigger + Claude skill pair, following the existing `bot-security` / `bot-pr-review` pattern. Use SQLite FTS5 for natural language log search. Leverage `osv-scanner` CLI or the OSV.dev API for vulnerability scanning. Use `gh` CLI for posting PR comments (test coverage gaps, PR summaries). Use `gh` CLI's `pr list --state merged` for changelog generation.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask + flask-openapi3 | 2.x / 3.x | API endpoints for bot results and management | Already in use; all routes use `APIBlueprint` |
| SQLite + FTS5 | Built-in | Full-text search on execution logs (BOT-07) | FTS5 ships with Python's `sqlite3` module; no external dependency needed |
| APScheduler | 3.10+ | Scheduled bot execution (BOT-01 daily/weekly scans) | Already in use for scheduled triggers |
| subprocess | stdlib | CLI invocation of `claude`, `gh`, `osv-scanner` | Already the execution model for all bot runs |
| Pydantic v2 | 2.x | Request/response validation for bot-specific models | Already in use across all API endpoints |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `osv-scanner` CLI | 2.x | Vulnerability scanning of package manifests (BOT-01) | Invoked via subprocess for dependency vulnerability triage |
| `gh` CLI | 2.x | PR comment posting (BOT-03, BOT-06), merged PR listing (BOT-05) | Already available on the system; used by `GitHubService` |
| `httpx` | 0.28+ | OSV.dev API queries for CVE cross-referencing (BOT-01) | Already a dependency in `pyproject.toml` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Rationale |
|------------|-----------|----------|-----------|
| `osv-scanner` CLI | Direct OSV.dev REST API (`https://api.osv.dev/v1/query`) | API is simpler to integrate but lacks lockfile parsing; CLI handles 19+ lockfile formats natively | Use CLI for manifest scanning, API for supplemental CVE details |
| SQLite FTS5 | Elasticsearch / Meilisearch | External dependency, operational overhead | FTS5 is zero-dependency (built into Python's sqlite3), sufficient for single-instance deployment |
| `gh pr comment` | GitHub REST API via `httpx` | REST API requires token management; `gh` CLI handles auth automatically | Use `gh` CLI for all GitHub interactions, consistent with existing `GitHubService` |

**Installation:**
```bash
# osv-scanner (Go binary, install via brew or download)
brew install osv-scanner
# OR: go install github.com/google/osv-scanner/cmd/osv-scanner@latest

# No new Python dependencies required — all libraries already in pyproject.toml
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
├── db/
│   ├── specialized_bots.py          # New: CRUD for bot-specific result tables
│   └── schema.py                    # Modified: add FTS5 virtual table, bot result tables
├── models/
│   ├── specialized_bot.py           # New: Pydantic models for bot-specific results
│   └── ...
├── routes/
│   ├── specialized_bots.py          # New: API endpoints for specialized bot operations
│   └── ...
├── services/
│   ├── vulnerability_scan_service.py     # New: BOT-01 vulnerability scanning logic
│   ├── code_tour_service.py              # New: BOT-02 code tour generation logic
│   ├── test_coverage_service.py          # New: BOT-03 test coverage gap detection
│   ├── postmortem_service.py             # New: BOT-04 incident postmortem logic
│   ├── changelog_service.py              # New: BOT-05 changelog generation logic
│   ├── pr_summary_service.py             # New: BOT-06 PR summary posting logic
│   ├── execution_search_service.py       # New: BOT-07 NL log search via FTS5
│   └── ...
└── ...

frontend/src/
├── views/
│   ├── VulnerabilityScanPage.vue         # New: Vulnerability scan results view
│   ├── CodeTourPage.vue                  # New: Code tour output view
│   └── ...
├── components/
│   ├── specialized-bots/                 # New: Bot-specific components
│   └── ...
└── services/api/
    ├── specialized-bots.ts               # New: API client for specialized bot endpoints
    └── ...
```

### Pattern 1: Predefined Trigger + Skill Pair

**What:** Each specialized bot is a predefined trigger (seeded on startup) paired with a Claude skill markdown file that provides task-specific instructions.

**When to use:** For all seven bots.

**Example:**
```python
# In backend/app/db/triggers.py — PREDEFINED_TRIGGERS list
{
    "id": "bot-vuln-scan",
    "name": "Dependency Vulnerability Scanner",
    "group_id": 0,
    "detection_keyword": "",
    "prompt_template": "/vulnerability-scan {paths}",
    "backend_type": "claude",
    "trigger_source": "scheduled",
    "schedule_type": "weekly",
    "schedule_time": "02:00",
    "schedule_day": 1,  # Monday
    "match_field_path": None,
    "match_field_value": None,
    "text_field_path": "text",
    "is_predefined": 1,
},
```

```markdown
# .claude/skills/vulnerability-scan/INSTRUCTIONS.md
# Claude skill instructions for dependency vulnerability scanning

You are a dependency vulnerability scanner. Given project paths, you must:
1. Find package manifest files (package.json, requirements.txt, pyproject.toml, Cargo.toml, go.mod)
2. Run `osv-scanner --format json --lockfile <lockfile>` for each manifest
3. Parse the JSON output to extract vulnerability details
4. Cross-reference each CVE with severity scores
5. Produce a prioritized findings report with fix recommendations
...
```

### Pattern 2: GitHub Event-Triggered Bot with PR Comment Output

**What:** Bots triggered by GitHub PR events that post results as PR comments via `gh pr comment`.

**When to use:** For BOT-03 (test coverage gaps) and BOT-06 (PR summaries).

**Example:**
```python
# Service method for posting a PR comment
@staticmethod
def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> bool:
    """Post a comment on a GitHub PR using gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "comment", str(pr_number),
             "--repo", repo_full_name,
             "--body", body],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
```

### Pattern 3: SQLite FTS5 for Natural Language Log Search

**What:** A virtual FTS5 table that indexes execution log content for efficient full-text search.

**When to use:** For BOT-07 (natural language log search).

**Example:**
```python
# Schema addition in backend/app/db/schema.py
conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS execution_logs_fts
    USING fts5(
        execution_id UNINDEXED,
        trigger_id UNINDEXED,
        trigger_name UNINDEXED,
        stdout_content,
        stderr_content,
        prompt,
        content=execution_logs,
        content_rowid=id,
        tokenize='porter unicode61'
    )
""")
```

```python
# Search service method
@staticmethod
def search_logs(query: str, limit: int = 50) -> list:
    """Search execution logs using FTS5 with BM25 ranking."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT e.execution_id, e.trigger_id, t.name as trigger_name,
                   e.started_at, e.status,
                   snippet(execution_logs_fts, 3, '<mark>', '</mark>', '...', 32) as match_context,
                   rank
            FROM execution_logs_fts
            JOIN execution_logs e ON execution_logs_fts.rowid = e.id
            LEFT JOIN triggers t ON e.trigger_id = t.id
            WHERE execution_logs_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
        return [dict(row) for row in cursor.fetchall()]
```

### Anti-Patterns to Avoid

- **Hardcoding bot logic in ExecutionService:** Each bot's pre/post-processing logic must live in its own service class, not in the already-large `execution_service.py` (currently 1300+ lines). The existing `save_threat_report()` method embedded in `ExecutionService` for `bot-security` is a pattern to avoid repeating.

- **Building a separate search engine for BOT-07:** SQLite FTS5 is sufficient. Do not introduce Elasticsearch, Redis Search, or any external search infrastructure. The execution logs table already stores `stdout_log` and `stderr_log` as TEXT columns — FTS5 can index these directly.

- **Polling for PR events from the bot itself:** The platform already has a GitHub webhook receiver (`/api/webhooks/github/`) that dispatches to matching triggers. New PR-triggered bots (BOT-03, BOT-06) should register as GitHub-sourced triggers and use the existing dispatch pipeline.

- **Creating separate database files for bot results:** All data must go into the single `agented.db` SQLite database, following the established pattern. Do not create per-bot SQLite files.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Package manifest parsing | Custom lockfile parsers | `osv-scanner` CLI (supports 19+ lockfile formats) | Lockfile formats change frequently; `osv-scanner` v2 handles edge cases (e.g., workspace packages, nested deps) |
| CVE database | Local CVE mirror or custom scraper | OSV.dev API (`https://api.osv.dev/v1/query`) | Aggregates GitHub Advisory, PyPA, RustSec, NVD data; stays current without maintenance |
| Full-text search | Custom tokenizer + inverted index | SQLite FTS5 with `porter` tokenizer | Built into Python's sqlite3; handles stemming, ranking (BM25), snippets natively |
| PR comment posting | GitHub REST API client with token management | `gh pr comment` CLI | Handles auth, pagination, rate limiting automatically; already used pattern in `GitHubService` |
| Merged PR listing for changelog | Custom GitHub API pagination | `gh pr list --state merged --json number,title,labels,mergedAt` | Handles pagination and auth; outputs structured JSON |
| Cron scheduling | Custom scheduler thread | APScheduler CronTrigger (already in `SchedulerService`) | Already powers all scheduled triggers; battle-tested |

**Key insight:** The platform's architecture already solves the hardest infrastructure problems (trigger dispatch, subprocess execution, log streaming, scheduling). The specialized bots are primarily prompt engineering + data pre-processing/post-processing, not new infrastructure.

## Common Pitfalls

### Pitfall 1: FTS5 Index Synchronization

**What goes wrong:** FTS5 content tables require explicit synchronization when the source table is modified. If execution logs are updated (e.g., `stdout_log` written on completion) without updating the FTS index, search results become stale or incomplete.

**Why it happens:** FTS5 with `content=` (external content) tables does not auto-sync.

**How to avoid:** Use SQLite triggers to keep the FTS index in sync:
```sql
CREATE TRIGGER execution_logs_ai AFTER INSERT ON execution_logs BEGIN
    INSERT INTO execution_logs_fts(rowid, execution_id, trigger_id, trigger_name, stdout_content, stderr_content, prompt)
    VALUES (new.id, new.execution_id, new.trigger_id, '', COALESCE(new.stdout_log, ''), COALESCE(new.stderr_log, ''), COALESCE(new.prompt, ''));
END;
CREATE TRIGGER execution_logs_au AFTER UPDATE ON execution_logs BEGIN
    INSERT INTO execution_logs_fts(execution_logs_fts, rowid, execution_id, trigger_id, trigger_name, stdout_content, stderr_content, prompt)
    VALUES ('delete', old.id, old.execution_id, old.trigger_id, '', COALESCE(old.stdout_log, ''), COALESCE(old.stderr_log, ''), COALESCE(old.prompt, ''));
    INSERT INTO execution_logs_fts(rowid, execution_id, trigger_id, trigger_name, stdout_content, stderr_content, prompt)
    VALUES (new.id, new.execution_id, new.trigger_id, '', COALESCE(new.stdout_log, ''), COALESCE(new.stderr_log, ''), COALESCE(new.prompt, ''));
END;
```

**Warning signs:** Search returning no results for recently completed executions; search returning stale content for re-run executions.

### Pitfall 2: Bot Prompt Template Overcrowding

**What goes wrong:** Cramming all bot instructions into the `prompt_template` field, making templates unwieldy and hard to iterate on.

**Why it happens:** The existing `bot-security` uses a simple template (`/weekly-security-audit {paths}`) that delegates to a Claude skill file. Developers unfamiliar with this pattern may try to put all instructions in the template itself.

**How to avoid:** Use the `skill_command` field to reference a Claude skill, keeping the `prompt_template` focused on context variables. The skill file (`.claude/skills/<bot-name>/INSTRUCTIONS.md`) contains the detailed instructions. This matches the existing `bot-security` pattern exactly.

**Warning signs:** Prompt templates exceeding 500 characters; difficulty iterating on bot behavior without restarting the server.

### Pitfall 3: PR Comment Bot Latency (BOT-06 60-Second SLA)

**What goes wrong:** The 60-second SLA for PR summary comments cannot be met if the bot execution pipeline has cold-start overhead or if multiple PRs arrive simultaneously.

**Why it happens:** The current execution pipeline involves: GitHub webhook receipt -> trigger dispatch -> subprocess spawn -> CLI startup -> AI processing -> output. Claude CLI cold start can take 5-10 seconds; AI processing for a meaningful PR summary takes 15-30 seconds.

**How to avoid:** (1) Use a lightweight prompt that focuses on the diff summary rather than deep code analysis. (2) Set a `timeout_seconds` of 55 on the trigger. (3) Use the existing rate limiting (60s per repo) in `github_webhook.py` to prevent concurrent executions for the same repo. (4) Consider using `litellm` direct API calls instead of CLI subprocess for latency-sensitive bots.

**Warning signs:** PR comments appearing >60 seconds after PR creation; timeout errors in execution logs for the PR summary bot.

### Pitfall 4: Predefined Trigger ID Collisions

**What goes wrong:** Adding new predefined triggers with IDs that collide with user-created triggers.

**Why it happens:** Predefined triggers use hardcoded `bot-*` IDs (e.g., `bot-security`, `bot-pr-review`). User-created triggers use randomly generated IDs with `trigger-` prefix. New predefined bots must use the `bot-` prefix consistently.

**How to avoid:** Use the established naming convention: `bot-vuln-scan`, `bot-code-tour`, `bot-test-coverage`, `bot-postmortem`, `bot-changelog`, `bot-pr-summary`, `bot-log-search`. Add all new IDs to `PREDEFINED_TRIGGER_IDS` set. Ensure `delete_trigger()` protection continues to work (it checks `is_predefined = 0`).

### Pitfall 5: Execution Log Size for FTS5 Indexing

**What goes wrong:** Large execution logs (security audit stdout can exceed 100KB) cause FTS5 index bloat and slow search performance.

**Why it happens:** FTS5 indexes all content. If execution logs contain verbose debug output or binary-like content, the index grows disproportionately.

**How to avoid:** (1) Only index the first N kilobytes of stdout/stderr (e.g., 32KB). (2) Use the `execution_logs` 30-day retention cleanup (already scheduled in `SchedulerService`) to keep the FTS index bounded. (3) Run `INSERT INTO execution_logs_fts(execution_logs_fts) VALUES('optimize')` periodically to compact the index.

## Paper-Backed Recommendations

### Recommendation 1: BM25 Ranking for Log Search (BOT-07)

**Recommendation:** Use SQLite FTS5's built-in BM25 ranking function for natural language log search rather than implementing custom relevance scoring.

**Evidence:**
- Robertson & Zaragoza (2009) "The Probabilistic Relevance Framework: BM25 and Beyond" — Established BM25 as the standard baseline for information retrieval. BM25 consistently outperforms TF-IDF on text retrieval benchmarks.
- SQLite FTS5 documentation (sqlite.org/fts5.html) — FTS5 implements BM25 natively via the `rank` column and `bm25()` auxiliary function with configurable per-column weights.
- Craswell et al. (2020) "Overview of the TREC 2019 Deep Learning Track" — Shows BM25 remains competitive with neural approaches on ad-hoc retrieval, especially for short queries against document collections <100K docs (our expected scale).

**Confidence:** HIGH — BM25 is the most-validated ranking function in information retrieval. FTS5's implementation is well-tested.

**Expected improvement:** Meaningful ranked results for free-text queries like "show me all PRs where the bot flagged SQL injection" — BM25 handles term frequency, document length normalization, and inverse document frequency automatically.

**Caveats:** BM25 is lexical (keyword matching), not semantic. Queries like "security problems" won't match logs containing "vulnerability" unless both terms appear. This is acceptable for v0.1.0; semantic search can be added later with embeddings.

### Recommendation 2: Structured Output Parsing for Bot Results

**Recommendation:** Instruct bots to produce structured JSON output (via Claude's `--output-format json`) and parse results in the post-processing service rather than relying on free-text parsing.

**Evidence:**
- The existing `bot-security` already uses `--output-format json` in `CommandBuilder.build()` (line 67: `"--output-format", "json"`).
- OpenAI (2024) "Structured Outputs" technical report — Demonstrates that constraining LLM output to JSON schemas significantly reduces parsing errors (from ~15% to <1% failure rate).
- Agented codebase convention — All CLI backends already support JSON output (`--output-format json` for claude, `--format json` for opencode, `--json` for codex).

**Confidence:** HIGH — This is already the standard pattern in the codebase.

### Recommendation 3: Prompt Engineering with Chain-of-Thought for Complex Bots

**Recommendation:** Use chain-of-thought (CoT) prompting in skill files for complex analytical bots (BOT-01 vulnerability triage, BOT-03 test coverage analysis, BOT-04 incident postmortem).

**Evidence:**
- Wei et al. (2022) "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models" — CoT improves reasoning accuracy on multi-step tasks by 10-30% across GPT-3.5/4 class models.
- The existing weekly security audit skill already uses structured step-by-step instructions implicitly (scan -> parse -> score -> report).

**Confidence:** MEDIUM-HIGH — CoT is well-established for reasoning tasks; benefit varies by model and task complexity.

### Recommendation 4: Conventional Commits Parsing for Changelog (BOT-05)

**Recommendation:** Parse merged PR titles using the Conventional Commits specification (`feat:`, `fix:`, `breaking:`) for automatic categorization in changelog generation, falling back to AI-based classification for non-conforming titles.

**Evidence:**
- Conventional Commits specification (conventionalcommits.org v1.0.0) — Industry-standard commit message format used by Angular, Vue.js, Lerna, and 100K+ repos on GitHub.
- `git-cliff` tool documentation — Demonstrates the pattern of parsing commit messages into structured changelog sections (Features, Bug Fixes, Breaking Changes).

**Confidence:** HIGH — Conventional Commits is the de facto standard for automated changelog generation.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Bot prompt template content (instructions, output format, examples)
- Trigger configuration (timeout, schedule, trigger source)
- FTS5 tokenizer choice (porter vs. unicode61 vs. trigram)

**Dependent variables:**
- Bot output quality (correct identification of vulnerabilities, accurate PR summaries, relevant log search results)
- Execution latency (time from trigger to completion)
- PR comment posting latency for BOT-06 (must be <60 seconds)

**Controlled variables:**
- Backend type (claude for all bots initially)
- Database (single SQLite instance)
- CLI tool versions

**Baseline comparison:**
- Method: Manual execution of each bot's task (e.g., manually running `npm audit`, manually writing PR summaries)
- Expected performance: Human takes 5-30 minutes per task; bot should complete in <2 minutes
- Our target: <60 seconds for PR-triggered bots; <5 minutes for scheduled bots

**Ablation plan:**
1. Bot with full CoT skill file vs. minimal prompt — tests prompt engineering impact on output quality
2. FTS5 with porter tokenizer vs. trigram tokenizer — tests search recall for log queries
3. `osv-scanner` CLI vs. direct OSV.dev API — tests vulnerability detection completeness

**Statistical rigor:**
- Number of runs: 5 runs per bot per test scenario (ensures consistency)
- Success criteria: 4/5 runs produce acceptable output
- Latency measurement: Median across 5 runs (avoid outlier skew from cold starts)

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Vulnerability detection recall | BOT-01 must find known CVEs | Compare bot findings against `osv-scanner` raw output | 100% of `osv-scanner` findings should appear in bot output |
| Code tour section count | BOT-02 success criterion: >=5 sections | Count distinct annotated sections in output | Manual tour: typically 5-10 sections |
| PR comment latency | BOT-06 SLA: <60 seconds | `finished_at - started_at` in execution_logs | N/A (new capability) |
| Search result relevance (FTS5) | BOT-07 must return relevant results | Manual evaluation: 10 test queries, check top-5 relevance | Simple LIKE search: ~30% precision |
| Changelog accuracy | BOT-05 must correctly categorize PR types | Compare auto-categorization against manual labels | N/A (new capability) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Predefined triggers seed correctly on startup | Level 1 (Sanity) | Database seeding is testable with `isolated_db` fixture |
| Prompt templates render without unresolved placeholders | Level 1 (Sanity) | `PromptRenderer.warn_unresolved()` already exists |
| FTS5 virtual table creation and basic search | Level 1 (Sanity) | SQL query against test data |
| `osv-scanner` CLI integration produces parseable JSON | Level 1 (Sanity) | Run against a known test manifest |
| `gh pr comment` posts successfully | Level 2 (Proxy) | Requires a test repo; mock in unit tests, verify in integration |
| BOT-01 finds known vulnerability in test package.json | Level 2 (Proxy) | Use a manifest with a known CVE |
| BOT-02 generates >=5 annotated sections for a small repo | Level 2 (Proxy) | Run against the Agented repo itself |
| BOT-03 identifies untested functions in a test PR | Level 2 (Proxy) | Create a PR with known untested code |
| BOT-05 correctly groups PRs by conventional commit type | Level 2 (Proxy) | Use mock PR data with known types |
| BOT-06 posts comment within 60 seconds of PR event | Level 2 (Proxy) | Measure wall-clock time in integration test |
| BOT-07 returns relevant results for 10 test queries | Level 2 (Proxy) | Seed execution logs with known content, evaluate search |
| All bots work end-to-end with real GitHub repos | Level 3 (Deferred) | Requires real webhook events and repos |
| BOT-04 produces complete postmortem from real incident | Level 3 (Deferred) | Requires incident context data |

**Level 1 checks to always include:**
- All 7 new predefined triggers exist in DB after `seed_predefined_triggers()` runs
- Each trigger's `prompt_template` renders cleanly with test data via `PromptRenderer.render()`
- FTS5 table accepts inserts and returns results for basic keyword queries
- New API endpoints return 200 for valid requests, 404 for missing entities
- Frontend builds without TypeScript errors (`just build`)

**Level 2 proxy metrics:**
- BOT-01: Run against a `package.json` containing `lodash@4.17.20` (has known CVE-2021-23337); verify CVE appears in output
- BOT-02: Run against this repo; verify output has >=5 sections with labels like "entry points", "data flow", etc.
- BOT-05: Feed 10 mock merged PRs with `feat:`, `fix:`, `chore:` prefixes; verify correct grouping
- BOT-06: Measure time from `dispatch_github_event()` call to `gh pr comment` completion
- BOT-07: Insert 20 execution logs with varied content; verify 10 test queries return relevant results

**Level 3 deferred items:**
- Full end-to-end test with real GitHub webhook for PR-triggered bots
- Vulnerability scan against production package manifests
- Incident postmortem with real incident data
- Changelog generation for an actual release cycle

## Production Considerations

### Known Failure Modes

- **osv-scanner CLI not installed:** The vulnerability scan bot (BOT-01) depends on `osv-scanner` being available on PATH. Must fail gracefully with a clear error message if not found (same pattern as `BackendDetectionService` for `claude`, `opencode` etc.).
  - Prevention: Add `osv-scanner` detection to startup health checks
  - Detection: Check `shutil.which("osv-scanner")` before dispatching BOT-01

- **gh CLI not authenticated:** PR comment posting (BOT-03, BOT-06) and merged PR listing (BOT-05) require `gh auth status` to be valid.
  - Prevention: Verify `gh auth status` in service initialization
  - Detection: Check `gh auth status` return code; log warning if unauthenticated

- **Large execution logs causing FTS5 slowdown:** If execution logs grow beyond 30 days of retention, FTS5 index size may degrade search performance.
  - Prevention: Rely on existing 30-day cleanup in `SchedulerService`; add FTS5 `optimize` command to cleanup job
  - Detection: Monitor search query latency; alert if >500ms

### Scaling Concerns

- **Concurrent PR events for BOT-06:** Multiple PRs opened simultaneously could overwhelm the execution pipeline. The existing per-repo rate limit (60s) in `github_webhook.py` already mitigates this, but multiple repos sending PRs concurrently could still queue many executions.
  - At current scale: Acceptable; single-user/small-team usage unlikely to generate concurrent bursts
  - At production scale: Consider a dedicated execution queue with concurrency limits per bot type

- **FTS5 index size:** With 30-day retention and ~10 executions/day, expect ~300 indexed documents with avg 10KB each = ~3MB index. This is well within SQLite FTS5's comfortable range (<100MB).
  - At current scale: No concern
  - At production scale: If execution volume exceeds 1000/day, consider periodic `optimize` and possibly sharding by time period

### Common Implementation Traps

- **Modifying `execution_service.py` directly:** The file is already 1300+ lines. Do not add bot-specific logic there. Create separate service classes per bot.
  - Correct approach: Bot services import from `execution_service` where needed, not the reverse.

- **Blocking the webhook handler for PR bots:** The GitHub webhook handler must return quickly (GitHub expects <10s response). Bot execution is already dispatched in background threads via `threading.Thread(daemon=True)` — maintain this pattern for BOT-03 and BOT-06.
  - Correct approach: Webhook handler dispatches, returns 200 immediately; bot execution and PR comment posting happen asynchronously.

- **Not handling the case where Claude skill files are missing:** If a skill file referenced by `skill_command` does not exist, the CLI will fail silently or produce garbage output.
  - Correct approach: Validate skill file existence at trigger seed time; log warnings if files are missing.

## Code Examples

### Adding a New Predefined Trigger (Seeds)

```python
# In backend/app/db/triggers.py — extend PREDEFINED_TRIGGERS list
{
    "id": "bot-vuln-scan",
    "name": "Dependency Vulnerability Scanner",
    "group_id": 0,
    "detection_keyword": "",
    "prompt_template": "/vulnerability-scan {paths}",
    "backend_type": "claude",
    "trigger_source": "scheduled",
    "match_field_path": None,
    "match_field_value": None,
    "text_field_path": "text",
    "is_predefined": 1,
},
{
    "id": "bot-pr-summary",
    "name": "PR Summary",
    "group_id": 0,
    "detection_keyword": "",
    "prompt_template": "/pr-summary {pr_url} {pr_title} {pr_author} {repo_full_name}",
    "backend_type": "claude",
    "trigger_source": "github",
    "match_field_path": None,
    "match_field_value": None,
    "text_field_path": "text",
    "is_predefined": 1,
},
```

### FTS5 Table Creation and Sync Triggers

```python
# In backend/app/db/schema.py — add to create_fresh_schema()
conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS execution_logs_fts
    USING fts5(
        stdout_content,
        stderr_content,
        prompt,
        content=execution_logs,
        content_rowid=id,
        tokenize='porter unicode61'
    )
""")

# Sync triggers (keep FTS in sync with source table)
conn.execute("""
    CREATE TRIGGER IF NOT EXISTS execution_logs_fts_insert
    AFTER INSERT ON execution_logs BEGIN
        INSERT INTO execution_logs_fts(rowid, stdout_content, stderr_content, prompt)
        VALUES (new.id, COALESCE(new.stdout_log, ''), COALESCE(new.stderr_log, ''), COALESCE(new.prompt, ''));
    END
""")

conn.execute("""
    CREATE TRIGGER IF NOT EXISTS execution_logs_fts_update
    AFTER UPDATE OF stdout_log, stderr_log ON execution_logs BEGIN
        INSERT INTO execution_logs_fts(execution_logs_fts, rowid, stdout_content, stderr_content, prompt)
        VALUES ('delete', old.id, COALESCE(old.stdout_log, ''), COALESCE(old.stderr_log, ''), COALESCE(old.prompt, ''));
        INSERT INTO execution_logs_fts(rowid, stdout_content, stderr_content, prompt)
        VALUES (new.id, COALESCE(new.stdout_log, ''), COALESCE(new.stderr_log, ''), COALESCE(new.prompt, ''));
    END
""")

conn.execute("""
    CREATE TRIGGER IF NOT EXISTS execution_logs_fts_delete
    AFTER DELETE ON execution_logs BEGIN
        INSERT INTO execution_logs_fts(execution_logs_fts, rowid, stdout_content, stderr_content, prompt)
        VALUES ('delete', old.id, COALESCE(old.stdout_log, ''), COALESCE(old.stderr_log, ''), COALESCE(old.prompt, ''));
    END
""")
```

### Execution Log Search Service

```python
# backend/app/services/execution_search_service.py
import logging
from typing import List, Optional

from ..db.connection import get_connection

logger = logging.getLogger(__name__)


class ExecutionSearchService:
    """Full-text search across execution logs using SQLite FTS5."""

    @staticmethod
    def search(query: str, limit: int = 50, trigger_id: Optional[str] = None) -> List[dict]:
        """Search execution logs using natural language query.

        Uses FTS5 BM25 ranking for relevance ordering.
        Returns matching executions with highlighted context snippets.
        """
        with get_connection() as conn:
            if trigger_id:
                cursor = conn.execute("""
                    SELECT e.execution_id, e.trigger_id, t.name as trigger_name,
                           e.started_at, e.status, e.prompt,
                           snippet(execution_logs_fts, 0, '<mark>', '</mark>', '...', 32) as stdout_match,
                           snippet(execution_logs_fts, 1, '<mark>', '</mark>', '...', 32) as stderr_match
                    FROM execution_logs_fts
                    JOIN execution_logs e ON execution_logs_fts.rowid = e.id
                    LEFT JOIN triggers t ON e.trigger_id = t.id
                    WHERE execution_logs_fts MATCH ?
                      AND e.trigger_id = ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, trigger_id, limit))
            else:
                cursor = conn.execute("""
                    SELECT e.execution_id, e.trigger_id, t.name as trigger_name,
                           e.started_at, e.status, e.prompt,
                           snippet(execution_logs_fts, 0, '<mark>', '</mark>', '...', 32) as stdout_match,
                           snippet(execution_logs_fts, 1, '<mark>', '</mark>', '...', 32) as stderr_match
                    FROM execution_logs_fts
                    JOIN execution_logs e ON execution_logs_fts.rowid = e.id
                    LEFT JOIN triggers t ON e.trigger_id = t.id
                    WHERE execution_logs_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, limit))
            return [dict(row) for row in cursor.fetchall()]
```

### Posting PR Comments via gh CLI

```python
# backend/app/services/pr_summary_service.py
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class PrSummaryService:
    """Service for posting AI-generated PR summary comments."""

    GH_TIMEOUT = 30  # seconds

    @classmethod
    def post_comment(cls, repo_full_name: str, pr_number: int, body: str) -> bool:
        """Post a comment on a GitHub PR using gh CLI.

        Args:
            repo_full_name: "owner/repo" format
            pr_number: PR number
            body: Markdown comment body

        Returns:
            True if comment was posted successfully
        """
        try:
            result = subprocess.run(
                ["gh", "pr", "comment", str(pr_number),
                 "--repo", repo_full_name,
                 "--body", body],
                capture_output=True,
                text=True,
                timeout=cls.GH_TIMEOUT,
            )
            if result.returncode == 0:
                logger.info("Posted PR comment on %s#%d", repo_full_name, pr_number)
                return True
            else:
                logger.warning(
                    "Failed to post PR comment on %s#%d: %s",
                    repo_full_name, pr_number, result.stderr
                )
                return False
        except subprocess.TimeoutExpired:
            logger.error("gh pr comment timed out for %s#%d", repo_full_name, pr_number)
            return False
        except FileNotFoundError:
            logger.error("gh CLI not found; cannot post PR comments")
            return False
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom CVE scrapers | OSV.dev aggregated API + osv-scanner CLI | 2023-2025 | Single source for all ecosystem vulnerabilities; 19+ lockfile formats supported |
| Manual changelog writing | Conventional Commits + automated tools (git-cliff, changelogen) | 2019-present | Machine-parseable commit messages enable fully automated changelogs |
| Keyword-based log search (LIKE) | FTS5 with BM25 ranking | SQLite 3.9.0 (2015), mature | 10-100x faster than LIKE for large text; relevance-ranked results |
| Static code tour documentation | AI-generated walkthroughs | 2024-2025 | LLMs can analyze codebase structure and generate contextual tours dynamically |
| Manual incident postmortems | AI-assisted postmortem drafting | 2024-2025 | AI aggregates logs, PRs, and deployment history into structured templates |

**Deprecated/outdated:**
- FTS3/FTS4: Replaced by FTS5 which offers better performance, BM25 ranking, and column filters. Do not use FTS3/FTS4.
- `npm audit` / `pip-audit` individually: Replaced by `osv-scanner` which handles all ecosystems in a single tool.

## Open Questions

1. **Skill file location standardization**
   - What we know: The existing `bot-security` uses `.claude/skills/weekly-security-audit/` with reports stored there
   - What's unclear: Should all 7 bots follow this exact pattern, or should skills be organized differently (e.g., `.claude/skills/bots/vulnerability-scan/`)?
   - Recommendation: Follow the existing flat pattern (`.claude/skills/<bot-slug>/INSTRUCTIONS.md`) for consistency. Each bot gets its own skill directory.

2. **BOT-04 incident data sources**
   - What we know: The success criteria says "given an incident identifier, pulls relevant logs and PR context"
   - What's unclear: What constitutes an "incident identifier" in this platform? There is no incident management system integrated. The platform has execution logs and PR reviews, but no incident tracking.
   - Recommendation: Define "incident" as a time range + optional trigger/repo filter. The postmortem bot aggregates execution logs and PR reviews from that time range. This avoids needing external incident management integration.

3. **BOT-07 query syntax — plain English vs. FTS5 syntax**
   - What we know: FTS5 supports both simple terms and advanced syntax (AND, OR, NOT, phrase matching)
   - What's unclear: Should the API expose raw FTS5 query syntax or translate natural language to FTS5 queries?
   - Recommendation: Accept plain English queries and pass them directly to FTS5 MATCH. FTS5 handles individual words as implicit OR by default, which maps well to natural language. For v0.1.0, this is sufficient. Add query translation (NL -> FTS5 syntax) as a future enhancement.

4. **PR comment bot identity**
   - What we know: `gh pr comment` posts as the authenticated GitHub user
   - What's unclear: Should the bot comments be identifiable as bot-generated (e.g., with a footer like "Posted by Agented BOT-06")?
   - Recommendation: Yes, always include a footer identifying the bot to avoid confusion with human comments. Use a consistent format: `---\n*Generated by [Bot Name] via Agented*`

## Sources

### Primary (HIGH confidence)
- SQLite FTS5 documentation (sqlite.org/fts5.html) — FTS5 API, tokenizers, ranking functions, content tables
- OSV.dev documentation (google.github.io/osv.dev/) — API endpoints, query format, supported ecosystems
- Conventional Commits specification (conventionalcommits.org v1.0.0) — Commit message format for changelog automation
- Agented codebase analysis (.planning/codebase/ARCHITECTURE.md, STRUCTURE.md, INTEGRATIONS.md) — Existing patterns and conventions

### Secondary (MEDIUM confidence)
- Robertson & Zaragoza (2009) "The Probabilistic Relevance Framework: BM25 and Beyond" — BM25 ranking theory
- Wei et al. (2022) "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models" — CoT prompt engineering
- Google Security Blog (2025) "Announcing OSV-Scanner V2" — osv-scanner v2 capabilities and container scanning
- google/osv-scanner GitHub repository — CLI tool documentation and supported lockfile formats
- Craswell et al. (2020) "Overview of the TREC 2019 Deep Learning Track" — BM25 competitiveness vs. neural approaches

### Tertiary (LOW confidence)
- Various blog posts on AI-powered PR review tools (dev.to, medium.com) — Community patterns for LLM-based PR summaries
- Rootly, incident.io documentation — Incident postmortem automation patterns (commercial tools, not directly applicable)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All libraries already in use or built into Python stdlib
- Architecture: HIGH — Follows established codebase patterns exactly (predefined triggers, skills, services)
- Paper recommendations: MEDIUM-HIGH — BM25 and CoT are well-established; specific bot quality outcomes depend on prompt engineering
- Pitfalls: HIGH — Based on direct codebase analysis (FTS5 sync, execution_service size, webhook threading)
- Production considerations: MEDIUM — Based on codebase patterns and scaling analysis; not yet tested at production scale

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days — stable domain, no fast-moving dependencies)
