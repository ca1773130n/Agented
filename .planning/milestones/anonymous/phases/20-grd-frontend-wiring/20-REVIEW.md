---
phase: 20-grd-frontend-wiring
verdict: passed
severity_gate: blocker
reviewed_by: orchestrator (direct diff review — grd-code-reviewer subagent truncated; fell back to inline review of security-critical surfaces)
date: 2026-06-13
---

# Phase 20 Code Review

**Verdict: PASSED — no blockers.** Reviewed `git diff main..HEAD` (25 commits) with focus on the security- and correctness-critical surfaces; the bulk of the diff is templated Vue components + 4-locale catalog keys whose parity is machine-verified (diff 0).

## Focused findings

| Area | Check | Result |
|------|-------|--------|
| Prompt injection (REQ-14) | `grd_research` handler must not let a research question break out of the `/grd:research` invocation | **Safe** — `json.dumps(question)` and `json.dumps(thread_id)` framing (execution_type_handler.py:865/867), mirroring the phase-19 grd_chat hardening verbatim. `grd_chat` path untouched. |
| Admin auth (REQ-16) | harness-evolution routes are admin-gated | **Correct** — `grdHarness.ts` routes Group B calls to the `/admin` base path; the global middleware (X-API-Key + bearer/cookie + CSRF) gates `/admin`, so routing IS the auth. Documented in-module. |
| Destructive action (REQ-16) | round revert must be confirm-guarded | **Correct** — `RoundDetail.vue` two-step: "Revert" only arms `confirmingRevert`; only the explicit "Confirm revert" calls `grdHarnessApi.revertRound`. Asserted by `autonomy-rounds-forge.test.ts`. |
| SSE (REQ-15) | research streaming reuses the authenticated event-source path | **Correct** — `useResearchSession.ts` → `createAuthenticatedEventSource`; routes reuse the generic `/sessions/{id}/output` SSE. |
| Markdown rendering | must avoid the broken `MarkdownContent.vue` | **Correct** — `renderMarkdown()` (marked + DOMPurify) used instead. |
| Missing-dir robustness | `list_threads` for a project with no `.planning/research/threads/` | **Correct** — returns `[]`, no crash. |
| i18n parity (REQ-18) | en/ko/ja/zh key-identical | **Correct** — `i18n-parity.mjs` diff 0. |
| Type safety | no NEW vue-tsc errors | **Correct** — 20-06 fixed the 15 `harness-panels.test.ts` TS2345s introduced by 20-04 (mis-classified by 20-05 as baseline). Remaining error is pre-existing AnswerGroundednessCard (PR #212). |

## Notes (non-blocking)

- 20-03/20-04 modify 15/18 files each, but the implementation surface is thin templated components + the 4 mandatory locale files; scoping is atomic and tests cover each.
- TDD honored for the manifest (RED commit `52f90f9` then GREEN).

No blocker- or warning-severity issues. Clear to merge.
