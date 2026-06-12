# Evaluation Plan: Phase 22 — Repeated-request Auto-skill

**Designed:** 2026-06-13
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Repeated-request signal store (UPSERT), cosine-match detector, safety scanner, hybrid auto/propose gate
**Reference papers:** N/A — codebase-grounded implementation; no academic baselines apply

## Evaluation Overview

Phase 22 closes the self-improvement loop by detecting recurring user requests, accumulating evidence in a hash-keyed signal store, and routing sufficiently-confident safe signals to auto-skill creation or the operator approval queue. The entire stack is backend-only Python; there is no model training, no benchmark dataset, and no external published baseline. Evaluation is therefore engineering-centric: does each component behave correctly per its contract, and does the assembled pipeline produce the right outcome end-to-end?

Proxy metrics are well-defined for this phase because the success criteria are expressed as precise thresholds (cosine ≥ 0.83, occurrence_count ≥ 3 within 30 days, verified_success_count ≥ 1, scan pass) that can be verified against labelled fixtures without needing production data. The only genuinely deferred evaluation is the 22-06 live dogfood — replaying real session transcripts to confirm the pipeline produces usable skills.

No paper evaluation methodology applies. All metric targets are derived from the phase success criteria and the project's house gates.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| `first_seen_at` preservation | 22-01 success criterion 1 | Core UPSERT invariant; failure causes silent data corruption |
| `occurrence_count` monotonic growth | 22-01 success criterion 1 | Gate reads this; decay would break the ≥3 auto threshold |
| `example_session_ids` cap = 5 FIFO | 22-01 success criterion 1 | Bounded storage; FIFO preserves recency |
| Cosine threshold = 0.83 | 22-03 predicted_outcome | Threshold in requirements; precision on labeled paraphrases proves the matcher does not over- or under-match |
| Non-blocking detector | 22-03 truth 3 | REQ-23 hard requirement; blocking the session-completion bus is a correctness failure, not a performance issue |
| Scanner rejection rate | 22-04 truth 1 | Fail-closed requirement; false-negative on any known attack pattern is a security bug |
| Gate matrix correctness | 22-05 predicted_outcome | Pure-function contract; wrong routing means the loop silently skips skills or auto-applies unsafely |
| Ruff format/lint | CLAUDE.md house gate | Code quality gate; must pass before any merge |
| pytest (targeted) | CLAUDE.md house gate | Backend correctness baseline |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 7 | Import smoke, ruff, table DDL, per-plan unit tests |
| Proxy (L2) | 4 | Cosine precision, gate matrix, dedup/provenance, non-blocking proof |
| Deferred (L3) | 2 | Live dogfood replay; operator quality review |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: Ruff format and lint on all new modules

- **What:** All new Python modules introduced by this phase are clean under the project's ruff config (line-length=100, py310).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check app/db/schema/_repeated_request_signals.py app/db/repeated_request_signals.py app/models/repeated_request_signal.py app/services/repeated_request_detector.py app/services/skill_safety_scanner.py app/services/repeated_request_gate.py && uv run ruff check app/db/schema/_repeated_request_signals.py app/db/repeated_request_signals.py app/models/repeated_request_signal.py app/services/repeated_request_detector.py app/services/skill_safety_scanner.py app/services/repeated_request_gate.py`
- **Expected:** Exit code 0, no output.
- **Failure means:** Style or lint violations that must be fixed before any other evaluation is meaningful.

### S2: Import smoke — all new modules importable

- **What:** Each new module can be imported in isolation without runtime errors, confirming no missing dependency or circular import.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.db.repeated_request_signals import upsert_signal, list_signals, get_signal, mark_skill_created, normalize_request_hash; from app.models.repeated_request_signal import RepeatedRequestSignal; from app.services.repeated_request_detector import detect_for_session; from app.services.skill_safety_scanner import scan_skill_content, find_duplicate_binding, provenance_allows_overwrite; from app.services.repeated_request_gate import evaluate_signal, convert_signal, GateDecision; print('OK')"`
- **Expected:** Prints `OK`.
- **Failure means:** Missing file, broken import chain, or circular dependency introduced during the phase.

### S3: DDL — table created on fresh schema

- **What:** `repeated_request_signals` table and all three indexes are present after `create_fresh_schema`.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "from app.db.schema import create_fresh_schema; import sqlite3; c=sqlite3.connect(':memory:'); create_fresh_schema(c); rows=c.execute(\"SELECT name FROM sqlite_master WHERE type IN ('table','index') AND name LIKE '%repeated_request%'\").fetchall(); print(rows); assert len(rows) >= 4, 'expected 1 table + 3 indexes'"`
- **Expected:** Prints 4 rows (1 table + 3 indexes); assert passes.
- **Failure means:** Schema registration missing or DDL syntax error.

### S4: Signal-store unit tests (22-01)

- **What:** UPSERT preserves `first_seen_at`, increments `occurrence_count`, caps `example_session_ids` at 5 FIFO, tracks `verified_success_count` and `skill_created`.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_repeated_request_signals_db.py -v`
- **Expected:** All cases green; zero failures.
- **Failure means:** Core store invariant broken — gate and detector cannot be trusted until this passes.

### S5: Consistency-fix unit tests (22-02)

- **What:** `_build_harness_session` returns a normalized `session_kind` for all five kinds (project_session, workflow, team_session, super_agent, trigger_execution).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_build_harness_session_kinds.py -v`
- **Expected:** All five kind assertions green.
- **Failure means:** The detector's kind dispatch will silently fall through for three of the five session kinds, producing zero signal coverage.

### S6: Safety-scanner unit tests (22-04)

- **What:** `scan_skill_content` rejects known injection, exfiltration, and invisible-Unicode payloads; `find_duplicate_binding` and `provenance_allows_overwrite` behave per contract.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_skill_safety_scanner.py tests/test_skill_dedup_provenance.py -v`
- **Expected:** All cases green; known-bad payloads always return `unsafe`.
- **Failure means:** Security regression — fail-closed contract violated. Block progression.

### S7: House-gate build (vue-tsc + vite)

- **What:** The repository still builds cleanly after backend-only changes (confirms no accidental frontend side-effect).
- **Command:** `cd /Users/neo/Developer/Projects/Agented && just build`
- **Expected:** Exit code 0.
- **Failure means:** Unintended file touched or type error introduced outside backend.

**Sanity gate:** ALL seven sanity checks must pass. Any failure blocks progression to Level 2.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of quality/performance.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full evaluation. Treat results with appropriate skepticism.

### P1: Cosine-match precision on labeled paraphrase fixtures

- **What:** The detector correctly groups semantically equivalent user requests into one signal (cosine ≥ 0.83 match) and keeps genuinely different requests as separate signals.
- **How:** Replay the ≥3-transcript fixture set in `backend/tests/fixtures/repeated_request_transcripts.py`. The fixture contains (a) three paraphrased variants of the same request and (b) two unrelated requests. Count resulting signals.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_repeated_request_detector.py -v -k "cosine"`
- **Target:** Paraphrase group → 1 signal with `occurrence_count = 3`; unrelated requests → 2 separate signals. Zero mis-groupings.
- **Evidence:** 22-03 `predicted_outcome` specifies "replaying 3 fixture transcripts containing the same paraphrased request produces ONE signal with occurrence_count=3 (cosine-matched)". Threshold 0.83 is from 22-RESEARCH.md §1 (embedding service contract).
- **Correlation with full metric:** HIGH — the fixture directly exercises the matching path the live pipeline uses; the only gap is that fixture embeddings are generated by the same embedding backend as production.
- **Blind spots:** Fixture paraphrases are hand-crafted; adversarial or domain-shift paraphrases may produce different cosine scores. Does not cover the embedding-backend-disabled fallback path (covered in P4).
- **Validated:** No — awaiting deferred validation at phase-22-dogfood (D1).

### P2: Gate-matrix correctness

- **What:** `evaluate_signal` routes to AUTO, PROPOSE, or REJECT as a pure function of (occurrence_count, verified_success_count, scan result, dedup result, provenance result, policy).
- **How:** Parametrized pytest covering all branching combinations: (occ≥3/verified≥1/scan-clean/dedup-ok/provenance-ok/skill-in-policy → AUTO), (occ=2 → PROPOSE), (occ≥3/unverified → PROPOSE), (scan-fail → PROPOSE-downgrade), (provenance-diverged → REJECT auto, PROPOSE), (skill not in allowed_kinds → PROPOSE).
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_repeated_request_gate.py -v`
- **Target:** All gate-matrix cases green; `create_and_bind_and_materialize` called exactly once in the AUTO case and zero times in all PROPOSE/REJECT cases (assert via mock).
- **Evidence:** 22-05 `must_haves.truths` specifies the exact branching conditions. The gate is designed as a pure function so unit-level mock testing is a direct measure of correctness.
- **Correlation with full metric:** HIGH — the gate is a pure function; unit tests exercise every branch path without needing live data.
- **Blind spots:** Mocked `create_and_bind_and_materialize` means atomic rollback behavior is not exercised here (covered by Phase 17 forge tests; deferred for full-pipeline confirmation in D1).
- **Validated:** No — awaiting deferred validation at phase-22-dogfood (D1).

### P3: Dedup and provenance guard tests

- **What:** `find_duplicate_binding` returns an existing binding (patch path) for near-duplicate candidates; `provenance_allows_overwrite` returns False when the on-disk sha256 diverges from `origin_hash`.
- **How:** Unit tests with a seeded in-memory DB: (a) insert a binding, then check a candidate with 90% name-cosine similarity → returns existing binding; (b) record an `origin_hash`, modify the file content, call `provenance_allows_overwrite` → False.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_skill_dedup_provenance.py -v`
- **Target:** All cases green; patch path exercised in (a); overwrite refused in (b).
- **Evidence:** 22-04 `must_haves.truths` specifies these exact behaviors. These are correctness tests for security-critical logic, not statistical proxies.
- **Correlation with full metric:** HIGH — correctness is binary; these tests directly falsify the known failure modes.
- **Blind spots:** Does not test the interaction between dedup and the downstream forge path (deferred to D1).
- **Validated:** No — awaiting deferred validation at phase-22-dogfood (D1).

### P4: Non-blocking proof — detector exception does not escape `on_session_complete`

- **What:** If `detect_for_session` raises any exception, `on_session_complete` continues normally; the exception is logged but not re-raised.
- **How:** Unit test that monkeypatches `detect_for_session` to raise `RuntimeError("simulated failure")`, then calls `on_session_complete` with a minimal fixture session. Assert: (a) no exception propagates; (b) the rest of `on_session_complete` (takeaway extraction path) still completes.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_repeated_request_detector.py -v -k "non_blocking"`
- **Target:** Test passes; no exception raised out of `on_session_complete`; log capture contains the error message.
- **Evidence:** 22-03 truth 3: "exceptions are caught and logged, never propagated into the completion event chain." This is a hard correctness requirement, not a quality metric.
- **Correlation with full metric:** HIGH — this is a binary correctness check with no approximation.
- **Blind spots:** Does not cover thread-safety or timing interactions in the actual daemon-thread dispatch (deferred to D1 live replay).
- **Validated:** No — awaiting deferred validation at phase-22-dogfood (D1).

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring integration or resources not available from unit tests alone.

### D1: Live dogfood — real session transcript replay — DEFER-22-01

- **What:** End-to-end pipeline confirmation: replay ≥3 real session transcripts containing a genuinely recurring request through `detect_for_session` → signal store → `evaluate_signal` → `create_and_bind_and_materialize` (AUTO path) or operator queue (PROPOSE path). Confirm the resulting skill is syntactically valid, correctly bound, and carries correct `origin_hash` provenance.
- **How:** Per 22-06-PLAN.md: select ≥3 real session_ids from the live DB that share a recurring request theme; invoke `detect_for_session` for each; verify signal `occurrence_count` reaches ≥3; trigger `evaluate_signal`; inspect the created skill file and binding record.
- **Why deferred:** Requires a live database with real session transcripts; the embedding backend must be operating against real text (not fixture strings); `create_and_bind_and_materialize` must be wired end-to-end. None of these conditions are satisfied at unit-test time.
- **Validates at:** phase-22-06-dogfood
- **Depends on:** Waves 1–3 all passing (22-01 through 22-05); live Agented instance with ≥3 sessions containing a shared recurring request; embedding service operational.
- **Target:** (a) One skill auto-created with `skill_created=1` on the signal row; OR one operator-queue entry at confidence 0.65 in the PROPOSE case. (b) Skill file on disk passes `scan_skill_content` (clean). (c) `origin_hash` recorded in `forge_origin`. (d) No exception propagated to `on_session_complete` caller.
- **Risk if unmet:** The detector or gate has a runtime bug not caught by fixtures — most likely a session-kind dispatch miss or an embedding-service error path. Fallback: revert to exact-hash-only matching (no cosine) and PROPOSE-only mode while the bug is diagnosed.
- **Fallback:** Disable auto path via `AGENTED_AUTONOMY=0`; confirm PROPOSE path still produces queue entries; file bug against the failing component.

### D2: Operator quality review of an auto-created skill — DEFER-22-02

- **What:** A human operator reviews the content of a skill auto-created by the pipeline and judges whether it is useful and correctly described.
- **How:** After D1 confirms a skill was auto-created: open the skill file; read the description and body; assess whether it correctly captures the recurring request pattern; compare to what a human would have written.
- **Why deferred:** Quality judgment is subjective and requires a real recurring request pattern — not reproducible with fixtures.
- **Validates at:** phase-22-06-dogfood (manual, after D1 passes)
- **Depends on:** D1 completing successfully with an AUTO-path skill.
- **Target:** Operator assesses the skill as "useful and correctly scoped" (binary pass/fail judgment). If PROPOSE path only (no AUTO), operator assesses that the queue entry contains sufficient information to approve or reject.
- **Risk if unmet:** The LLM-generated skill description is too generic or incorrect — the gate thresholds are right but the skill synthesis quality needs improvement. This would require prompt tuning in the evolver's `_PROMPT_TEMPLATE` (REQ-26 scope).
- **Fallback:** Lower auto-apply confidence requirement; route more cases to PROPOSE for human review.

---

## Ablation Plan

### A1: Embedding-disabled fallback

- **Condition:** Run the detector with `embed_text` monkeypatched to return `None` (simulates embedding service outage).
- **Expected impact:** Detector falls back to exact normalized-hash matching. No crash; paraphrase variants that differ in wording are treated as separate signals (expected degradation); verbatim repeats still coalesce.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_repeated_request_detector.py -v -k "embed_disabled"`
- **Evidence:** 22-03 truth 2: "with no embedding backend it falls back to exact normalized-hash match (no crash)."

### A2: Scan-fail downgrade

- **Condition:** Feed a scan-failing payload through the gate with occurrence_count=5 and verified_success_count=2 (would otherwise auto-apply).
- **Expected impact:** Gate downgrades to PROPOSE (confidence 0.65), never calls `create_and_bind_and_materialize`.
- **Command:** Covered within `tests/test_repeated_request_gate.py` gate-matrix parametrize (included in P2).
- **Evidence:** 22-05 truth: "an unsafe or provenance-diverged signal REJECTS auto and downgrades to propose."

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| pytest full suite | Backend unit tests pre-phase | 0 new failures | CLAUDE.md house gate |
| frontend test:run | Vue/Vitest suite | 0 new failures (7 known baseline failures permitted) | CLAUDE.md house gate |
| `just build` | vue-tsc + vite | Exit 0 | CLAUDE.md house gate |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_repeated_request_signals_db.py   (22-01, S4)
backend/tests/test_build_harness_session_kinds.py   (22-02, S5)
backend/tests/test_repeated_request_detector.py     (22-03, P1, P4, A1)
backend/tests/test_skill_safety_scanner.py          (22-04, S6)
backend/tests/test_skill_dedup_provenance.py        (22-04, P3)
backend/tests/test_repeated_request_gate.py         (22-05, P2, A2)
backend/tests/fixtures/repeated_request_transcripts.py  (fixture data)
```

**How to run targeted suite (recommended — avoids full-suite hang):**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest \
  tests/test_repeated_request_signals_db.py \
  tests/test_build_harness_session_kinds.py \
  tests/test_repeated_request_detector.py \
  tests/test_skill_safety_scanner.py \
  tests/test_skill_dedup_provenance.py \
  tests/test_repeated_request_gate.py \
  -v --tb=short
```

**How to run ruff:**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check . && uv run ruff check .
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1 — Ruff | | | |
| S2 — Import smoke | | | |
| S3 — DDL / fresh schema | | | |
| S4 — Signal store tests (22-01) | | | |
| S5 — Consistency tests (22-02) | | | |
| S6 — Safety scanner tests (22-04) | | | |
| S7 — House-gate build | | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1 — Cosine precision | 1 signal / occ=3 for paraphrases | | | |
| P2 — Gate matrix | All branches correct | | | |
| P3 — Dedup + provenance | patch path + refuse overwrite | | | |
| P4 — Non-blocking | No exception propagation | | | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1 — embed disabled | Exact-hash fallback, no crash | | |
| A2 — scan-fail downgrade | PROPOSE only, no auto-apply | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-22-01 | Live transcript replay (E2E) | PENDING | phase-22-06-dogfood |
| DEFER-22-02 | Operator skill quality review | PENDING | phase-22-06-dogfood (manual) |

---

## Success Criterion Coverage

| Success Criterion | Covered By | Level |
|-------------------|------------|-------|
| 1 — Signal store UPSERT invariants | S4 (test_repeated_request_signals_db) | L1 |
| 2 — `_build_harness_session` normalization | S5 (test_build_harness_session_kinds) | L1 |
| 3 — Detector on all 5 session kinds, cosine ≥ 0.83, non-blocking | P1, P4, A1 | L2 |
| 4 — Safety scanner, dedup, provenance guard | S6, P3 | L1 + L2 |
| 5 — Hybrid gate matrix (auto/propose/reject) + per-project policy | P2, A2 | L2 |
| 6 — Live dogfood replay ≥3 real transcripts, operator review | D1, D2 | L3 |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: adequate — 7 checks cover import, DDL, and all per-plan unit test suites; each has an exact command.
- Proxy metrics: well-evidenced — all four proxies trace directly to phase success criteria or explicit `must_haves.truths` in the plan files; none are invented. Correlation is HIGH for P2/P3/P4 (pure-function correctness), HIGH for P1 (same embedding backend as production).
- Deferred coverage: appropriate — the two deferred items require real data and human judgment; their scope is precisely bounded and both resolve at the 22-06 dogfood phase.

**What this evaluation CAN tell us:**
- Whether every UPSERT invariant holds under the full test matrix.
- Whether the gate is a correct pure function for all branching combinations.
- Whether the safety scanner rejects all known attack classes.
- Whether the detector is non-blocking under simulated failure.

**What this evaluation CANNOT tell us:**
- Whether the pipeline produces quality skills from real-world recurring requests (resolved at D1/D2, phase-22-06).
- Whether embedding-based cosine matching generalizes beyond the hand-crafted fixture paraphrases (partially addressed in D1 by using real transcripts).
- Whether the auto-apply rate in production is appropriate (too high = noise; too low = the loop never fires) — this is a product-tuning question outside the phase scope.

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-13*
