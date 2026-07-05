# Changelog

All notable changes to Agented. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). The full planning trail lives in
[.planning/MILESTONES.md](.planning/MILESTONES.md).

## [Unreleased]

### Added
- Daily/weekly **Activity Summary** page (Observability) — "what you did each
  day/week across every project", powered by Tesserae **v0.14.0**'s
  `tesserae summary`. (#302)

### Changed
- Page-consistency pass — uniform title/subtitle typography (18px/13px via the
  shared `PageHeader`) and horizontal margins across every content page. (#299–#301)
- Tesserae workspace **auto-resolves** on activate — no more path prompt. (#298)

### Security
- Closed **argv flag-smuggling** in the Tesserae subprocess calls
  (activity-summary inputs + the `ask`/`context` question positional). (#303)

## [0.10.0] — 2026-07-04 — Competitive Hardening

Hardening driven by the omnigent competitive analysis; 4 phases (23–26), PRs
#286–290, each codex-reviewed-until-green and **fail-closed** by design.

### Added
- **Stackable policy / governance engine** — server→team→session stacking with
  DENY short-circuit; builtins (cost budgets, tool-call caps, ask-on-OS-tools,
  enforce-sandbox); enforced at all 14 autonomous launch sites; `/admin/policies`
  CRUD + PolicyManagement UI. (#286)
- **OS-level harness sandboxing + deny-by-default egress** — bwrap (Linux) /
  seatbelt (macOS), credential denies, opt-in via `AGENTED_SANDBOX`. (#287)
- **Real-time multi-user collaboration** — live-share (hashed-at-rest scoped
  tokens, read-only multi-attach), co-drive, session fork, optional OIDC SSO
  alongside the X-API-Key path. (#288, #290)
- **Deployment & extensibility** — experimental Postgres adapter alongside
  SQLite (`DATABASE_URL`), container image + self-update + Render blueprint,
  declarative-YAML agent/team authoring, optional server/runner LLM-key
  isolation (`AGENTED_SERVER_NO_LLM_KEYS`). (#289)

### Fixed
- Repaired 7 backend-suite drift failures surfaced once the CI hang was fixed
  (#295) — stale count pins / mocks that lagged the evolved code, not regressions.

### Security
- Fail-closed across the new policy / sandbox / collaboration surfaces; closed a
  `curl | bash` install RCE and capped YAML-import body size. (#289)

## [0.9.0] — 2026-06-20 — Competitive Intelligence

PR-driven (#240–248), each codex-reviewed-until-green.

### Added
- Competitor **monitor** MVP, autonomous **discovery**, source adapters (arXiv +
  Greenhouse/Lever job boards), **strategy → HITL → gated-materialize** (legal
  gate + inert auto-implement), human-gated auto-implement in a worktree
  goal-loop, and pluggable market-lookalikes. Full monitor → discover → source →
  strategize → implement arc.

## [0.8.0] — 2026-06-13 — Team Harness & Self-Improvement

6 phases (17–22).

### Added
- **Forge creation surface** (skill / rule / hook / command / subagent creators +
  session-completion auto-import) and Sketch → primitive routing.
- **GRD as the default execution driver**, plus GRD frontend wiring (autoresearch
  page, life-harness completion UI, `/grd:` command bar).
- **One-click team-harness setup** — a 6-step per-project orchestrator.
- Repeated-request → **auto-skill mining**.
- The eval-gated, git-reversible **self-improvement "life-harness" loop**.

## Earlier

Condensed — see [.planning/MILESTONES.md](.planning/MILESTONES.md) for detail.

- **v0.7.0 – v0.7.98** (2026-04 → 2026-05-21) — rapid PR-driven wave.
- **v0.6.x** (2026-04) — architecture hardening; the **unified loop layer**
  (`LoopSpec` + a single goal-loop executor).
- **v0.5.0** (2026-03-23) + the **v0.5.x** patch wave — production-level
  onboarding experience.
- **v0.2.0** (2026-03-05) — miscellaneous.
- **v0.1.0** (2026-02) — initial skeleton.
