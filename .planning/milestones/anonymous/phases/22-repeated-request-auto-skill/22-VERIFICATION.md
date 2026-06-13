---
phase: 22-repeated-request-auto-skill
verified: 2026-06-13T00:00:00Z
status: passed
score:
  level_1: 8/8 sanity checks passed
  level_2: 71/71 targeted tests passed
  level_3: 2 deferred (D1/D2 true-live rerun, tracked in 22-DOGFOOD.md)
re_verification:
  previous_status: none
gaps: []
deferred_validations:
  - description: "True-live dogfood rerun against live session_ids (not recorded-real transcripts)"
    metric: "end-to-end skill creation from live sessions"
    target: "PASS"
    depends_on: "live session traffic in deployment"
    tracked_in: "22-DOGFOOD.md (Deferred section)"
human_verification: []
---

# Phase 22: Repeated-Request Auto-Skill Verification Report

**Phase Goal:** The harness self-improves — a `repeated_request_signals` store and a session-completion detection handler (over all five session kinds) embed and match recurring user requests, hybrid confidence gates convert them into skills automatically or queue for approval, with patch-over-create dedup, origin-hash provenance, and prompt-injection/exfiltration/invisible-Unicode scanning.
**Status:** passed
**Re-verification:** No — initial verification

## Level 2: Targeted Test Suite

`uv run pytest tests/test_repeated_request_signals_db.py tests/test_build_harness_session_kinds.py tests/test_repeated_request_detector.py tests/test_skill_safety_scanner.py tests/test_skill_dedup_provenance.py tests/test_repeated_request_gate.py tests/test_repeated_request_dogfood.py -q`

Output: `71 passed, 1 warning in 31.61s`

Frontend isolation: `git diff --name-only main...HEAD | grep frontend` → empty (FRONTEND_EXIT=1, no matches). Backend-only phase; known AnswerGroundednessCard.vue TS2345 failure not attributable.

## Must-Have Verification

| # | Must-Have | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `repeated_request_signals` UPSERT: first_seen preserved, occurrence++, embedding, FIFO-5 example_session_ids, verified_success_count + skill_created | PASS | repeated_request_signals.py:66-94 (`occurrence_count = occurrence_count + 1`, `example_session_ids` capped at 5, `first_seen_at` set ONLY by insert); schema/_repeated_request_signals.py exists (2341 bytes); 71/71 tests incl. test_repeated_request_signals_db.py |
| 2 | Detection handler on session-completion bus for all 5 kinds; user-turn extraction; cosine ≥ 0.83; embed-disabled exact-hash fallback; non-blocking | PASS | repeated_request_detector.py:47 `_COSINE_MATCH_THRESHOLD = 0.83`; :136-137 exact-hash fallback; :165 `register_session_handler(on_session_complete_detect)`; reuses harness_failure_annotator._FETCHERS (annotator.py:304-310 lists all 5: trigger_execution/super_agent/project_session/workflow/team_session); lifecycle.py:517 registration; bus isolates exceptions (non-blocking) |
| 3 | Hybrid gate: AUTO (≥3 occ/30d + ≥1 verified + scan + dedup + provenance + policy) → discovered_procedure conf 0.9 → evolver _create_dispatch["skill"]; PROPOSE 0.65; REJECT; per-project policy w/ AGENTED_TAKEAWAY_AUTOAPPLY fallback | PASS | repeated_request_gate.py:10-11 (`occurrence_count >= 3`/30d + `verified_success_count >= 1`); :45-46 `_CONF_AUTO=0.9`/`_CONF_PROPOSE=0.65`; :242 `_update_dispatch["skill"]`, :246 `_create_dispatch["skill"]` (create_and_bind_and_materialize deliberately NOT used per :22); :27-28 project_autonomy_config → AGENTED_TAKEAWAY_AUTOAPPLY fallback |
| 4 | Safety: fail-closed scan (injection/exfil/invisible-Unicode); patch-over-create dedup; origin-hash provenance never overwrites operator-modified skills | PASS | skill_safety_scanner.py:98 invisible-Unicode (U+2060–U+2064); :188-189 provenance match→allow / divergence→refuse; :203 `content_hash(text) == origin.get("origin_hash")` hashes rendered SKILL.md; test_skill_safety_scanner.py + test_skill_dedup_provenance.py pass |
| 5 | Consistency: evolver declares skills writable; _build_harness_session normalizes all 5 kinds | PASS | harness_evolver.py:67 `WRITABLE_KINDS = (..., "skill")`; :343 "skills/<name>.json (writable — create/update like the rest)"; tesserae_integration.py:477 `_build_harness_session` with 5 normalizers (:273 super_agent, :313 trigger_execution, :366 project_session, :406 workflow, :437 team_session); test_build_harness_session_kinds.py passes |
| 6 | Live dogfood replay (deferred D1/D2) | DEFERRED | 22-DOGFOOD.md: D1 verdict PASS, D2 verdict PASS on recorded-real transcripts via live embedding backend (384-dim cosine path); only true-live session_id sourcing deferred — tracked in "Deferred" section |

## Reflection

| Field | Value |
|-------|-------|
| hypothesis | A repeated-request store + completion-bus detector + hybrid gate can auto-convert recurring requests into safe skills across all 5 session kinds |
| predicted_outcome | Tests green; detector registered; gate uses evolver dispatch; provenance/scan/dedup enforced; dogfood D1/D2 pass on real transcripts |
| actual_outcome | All 6 must-haves verified in code; 71/71 targeted tests pass; D1/D2 PASS on recorded-real transcripts with only true-live rerun deferred |
| verdict | confirmed |
| evidence | 71 passed in 31.61s; repeated_request_detector.py:165 registration + :47 threshold; repeated_request_gate.py:246 _create_dispatch["skill"]; skill_safety_scanner.py:203 origin-hash on rendered SKILL.md |

---

_Verified: 2026-06-13_
_Verifier: Claude (grd-verifier)_
_Verification levels applied: Level 1 (sanity), Level 2 (targeted suite), Level 3 (D1/D2 deferred)_
