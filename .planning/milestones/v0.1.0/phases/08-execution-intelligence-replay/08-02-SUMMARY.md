---
phase: 08-execution-intelligence-replay
plan: 02
subsystem: backend
tags: [chunking, branching, deduplication, conversation-tree, execution-pipeline]
dependency_graph:
  requires: [08-01]
  provides: [ChunkService, ConversationBranchService, chunked-execution-api, branch-api]
  affects: [08-05]
tech_stack:
  added: []
  patterns: [code-aware-chunking, tree-structured-messages, background-thread-dispatch]
key_files:
  created:
    - backend/app/services/chunk_service.py
    - backend/app/services/conversation_branch_service.py
    - backend/app/models/conversation_branch.py
    - backend/app/db/conversation_branches.py
    - backend/app/db/chunk_results.py
    - backend/app/routes/conversation_branches.py
    - backend/app/routes/chunks.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/db/__init__.py
    - backend/app/routes/__init__.py
decisions:
  - "Explicit max_chars parameter overrides SIZE_THRESHOLD to allow fine-grained chunking for testing"
  - "Overlap capped at min(OVERLAP_CHARS, chunk_size/5) to prevent excessive chunk growth"
  - "Background chunk processing uses Semaphore(3) per 08-RESEARCH.md anti-pattern guidance"
metrics:
  duration: 17min
  completed: 2026-03-05
---

# Phase 08 Plan 02: Smart Context Chunking & Conversation Branching Summary

ChunkService provides code-aware splitting at semantic boundaries (class/function definitions) with normalized string deduplication and merged results. ConversationBranchService implements tree-structured conversation branching with deep-copy semantics preserving original threads immutably, based on the ContextBranch paper (arXiv:2512.13914).

## What Was Built

### Smart Context Chunking (EXE-03)
- **ChunkService** splits content >100KB at code boundaries using prioritized separators (class > function > block > line)
- Configurable max chunk size (~500 tokens / 2000 chars default) with 10% overlap for context continuity
- Import preamble extraction prepended to each chunk per 08-RESEARCH.md Pitfall 2
- **Deduplication** via normalized string matching (lowercase, whitespace normalization, line number anonymization)
- **merge_chunk_results()** aggregates all chunk outputs with duplicate removal stats

### Conversation Branching (EXE-04)
- **ConversationBranchService** creates branches from any message index with deep-copy semantics
- Original conversation messages are never modified (immutable per ContextBranch paper)
- Tree-structured messages stored as normalized rows with parent_message_id references
- Branch tree visualization via get_branch_tree()
- Five API endpoints: create/list branches, get tree, get/add messages

### Chunked Execution Pipeline (EXE-03)
- **POST /admin/bots/{bot_id}/run-chunked** splits content, creates DB records, dispatches background threads
- Background threads use threading.Semaphore(3) to limit concurrent AI invocations
- **GET /admin/chunked-executions/{id}** returns status with progress (completed_chunks/total_chunks)
- **GET /admin/chunked-executions/{id}/results** returns merged/deduplicated output (409 if still processing)

### Database Tables
- **conversation_messages**: tree-structured messages with parent_message_id, branch_id, conversation_id
- **conversation_branches**: branch metadata with parent_branch_id, fork_message_id
- **chunked_executions**: overall chunked execution tracking (status, merged_output, stats)
- **chunk_results**: per-chunk bot output storage (chunk_content, bot_output, token_count)

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Smart chunking service | 7707246 | chunk_service.py, conversation_branch.py (models) |
| 2 | Conversation branching | 355c9ee | conversation_branches.py (db, routes, service), schema.py, migrations.py |
| 3 | Chunked execution endpoint | 9c1a410 | chunk_results.py (db), chunks.py (routes) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SIZE_THRESHOLD bypass for explicit max_chars**
- **Found during:** Task 1 verification
- **Issue:** Plan's verify test passes max_chars=500 on content under 100KB, but code returned single chunk due to SIZE_THRESHOLD check
- **Fix:** Only apply SIZE_THRESHOLD when max_chars is not explicitly provided
- **Files modified:** backend/app/services/chunk_service.py
- **Commit:** 7707246

**2. [Rule 1 - Bug] Overlap size causing chunks to exceed max bounds**
- **Found during:** Task 1 verification
- **Issue:** Fixed 200-char overlap was 40% of a 500-char chunk, exceeding the 700-char test tolerance
- **Fix:** Cap overlap at min(OVERLAP_CHARS, chunk_size/5) for proportional scaling
- **Files modified:** backend/app/services/chunk_service.py
- **Commit:** 7707246

## Verification Results

- All ChunkService tests pass (small content no-chunk, large content chunking, deduplication, merge)
- All imports succeed for both services and DB modules
- 1166 existing tests pass with zero regressions
- Pre-existing test_post_execution_hooks failure unrelated to changes

## Self-Check: PASSED
