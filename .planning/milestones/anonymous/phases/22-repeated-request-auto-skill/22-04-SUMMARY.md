---
phase: 22-repeated-request-auto-skill
plan: 04
subsystem: backend/services
tags: [safety, scanner, dedup, provenance, fail-closed, tdd]
requires: []
provides:
  - scan_skill_content
  - find_duplicate_binding
  - provenance_allows_overwrite
affects:
  - backend/app/services/skill_safety_scanner.py
tech-stack:
  added: []
  patterns: ["fail-closed scanner", "get_origin->rehash compare", "difflib name-cosine dedup"]
key-files:
  created:
    - backend/app/services/skill_safety_scanner.py
    - backend/tests/test_skill_safety_scanner.py
    - backend/tests/test_skill_dedup_provenance.py
  modified: []
decisions:
  - "Fail-closed everywhere: any injection/exfil/invisible-Unicode match -> unsafe; unreadable on-disk file -> refuse overwrite."
  - "Dedup name-similarity threshold pinned at >=0.9 (Phase-22), difflib SequenceMatcher as documented name-cosine stand-in."
  - "Provenance tests route through autouse isolated_db/init_db so migration-only forge_origin (#157) exists."
metrics:
  duration: ~7m
  completed: 2026-06-12
---

# Phase 22 Plan 04: Skill Safety Scanner + Dedup + Provenance Guard Summary

Fail-closed safety guard (REQ-25) the auto-skill gate (22-05) calls before any auto-apply: a pure-function content scanner that rejects every known prompt-injection / exfiltration / invisible-Unicode payload, name-cosine dedup that turns near-duplicates into patch-over-create, and an origin-hash provenance check that refuses to overwrite operator-modified skills.

## What Was Built

- `scan_skill_content(content) -> ScanResult` — three detectors (injection regex set, exfiltration secret+outbound-send regex, invisible-Unicode codepoint sweep over U+200B-200F / U+202A-202E / U+2060-2064 / U+E0000-E007F). ANY match -> `safe=False` with auditable reasons. No DB, no IO.
- `find_duplicate_binding(name, content=None) -> dict | None` — exact `get_user_skill_by_name` first, then highest name-similarity bound skill at/above 0.9 via difflib (case/separator-normalized).
- `provenance_allows_overwrite(asset_id, kind, on_disk_path) -> bool` — `forge_origin.get_origin`; no row -> allow, hash match -> allow, divergence or unreadable file -> refuse. Mirrors the forge_session_import get_origin->compare idiom.

## Tasks & Commits

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | scan_skill_content (RED->GREEN S6) | 788cb437fb | skill_safety_scanner.py, test_skill_safety_scanner.py |
| 2 | dedup + provenance (RED->GREEN P3) | 3cb6e43347 | test_skill_dedup_provenance.py |

## Deviations from Plan

None of substance. The scanner module (all three functions) was authored in Task 1 since they share one file; Task 2 added its dedicated test suite against the already-present implementation, so its RED phase was the missing test file rather than missing code. All behaviour matches the plan.

## Experiment Results

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| known-bad payload rejection rate | no scanner (unsafe reaches forge) | 100% fail-closed | 16/16 known-bad -> unsafe | PASS |
| dedup patch-path hit | — | near-dup -> existing binding | exact + ~0.9 name match return binding | PASS |
| provenance overwrite refusal | — | diverged hash -> no overwrite | diverged + missing file -> False | PASS |

### Analysis

26/26 targeted tests pass. Invisible-Unicode is a pure codepoint sweep (no allowlist) so it cannot be regex-evaded. Provenance correctly fails closed on an unreadable file (defense-in-depth beyond the spec's match/diverge cases). Dedup threshold 0.9 cleanly separates `format_json_output` (near-dup) from `deploy-kubernetes-cluster` (distinct).

### Artifacts

- Module: `backend/app/services/skill_safety_scanner.py`
- Tests: `backend/tests/test_skill_safety_scanner.py` (S6), `backend/tests/test_skill_dedup_provenance.py` (P3)

## Self-Check: PASSED

- FOUND: backend/app/services/skill_safety_scanner.py
- FOUND: backend/tests/test_skill_safety_scanner.py
- FOUND: backend/tests/test_skill_dedup_provenance.py
- FOUND commit: 788cb437fb
- FOUND commit: 3cb6e43347
- Tests: 26 passed; Ruff: all checks passed
