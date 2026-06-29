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

Phase: 23 of 26 (Stackable policy / governance engine) — **not started (planning)**
Status: Milestone defined; no phase planned yet.

Progress: [----------] 0% (0 of 4 phases complete)

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

Last session: 2026-06-30
Stopped at: Executed phase 24 plan 24-01 (OS-level sandbox-command-prefix builder)
on branch grd/v0.10.0/24-24. Created backend/app/services/sandbox_wrap.py +
test_sandbox_wrap.py (9 tests green, ruff clean). 24-01-SUMMARY.md written.
Next: 24-02 (local egress proxy) / 24-03 (wire prefix into Popen chokepoint).
Resume file: None

## Decisions (Phase 24)

- 24-01: Sandbox isolation is an argv-PREFIX builder prepended at the existing
  Popen chokepoint (bwrap on Linux, sandbox-exec/SBPL on macOS) — NOT a new
  launcher. Stdlib only, no new deps.
- 24-01: Detection probe-runs the primitive (not just shutil.which) and degrades
  to (cmd, False)+warning when missing/unusable (Pitfall 2); never raises so the
  Phase-23 enforce_sandbox policy (24-03) decides launch-vs-refuse.
- 24-01: Env-var egress (HTTPS_PROXY) is best-effort; airtight netns+nftables
  egress is the deferred upgrade (Pitfall 3).
