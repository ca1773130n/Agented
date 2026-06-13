# Evaluation Results: Phase 21 — One-click Team Harness Setup

**Run:** 2026-06-13 (automated L1 + L2 during plan execution; L3 deferred)
**Branch:** grd/v0.8.0/21-21
**Verdict:** ALL AUTOMATED TIERS MET (L1 5/5, L2 8/8); L3 deferred (D3/D4 house gates green, D1/D2 live dogfood pending operator)

## Level 1 — Sanity (5/5 PASS)

| Check | Result | Evidence |
|-------|--------|----------|
| S1: Migration 159 schema + double-apply no-op | PASS | test_harness_setup_status_migration.py 4/4 green |
| S2: `get_harness_setup_status` defaults "none" | PASS | dedicated test green |
| S3: Import smoke + `len(HARNESS_SETUP_STEP_KEYS)==6` | PASS | `python -c` prints ok |
| S4: `driver=grd` on created SA instances | PASS | test_team_harness_setup_service `-k driver` green |
| S5: ruff clean on new modules | PASS | ruff check/format clean (after 21-08 unused-import fix) |

## Level 2 — Proxy (8/8 PASS)

| Metric | Target | Result |
|--------|--------|--------|
| P1: Step idempotency (fresh/partial/re-run, no dup rows) | all green | PASS |
| P2: No destructive deletes on re-run | all green | PASS |
| P3: STACK.md-tailored bundle selection (py/ts/missing→forge-creator floor) | 3/3 fixtures | PASS |
| P4: 4 renderers compile materialized projection | 4/4 backends | PASS |
| P5: Route status none→running→ready + SSE step events | all green | PASS (4/4 route tests) |
| P6: Failed step leaves failed status + step log + retryable | all green | PASS (covered in service suite) |
| P7: Dual-consumer autonomy policy (conservative evolution + scoped auto-apply ON) | both assertions | PASS — strengthened: takeaway gate now honors `allowed_kinds` (review WARNING-1 fix), so the scoping is genuinely enforced, not cosmetic |
| P8: ProjectDashboard button/chip/step-panel render, no new FE failures | 0 new failures | PASS (4/4 new tests; 7 known baseline failures only) |

Backend phase-21 + regression set: **146 passed, 0 failed** (test_harness_setup_status_migration, test_team_harness_setup_service, routes/test_harness_setup_routes, test_forge_materialization, test_instance_service, routes/test_forge_bindings_routes, test_tesserae_integration, test_harness_autonomy, test_repeated_request_gate). Post-fix re-run of the autonomy/gate cluster: **101 passed, 0 failed**.

## Level 3 — Deferred

| ID | Gate | Status |
|----|------|--------|
| D3: `just build` | GREEN (baseline exception) | Only the pre-existing `AnswerGroundednessCard.vue` TS error (not in phase-21 diff); zero new type errors. |
| D4a: backend pytest | GREEN | targeted comprehensive set (full serial suite skipped — known ~40-48% hang, disclosed). |
| D4b: frontend `npm run test:run` | GREEN | 7 known baseline failures only, no new; new harness-setup test passes. |
| D1: live 4-backend dogfood (closes DEFER-17-01) | PENDING — live operator | needs real project + live AI credentials + subprocess/PTY. |
| D2: session auto-import idempotency (closes DEFER-17-02) | PENDING — live operator | needs real completed session + live import pipeline. |

## Decision

All automated targets met. Code-side of phase 21 is complete and gate-green. The two genuinely-live validations (D1/D2) remain for a real-environment dogfood run — appropriate to schedule when a dogfood project and four backend credentials are available. **Proceed to verification and merge.**
