# Milestones

Chronological summary of shipped milestones. Per-milestone detail lives
under ``.planning/milestones/<version>/STATE.md``.

---

## v0.1.0 — Initial Skeleton (Shipped: 2026-02)

Bootstrap of the harness-engineering meta-layer: Flask backend, Vue 3
frontend, SQLite schema, initial bot management, security audit endpoints,
webhook receivers.

See: ``.planning/milestones/v0.1.0/``

---

## v0.2.0 Miscellaneous (Shipped: 2026-03-05)

**Phases completed:** 9 phases, 37 plans, 33 tasks.

Mixed work — DAG-based workflows, multi-provider fallback chains, account
rotation, real-time SSE observability. Tracked at phase granularity.

See: ``.planning/milestones/v0.2.0/``

---

## v0.5.0 — Production-Level Onboarding Experience (Shipped: 2026-03-23)

**Phases completed:** 10 phases, 19 plans, 18 summaries.

Replaced the flat-index tour system with XState v5 + Floating UI + custom
Vue overlay components. A new user can complete workspace setup, register
at least one AI backend account, and run their first bot in under 3 minutes.

Last GRD-planned milestone with full phase/plan/research/verification trail.

See: ``.planning/milestones/v0.5.0/`` (full phase tree)
See: ``.planning/milestones/v0.5.0/ROADMAP.md`` (formal roadmap)

---

## v0.5.x Patch Wave (v0.5.1 — v0.5.15, Shipped: 2026-03 to 2026-04)

15 patch-level fixes following v0.5.0 — OB-24 anchor + coverage gate, two
silent-failure cleanup passes, modal-interaction E2E, anchor stability,
spotlight geometry refinements, and miscellaneous tour polish.

Per-version stubs at ``.planning/milestones/v0.5.{1..15}/STATE.md``.

---

## v0.6.x — Architecture Hardening (Shipped: 2026-04)

5 milestones around backend hardening — multi-tenancy migrations,
password reset flow, owned-entity user_id columns, plugin filesystem
discovery + ``GET /admin/plugins/discover``.

Per-version stubs at ``.planning/milestones/v0.6.{0..4}/STATE.md``.

---

## v0.7.0 — v0.7.98 — Rapid PR-Driven Wave (Shipped: 2026-04 to 2026-05-21)

**94 versions / 100+ merged PRs** shipped in this window. No formal GRD
roadmap; cadence is PR-driven with codex-review-until-green policy.

Major arcs visible in the wave:

- **Wizard / chat refactors** (v0.7.0 – v0.7.30): account wizard with
  proxy + plan + Save flow, sketch routing, design conversations.
- **Streaming / SSE consolidation** (v0.7.40 – v0.7.60): conversation
  services unified, GRD chat view, project-session panel.
- **Forge bindings + per-project allowed accounts** (v0.7.58 – v0.7.70):
  per-project account whitelist, yolo-mode bypass, Forge asset
  bindings.
- **Goal-loop / Ouroboros** (v0.7.74 – v0.7.92): GoalLoopRunner, GRD
  evolve session handler, SuperAgent → goal_loop bridge, system-prompt
  forwarding, SA-side activity surface.
- **Credential + multi-account observability** (v0.7.93 – v0.7.94):
  Token Usage Dashboard banner for missing OAuth credentials,
  keychain duplicate-svce shadowing fix (resolved Personal2's
  invisible token).
- **Inspector + bridge race + proxy-empty-content sweep**
  (v0.7.95 – v0.7.97): SA inspector "Recent Ouroboros runs" panel,
  ``SessionPersistError`` + global 409 handler + watchdog thread for
  SIGTERM-ignoring children, ``drop_empty_content_messages`` extracted
  across 6 callers.
- **Simplify pass** (v0.7.98): reuse / quality / efficiency review
  agents over the v0.7.95–.97 wave, collapsed duplicate filters,
  swapped local helpers for shared utils, dropped redundant route
  catches.

Per-version stubs at ``.planning/milestones/v0.7.N/STATE.md`` — backfilled
in PR #148 from commit-message + diff data.

---

## Convention

- **Version numbers** live in commit subjects (e.g. ``fix(v0.7.97): …``).
  ``backend/pyproject.toml`` / ``frontend/package.json`` are bumped on
  each milestone-summary PR rather than every commit; both are at
  v0.7.98 as of this PR.
- **Git tags** track the major arcs (last tag is v0.6.4); patch-level
  versions are commit-subject only.
- **Per-version STATE.md** files are the canonical planning trail when
  the wave was PR-driven rather than phase-planned.
