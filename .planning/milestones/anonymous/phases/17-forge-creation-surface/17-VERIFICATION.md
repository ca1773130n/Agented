---
phase: 17-forge-creation-surface
verified: 2026-06-12T20:06:41Z
status: passed
score:
  level_1: 6/7 sanity checks passed (S7 just build is a known pre-existing TS error, recorded as external issue)
  level_2: 11/11 proxy metrics met
  level_3: 2/2 deferred (tracked for phase-21-integration)
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
deferred_validations:
  - description: "End-to-end forge/create against a real git-tracked project workspace"
    metric: "HTTP 201 + file on disk + manifest updated + 4 renderers compile"
    target: "all pass"
    depends_on: "phase-21-integration"
    tracked_in: "STATE.md (DEFER-17-01)"
  - description: "Live session-completion auto-import dogfood (session_kind gate fires)"
    metric: "imported primitive + forge_origin sha256 + idempotent second run"
    target: "all pass"
    depends_on: "phase-21-integration"
    tracked_in: "STATE.md (DEFER-17-02)"
external_issues:
  - id: "EXT-just-build-ts"
    description: "just build fails with a pre-existing vue-tsc TypeScript error unrelated to phase 17 (frontend untouched this phase)"
    scope: "external / pre-existing — NOT a phase-17 gap"
    evidence: "Phase 17 is backend-only; no frontend files modified. The TS error reproduces on the pre-phase baseline."
human_verification: []
---

# Phase 17: Forge Creation Surface Verification Report

**Phase Goal:** Extend the forge primitive system — add the `subagent` kind end-to-end (DB → materialization → renderer → route), an atomic create endpoint with compensating cleanup, cross-kind forge bundles, the forge-creator seed, and session-completion auto-import with provenance.
**Verified:** 2026-06-12T20:06:41Z
**Status:** passed
**Re-verification:** No — initial verification

## Verification Summary by Tier

### Level 1: Sanity Checks

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| S1 | ruff format + lint on touched backend files | PASS | Exit 0, no output |
| S2 | Python import smoke — 6 new modules | PASS | `OK` |
| S3 | both kind registries contain 'subagent' | PASS | `OK` |
| S4 | DB schema smoke — 4 new tables created | PASS | `OK` |
| S5 | 5 SKILL.md files parse as valid frontmatter | PASS | `OK` |
| S6 | forge/create route registered | PASS | `OK` |
| S7 | just build (frontend regression guard) | FAIL (external) | Pre-existing vue-tsc TS error, frontend untouched this phase — recorded as EXT-just-build-ts, not a phase-17 gap |

**Level 1 Score:** 6/7 passed (S7 attributed to external pre-existing TS error)

### Level 2: Proxy Metrics

| # | Metric | Target | Status |
|---|--------|--------|--------|
| P1 | replace_for_project propagation round-trip | all pass | PASS |
| P2 | subagent CRUD + kind registry | all pass | PASS |
| P3 | subagent golden materialization | all pass | PASS |
| P4 | forge_bundles cross-kind + skill_sets unchanged | all pass | PASS |
| P5 | 4-backend renderer goldens | all pass (4 harnesses) | PASS |
| P6 | subagent in ContextBundle | all pass | PASS |
| P7 | atomic create + no-orphan (3 sub-cases) + bundle-bind | all pass | PASS |
| P8 | forge-creator seed idempotence | all pass | PASS |
| P9 | session import diff/gate/provenance | all pass | PASS |
| P10 | backend pytest house gate (targeted) | 0 new failures | PASS |
| P11 | frontend no-new-failures | <=7 failures | PASS |

**Level 2 Score:** 11/11 met target

### Level 3: Deferred Validations

| # | Validation | Depends On | Status |
|---|-----------|------------|--------|
| DEFER-17-01 | End-to-end forge/create real workspace | phase-21-integration | DEFERRED |
| DEFER-17-02 | Live session auto-import dogfood | phase-21-integration | DEFERRED |

**Level 3:** 2 items tracked for phase-21-integration

## Goal Achievement — Per Success Criterion

| # | Success Criterion | Proxy Test(s) | Status | Evidence |
|---|-------------------|---------------|--------|----------|
| 1 | subagent valid forge kind (DB + materialization + renderer + compiler) | P2, P3, P5, P6 | VERIFIED | P2/P3/P5/P6 all PASS; renderer goldens pass across all 4 harnesses |
| 2 | atomic create with compensating cleanup (no orphans) | P7 | VERIFIED | P7 PASS — create-success + no-orphan at bind failure + no-orphan at materialize failure |
| 3 | replace_for_project preserves propagation columns | P1 | VERIFIED | P1 PASS — round-trip preserves source_scope, source_shared_binding_id, fingerprint, conflict_policy |
| 4 | forge_bundles + bundle-bind; skill_sets unchanged | P4, P7 | VERIFIED | P4 PASS (cross-kind + skill_sets DDL guard); P7 bundle-bind sub-case PASS |
| 5 | forge-creator seed + auto-import with provenance | P8, P9 | VERIFIED | P8 idempotence PASS; P9 gate/provenance PASS |
| 6 | House gates pass | S7, P10, P11 | VERIFIED (with external note) | P10 + P11 PASS; S7 just build fails on pre-existing TS error (external, frontend untouched) |

**Goal Score:** 6/6 success criteria verified at proxy level

## External Issues (Not Phase-17 Gaps)

| ID | Issue | Scope | Rationale |
|----|-------|-------|-----------|
| EXT-just-build-ts | `just build` fails with a pre-existing vue-tsc TypeScript error | external / pre-existing | Phase 17 is backend-only; no frontend files modified. The error is not introduced by this phase and reproduces on the pre-phase baseline. Recorded so phase-21 / a frontend phase can address it; does NOT block the phase-17 proxy verdict. |

## Reflection

| Field | Value |
|-------|-------|
| hypothesis | Extending the forge primitive system with a subagent kind, atomic create, cross-kind bundles, seed, and auto-import can be delivered behaviorally-correct at proxy tier without touching the frontend. |
| predicted_outcome | All sanity + proxy tests pass; full-workspace + live-session validation deferred to integration. |
| actual_outcome | All 11 proxy tests and 6/7 sanity checks pass (S7 is a pre-existing frontend TS error, external to this backend-only phase); both Tier-3 items tracked for phase-21. |
| verdict | confirmed |
| evidence | P1-P11 all PASS; S7 attributed to EXT-just-build-ts (frontend untouched); DEFER-17-01/02 tracked; 6/6 success criteria verified |

---

_Verified: 2026-06-12T20:06:41Z_
_Verifier: Claude (grd-verifier)_
_Verification levels applied: Level 1 (sanity), Level 2 (proxy), Level 3 (deferred)_
