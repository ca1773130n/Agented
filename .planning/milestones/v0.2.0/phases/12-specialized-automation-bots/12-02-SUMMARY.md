---
phase: 12-specialized-automation-bots
plan: 02
subsystem: specialized-bots
tags: [claude-skills, chain-of-thought, gh-cli, osv-scanner, conventional-commits]
dependency_graph:
  requires: [12-01]
  provides: [skill-instructions, specialized-bot-service]
  affects: [bot-execution, pr-comments, changelog-generation]
tech_stack:
  added: [osv-scanner-integration, conventional-commits-parsing]
  patterns: [chain-of-thought-prompting, classmethod-service]
key_files:
  created:
    - .claude/skills/vulnerability-scan/INSTRUCTIONS.md
    - .claude/skills/code-tour/INSTRUCTIONS.md
    - .claude/skills/test-coverage-gaps/INSTRUCTIONS.md
    - .claude/skills/incident-postmortem/INSTRUCTIONS.md
    - .claude/skills/generate-changelog/INSTRUCTIONS.md
    - .claude/skills/pr-summary/INSTRUCTIONS.md
    - .claude/skills/search-logs/INSTRUCTIONS.md
    - backend/app/services/specialized_bot_service.py
  modified: []
decisions:
  - "Used chain-of-thought structured steps (Wei et al. 2022) for all skill instructions"
  - "osv-scanner as primary scanner with ecosystem-specific fallbacks per 12-RESEARCH.md"
  - "PR summary optimized for 60s SLA with lightweight diff analysis"
  - "Conventional Commits v1.0.0 parsing with AI fallback for non-conforming titles"
  - "SpecializedBotService uses classmethod pattern matching existing services"
metrics:
  duration: "12min"
  completed: "2026-03-05"
---

# Phase 12 Plan 02: Claude Skill Instructions and SpecializedBotService Summary

Created 7 Claude skill instruction files with chain-of-thought structured steps for specialized bots, plus a SpecializedBotService with PR comment posting and merged PR listing helpers via gh CLI.

## Task Results

### Task 1: Create Claude Skill Instruction Files for All 7 Bots

Created 7 INSTRUCTIONS.md files under `.claude/skills/`, each with chain-of-thought structured steps:

| Bot | Skill Directory | Size | Key Tools |
|-----|----------------|------|-----------|
| BOT-01 | vulnerability-scan | 4.6KB | osv-scanner, npm audit, pip-audit |
| BOT-02 | code-tour | 5.3KB | Repository analysis (5+ sections) |
| BOT-03 | test-coverage-gaps | 4.8KB | gh pr diff, gh pr comment |
| BOT-04 | incident-postmortem | 6.6KB | Execution log search, gh pr list |
| BOT-05 | generate-changelog | 5.0KB | gh pr list, Conventional Commits |
| BOT-06 | pr-summary | 3.8KB | gh pr diff, gh pr comment |
| BOT-07 | search-logs | 4.4KB | FTS5 search endpoint |

Key design choices:
- BOT-01 uses exploitability scoring (1-10) based on severity, dependency depth, fix availability, and runtime exposure
- BOT-02 requires minimum 5 labeled sections: Entry Points, Key Abstractions, Data Flow, Design Patterns, Gotchas
- BOT-03 and BOT-06 include required bot identification footers
- BOT-04 uses 5-Whys root cause analysis technique
- BOT-05 parses Conventional Commits v1.0.0 with AI fallback for non-conforming titles
- BOT-06 designed for 60s SLA with lightweight diff analysis
- BOT-07 leverages FTS5 BM25 ranking from Plan 01

### Task 2: Create SpecializedBotService

Created `backend/app/services/specialized_bot_service.py` with 4 classmethods:

| Method | Purpose | Error Handling |
|--------|---------|---------------|
| `post_pr_comment()` | Post PR comment via `gh pr comment` | TimeoutExpired, FileNotFoundError |
| `list_merged_prs()` | List merged PRs via `gh pr list` | TimeoutExpired, FileNotFoundError, JSONDecodeError |
| `check_gh_auth()` | Verify gh CLI authentication | FileNotFoundError, TimeoutExpired |
| `check_osv_scanner()` | Check osv-scanner on PATH | N/A (shutil.which) |

All methods use 30-second timeout, return graceful defaults on failure, and log operations.

## Verification Results

- All 7 skill files exist with >500 bytes of content (range: 3.8KB - 6.6KB)
- SpecializedBotService imports successfully with all 4 expected methods
- `ruff check` and `ruff format` pass on new service file
- Backend tests: 1212 passed (1 pre-existing failure in unrelated test_post_execution_hooks.py)

## Deviations from Plan

None -- plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 3749df1 | feat(12-02): create Claude skill instruction files for 7 specialized bots |
| 2 | c63382f | feat(12-02): create SpecializedBotService with PR comment and changelog helpers |

## Self-Check: PASSED

- [x] .claude/skills/vulnerability-scan/INSTRUCTIONS.md exists (4666 bytes)
- [x] .claude/skills/code-tour/INSTRUCTIONS.md exists (5322 bytes)
- [x] .claude/skills/test-coverage-gaps/INSTRUCTIONS.md exists (4753 bytes)
- [x] .claude/skills/incident-postmortem/INSTRUCTIONS.md exists (6578 bytes)
- [x] .claude/skills/generate-changelog/INSTRUCTIONS.md exists (4964 bytes)
- [x] .claude/skills/pr-summary/INSTRUCTIONS.md exists (3793 bytes)
- [x] .claude/skills/search-logs/INSTRUCTIONS.md exists (4411 bytes)
- [x] backend/app/services/specialized_bot_service.py exists and imports
- [x] Commit 3749df1 exists
- [x] Commit c63382f exists
