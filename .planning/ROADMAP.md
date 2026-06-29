# Roadmap: v0.10.0 — Competitive Hardening (omnigent lessons)

> **Active milestone.** Operationalizes the verified competitive analysis
> `docs/research/omnigent-vs-agented.md` (+ `.ko.md`). Delivery is
> PR-per-phase with codex-review-until-green before merge. The paused v0.8.0
> roadmap lives at `.planning/milestones/v0.8.0/ROADMAP.md`.

## Overview

omnigent-ai/omnigent (a Databricks meta-harness in Agented's exact category)
is genuinely ahead on five operator-facing dimensions: a stackable
policy/governance engine, real-time multi-user collaboration, OS-level
sandboxing + deployment breadth, a key-isolated server/runner split, and
frictionless distribution. Agented remains ahead on autonomy (unified loop
layer), memory (Tesserae/CodeGraph), and self-improvement (life-harness,
competitive-intel) — which omnigent has no equivalent for.

This milestone **closes the governance/collaboration/deployment gap** without
touching the moat. Order is risk-first: land the policy engine (Phase 23)
because it both consolidates today's scattered controls and is the
prerequisite that keeps the later sandboxing and shared-session features safe;
then OS-level sandboxing (Phase 24) to remove the real safety gap where
autonomous harnesses run with host file/shell/network access; then multi-user
collaboration (Phase 25), built on the existing SSE fan-out and governed by
Phase 23; finally deployment/extensibility ergonomics (Phase 26).

## Phases

### Phase 23 — Stackable policy / governance engine
**Goal:** one declarative `ALLOW/DENY/ASK` policy layer, stacked across
server → team → session (session-first, short-circuit on DENY), that subsumes
RBAC checks, the safety bots, the goal_loop human-gate, and exit-ladder
budgets. Builtins: cost caps (hard + soft), max tool calls, approve-before
shell/file-write, enforce-sandbox.
**Requirements:** REQ-27, REQ-28, REQ-29, REQ-30.
**Touches:** `app_litestar/middleware.py`, `ExecutionService`,
`goal_loop_runner.py`, frontend `budgets.ts` + a policy editor.
**Why first:** highest impact / moderate effort, and the safety substrate the
next two phases depend on.

### Phase 24 — OS-level harness sandboxing + egress control
**Goal:** wrap each `subprocess.Popen` harness in bwrap (Linux) / seatbelt
(macOS) behind an L7 egress allowlist; generalize `sandbox_eval.py` from
deterministic checks to the live harness; deny-by-default egress for
autonomous runs.
**Requirements:** REQ-31, REQ-32, REQ-33.
**Touches:** `ExecutionService` (subprocess launch), `sandbox_eval.py`, a new
egress-proxy component; interim cloud-sandbox runner (E2B/Modal).
**Why:** removes a real safety gap — auto-implement and life-harness autonomy
execute real harness sessions on the operator's host today.

### Phase 25 — Real-time multi-user collaboration
**Goal:** live-share an SSE session by scoped URL (read + chat), co-drive
(teammate message executes against the operator's session, **policy-governed**),
fork a session, optional OIDC SSO.
**Requirements:** REQ-34, REQ-35, REQ-36, REQ-37.
**Touches:** frontend SSE layer + Vue console (share/attach UI),
`ExecutionService` session model (multi-attach), auth middleware (scoped share
tokens), optional OIDC in the ApiKey middleware + ai-accounts.
**Why:** live-share is an incremental extension of the existing stream; pairs
with Phase 23 so shared sessions stay governed.

### Phase 26 — Deployment & extensibility ergonomics
**Goal:** first-class Postgres alongside SQLite (same schema/migrations,
`DATABASE_URL`), a container image + one-click target + single-install/
self-update, declarative-YAML agent/team authoring, optional server/runner
key-isolation split.
**Requirements:** REQ-38, REQ-39, REQ-40, REQ-41.
**Touches:** `app/database.py`, packaging/deploy, teams/super-agents config
layer, ai-accounts (runner-side key custody).
**Why:** lowest of the four on impact; lowers onboarding friction and unlocks
hosted/multi-user deployment.

## Out of scope (the moat)

Unified loop layer, Tesserae/CodeGraph grounding, life-harness,
competitive-intel, GRD, triggers, HarnessSync — keep investing; do **not**
chase omnigent here.

---
*Roadmap authored 2026-06-30 directly from the verified analysis (the plan was
already decomposed into these four phases; no re-survey needed).*
