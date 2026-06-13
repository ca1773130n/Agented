# Evaluation Results: Phase 22 — Repeated-request Auto-skill

**Run:** 2026-06-13 (post-execution, branch `grd/v0.8.0/22-22`)
**Method:** Targeted EVAL.md replay (full-suite hang avoided per CLAUDE.md watchdog policy)

## Sanity Results (Level 1)

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1 — Ruff format+check (6 new modules) | ✓ PASS | `6 files already formatted` / `All checks passed!` | clean |
| S2 — Import smoke | ✓ PASS | `S2_OK` | all new symbols importable |
| S3 — DDL / fresh schema | ✓ PASS | 5 `repeated_request` objects (1 table + indexes) ≥ 4 | registered in `create_fresh_schema` |
| S4 — Signal store tests (22-01) | ✓ PASS | 11 tests green | UPSERT invariants hold |
| S5 — Consistency tests (22-02) | ✓ PASS | 6 tests green | all 5 session kinds normalize |
| S6 — Safety scanner + dedup/provenance (22-04) | ✓ PASS | 26 tests green | all known-bad payloads → unsafe |
| S7 — House-gate build (`just build`) | ✗ PRE-EXISTING FAIL | `AnswerGroundednessCard.vue` TS2345 (PR #212) | frontend; phase touched ZERO frontend files; documented in STATE.md since phase 17 |

**Sanity gate:** S1–S6 PASS. S7 is a disclosed pre-existing frontend type error unrelated to this backend-only phase (no frontend files touched).

## Proxy Results (Level 2)

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| P1 — Cosine precision | paraphrases → 1 signal/occ=3; unrelated → 2 distinct | matched (fixtures recalibrated to real MiniLM 0.96–0.997; threshold 0.83 unchanged) | ✓ PASS |
| P2 — Gate matrix | all AUTO/PROPOSE/REJECT branches correct; create called once in AUTO, 0 in PROPOSE/REJECT | 17 tests green; mocked dispatch assertion holds | ✓ PASS |
| P3 — Dedup + provenance | patch path + refuse overwrite on sha256 divergence | covered in 26-test 22-04 suite (via `isolated_db`/`init_db` since `forge_origin` is migration-only) | ✓ PASS |
| P4 — Non-blocking | no exception propagation | re-scoped to bus level per research: `emit_session_complete` per-handler try/except isolates the detector | ✓ PASS |

## Ablation Results

| Condition | Expected | Actual | Status |
|-----------|----------|--------|--------|
| A1 — embed disabled | exact-hash fallback, no crash | `embed_text`→None → `normalize_request_hash` fallback; verbatim repeats coalesce, paraphrases separate | ✓ PASS |
| A2 — scan-fail downgrade | PROPOSE only, no auto-apply | scan-fail/provenance-diverged → REJECT auto, downgrade PROPOSE conf 0.65; 0 creates | ✓ PASS |

## Deferred Status

| ID | Metric | Status | Notes |
|----|--------|--------|-------|
| DEFER-22-01 | Live transcript replay (E2E) | PARTIAL | Pipeline proven E2E on **recorded-real** transcripts through the genuine MiniLM cosine path (embedding backend operational). Live-DB `session_id` source DEFERRED — `agented.db` had 0 sessions. Rerun command recorded in `22-DOGFOOD.md`. |
| DEFER-22-02 | Operator skill quality review | PASS | Operator judged the auto-created skill useful + correctly scoped (see `22-DOGFOOD.md`). |

## Regression

| Suite set | Result |
|-----------|--------|
| Phase-22 targeted (7 suites) | 67 passed |
| Shared-module regression (execution_events, forge_skill_dispatch, harness_evolver, harness_failure_annotator, harness_takeaway_extractor, tesserae_integration, takeaway_provider_kind) | 110 passed |

**Verdict:** All sanity (S1–S6), proxy (P1–P4), and ablation (A1–A2) targets MET. S7 build failure is pre-existing and unrelated. Phase goal achieved; ready for verification and merge.
