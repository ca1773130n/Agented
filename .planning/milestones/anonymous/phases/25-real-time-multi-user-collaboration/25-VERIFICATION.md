# Verification Report: Phase 25 — Real-time Multi-user Collaboration

**Run:** 2026-07-02
**Branch / PR:** `grd/v0.10.0/25-25` / #288 (0 behind `main`, +11 ahead)
**Method:** Local execution of the `25-EVAL.md` gates (no CI test checks exist on the PR — only GitGuardian). Full serial pytest is skipped per CLAUDE.md (known ~40–48% hang); a targeted Phase-25 file set + build + frontend suite is substituted.

## Verdict: ✅ VERIFIED — house gates green

Feature-complete, security-hardened, and behaviorally verified. Remaining merge-blockers are **process, not correctness** (commit the format fix; obtain review/approval).

## Level 1 — Sanity

| ID | Check | Result |
|----|-------|--------|
| S1 | `ruff format --check` (Phase-25 Python, 29 files) | ✅ PASS — after reformatting 2 Phase-25 files (`app/db/migrations/v08_features.py`, `app_litestar/routes/streams.py`) |
| S2 | `just build` (vue-tsc + vite) | ✅ PASS — built in 47.27s, 0 type errors (only the standard >500 kB chunk-size warning) |
| S8 | Frontend baseline (`npm run test:run`) | ✅ PASS — **7 failed / 1683 passed (1690)**; all 7 in known-baseline areas (MarkdownContent×4, WorkingMemoryView, RateLimitGauge, useTourMachine). **No new failures.** |

> Repo-wide `ruff format` still flags 4 **pre-existing** files (`test_competitor_intel_routes`, `test_migration_171_competitor_intel`, `test_migration_176_policies`, `test_policy_builtins`) — Phase 23/24 code, out of Phase-25 scope.

## Level 2 — Behavioral proxy (criteria 1–6, 8)

Backend targeted run: **✅ 67 passed, 0 failed** (the "I/O operation on closed file" lines are teardown logging noise, not failures).

| Criterion | Test file | Result |
|-----------|-----------|--------|
| 1 — 2nd client attaches by token, read-only deltas | `test_session_shares.py` | ✅ |
| 2 — non-owner without token → 404 on stream | `test_stream_project_session_gate.py` | ✅ |
| 3 — DENY blocks / ASK pauses / ALLOW proceeds *(was GATED)* | `test_co_drive.py` | ✅ |
| 4 — parent byte-identical after fork; child diverges | `test_session_fork.py` | ✅ |
| 5 — OIDC callback mints cookie; X-API-Key path unchanged | `test_oidc_auth.py` | ✅ |
| 6 — two-client live-share + co-drive e2e *(was GATED)* | `test_live_share_e2e.py` | ✅ |
| (hardening) session `created_by` stamp/backfill | `test_session_owner_stamp.py` | ✅ |
| 8 — 4-locale parity (en/ko/ja/zh) | `test_phase25_locale_parity.py` | ✅ |

## Phase-23 dependency gate (co-drive) — RESOLVED

The EVAL's planned symbol names (`enforce_action`, `PolicyContext`, `PolicyDeniedError`) do **not** match the shipped API. Actual gate: `app/services/policy_service.py` exposes **`PolicyService`** + **`PolicyDenied`**; `test_co_drive.py` imports those (+ `SessionSharingService`, `CoDriveScopeError`) and all imports resolve. The two previously-GATED Tier-2 items (criteria 3 & 6) are now **un-gated and green**.

## Level 3 — Deferred (NOT run)

Real OIDC-provider round-trip · real multi-browser UX · ASK round-trip latency · full serial pytest suite.

## Follow-ups before merge

1. **Commit the format fix** — 2 Phase-25 files were reformatted during this run and are currently uncommitted in the p25 worktree.
2. **Review/approval** — PR #288 has no `reviewDecision` yet.
3. (Optional) clear the 4 pre-existing Phase 23/24 ruff-format failures separately.
