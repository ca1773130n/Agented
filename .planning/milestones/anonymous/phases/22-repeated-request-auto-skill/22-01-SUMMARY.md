---
phase: 22-repeated-request-auto-skill
plan: 01
subsystem: backend/db
tags: [self-improvement-loop, signal-store, upsert, embedding, tdd]
requires: []
provides:
  - "repeated_request_signals table + 3 indexes (fresh schema)"
  - "app.db.repeated_request_signals repo (upsert_signal, get_signal, list_signals, mark_skill_created, increment_verified_success, normalize_request_hash)"
  - "RepeatedRequestSignal Pydantic v2 model"
affects:
  - "22-03 detector (writes signals)"
  - "22-05 gate (reads occurrence_count + verified_success_count)"
tech-stack:
  added: []
  patterns:
    - "ON CONFLICT(request_hash) DO UPDATE accumulation (no decay)"
    - "embedding BLOB via serialize_embedding (agent_memory encoding)"
    - "JSON FIFO-capped example list in repo layer"
key-files:
  created:
    - backend/app/db/schema/_repeated_request_signals.py
    - backend/app/db/repeated_request_signals.py
    - backend/app/models/repeated_request_signal.py
    - backend/tests/test_repeated_request_signals_db.py
  modified:
    - backend/app/db/schema/__init__.py
decisions:
  - "first_seen_at set only in INSERT clause; ON CONFLICT branch never touches it — monotonic provenance"
  - "FIFO merge of example_session_ids computed in Python (read-then-merge) rather than in SQL — keeps the dedup + cap logic single-sourced and testable"
  - "representative_text + embedding refreshed on each upsert so the stored canonical example tracks the latest sighting"
metrics:
  duration: 6min
  completed: 2026-06-13
  tasks: 2
  tests: 11
---

# Phase 22 Plan 01: Repeated-request Signal Store Summary

Hash-keyed `repeated_request_signals` store whose UPSERT accumulates salience
(occurrence_count grows, first_seen_at preserved) — the durable, monotonic
substrate the self-improvement loop's detector writes and gate reads.

## What Was Built

- **DDL module** `_repeated_request_signals.py` — one table (`request_hash`
  PRIMARY KEY) + 3 indexes (project, kind, skill_created); registered in
  `create_fresh_schema` after the harness-takeaway tables.
- **Repo** `repeated_request_signals.py` — raw SQLite via `get_connection()`.
  `upsert_signal` uses `ON CONFLICT(request_hash) DO UPDATE` to increment
  `occurrence_count`, advance `last_seen_at`, and FIFO-merge the new session id
  (cap 5), while `first_seen_at` is fixed by the INSERT clause only. Embedding
  stored as a `serialize_embedding` BLOB. Plus `normalize_request_hash`,
  `get_signal`, `list_signals`, `mark_skill_created`, `increment_verified_success`.
- **Model** `RepeatedRequestSignal` (Pydantic v2) — `embedding` and
  `example_session_ids` typed; nothing decays.
- **Tests** — 11 UPSERT-invariant cases (S4), all green.

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | DDL + schema registration | 6418f57268 | `_repeated_request_signals.py`, `schema/__init__.py` |
| 2a (RED) | failing invariant suite | b721b4ef21 | `test_repeated_request_signals_db.py` |
| 2b (GREEN) | repo + model | 818de9dec4 | `repeated_request_signals.py`, `repeated_request_signal.py`, test |

## Deviations from Plan

None — plan executed exactly as written. The plan's listed file
`backend/app/db/schema/_repeated_request_signals.py` and all repo/model exports
match. One linter-applied reflow (long SQL strings to single lines) by `ruff
format`; no logic change.

## Verification

- **S3:** `create_fresh_schema(:memory:)` yields table + 3 indexes (5
  sqlite_master rows incl. autoindex) — assert ≥4 passes.
- **S4:** `uv run pytest tests/test_repeated_request_signals_db.py -v` → 11
  passed, 0 failed.
- **S1/S2:** `ruff format --check` + `ruff check` clean on all new modules.

## Self-Check: PASSED

- FOUND: backend/app/db/schema/_repeated_request_signals.py
- FOUND: backend/app/db/repeated_request_signals.py
- FOUND: backend/app/models/repeated_request_signal.py
- FOUND: backend/tests/test_repeated_request_signals_db.py
- FOUND commit 6418f57268, b721b4ef21, 818de9dec4
- Tests: 11 passed
