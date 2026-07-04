# Requirements — v0.10.0 Competitive Hardening (omnigent lessons)

Derived from the verified competitive analysis
`docs/research/omnigent-vs-agented.md` (+ `.ko.md`). Goal: close the
governance / collaboration / deployment gap that omnigent-ai/omnigent
demonstrates, **without** diluting Agented's autonomy/memory/self-improvement
moat. Requirement numbering continues from v0.8.0 (last was REQ-26).

**Traceability:** every REQ maps to exactly one phase (23–26).

> v0.8.0 (Team Harness & Self-Improvement, phases 17–22) is **paused** and
> archived at `.planning/milestones/v0.8.0/`; its open REQs (01–13, 19–21)
> carry forward and can be resumed after this milestone.

## Policy / governance engine (POL) — Phase 23

- [ ] **REQ-27** — Policy engine primitive: `policies` store + a `PolicyVerdict` (`ALLOW`/`DENY`/`ASK`) evaluator that **stacks across server → team → session scopes with the session (stricter) scope evaluated first and able to short-circuit on DENY**. Anchored on the SESSION scope per the standing session-not-bot rule. (Phase: 23)
- [ ] **REQ-28** — Builtin policies consolidating today's scattered controls: `cost_budget` (hard `max_cost_usd` + soft `ask_thresholds_usd`), `max_tool_calls_per_session`, `ask_on_os_tools` (approval before shell / file-write), `enforce_sandbox`. Subsumes the goal_loop exit-ladder budgets and the `bot-security`/`bot-pr-review` safety checks under one declarative layer. (Phase: 23)
- [ ] **REQ-29** — Enforcement integration: policy checks at action boundaries in `ExecutionService` + a `goal_loop_runner.py` human-gate hook; an `ASK` verdict surfaces an approval card over SSE and blocks until resolved. (Phase: 23)
- [ ] **REQ-30** — Policy API + UI: `/admin/policies` CRUD (+ `app_litestar/middleware.py` policy middleware), a frontend policy editor, `budgets.ts` surfacing the cost-cap verdicts; en/ko/ja/zh key-identical catalogs. (Phase: 23)

## OS-level harness sandboxing + egress (SBX) — Phase 24

- [ ] **REQ-31** — Sandbox the live harness: wrap each `subprocess.Popen` harness in **bwrap (Linux) / seatbelt (macOS)**, generalizing `sandbox_eval.py` beyond deterministic eval checks to the running harness; graceful degrade (with a logged warning) where the OS sandbox is unavailable. (Phase: 24)
- [ ] **REQ-32** — L7 egress allowlist proxy: outbound-network allowlist for harness sessions, **deny-by-default for autonomous / auto-implement runs**. (Phase: 24)
- [ ] **REQ-33** — Cloud-sandbox runner (interim, lower-effort): an optional E2B/Modal runner for untrusted autonomous runs — the highest-risk consumers are competitive-intel **auto-implement** and the **life-harness autonomy** loop. (Phase: 24)

## Real-time multi-user collaboration (COL) — Phase 25

- [ ] **REQ-34** — Live-share: share a running SSE session by a **scoped URL token** (read + chat); a multi-attach session model in `ExecutionService`. Incremental extension of the existing SSE fan-out. (Phase: 25)
- [ ] **REQ-35** — Co-drive: a teammate's message **executes against the operator's running session**, governed by the Phase-23 policy engine so shared sessions stay safe. (Phase: 25)
- [ ] **REQ-36** — Session fork: fork a conversation/session onto a separate run. (Phase: 25)
- [ ] **REQ-37** — OIDC SSO (optional): Google / GitHub / Okta / Microsoft via the ApiKey/auth middleware + ai-accounts, alongside the existing API-key path. (Phase: 25)

## Deployment & extensibility ergonomics (DEP) — Phase 26

- [ ] **REQ-38** — First-class Postgres alongside SQLite: a Postgres adapter in `app/database.py` with the **same schema + migrations**, selected via `DATABASE_URL`; SQLite stays the zero-config default. (Phase: 26)
- [ ] **REQ-39** — Container image + one-click deploy target + a single-install / self-update distribution path (lower the bar from clone-and-run). (Phase: 26)
- [ ] **REQ-40** — Declarative YAML agent/team/orchestrator definitions ("the YAML file is the agent") so teams/super-agents are authorable without code. (Phase: 26)
- [ ] **REQ-41** — Optional server/runner key-isolation split: a hosted deployment carries no LLM keys (runner-side key custody via ai-accounts). (Phase: 26)

## Out of scope (the moat — keep investing, do NOT chase omnigent)

- Unified loop layer (LoopSpec + goal_loop_runner exit ladder) — Agented already leads.
- Tesserae / CodeGraph federated knowledge grounding — no omnigent equivalent.
- Self-improvement life-harness, competitive-intelligence pipeline, GRD planning, trigger-based delivery, HarnessSync — all differentiators with no omnigent equivalent.

> The goal is to **widen** the autonomy/memory/self-improvement gap while **closing** the governance/collaboration/deployment gap.
