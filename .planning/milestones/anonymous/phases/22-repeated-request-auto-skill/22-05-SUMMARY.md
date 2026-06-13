---
phase: 22-repeated-request-auto-skill
plan: 05
subsystem: self-improvement/auto-skill-gate
tags: [gate, hybrid-confidence, evolver, autonomy-policy, skill-forge]
requires: ["22-01", "22-03", "22-04"]
provides: ["evaluate_signal", "convert_signal", "GateDecision"]
affects: ["repeated-request signal store", "harness_evolver skill dispatch", "session_takeaways", "forge_origin"]
tech-stack:
  added: []
  patterns: ["pure-function gate + effectful driver split", "proven evolver _create_dispatch['skill'] path", "per-project policy with env fallback"]
key-files:
  created:
    - backend/app/services/repeated_request_gate.py
    - backend/tests/test_repeated_request_gate.py
  modified: []
decisions:
  - "AUTO path uses evolver _create_dispatch['skill'] / _update_dispatch['skill'] (proven), NOT create_and_bind_and_materialize (skill absent from _CREATE_FNS)"
  - "scan-fail / provenance-diverged / policy-off downgrade AUTO to PROPOSE (never silent REJECT)"
  - "per-project project_autonomy_config gates AUTO; AGENTED_TAKEAWAY_AUTOAPPLY env only when no project row"
metrics:
  duration: ~25m
  completed: 2026-06-13
---

# Phase 22 Plan 05: Hybrid Auto-Skill Confidence Gate Summary

Pure-function hybrid gate that routes recurring-request signals to AUTO / PROPOSE / REJECT and drives the AUTO lane into a forged skill via the proven evolver dispatch — 17 gate-matrix tests green, skill-create fires exactly once on AUTO and zero times on every weaker branch.

## What Was Built

- `evaluate_signal(...) -> GateDecision`: a side-effect-free router. AUTO iff `occurrence_count >= 3` within a 30-day window AND `verified_success_count >= 1` AND scan-clean AND dedup-ok AND provenance-ok AND per-project policy enabled. Any failing axis collects a reason and routes to PROPOSE (confidence 0.65). `patch=True` whenever a near-duplicate binding exists.
- `GateDecision` frozen dataclass: `route` (auto/propose/reject), `confidence` (0.9/0.65), `patch`, `reasons`.
- `convert_signal(signal, ...)`: computes the decision (policy from `_auto_apply_policy`), and on AUTO inserts a `discovered_procedure` takeaway at 0.9 (`harness_takeaways.insert_many`), creates the skill via `_create_dispatch['skill']` (or patches via `_update_dispatch['skill']` on a dedup hit), records `forge_origin` (sha256 of content), and `mark_skill_created`. PROPOSE/REJECT never create.
- `_auto_apply_policy(project_id)`: reads `project_autonomy_config` (honors `enabled` and optional `policy_json {"kinds": [...]}` scoping for `discovered_procedure`); falls back to `AGENTED_TAKEAWAY_AUTOAPPLY` only when no row exists.

## Deviations from Plan

None — plan executed as written. uv.lock incidentally re-resolved during `uv run`; reverted before commit per working-directory instruction.

## Experiment Results

### Parameters

| Parameter | Value |
|-----------|-------|
| AUTO occurrence min | 3 |
| AUTO window | 30 days |
| AUTO confidence | 0.9 |
| PROPOSE confidence | 0.65 |
| takeaway kind | discovered_procedure |

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| gate-matrix branch correctness | no gate | 100% | 17/17 tests pass | PASS |
| AUTO skill-create call count | n/a | exactly 1 | 1 | PASS |
| PROPOSE/REJECT skill-create count | n/a | 0 | 0 | PASS |
| scan-fail/provenance downgrade | n/a | PROPOSE | PROPOSE | PASS |

### Analysis

Every gate-matrix branch (P2) plus the scan-fail downgrade (A2) routes correctly. The AUTO path drives exactly one `_create_dispatch['skill']` call; the dedup hit re-routes to `_update_dispatch['skill']` (patch-over-create) with zero creates. No regression in `test_forge_skill_dispatch.py` (22 pass combined).

### Artifacts

- Gate module: `backend/app/services/repeated_request_gate.py`
- Test suite: `backend/tests/test_repeated_request_gate.py` (17 tests)

## Commits

- `dd4ef1da77` — feat(22-05): evaluate_signal pure-function gate matrix
- `d86dd737bf` — test(22-05): convert_signal AUTO/PROPOSE/REJECT effect matrix

## Self-Check: PASSED

- FOUND: backend/app/services/repeated_request_gate.py
- FOUND: backend/tests/test_repeated_request_gate.py
- FOUND commit: dd4ef1da77
- FOUND commit: d86dd737bf
- Tests: 17/17 pass; combined with dispatch suite 22/22; ruff clean; uv.lock not committed
