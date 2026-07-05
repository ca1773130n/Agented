# Project State

## Project Reference

See: .planning/PROJECT.md
**Core value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard
**Current version:** v0.10.0 (pyproject + package.json bumped at the v0.10.0 close-out; git tag v0.10.0)

## Current Position

**No active milestone.** Latest shipped: **v0.10.0 — Competitive Hardening**
(2026-07-04, tag v0.10.0), archived at `.planning/milestones/v0.10.0/`
(STATE/ROADMAP/REQUIREMENTS). All 4 phases (23–26) merged, each codex-reviewed
until green (fail-closed everywhere):

- **#286** Phase 23 — stackable policy / governance engine (SESSION→team→server, DENY short-circuit; enforced at all 14 autonomous launch sites; 5 codex rounds)
- **#287** Phase 24 — OS-level harness sandboxing + deny-by-default egress (bwrap Linux / seatbelt macOS; opt-in `AGENTED_SANDBOX`; 4 codex rounds)
- **#288** / **#290** Phase 25 — real-time multi-user collaboration (live-share, co-drive, session fork, optional OIDC SSO; 3 codex rounds)
- **#289** Phase 26 — deployment & extensibility (experimental Postgres alongside SQLite, container + self-update distribution, declarative-YAML agent/team authoring, optional server/runner key-isolation). Built by the parallel `/remote-control` process; final merge + the curl|bash install-RCE and YAML-body-cap fixes taken over here.

Post-v0.10.0 (PR-driven, no formal milestone): Tesserae **v0.14.0** released +
wired as the daily/weekly **Activity Summary** page (#302), tesserae argv-injection
hardening (#303), and page-consistency + Tesserae-auto-resolve UX fixes (#298–#301).

**Next command:** `/grd:new-milestone` to scope the next milestone — or continue
PR-driven as with the post-v0.10.0 items above.

## Shipped milestone — v0.8.0 (Team Harness & Self-Improvement)

**SHIPPED 2026-06-13** — all 6 phases (17–22) landed on main and are archived at
`.planning/milestones/v0.8.0/` (see MILESTONES.md). This supersedes the earlier
"paused / phase 21 in progress" note, which was stale mid-development state.

Delivered here and **live today**: the **one-click team-harness setup** (phase 21
— a 6-step idempotent orchestrator: `grd_init → team_topology → bundle_binding →
tesserae_enable → default_policies → materialize_compile`), reachable from the
Project Dashboard's **Set up harness** button (`POST /admin/grd/{project_id}/
harness-setup`, live SSE step progress; retry resumes from the failed step, never
rolls back). Also shipped: the Forge creation surface, GRD-as-default-driver + GRD
frontend wiring, Sketch→primitive routing, repeated-request→auto-skill mining, and
the eval-gated, git-reversible self-improvement "life-harness" loop.

## Session Continuity

Last milestone: **v0.10.0 shipped 2026-07-04**. No active GRD phase in progress.
Recent work is PR-driven (see MILESTONES.md / git log) — most recently the Tesserae
v0.14.0 Activity Summary page and the tesserae argv-injection fix.
Resume file: None
