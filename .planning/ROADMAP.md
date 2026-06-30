# Roadmap: v0.10.0 — Competitive Hardening (omnigent lessons)

> **Active milestone.** Operationalizes the verified competitive analysis
> `docs/research/omnigent-vs-agented.md` (+ `.ko.md`). Delivery is
> PR-per-phase with codex-review-until-green before merge. The paused v0.8.0
> roadmap lives at `.planning/milestones/v0.8.0/ROADMAP.md`.

## Overview

omnigent-ai/omnigent (a Databricks meta-harness in Agented's exact category)
is genuinely ahead on three operator-facing dimensions: a stackable
policy/governance engine, OS-level sandboxing + egress control, and real-time
multi-user collaboration, plus deployment/extensibility breadth (Postgres,
container/self-update distribution, YAML-authored agents, key-isolated
server/runner split). Agented remains ahead on autonomy (unified loop layer),
memory (Tesserae/CodeGraph), and self-improvement (life-harness,
competitive-intel) — which omnigent has no equivalent for.

This milestone **closes the governance/collaboration/deployment gap** without
touching the moat. Order is risk-first: land the policy engine (Phase 23)
because it both consolidates today's scattered controls and is the prerequisite
that keeps the later sandboxing and shared-session features safe; then OS-level
sandboxing + egress control (Phase 24, gated by the Phase-23 `enforce_sandbox`
policy hook); then multi-user collaboration (Phase 25, governed by the Phase-23
policy engine so shared sessions stay safe); finally deployment/extensibility
ergonomics (Phase 26, independent of the other three).

## Phases

**Phase Numbering:**
- Integer phases: Planned milestone work. This milestone continues the
  project's phase sequence — v0.8.0 ran phases **17–22**, so v0.10.0 runs
  phases **23–26**.
- Decimal phases (23.1, 23.2): Urgent insertions (marked with INSERTED).

**Phase Types:** survey | implement | evaluate | integrate

- [ ] **Phase 23: Stackable policy / governance engine** - one declarative `ALLOW`/`DENY`/`ASK` policy layer stacked across server → team → session (session-first, short-circuit on DENY), builtins (cost caps, max tool calls, ask-on-os-tools, enforce-sandbox), enforcement at action boundaries + goal_loop human-gate, CRUD API + editor UI `implement`
- [ ] **Phase 24: OS-level harness sandboxing + egress control** - bwrap/seatbelt wrap of each `subprocess.Popen` harness, L7 egress allowlist (deny-by-default for autonomous runs), interim cloud-sandbox (E2B/Modal) runner `implement`
- [ ] **Phase 25: Real-time multi-user collaboration** - live-share by scoped URL token, co-drive against the operator's running session (policy-governed), session fork, optional OIDC SSO `implement`
- [ ] **Phase 26: Deployment & extensibility ergonomics** - first-class Postgres alongside SQLite, container image + one-click/self-update distribution, declarative-YAML agent/team authoring, optional server/runner key-isolation split `implement`

## Phase Details

### Phase 23: Stackable policy / governance engine
**Goal**: One declarative `ALLOW`/`DENY`/`ASK` policy layer, stacked across server → team → session (session, the stricter scope, evaluated first and able to short-circuit on DENY), that subsumes today's scattered controls — the goal_loop exit-ladder budgets and the `bot-security`/`bot-pr-review` safety checks — under one layer, enforced at action boundaries with an `ASK` approval card over SSE.
**Type**: implement
**Depends on**: Nothing (first phase of milestone; the safety substrate the next two phases build on)
**Requirements**: REQ-27, REQ-28, REQ-29, REQ-30
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. A `policies` store + a `PolicyVerdict` (`ALLOW`/`DENY`/`ASK`) evaluator stacks across server → team → session scopes, evaluating the session (stricter) scope first and short-circuiting on DENY; anchored on the SESSION scope per the standing session-not-bot rule (stacking-order unit test: session DENY short-circuits a server ALLOW).
  2. Builtin policies exist and consolidate today's controls: `cost_budget` (hard `max_cost_usd` + soft `ask_thresholds_usd`), `max_tool_calls_per_session`, `ask_on_os_tools` (approve before shell / file-write), `enforce_sandbox`; the goal_loop exit-ladder budgets and `bot-security`/`bot-pr-review` checks route through this layer (builtin-evaluator tests per policy).
  3. Enforcement integrates at action boundaries in `ExecutionService` plus a `goal_loop_runner.py` human-gate hook; an `ASK` verdict surfaces an approval card over SSE and blocks the action until resolved (enforcement + ASK-blocks-until-resolved tests).
  4. `/admin/policies` CRUD + `app_litestar/middleware.py` policy middleware, a frontend policy editor, and `budgets.ts` surfacing cost-cap verdicts ship with en/ko/ja/zh key-identical catalogs (route + middleware + component tests).
  5. **Verification check:** a policy ALLOW/DENY/ASK end-to-end test drives a real session — a configured DENY blocks the action, an ASK pauses for an approval card and resumes on approve, and an ALLOW passes through.
  6. House gates pass: `just build`; backend pytest (watchdog procedure, targeted substitution disclosed if the known hang hits); frontend no-new-failures.
**Plans**: 5 plans

Plans:
- [ ] 23-01-PLAN.md — policies table (migration 176) + PolicyService.evaluate stacking/short-circuit (TDD, SC1)
- [ ] 23-02-PLAN.md — four builtin evaluators (cost_budget, max_tool_calls_per_session, ask_on_os_tools, enforce_sandbox) (TDD, SC2)
- [ ] 23-03-PLAN.md — enforcement: ExecutionService Popen boundary + goal_loop human-gate + ASK-over-SSE reuse + route bot/budget checks through (SC2/SC3)
- [ ] 23-04-PLAN.md — /admin/policies CRUD + /decision route + PolicyMiddleware (SC4)
- [ ] 23-05-PLAN.md — frontend editor + ASK card + budgets.ts verdicts + en/ko/ja/zh + e2e ALLOW/DENY/ASK + house gates (SC4/SC5/SC6)

### Phase 24: OS-level harness sandboxing + egress control
**Goal**: Each live harness `subprocess.Popen` runs inside an OS sandbox (bwrap on Linux / seatbelt on macOS) behind an L7 egress allowlist — generalizing `sandbox_eval.py` beyond deterministic eval checks to the running harness, deny-by-default egress for autonomous / auto-implement runs, and an optional cloud-sandbox (E2B/Modal) runner for the highest-risk autonomous consumers — gated by the Phase-23 `enforce_sandbox` policy.
**Type**: implement
**Depends on**: Phase 23 (the `enforce_sandbox` policy hook decides when sandboxing is mandatory)
**Requirements**: REQ-31, REQ-32, REQ-33
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Each `subprocess.Popen` harness is wrapped in bwrap (Linux) / seatbelt (macOS), generalizing `sandbox_eval.py` from deterministic eval checks to the running harness; where the OS sandbox is unavailable it degrades gracefully with a logged warning (sandbox-wrap test + degrade-path test).
  2. An L7 egress allowlist proxy governs outbound network for harness sessions, deny-by-default for autonomous / auto-implement runs (allowlist pass + denied-host block tests).
  3. An optional E2B/Modal cloud-sandbox runner exists for untrusted autonomous runs, wired as the execution target for competitive-intel auto-implement and the life-harness autonomy loop (runner-selection test; absent-credential graceful skip).
  4. The Phase-23 `enforce_sandbox` verdict drives whether a session is admitted unsandboxed (integration test: `enforce_sandbox` DENY refuses to launch an unsandboxed harness).
  5. **Verification check:** a sandbox-escape attempt (write outside the workspace + connect to a non-allowlisted host) from inside a wrapped harness is blocked and logged.
  6. House gates pass: `just build`; backend pytest (watchdog procedure); frontend no-new-failures.
**Plans**: TBD

Plans:
- [ ] 24-NN: TBD (set by /grd:plan-phase 24)

### Phase 25: Real-time multi-user collaboration
**Goal**: A running SSE session can be shared, co-driven, and forked across users — live-share by a scoped URL token (read + chat) over a multi-attach session model, co-drive where a teammate's message executes against the operator's running session **governed by the Phase-23 policy engine**, session fork onto a separate run, and optional OIDC SSO alongside the existing API-key path.
**Type**: implement
**Depends on**: Phase 23 (shared sessions must stay policy-governed; co-drive routes teammate actions through the policy engine)
**Requirements**: REQ-34, REQ-35, REQ-36, REQ-37
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. Live-share: a running SSE session is shareable by a scoped URL token (read + chat) backed by a multi-attach session model in `ExecutionService`, an incremental extension of the existing SSE fan-out (share-token mint + two-client attach test).
  2. Co-drive: a teammate's message executes against the operator's running session and every co-drive action is evaluated by the Phase-23 policy engine before execution (co-drive test asserting a DENY/ASK verdict blocks the teammate action).
  3. Session fork: a conversation/session forks onto a separate independent run (fork test: parent unaffected, child diverges).
  4. Optional OIDC SSO (Google / GitHub / Okta / Microsoft) via the ApiKey/auth middleware + ai-accounts, alongside the existing API-key path (OIDC-mocked auth test; API-key path unchanged regression).
  5. **Verification check:** a live-share two-client end-to-end test — a second client attaches by scoped token, sees streamed deltas read-only, and a co-drive message is policy-checked before it runs.
  6. House gates pass: `just build`; backend pytest (watchdog procedure); frontend no-new-failures (new share/attach UI ships en/ko/ja/zh).
**Plans**: TBD

Plans:
- [ ] 25-NN: TBD (set by /grd:plan-phase 25)

### Phase 26: Deployment & extensibility ergonomics
**Goal**: Lower the bar from clone-and-run — first-class Postgres alongside SQLite (same schema + migrations, selected via `DATABASE_URL`, SQLite stays the zero-config default), a container image + one-click deploy target + single-install/self-update distribution, declarative-YAML agent/team/orchestrator authoring ("the YAML file is the agent"), and an optional server/runner key-isolation split (hosted server carries no LLM keys).
**Type**: implement
**Depends on**: Nothing (independent of the governance/sandbox/collaboration track)
**Requirements**: REQ-38, REQ-39, REQ-40, REQ-41
**Verification Level**: proxy
**Success Criteria** (what must be TRUE):
  1. A Postgres adapter in `app/database.py` runs the same schema + migrations as SQLite, selected via `DATABASE_URL`; SQLite stays the zero-config default (adapter parity tests).
  2. A container image + one-click deploy target + a single-install / self-update distribution path exist, lowering the bar from clone-and-run (image build smoke + self-update path test).
  3. Declarative YAML agent/team/orchestrator definitions make teams/super-agents authorable without code; a YAML file round-trips to a created team/SA (YAML-load → materialize test).
  4. An optional server/runner key-isolation split lets a hosted deployment carry no LLM keys, with runner-side key custody via ai-accounts (no-keys-on-server config test).
  5. **Verification check:** the same backend pytest suite runs green against both SQLite and a Postgres `DATABASE_URL` (Postgres + SQLite same-suite green).
  6. House gates pass: `just build`; backend pytest (watchdog procedure); frontend no-new-failures.
**Plans**: TBD

Plans:
- [ ] 26-NN: TBD (set by /grd:plan-phase 26)

## Out of scope (the moat)

Unified loop layer (LoopSpec + goal_loop_runner exit ladder), Tesserae/CodeGraph
federated grounding, life-harness self-improvement, competitive-intelligence
pipeline, GRD planning, trigger-based delivery, HarnessSync — keep investing;
do **not** chase omnigent here. The goal is to **widen** the
autonomy/memory/self-improvement gap while **closing** the
governance/collaboration/deployment gap.

## Dependencies

```
23 ──► 24
23 ──► 25
26  (independent)
```

- 23 → 24 (sandboxing is gated by the `enforce_sandbox` policy hook)
- 23 → 25 (shared/co-driven sessions must stay policy-governed)
- 26 has no dependencies

**Execution order:** 23, 24, 25, 26. Dependency waves (Kahn): **Wave 1 = {23, 26}**,
**Wave 2 = {24, 25}** — but `parallelization` is disabled in config, so phases
execute sequentially by number.

## Progress

| Phase | Name | Requirements | Depends on | Verification | Status |
|-------|------|--------------|------------|--------------|--------|
| 23 | Stackable policy / governance engine | REQ-27..30 | — | proxy | Not started |
| 24 | OS-level harness sandboxing + egress control | REQ-31..33 | 23 | proxy | Not started |
| 25 | Real-time multi-user collaboration | REQ-34..37 | 23 | proxy | Not started |
| 26 | Deployment & extensibility ergonomics | REQ-38..41 | — | proxy | Not started |

**Coverage:** 15/15 requirements mapped (REQ-27 … REQ-41), each to exactly one
phase. No orphans, no duplicates.

**Integration note:** no separate integration phase — Phase 24 and Phase 25 are
each integration points against Phase 23's policy substrate (sandbox admission
and co-drive governance respectively), verified by their escape-attempt and
two-client end-to-end checks.
