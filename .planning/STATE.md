# Project State

## Project Reference

See: .planning/PROJECT.md
**Core value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard
**Current version:** v0.7.98 (pyproject); informal v0.9.0 competitive-intel shipped via PRs

## Current Position

**Active milestone:** v0.10.0 — Competitive Hardening (omnigent lessons),
started 2026-06-30. **Roadmap created 2026-06-30** — 4 phases (23–26),
15 requirements (REQ-27..41) mapped. Basis: the verified competitive analysis
`docs/research/omnigent-vs-agented.md` (+ `.ko.md`). PR-per-phase +
codex-review-until-green cadence.

Phase: 23 of 26 (Stackable policy / governance engine) — **✅ COMPLETE & MERGED** (PR #286, main 3cec4976c3, 2026-07-01)
Status: Full engine shipped — policies store (migration 176), PolicyEvaluator (server→team→session,
session-first, DENY short-circuit), builtins (cost_budget hard/soft, max_tool_calls, ask_on_os_tools,
enforce_sandbox), enforcement at ALL 14 autonomous harness/eval/generation launch sites via one shared
`PolicyService.enforce_launch`, `/admin/policies` CRUD (admin-gated) + decision endpoint, PolicyManagement
UI + PolicyAskCard (SSE-wired, persist+replay), e2e. FAIL-CLOSED everywhere (malformed params, DB error,
unknown effects). Hardened over **5 Codex rounds** (fixed 2 fail-opens, 14 ungated launch paths, a
stale-approval leak, a broken ASK flow, a TTL leak). Accepted follow-ups: create_session-ASK async
refactor (fail-closed), setup_execution operator-command gate.

Phase: 24 of 26 (OS-level harness sandboxing + egress) — **✅ COMPLETE & MERGED** (PR #287, main efb2efa548, 2026-07-02)
Status: sandbox_wrap (bwrap Linux / seatbelt macOS, realpath-canonicalized credential denies, validated config-dir
allows), deny-by-default egress proxy (fail-closed on non-readiness), wrap→enforce at ALL launch sites incl. the
project_session_manager chokepoint, cloud_sandbox_runner (goal-loop→local fallback, no ungoverned stub), escape
tests (live seatbelt: secret-read + non-allowlisted-connect blocked), docs/sandboxing.md(+.ko). Hardened over
**4 Codex rounds** (fixed a globally-readable sandbox, --share-net proxy bypass, egress fail-open+leak, 6+
wrap-without-enforce paths, ordering bug, cloud shell-injection, config-dir re-exposure, realpath/symlink escapes).
Opt-in via AGENTED_SANDBOX (default off; require_sandbox + off → fail closed). Follow-ups: bwrap netns↔proxy bridge
(Linux egress currently fail-closed-offline), live E2B/Modal creds.

Phase: 25 of 26 (Real-time multi-user collaboration) — **✅ COMPLETE & MERGED** (PR #288, main 4969a39dc0, 2026-07-02)
Status: live-share (scoped URL share tokens, hashed-at-rest, read-only multi-attach, owner-gated stream),
co-drive (teammate message runs against the operator's session, policy-checked via `PolicyService`/`PolicyDenied`
+ CSRF), session fork (fork a conversation onto a separate independent run, ownership-gated), optional OIDC SSO
(authlib code-flow alongside the unchanged X-API-Key path), 4-locale parity. Security-hardened post-implementation
(token hashing at rest, ownership gates on mint/fork/revoke, fail-CLOSED on unknown session owner + created_by
backfill, co-drive CSRF, real cost/tool policy context). Verified locally (CI runs only GitGuardian): build ✅ 0
type errors, backend 67 passed / 0 failed across 8 phase-25 files, frontend 7 known-baseline failures / no new
(see `25-VERIFICATION.md`). Note: per-plan SUMMARY.md files (25-01..05) were not committed, so grd-tools
auto-routing undercounts summaries and mis-reports current phase — position tracked here.

Next: **Phase 26** (deployment & extensibility ergonomics — first-class Postgres alongside SQLite, container
image + one-click/self-update distribution, declarative-YAML agent/team authoring, optional server/runner
key-isolation split) — plans 26-01..04 + RESEARCH + EVAL ready; independent of phases 23–25.

Progress: [###############-----] 75% (3 of 4 phases complete — Phases 23+24+25 merged)

**Decisions (23-01):** PolicyVerdict = `{decision, policy_id, kind, reason, scope}`;
SESSION-first stacking with first-DENY short-circuit (SC1 proven); default ALLOW has
scope=None and explicit ALLOW rows never short-circuit; `_BUILTINS` dispatch seam left
for 23-02; `PolicyDenied` exported for 23-03 enforcement.

**Decisions (23-02):** Four builtin evaluators on `_BUILTINS` dispatch; signature is
`(row, action) -> (decision, reason)` (matches 23-01 `_eval_row`, not plan's `(params,
action)`); cost_budget reuses budget_service hard/soft semantics but stays pure (spend on
action ctx); enforce_sandbox INERT until Phase 24 (verdict only, no sandbox); zero/absent
caps disable rather than deny. Action-ctx keys for 23-03: `total_cost_usd`, `tool_calls`,
`kind`, `sandboxed`.

**Phase queue:** 23 Policy/governance engine (REQ-27..30) → 24 OS-level harness
sandboxing + egress (REQ-31..33) → 25 Real-time multi-user collaboration
(REQ-34..37) → 26 Deployment & extensibility ergonomics (REQ-38..41).

**Next command:** `/grd:discuss-phase 23` (or `/grd:plan-phase 23` to plan directly)

## Paused milestone

**v0.8.0 — Team Harness & Self-Improvement** (phases 17–22) is **paused** and
archived at `.planning/milestones/v0.8.0/` (ROADMAP/REQUIREMENTS/STATE). Open
REQs 01–13 and 19–21 carry forward; resume after v0.10.0 or interleave a phase
if a v0.8.0 item becomes urgent. Phases 17, 19, 20, 22 landed on main via PRs;
phase 21 (one-click team harness setup) was in progress at 21-07.

## Session Continuity

Last session: 2026-06-30 — Completed 23-02-PLAN.md
Stopped at: Completed 23-01-PLAN.md (policy engine primitive — migration 176 +
PolicyService.evaluate stacking/short-circuit, TDD, 15 tests green). Next plan in
phase 23 (23-02 builtins) or continue `/grd:execute-phase 23`.
Resume file: None
