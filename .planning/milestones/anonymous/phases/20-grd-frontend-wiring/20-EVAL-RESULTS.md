---
phase: 20-grd-frontend-wiring
eval_run: 2026-06-13
tiers_run: [1, 2]
tier_3: deferred
verdict: targets met
---

# Phase 20 Eval Results

Tier 1 (sanity) and Tier 2 (proxy) executed via the 20-06 house gate and re-confirmed by the orchestrator. Tier 3 (live SSE / running-server integration) deferred per 20-EVAL D1-D3 (no `gd` binary / live server in this environment).

| Tier | Metric | Target | Actual | Status |
|------|--------|--------|--------|--------|
| 1 | vue-tsc on phase-20 files | 0 new errors | 0 new (only pre-existing PR#212 AnswerGroundednessCard) | ✓ |
| 1 | ruff format (backend touched files) | clean | clean | ✓ |
| 1 | backend handler/route tests | 0 fail | 27 passed (research) + 88 (bridge/cli/litestar-grd) | ✓ |
| 2 | i18n parity diff (en/ko/ja/zh) | 0 | 0 | ✓ |
| 2 | frontend test:run | no NEW failures | 1485 passed / 7 known baseline / 0 new | ✓ |
| 2 | GRD routes reachable in UI | 16 | 16 (27 grdHarnessApi methods) | ✓ |
| 2 | `/grd:` command groups in manifest | ≥6 | 6 | ✓ |

**Verdict: targets met.** Proceed to phase completion.
