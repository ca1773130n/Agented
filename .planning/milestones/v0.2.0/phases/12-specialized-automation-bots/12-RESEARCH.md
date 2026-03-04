# Phase 12: Specialized Automation Bots - Research

**Researched:** 2026-03-04
**Domain:** Bot automation platform -- predefined specialized bots for engineering workflows
**Confidence:** HIGH

## Summary

Phase 12 adds seven predefined specialized bots to the existing Agented bot automation infrastructure. The platform already has a mature bot execution pipeline: triggers (with `is_predefined=1`) are seeded into the SQLite database at startup, each with a `prompt_template` that references Claude skills (e.g., `/weekly-security-audit {paths}`). Execution flows through `OrchestrationService` -> `ExecutionService.run_trigger()` -> `subprocess.Popen` -> CLI tool (claude/opencode/gemini/codex). The two existing predefined bots (`bot-security` for weekly security audits, `bot-pr-review` for PR reviews) provide a proven template.

The implementation pattern is clear: each new bot requires (1) a predefined trigger definition in `PREDEFINED_TRIGGERS`, (2) a Claude skill file with the prompt logic, (3) appropriate trigger source and placeholders, and optionally (4) new API endpoints for bot-specific data views. The most technically novel requirement is BOT-07 (natural language log search), which requires SQLite FTS5 for full-text search over execution log data. The remaining six bots follow the established pattern of prompt-template-driven CLI execution with different trigger sources (scheduled, github, webhook, manual).

**Primary recommendation:** Implement all seven bots using the existing predefined trigger + Claude skill pattern. Add SQLite FTS5 virtual tables for BOT-07 log search. Use the OSV.dev API for BOT-01 CVE cross-referencing. Leverage `gh pr list --state merged --json` for BOT-05 changelog generation.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLite FTS5 | Built-in | Full-text search for BOT-07 log search | Ships with Python's sqlite3 module; zero dependencies; proven BM25 ranking |
| `urllib.request` | stdlib | OSV.dev API calls for BOT-01 | Already used throughout codebase for provider APIs; no new dependencies |
| `gh` CLI | Existing | PR listing for BOT-05/BOT-06 | Already integrated via `GitHubService`; `gh pr list --state merged --json` |
| APScheduler | Existing | Scheduled trigger execution for BOT-01/BOT-05 | Already integrated via `SchedulerService` |
| Claude CLI | Existing | Bot execution backend | Core execution path via `CommandBuilder.build()` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` | stdlib | OSV API response parsing, CHANGELOG formatting | BOT-01 CVE data, BOT-05 changelog structure |
| `re` | stdlib | Conventional commit message parsing for BOT-05 | Grouping PRs by type (feat/fix/breaking) |
| `subprocess` | stdlib | `gh` CLI calls for PR data, `coverage.py` for BOT-03 | BOT-03/BOT-05/BOT-06 data gathering |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Rationale |
|------------|-----------|----------|-----------|
| OSV.dev API | `osv-scanner` CLI | CLI requires Go install; API is HTTP-only, zero deps | Use API -- platform already uses `urllib.request` for provider APIs |
| SQLite FTS5 | Elasticsearch/Meilisearch | External service dependency; overkill for single-user platform | FTS5 is built into SQLite, zero infrastructure |
| Custom changelog parser | `release-please` / `conventional-changelog` | External tools with own opinionated workflow | Custom parsing via `gh pr list` keeps it simple and platform-native |
| Custom coverage analysis | `coverage.py` report parsing | coverage.py requires project-specific test runner setup | Let the AI (Claude) analyze the diff directly -- it can reason about untested paths |

**Installation:**
```bash
# No new dependencies required -- all capabilities are built-in or already installed
# FTS5 is compiled into Python's sqlite3 by default on all major platforms
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
├── db/
│   ├── triggers.py          # Extended: new PREDEFINED_TRIGGERS entries
│   ├── migrations.py        # Extended: same PREDEFINED_TRIGGERS list
│   ├── seeds.py             # Extended: same seeding logic
│   └── search.py            # NEW: FTS5 search functions for BOT-07
├── services/
│   ├── execution_service.py # Extended: bot-specific prompt preprocessing
│   ├── prompt_renderer.py   # Extended: new placeholder names
│   ├── bot_data_service.py  # NEW: data gathering for specialized bots (OSV, gh pr list, etc.)
│   └── log_search_service.py # NEW: FTS5 search service for BOT-07
├── models/
│   └── trigger.py           # Extended: new response models for bot-specific views
└── routes/
    └── bot_dashboard.py     # NEW: bot-specific dashboard endpoints (optional)
.claude/skills/
├── weekly-security-audit/   # Existing
├── pr-review/               # NEW: skill for BOT-06 (auto PR summaries)
├── vulnerability-triage/    # NEW: skill for BOT-01
├── code-tour/               # NEW: skill for BOT-02
├── test-coverage-gap/       # NEW: skill for BOT-03
├── incident-postmortem/     # NEW: skill for BOT-04
├── changelog-generator/     # NEW: skill for BOT-05
└── log-search/              # NEW: skill for BOT-07 (optional, may be API-only)
```

### Pattern 1: Predefined Trigger Registration

**What:** Each specialized bot is registered as a predefined trigger with `is_predefined=1`, a fixed `bot-*` ID, and a prompt template referencing a Claude skill.

**When to use:** For every new bot (BOT-01 through BOT-07).

**Example:**
```python
# Source: backend/app/db/triggers.py (existing pattern)
PREDEFINED_TRIGGERS = [
    # ... existing entries ...
    {
        "id": "bot-vuln-triage",
        "name": "Dependency Vulnerability Triage",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/vulnerability-triage {paths}",
        "backend_type": "claude",
        "trigger_source": "scheduled",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
]
```

### Pattern 2: Claude Skill as Bot Brain

**What:** Each bot's intelligence lives in a Claude skill file (markdown with instructions). The prompt template invokes the skill via `/skill-name`. Claude CLI reads the skill and follows its instructions.

**When to use:** For all bots that need complex reasoning (all seven).

**Example:**
```markdown
<!-- .claude/skills/vulnerability-triage/instructions.md -->
# Vulnerability Triage Skill

When invoked, perform these steps:
1. Read the project's package manifests (package.json, requirements.txt, Cargo.toml)
2. For each dependency, query the OSV.dev API for known vulnerabilities
3. Score exploitability based on CVSS/EPSS data
4. Produce a prioritized finding list with fix recommendations
```

### Pattern 3: FTS5 External Content Table (BOT-07)

**What:** Create an FTS5 virtual table that indexes execution log stdout content, linked to the existing `execution_logs` table via external content pattern. Keep canonical data in the normal table, FTS5 as search index.

**When to use:** BOT-07 natural language log search only.

**Example:**
```sql
-- Source: SQLite FTS5 official documentation (https://sqlite.org/fts5.html)
CREATE VIRTUAL TABLE IF NOT EXISTS execution_logs_fts USING fts5(
    prompt,
    stdout_log,
    content='execution_logs',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Search query with BM25 ranking
SELECT e.execution_id, e.trigger_id, e.started_at,
       snippet(execution_logs_fts, 1, '<mark>', '</mark>', '...', 32) as matched_snippet,
       rank
FROM execution_logs_fts
JOIN execution_logs e ON e.id = execution_logs_fts.rowid
WHERE execution_logs_fts MATCH ?
ORDER BY rank;
```

### Pattern 4: Prompt Template Placeholders

**What:** The `PromptRenderer` substitutes `{placeholder}` tokens in prompt templates. New bots may need additional placeholders beyond the existing set (`{paths}`, `{message}`, `{pr_url}`, `{pr_title}`, `{pr_author}`, `{repo_url}`, `{repo_full_name}`).

**When to use:** When a bot needs context injected into its prompt (e.g., `{incident_id}` for BOT-04, `{last_release_tag}` for BOT-05).

**Example:**
```python
# Source: backend/app/services/prompt_renderer.py (extended)
_KNOWN_PLACEHOLDERS = {
    # existing...
    "incident_id",       # BOT-04
    "last_release_tag",  # BOT-05
    "search_query",      # BOT-07
}
```

### Anti-Patterns to Avoid

- **Hardcoding bot logic in Python services:** The intelligence should live in Claude skills (markdown), not in Python code. Python code handles data gathering and plumbing; the AI does the analysis. This is the pattern established by `bot-security`.
- **Creating separate execution pipelines per bot:** All bots should use the same `ExecutionService.run_trigger()` pipeline. Bot-specific preprocessing (like `save_threat_report` for bot-security) should be minimal and added to `run_trigger()` with pattern matching.
- **Putting FTS5 tables in the main schema creation:** FTS5 virtual tables should be created via a schema migration, not in `create_fresh_schema()`, to avoid breaking existing databases.
- **Duplicating PREDEFINED_TRIGGERS across files:** Currently the list exists in both `triggers.py` and `migrations.py`. New bots must be added to BOTH lists. Consider consolidating to a single source of truth.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CVE database lookup | Custom vulnerability database | OSV.dev API (`POST https://api.osv.dev/v1/query`) | Aggregates GitHub Advisory, PyPA, RustSec, NVD; free; no API key needed; covers npm, pip, cargo ecosystems |
| Full-text search | Custom text search with LIKE/regex | SQLite FTS5 with BM25 ranking | Built into Python's sqlite3; handles tokenization, stemming, ranking; orders of magnitude faster than LIKE |
| Merged PR listing | Custom GitHub API pagination | `gh pr list --state merged --json title,mergedAt,labels,url --limit N` | Already integrated; handles auth, pagination, rate limiting |
| PR diff retrieval | Custom GitHub diff parsing | `gh pr diff <number>` or `gh api repos/{owner}/{repo}/pulls/{number}` | Already integrated; handles large diffs, binary files |
| Commit type parsing | Custom regex parser | Simple regex `^(feat|fix|docs|chore|refactor|perf|test|ci|build|style)(\(.+\))?!?:` | Conventional commits spec is well-defined; no library needed |
| Incident timeline construction | Custom log correlator | Let Claude analyze raw execution logs + PR history | AI excels at narrative synthesis from structured data |

**Key insight:** The platform's architecture is "AI does the thinking, Python does the plumbing." Bot-specific data gathering (OSV queries, `gh` commands, FTS5 searches) belongs in Python services. Analysis, synthesis, and report generation belong in Claude skill prompts.

## Common Pitfalls

### Pitfall 1: FTS5 Index Drift

**What goes wrong:** The FTS5 virtual table gets out of sync with the `execution_logs` table when logs are inserted or deleted without updating the FTS index.
**Why it happens:** External content FTS5 tables don't auto-sync -- inserts/updates/deletes to the content table don't propagate to the FTS index.
**How to avoid:** Use SQLite triggers to keep the FTS index in sync, OR rebuild the index periodically. The recommended approach is SQLite triggers:
```sql
CREATE TRIGGER execution_logs_ai AFTER INSERT ON execution_logs BEGIN
    INSERT INTO execution_logs_fts(rowid, prompt, stdout_log)
    VALUES (new.id, new.prompt, new.stdout_log);
END;
```
**Warning signs:** Search returns stale or missing results; search returns results for deleted executions.
**Source:** [SQLite FTS5 official docs](https://sqlite.org/fts5.html) -- External Content Tables section.

### Pitfall 2: PREDEFINED_TRIGGERS List Duplication

**What goes wrong:** New bot definitions are added to `triggers.py` but not `migrations.py` (or vice versa), causing the bot to exist in new databases but not upgraded ones.
**Why it happens:** The `PREDEFINED_TRIGGERS` list is duplicated in two files: `backend/app/db/triggers.py` and `backend/app/db/migrations.py`.
**How to avoid:** Add new bots to both files simultaneously. Better yet, consolidate to a single source of truth by having `migrations.py` import from `triggers.py`.
**Warning signs:** Bot appears after fresh install but not after upgrade (or vice versa).

### Pitfall 3: Prompt Template Too Large

**What goes wrong:** Bot prompt templates that include too much context (e.g., full PR diffs, full package manifests) exceed Claude CLI's prompt length limits or cause slow execution.
**Why it happens:** Attempting to pass all data inline in the prompt template instead of having the Claude skill read files from the filesystem.
**How to avoid:** Use `{paths}` to point Claude at the project directory. Let the Claude skill use its file-reading tools (Read, Glob, Grep, Bash) to gather data at execution time. Only pass metadata (PR URL, incident ID, search query) in the prompt.
**Warning signs:** Execution timeouts, truncated prompts, OOM in subprocess.

### Pitfall 4: OSV API Rate Limiting

**What goes wrong:** BOT-01 makes too many OSV API calls when scanning a large project with hundreds of dependencies.
**Why it happens:** Querying each dependency individually without batching.
**How to avoid:** Use the OSV batch query endpoint (`POST https://api.osv.dev/v1/querybatch`) which accepts up to 1000 queries per request. Alternatively, have the Claude skill parse the manifest and make targeted queries.
**Warning signs:** 429 responses from OSV API, slow scan times.
**Source:** [OSV.dev API docs](https://google.github.io/osv.dev/)

### Pitfall 5: Scheduled Bot Overload

**What goes wrong:** Multiple scheduled bots (BOT-01, BOT-05) fire at the same time, competing for the single CLI backend.
**Why it happens:** Default schedule times are too close together.
**How to avoid:** Stagger schedule times for different bots (e.g., BOT-01 at 02:00, BOT-05 at 04:00). The existing `OrchestrationService` handles fallback chains, but concurrent executions still compete for CPU.
**Warning signs:** Execution timeouts, backed-up scheduler queue.

### Pitfall 6: GitHub Event Trigger Overlap

**What goes wrong:** BOT-03 (test coverage gap), BOT-06 (PR summary), and the existing `bot-pr-review` all trigger on the same GitHub PR event, causing three concurrent executions.
**Why it happens:** All three bots have `trigger_source: "github"` and match on `pull_request` events.
**How to avoid:** This is actually acceptable -- each bot serves a different purpose. But ensure the per-repo rate limiting (currently 60 seconds in `github_webhook.py`) is adjusted or the bots are dispatched sequentially. Consider adding a priority/ordering mechanism.
**Warning signs:** Rate limit rejections for legitimate PR events, out-of-order PR comments.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Bot type (BOT-01 through BOT-07)
- Project size (small: <10 deps, medium: 10-100 deps, large: 100+ deps)
- Execution backend (claude, gemini)

**Dependent variables:**
- Execution time (seconds)
- Output quality (structured output conformance)
- Success rate (exit code 0)
- FTS5 search relevance (precision@10 for BOT-07)

**Controlled variables:**
- Same project paths across runs
- Same backend account (no fallback chain variation)
- Same Claude CLI version

**Baseline comparison:**
- Method: Manual execution of equivalent tasks (manual CVE lookup, manual changelog writing, etc.)
- Expected performance: 10-30 minutes for manual tasks
- Our target: <5 minutes per bot execution, >80% output quality

**Ablation plan:**
1. Bot with full Claude skill vs. bare prompt (no skill file) -- tests skill file value
2. FTS5 search vs. LIKE-based search -- tests search quality improvement for BOT-07
3. OSV API batch vs. individual queries -- tests BOT-01 scan time

**Statistical rigor:**
- Number of runs: 3 per bot per project size
- Success measured as: structured output contains all required sections
- Timing measured as: `duration_ms` from `execution_logs` table

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Execution success rate | Core reliability | `COUNT(status='success') / COUNT(*)` from execution_logs | 100% target |
| Execution duration | User experience | `duration_ms` from execution_logs | <300s per bot |
| Output section completeness | Quality | Parse stdout for required sections per bot type | >80% |
| FTS5 search precision@10 | BOT-07 relevance | Manual review of top 10 results for 5 test queries | >70% |
| PR comment latency | BOT-06 SLA | Time from PR webhook to comment posted | <60s target |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Predefined triggers seeded correctly | Level 1 (Sanity) | Check DB after init_db() |
| Claude skill files exist and are valid markdown | Level 1 (Sanity) | File existence check |
| FTS5 virtual table created successfully | Level 1 (Sanity) | SQL query after migration |
| OSV API returns results for known vulnerable package | Level 2 (Proxy) | Integration test with real API |
| `gh pr list --state merged` returns valid JSON | Level 2 (Proxy) | Subprocess check |
| Each bot produces structured output with required sections | Level 2 (Proxy) | Parse stdout of test execution |
| FTS5 search returns relevant results for test queries | Level 2 (Proxy) | Compare search results to expected |
| BOT-06 posts PR comment within 60 seconds | Level 3 (Deferred) | End-to-end with live GitHub repo |
| BOT-01 finds real CVEs in a known-vulnerable project | Level 3 (Deferred) | End-to-end with real project scan |
| All bots work reliably under production load | Level 3 (Deferred) | Production monitoring |

**Level 1 checks to always include:**
- All seven predefined trigger entries exist in database after `seed_predefined_triggers()`
- Each trigger has valid `prompt_template`, `trigger_source`, `backend_type`
- FTS5 virtual table `execution_logs_fts` exists after schema migration
- New `_KNOWN_PLACEHOLDERS` are registered in `PromptRenderer`
- Claude skill files exist at expected paths

**Level 2 proxy metrics:**
- Manual trigger execution for each bot with test input produces non-empty stdout
- Bot output contains expected sections (e.g., BOT-01 output has "vulnerabilities", "recommendations")
- FTS5 search for a known execution log phrase returns the correct execution
- `seed_predefined_triggers()` is idempotent (running twice doesn't duplicate)

**Level 3 deferred items:**
- End-to-end GitHub PR workflow for BOT-03 and BOT-06
- Real CVE scanning against known-vulnerable package manifests
- Production-scale FTS5 performance with 10,000+ execution logs
- Multi-bot concurrent execution stress test

## Production Considerations

### Known Failure Modes

- **Claude CLI not installed:** All bots depend on the Claude CLI being available. The platform already handles this gracefully via `backend_detection_service.py`, but new bots should log clear error messages if the CLI is missing.
  - Prevention: Check CLI availability at startup; disable bots if CLI unavailable.
  - Detection: `ExecutionService.build_command()` will fail with `FileNotFoundError`.

- **OSV API downtime (BOT-01):** The OSV API is a free, Google-maintained service. Outages are rare but possible.
  - Prevention: Cache last-known vulnerability data; allow manual re-scan.
  - Detection: HTTP timeout or 5xx response from `api.osv.dev`.

- **GitHub rate limiting (BOT-03, BOT-05, BOT-06):** `gh` CLI respects GitHub API rate limits (5000 req/hour for authenticated users).
  - Prevention: The existing per-repo rate limiting (60s) in `github_webhook.py` helps. BOT-05 changelog generation should be scheduled, not triggered per-merge.
  - Detection: `gh` CLI prints rate limit warnings to stderr; `RateLimitService` already monitors stderr.

### Scaling Concerns

- **FTS5 index size (BOT-07):** At current scale (hundreds of executions), FTS5 will perform well. At 100,000+ execution logs, the FTS index may consume significant disk space.
  - At current scale: No optimization needed.
  - At production scale: Consider periodic FTS index rebuild (`INSERT INTO execution_logs_fts(execution_logs_fts) VALUES('rebuild')`), or limit FTS indexing to recent logs (last 90 days).

- **Concurrent GitHub-triggered bots:** Three bots (existing `bot-pr-review`, new BOT-03, new BOT-06) all trigger on PR events. This triples the execution load per PR.
  - At current scale: Acceptable -- PRs are infrequent enough.
  - At production scale: Consider a unified GitHub bot that handles all PR-related tasks in a single execution, or sequential dispatch with priority ordering.

### Common Implementation Traps

- **Trap: Adding bot logic to Python instead of Claude skills**
  - Correct approach: Python gathers data (OSV API, `gh` output, FTS5 results). Claude skill analyzes and generates reports. This keeps bots updatable without code changes.

- **Trap: Creating new database tables per bot type**
  - Correct approach: All bots use the existing `triggers` + `execution_logs` tables. Bot-specific structured output is stored in `stdout_log`. Only BOT-07 needs a new table (the FTS5 virtual table).

- **Trap: Writing bot-specific execution services**
  - Correct approach: All bots flow through `ExecutionService.run_trigger()`. Bot-specific preprocessing (data gathering, file preparation) is minimal and pattern-matched on trigger ID or skill command.

## Code Examples

Verified patterns from the existing codebase:

### Adding a New Predefined Trigger

```python
# Source: backend/app/db/triggers.py (existing pattern)
# Must be added to BOTH triggers.py AND migrations.py
PREDEFINED_TRIGGERS = [
    # ... existing entries ...
    {
        "id": "bot-changelog",
        "name": "Changelog Generator",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/changelog-generator {paths} {last_release_tag}",
        "backend_type": "claude",
        "trigger_source": "scheduled",  # or "manual"
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
]
```

### Creating FTS5 Virtual Table via Migration

```python
# Source: backend/app/db/migrations.py (new versioned migration)
def _migrate_add_fts5_search(conn):
    """Add FTS5 full-text search index for execution logs."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS execution_logs_fts USING fts5(
            prompt,
            stdout_log,
            content='execution_logs',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """)
    # Sync triggers to keep FTS in sync with execution_logs
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS execution_logs_fts_insert
        AFTER INSERT ON execution_logs BEGIN
            INSERT INTO execution_logs_fts(rowid, prompt, stdout_log)
            VALUES (new.id, new.prompt, new.stdout_log);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS execution_logs_fts_update
        AFTER UPDATE OF stdout_log ON execution_logs BEGIN
            INSERT INTO execution_logs_fts(execution_logs_fts, rowid, prompt, stdout_log)
            VALUES ('delete', old.id, old.prompt, old.stdout_log);
            INSERT INTO execution_logs_fts(rowid, prompt, stdout_log)
            VALUES (new.id, new.prompt, new.stdout_log);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS execution_logs_fts_delete
        AFTER DELETE ON execution_logs BEGIN
            INSERT INTO execution_logs_fts(execution_logs_fts, rowid, prompt, stdout_log)
            VALUES ('delete', old.id, old.prompt, old.stdout_log);
        END
    """)
    # Populate FTS index from existing data
    conn.execute("""
        INSERT INTO execution_logs_fts(rowid, prompt, stdout_log)
        SELECT id, prompt, stdout_log FROM execution_logs
        WHERE stdout_log IS NOT NULL
    """)
```

### FTS5 Search Query

```python
# Source: New service -- backend/app/services/log_search_service.py
from app.db.connection import get_connection

class LogSearchService:
    """Full-text search over execution logs using SQLite FTS5."""

    @staticmethod
    def search(query: str, limit: int = 20, offset: int = 0) -> list:
        """Search execution logs using natural language query.

        Args:
            query: Plain English search query (e.g., "SQL injection findings")
            limit: Maximum results to return
            offset: Pagination offset

        Returns:
            List of dicts with execution metadata and highlighted snippets
        """
        with get_connection() as conn:
            # FTS5 MATCH with BM25 ranking
            cursor = conn.execute("""
                SELECT e.execution_id, e.trigger_id, e.started_at, e.status,
                       e.backend_type, t.name as trigger_name,
                       snippet(execution_logs_fts, 1, '<mark>', '</mark>', '...', 64)
                           as matched_snippet,
                       rank
                FROM execution_logs_fts
                JOIN execution_logs e ON e.id = execution_logs_fts.rowid
                LEFT JOIN triggers t ON e.trigger_id = t.id
                WHERE execution_logs_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?
            """, (query, limit, offset))
            return [dict(row) for row in cursor.fetchall()]
```

### OSV API Query for BOT-01

```python
# Source: New service or Claude skill data preparation
import json
import urllib.request

def query_osv_vulnerabilities(package_name: str, ecosystem: str, version: str = None) -> list:
    """Query OSV.dev API for known vulnerabilities.

    Source: https://google.github.io/osv.dev/post-v1-query/
    """
    payload = {
        "package": {
            "name": package_name,
            "ecosystem": ecosystem,
        }
    }
    if version:
        payload["version"] = version

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.osv.dev/v1/query",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    return result.get("vulns", [])
```

### Bot-Specific Preprocessing in ExecutionService

```python
# Source: backend/app/services/execution_service.py (extend existing pattern)
# In run_trigger(), after prompt rendering:

# Existing pattern for bot-security:
if "/weekly-security-audit" in prompt:
    threat_report_path = cls.save_threat_report(trigger_id, message_text)
    prompt = prompt.replace(
        "/weekly-security-audit", f"/weekly-security-audit {threat_report_path}"
    )

# New pattern for bot-changelog:
if "/changelog-generator" in prompt and "{last_release_tag}" in prompt:
    last_tag = cls._get_last_release_tag(effective_paths)
    prompt = prompt.replace("{last_release_tag}", last_tag or "v0.0.0")
```

## Paper-Backed Recommendations

### Recommendation 1: SQLite FTS5 with BM25 for Log Search (BOT-07)

**Recommendation:** Use SQLite FTS5 with the `porter unicode61` tokenizer and built-in BM25 ranking for natural language search over execution logs.

**Evidence:**
- SQLite FTS5 official documentation (2024) -- FTS5 provides "full-text search functionality to database applications" with built-in BM25 scoring that "assigns a relevance score based on term frequency and other signals."
- Sling Academy best practices guide (2025) -- Recommends "external content tables" pattern: "store canonical data in normal tables, and keep an FTS5 table as an index" for production apps.
- TheLinuxCode practical guide (2025) -- Confirms FTS5 with porter stemming enables "token-aware matching, phrase queries, prefix search, and relevance ranking."

**Confidence:** HIGH -- FTS5 is a mature, well-documented SQLite extension included in Python's standard library.
**Expected improvement:** Full-text search over 10,000+ logs in <10ms vs. seconds with LIKE-based search.
**Caveats:** FTS5 external content tables require sync triggers or periodic rebuild. Porter stemmer may produce surprising results for technical terms.

### Recommendation 2: OSV.dev API for Vulnerability Lookup (BOT-01)

**Recommendation:** Use the OSV.dev REST API (`POST https://api.osv.dev/v1/query`) for dependency vulnerability cross-referencing. Use the batch endpoint (`/v1/querybatch`) for projects with many dependencies.

**Evidence:**
- OSV.dev official documentation (Google, 2024-2025) -- Aggregates vulnerabilities from "GitHub Security Advisories, PyPA, RustSec, and Global Security Database" covering Python, JavaScript, Go, Rust, and more.
- OSV-Scanner documentation (Google, 2025) -- Demonstrates scanning of "package.json, package-lock.json, yarn.lock, requirements.txt, Pipfile.lock, poetry.lock, pdm.lock, uv.lock" and other manifest files.

**Confidence:** HIGH -- OSV.dev is Google-maintained, free, requires no API key, and is the standard for open-source vulnerability lookup.
**Expected improvement:** Automated CVE identification in <30 seconds per project vs. manual NVD search.
**Caveats:** API is case-sensitive; ecosystem names must match exactly (e.g., "PyPI" not "pypi"). Rate limiting may apply for very large batch queries.

### Recommendation 3: Conventional Commits Parsing for Changelog (BOT-05)

**Recommendation:** Parse PR titles and commit messages using the Conventional Commits specification (`^(feat|fix|docs|chore|refactor|perf|test|ci|build|style)(\(.+\))?!?:`) to group changelog entries by type.

**Evidence:**
- Conventional Commits specification v1.0.0 (2019, widely adopted) -- "fix type commits should be translated to PATCH releases. feat type commits should be translated to MINOR releases."
- Google's Release Please (2024-2025) -- "parses your git history, looking for Conventional Commit messages" to generate changelogs grouped by type.
- conventional-changelog (2025, 5.6k GitHub stars) -- Standard tool that demonstrates the grouping pattern.

**Confidence:** HIGH -- Conventional Commits is the dominant standard for changelog generation.
**Expected improvement:** Consistent, well-structured changelogs generated in seconds vs. hours of manual work.
**Caveats:** Requires PRs to follow conventional commit conventions; bot should handle non-conforming PR titles gracefully (group as "Other").

### Recommendation 4: AI-Driven Postmortem Generation (BOT-04)

**Recommendation:** Use Claude's narrative synthesis capability to draft structured postmortems. Provide raw data (execution logs, PR history, deployment timeline) as context and let Claude generate the timeline, root cause, impact, and action items sections.

**Evidence:**
- Rootly SRE documentation (2025) -- "AI-generated postmortems offer a smarter way to handle incident reviews by automating data collection and report generation." AI "synthesizes this timeline into a coherent narrative summary."
- Atlassian Incident Management Handbook (2025) -- Standard postmortem template includes: "Summary, Impact, Timeline, Root Cause, Trigger, Resolution, Action Items."

**Confidence:** MEDIUM -- AI postmortem generation is an emerging practice (2024-2025); effectiveness depends heavily on prompt quality and available incident data.
**Expected improvement:** Draft postmortem in <5 minutes vs. 1-2 hours of manual writing.
**Caveats:** AI may hallucinate root causes if insufficient data is provided; always requires human review.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual CVE lookup in NVD | Automated OSV.dev API scanning | 2022-2024 | Scan hundreds of deps in seconds |
| Manual changelog writing | Conventional Commits + auto-generation | 2019-2024 | Consistent, typed changelogs |
| LIKE-based text search | FTS5 with BM25 ranking | Mature since SQLite 3.9 (2015) | Orders of magnitude faster search |
| Manual postmortem writing | AI-assisted draft generation | 2024-2025 | Draft in minutes, human refines |
| Manual PR review | AI code review bots | 2023-2025 | Immediate feedback on PRs |

**Deprecated/outdated:**
- **FTS3/FTS4:** Superseded by FTS5 which adds better ranking (BM25), column filters, and external content table support.
- **NVD API v1.0:** Replaced by NVD API v2.0 (2023), but OSV.dev aggregates NVD data anyway.

## Open Questions

1. **Per-repo rate limiting for multiple GitHub-triggered bots**
   - What we know: Currently, `github_webhook.py` enforces 60-second rate limiting per repo. With three bots (bot-pr-review, BOT-03, BOT-06) all triggering on PR events, only the first bot would fire; subsequent events within 60s are rejected.
   - What's unclear: Should all three bots be dispatched from a single webhook event (bypassing per-repo rate limit), or should they be dispatched sequentially with delays?
   - Recommendation: Modify `dispatch_github_event()` to dispatch all matching triggers from a single webhook receipt (which it already does -- the rate limit is per-webhook-receipt, not per-trigger). Verify this by reading `dispatch_github_event()` more carefully. The existing code dispatches all matching triggers in threads from a single webhook call, so the rate limit only prevents duplicate webhook deliveries, not duplicate trigger dispatches.

2. **Claude skill discovery mechanism**
   - What we know: The existing `bot-security` uses a `/weekly-security-audit` skill command. The skill is referenced by name in the prompt template.
   - What's unclear: How does Claude CLI discover and load skill files? Are they auto-discovered from `.claude/skills/` or must they be configured somewhere?
   - Recommendation: Investigate Claude CLI skill loading mechanism. The `SkillDiscoveryService` in the codebase may provide answers.

3. **FTS5 initial population for existing databases**
   - What we know: New databases will create the FTS5 table and start indexing from the beginning. Existing databases need a one-time population of the FTS index.
   - What's unclear: How long does initial FTS5 population take for a database with thousands of execution logs?
   - Recommendation: Include `INSERT INTO execution_logs_fts SELECT ... FROM execution_logs` in the migration. For large databases, this may take a few seconds but is a one-time cost.

4. **BOT-04 incident identifier format**
   - What we know: The spec says "given an incident identifier, pulls relevant logs and PR context."
   - What's unclear: What constitutes an "incident identifier" in Agented? There is no incident tracking system in the platform.
   - Recommendation: Define incident identifier as an execution_id, a date range, or a free-text description. BOT-04 can accept any of these via `{message}` placeholder and search execution logs for context.

## Sources

### Primary (HIGH confidence)
- [SQLite FTS5 Extension](https://sqlite.org/fts5.html) -- Official FTS5 documentation, virtual table creation, BM25 ranking, external content tables
- [OSV.dev API](https://google.github.io/osv.dev/) -- Vulnerability query API, batch queries, supported ecosystems
- [OSV-Scanner](https://google.github.io/osv-scanner/) -- Supported manifest files, scan capabilities
- [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) -- Commit type specification (feat/fix/breaking)
- [GitHub CLI Manual: gh pr list](https://cli.github.com/manual/gh_pr_list) -- Merged PR listing, JSON output format
- Existing codebase: `backend/app/db/triggers.py`, `backend/app/db/seeds.py`, `backend/app/services/execution_service.py`, `backend/app/services/prompt_renderer.py`

### Secondary (MEDIUM confidence)
- [Sling Academy FTS5 Best Practices](https://www.slingacademy.com/article/best-practices-for-using-fts-virtual-tables-in-sqlite-applications/) -- External content table pattern, sync triggers
- [Google Release Please](https://github.com/googleapis/release-please) -- Conventional commit changelog generation pattern
- [Rootly AI Postmortems](https://rootly.com/sre/ai-generated-postmortems-rootlys-automated-rca-tool) -- AI-driven postmortem generation patterns
- [Atlassian Postmortem Handbook](https://www.atlassian.com/incident-management/handbook/postmortems) -- Standard postmortem template structure
- [Claude Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) -- XML tags for structured prompts

### Tertiary (LOW confidence)
- [Merged PRs Changelog Gist](https://gist.github.com/motss/d9d6c58ca7b064982dcdbb5e663f047f) -- Example `gh pr list` changelog script (community source, needs validation)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- No new dependencies; all capabilities are built-in or already integrated
- Architecture: HIGH -- Follows established predefined trigger + Claude skill pattern from existing bots
- Paper recommendations: HIGH -- FTS5, OSV.dev, and Conventional Commits are mature, well-documented standards
- Pitfalls: HIGH -- Identified from codebase analysis (PREDEFINED_TRIGGERS duplication, FTS sync, rate limiting)
- Experiment design: MEDIUM -- Proxy metrics are well-defined; end-to-end validation depends on real project data

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain -- no fast-moving components)
